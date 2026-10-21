import hashlib
import tempfile
import unittest
import zipfile
import cv2
import numpy as np
from fastapi.testclient import TestClient
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

from app import database
from app.services import condition_incidents,governance,vehicle_records

class ConditionIncidentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=self.temp.name
        self.p1=patch.object(database,"DB_DIR",root);self.p2=patch.object(database,"DB_PATH",str(Path(root)/"test.db"));self.p1.start();self.p2.start();self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop);database.init_db()
        _,self.user=governance.bootstrap("Northside Motors","admin@example.com","Admin User","correct horse battery staple")
        self.vehicle=vehicle_records.save_vehicle(self.user,{"plate":"ABC123","status":"active"})

    def _inspection(self,kind="arrival"):
        row=condition_incidents.create_inspection(self.user,{"vehicle_id":self.vehicle["vehicle_id"],"inspection_type":kind,"device_label":"Service tablet","captured_at":"2020-01-01T12:00:00+00:00"})
        folder=Path(self.temp.name)/"evidence"/"inspections"/row["inspection_id"];folder.mkdir(parents=True);path=folder/"front.jpg";path.write_bytes(b"immutable-original-image")
        media=condition_incidents.register_media(self.user,row["inspection_id"],{"viewpoint":"front","source_filename":"front.jpg","storage_path":str(path),"mime_type":"image/jpeg","sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"width":100,"height":80})
        return row,media,path

    def test_guided_inspection_annotation_and_original_hash(self):
        inspection,media,path=self._inspection()
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        annotation=condition_incidents.annotate(self.user,media["media_id"],{"x":.1,"y":.2,"width":.3,"height":.2,"damage_type":"scratch","severity":"minor","assessment":"possible_change","notes":"Lighting may affect appearance."})
        completed=condition_incidents.complete_inspection(self.user,inspection["inspection_id"])
        self.assertEqual(completed["status"],"completed");self.assertEqual(annotation["review_status"],"requires_review");self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        self.assertIn("front",completed["required_viewpoints"]);self.assertIn("windscreen",completed["required_viewpoints"])

    def test_incident_hold_approval_reopen_and_hashed_export(self):
        inspection,media,path=self._inspection("departure");condition_incidents.complete_inspection(self.user,inspection["inspection_id"])
        incident=condition_incidents.create_incident(self.user,{"vehicle_id":self.vehicle["vehicle_id"],"title":"Condition review","summary":"Possible change requires review.","priority":"normal"})
        condition_incidents.add_evidence(self.user,incident["incident_id"],{"evidence_type":"inspection","entity_id":inspection["inspection_id"],"note":"Departure inspection"})
        condition_incidents.add_note(self.user,incident["incident_id"],"Compare against the arrival viewpoint before reaching a conclusion.")
        condition_incidents.place_hold(self.user,incident["incident_id"],"Preserve while manager review is open.")
        self.assertEqual(condition_incidents.decision(self.user,incident["incident_id"],"approve","Evidence package reviewed.")["status"],"approved")
        self.assertEqual(condition_incidents.decision(self.user,incident["incident_id"],"reopen","Additional context is required.")["status"],"requires_review")
        exported=condition_incidents.export_incident(self.user,incident["incident_id"],self.temp.name);archive=Path(exported["path"])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),exported["archive_sha256"])
        with zipfile.ZipFile(archive) as bundle:self.assertIn("manifest.json",bundle.namelist());self.assertTrue(any(name.startswith("files/") for name in bundle.namelist()))
        result=condition_incidents.apply_retention(self.user,self.temp.name,datetime(2030,1,1,tzinfo=timezone.utc));self.assertEqual(result["deleted_inspections"],0);self.assertTrue(path.exists())

    def test_retention_removes_expired_unheld_inspection(self):
        inspection,_,path=self._inspection();condition_incidents.complete_inspection(self.user,inspection["inspection_id"])
        result=condition_incidents.apply_retention(self.user,self.temp.name,datetime(2030,1,1,tzinfo=timezone.utc));self.assertEqual(result["deleted_inspections"],1);self.assertFalse(path.exists())
        with database.get_db_connection() as conn:self.assertIsNone(conn.execute("SELECT 1 FROM inspections WHERE inspection_id=?",(inspection["inspection_id"],)).fetchone())

    def test_authenticated_api_upload_annotation_and_incident_workflow(self):
        from app.main import app
        from app.api import endpoints
        with patch.object(endpoints,"DATA_DIR",self.temp.name):
            client=TestClient(app,base_url="http://localhost");self.addCleanup(client.close)
            self.assertEqual(client.post("/api/auth/login",json={"email":"admin@example.com","password":"correct horse battery staple"}).status_code,200)
            created=client.post("/api/inspections",json={"vehicle_id":self.vehicle["vehicle_id"],"inspection_type":"arrival","device_label":"tablet"})
            self.assertEqual(created.status_code,200,created.text);inspection_id=created.json()["inspection_id"]
            ok,image=cv2.imencode(".png",np.zeros((20,30,3),np.uint8));self.assertTrue(ok)
            media=client.post(f"/api/inspections/{inspection_id}/media?viewpoint=front",files={"file":("front.png",image.tobytes(),"image/png")})
            self.assertEqual(media.status_code,200,media.text);self.assertEqual(len(media.json()["sha256"]),64)
            annotation=client.post(f"/api/inspection-media/{media.json()['media_id']}/annotations",json={"x":.1,"y":.1,"width":.2,"height":.2,"damage_type":"scratch","severity":"minor","assessment":"possible_change","notes":"Requires review"})
            self.assertEqual(annotation.status_code,200,annotation.text)
            self.assertEqual(client.post(f"/api/inspections/{inspection_id}/complete").json()["status"],"completed")
            incident=client.post("/api/incidents",json={"vehicle_id":self.vehicle["vehicle_id"],"title":"Condition review"}).json();incident_id=incident["incident_id"]
            self.assertEqual(client.post(f"/api/incidents/{incident_id}/evidence",json={"evidence_type":"inspection","entity_id":inspection_id}).status_code,200)
            attachment=client.post(f"/api/incidents/{incident_id}/attachments",files={"file":("review.txt",b"review attachment","text/plain")});self.assertEqual(attachment.status_code,200,attachment.text);self.assertEqual(len(attachment.json()["sha256"]),64)
            self.assertEqual(len(client.get(f"/api/incidents/{incident_id}").json()["attachments"]),1)
            self.assertEqual(client.post(f"/api/incidents/{incident_id}/holds",json={"reason":"Preserve evidence"}).status_code,200)
            exported=client.post(f"/api/incidents/{incident_id}/exports");self.assertEqual(exported.status_code,200,exported.text);self.assertEqual(len(exported.headers["x-archive-sha256"]),64)

if __name__=="__main__":unittest.main()
