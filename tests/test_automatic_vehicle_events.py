import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import database
from app.models.schemas import TargetConfiguration, VideoMetadata
from app.services import automatic_vehicle_events, governance, vehicle_events, vehicle_records


class AutomaticVehicleEventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p1=patch.object(database,"DB_DIR",self.temp.name);self.p2=patch.object(database,"DB_PATH",str(Path(self.temp.name)/"db.sqlite"))
        self.p1.start();self.p2.start();self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop);database.init_db()
        _,self.user=governance.bootstrap("Northside","admin@example.com","Admin","correct horse battery staple")
        self.camera=vehicle_records.create_camera(self.user,{"name":"Main gate","role":"lot_entry","timezone":"America/Toronto"})
        self.boundary=vehicle_events.create_boundary(self.user,self.camera["camera_id"],{"name":"Entry","boundary_type":"entrance","x1":.1,"y1":.5,"x2":.9,"y2":.5,"travel_direction":"negative_to_positive","min_vehicle_width":.05,"min_vehicle_height":.05,"min_visible_fraction":.5})
        self.vehicle=vehicle_records.save_vehicle(self.user,{"plate":"ABC123","status":"off_lot"})
        self.session="case-auto"
        with database.get_db_connection() as conn:
            conn.execute("INSERT INTO sessions(session_id,status,target_config,dealership_id) VALUES (?,?,?,?)",(self.session,"completed","{}",self.user["dealership_id"]))
        self.target=TargetConfiguration(free_text_description="all vehicles",inventory_scan=True,camera_name="Main gate",recorded_start_at="2026-10-26T08:00:00-04:00")
        self.video=VideoMetadata(filename="gate.mp4",filepath="C:/evidence/gate.mp4",duration_seconds=30,frame_count=900,fps=30,width=1000,height=500,codec="h264",file_size_mb=1,creation_timestamp="")

    def items(self, suffix=""):
        provenance=SimpleNamespace(model_dump=lambda **_: {"name":"detector","version":"1"})
        def item(frame,y,t):
            vehicle=SimpleNamespace(bbox=[350,y,650,y+100],crop_path=f"crop-{frame}.jpg",provenance=provenance)
            return {"frame_idx":frame,"timestamp_seconds":t,"frame_path":f"frame-{frame}.jpg","vehicle":vehicle,"plate_observations":[]}
        return [item(1,100,1),item(2,300,2)]

    def submit(self, track="vehicle-sighting-1", items=None):
        return automatic_vehicle_events.submit_recording_track(session_id=self.session,target=self.target,video=self.video,track_id=track,track_items=items or self.items(),plate_observations=[],consensus={"selected_plate":"ABC123","state":"exact_consensus"},best_vehicle_crop="vehicle.jpg",best_plate_crop="plate.png",model_manifest={"vehicle_detector":{"version":"1"}})

    def test_track_crossing_creates_event_and_safe_inventory_transition(self):
        result=self.submit()
        self.assertEqual(result["submitted"],1);self.assertTrue(result["results"][0]["created"])
        event=result["results"][0]["event"]
        self.assertEqual(event["review_state"],"confirmed")
        self.assertEqual(vehicle_records.get_vehicle(self.user,self.vehicle["vehicle_id"])["status"],"on_lot")
        detail=vehicle_events.get_event(self.user,event["event_id"])
        self.assertEqual(len(detail["observations"]),2)
        self.assertEqual(detail["model_manifest"]["vehicle_detector"]["version"],"1")

    def test_approach_without_crossing_creates_no_event(self):
        items=self.items();items[1]["vehicle"].bbox=[350,150,650,250]
        result=self.submit(items=items)
        self.assertFalse(result["results"][0]["created"])
        self.assertEqual(result["results"][0]["reason"],"no_eligible_directed_crossing")

    def test_fragmented_track_duplicate_is_suppressed(self):
        first=self.submit("fragment-a");self.assertTrue(first["results"][0]["created"])
        # Restore the pre-event state only to isolate duplicate-event behavior.
        with database.get_db_connection() as conn: conn.execute("UPDATE vehicles SET status='off_lot' WHERE vehicle_id=?",(self.vehicle["vehicle_id"],))
        second=self.submit("fragment-b")
        self.assertFalse(second["results"][0]["created"]);self.assertEqual(second["results"][0]["reason"],"duplicate_fragment")
        with database.get_db_connection() as conn:self.assertEqual(conn.execute("SELECT count(*) FROM vehicle_events").fetchone()[0],1)

    def test_missing_absolute_time_skips_without_guessing(self):
        self.target=self.target.model_copy(update={"recorded_start_at":None})
        result=self.submit();self.assertEqual(result["skip_reason"],"recording_start_time_missing")


if __name__=="__main__":unittest.main()
