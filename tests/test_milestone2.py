import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.services import governance, vehicle_records
from fastapi.testclient import TestClient


class GovernanceAndRecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.patch_dir=patch.object(database,"DB_DIR",self.temp.name); self.patch_path=patch.object(database,"DB_PATH",str(Path(self.temp.name)/"test.db"))
        self.patch_dir.start();self.patch_path.start();self.addCleanup(self.patch_dir.stop);self.addCleanup(self.patch_path.stop)
        database.init_db()
        self.token,self.user=governance.bootstrap("Northside Motors","admin@example.com","Admin User","correct horse battery staple")

    def test_login_roles_and_logout_are_server_enforced(self):
        self.assertEqual(governance.authenticate(self.token)["role"],"administrator")
        self.assertTrue(governance.permitted("reviewer","POST","/api/vehicle-sightings/s1/review"))
        self.assertFalse(governance.permitted("viewer","POST","/api/vehicle-sightings/s1/review"))
        self.assertFalse(governance.permitted("reviewer","POST","/api/vehicles"))
        created=governance.create_user(self.user,"reviewer@example.com","Review User","reviewer","another secure password")
        self.assertEqual(created["role"],"reviewer")
        reviewer_token,reviewer=governance.create_session("reviewer@example.com","another secure password")
        self.assertEqual(reviewer["dealership_id"],self.user["dealership_id"])
        governance.logout(reviewer_token);self.assertIsNone(governance.authenticate(reviewer_token))

    def test_vehicle_timeline_link_and_audit_are_persistent(self):
        vehicle=vehicle_records.save_vehicle(self.user,{"plate":"ABC 123","make":"Toyota","model":"RAV4","year":2024,"status":"active","reason":"Added from stock intake"})
        with database.get_db_connection() as conn:
            conn.execute("INSERT INTO sessions(session_id,status,dealership_id) VALUES (?,?,?)",("case","completed",self.user["dealership_id"]))
            conn.execute("INSERT INTO searches(search_id,session_id,status,query_json) VALUES (?,?,?,?)",("search","case","completed","{}"))
            conn.execute("""INSERT INTO vehicle_sightings(sighting_id,session_id,search_id,requested_plate,observed_plate,plate_match_mode,match_kind,ocr_confidence,similarity,first_seen_seconds,last_seen_seconds,best_timestamp_seconds,camera_role,event_type,dealership_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",("s1","case","search","ABC123","ABC12B","exact","review_candidate",.8,.8,1,2,1.5,"unknown","observed",self.user["dealership_id"]))
        vehicle_records.link_sighting(self.user,"s1",vehicle["vehicle_id"],"Verified against stock record")
        vehicle_records.add_alias(self.user,vehicle["vehicle_id"],{"plate":"OLD123","reason":"Previous registration"})
        timeline=vehicle_records.timeline(self.user,vehicle["vehicle_id"])
        self.assertIn("sighting",{item["type"] for item in timeline})
        self.assertIn("plate_alias",{item["type"] for item in timeline})
        actions={row["action"] for row in vehicle_records.list_audit(self.user)}
        self.assertTrue({"vehicle.created","sighting.linked","plate_alias.created"}.issubset(actions))
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT observed_plate FROM vehicle_sightings WHERE sighting_id='s1'").fetchone()[0],"ABC12B")

    def test_retention_and_camera_changes_are_audited(self):
        camera=vehicle_records.create_camera(self.user,{"name":"North gate","role":"lot_entry","timezone":"America/Toronto"})
        self.assertEqual(camera["role"],"lot_entry")
        policy=vehicle_records.update_retention(self.user,{"source_video_days":30,"derived_media_days":60,"sightings_days":365,"audit_days":2555})
        self.assertEqual(policy["source_video_days"],30)
        actions={row["action"] for row in vehicle_records.list_audit(self.user)}
        self.assertTrue({"camera.created","retention.updated"}.issubset(actions))

    def test_application_middleware_requires_login_and_enforces_role(self):
        # This test uses the real application middleware, not a router-only fixture.
        from app.main import app
        client=TestClient(app,base_url="http://localhost"); self.addCleanup(client.close)
        unauthenticated=client.get("/api/vehicles")
        self.assertEqual(unauthenticated.status_code,401)
        login=client.post("/api/auth/login",json={"email":"admin@example.com","password":"correct horse battery staple"})
        self.assertEqual(login.status_code,200,login.text)
        self.assertEqual(client.get("/api/vehicles").status_code,200)
        governance.create_user(self.user,"viewer@example.com","View User","viewer","viewer secure password")
        viewer=TestClient(app,base_url="http://localhost"); self.addCleanup(viewer.close)
        self.assertEqual(viewer.post("/api/auth/login",json={"email":"viewer@example.com","password":"viewer secure password"}).status_code,200)
        forbidden=viewer.post("/api/vehicles",json={"plate":"ABC123"})
        self.assertEqual(forbidden.status_code,403)


if __name__=="__main__": unittest.main()
