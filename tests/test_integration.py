"""Integration checks use isolated SQLite and synthetic detections, never saved flights."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import database
from app.api import endpoints
from app.services import agentic_loop, analysis_worker
from app.models.schemas import DetectionItem


class FakeDetector:
    def __init__(self, crop_dir):
        pass

    def detect_in_frame(self, frame, session_id, frame_idx, timestamp_seconds, **kwargs):
        return [DetectionItem(detection_id=f'{session_id}_{frame_idx}', frame_idx=frame_idx,
            timestamp_seconds=timestamp_seconds, bbox=[0,0,50,100], confidence=.9,
            detector_name='YOLO instance segmentation', model_version='synthetic-test', quality_score=.8,
            color_features={'upper': {'green': .9}}, attribute_visibility={'upper':'partial'})]

    def refine_evidence(self, detection):
        return detection


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = self.temp.name
        for module, name, value in [(database,'DB_DIR',root), (database,'DB_PATH',str(Path(root)/'test.db')),
                                    (agentic_loop,'DATA_DIR',root), (endpoints,'DATA_DIR',root)]:
            patcher=patch.object(module,name,value); patcher.start(); self.addCleanup(patcher.stop)
        database.init_db()
        app=FastAPI(); app.include_router(endpoints.router)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)
        self.video=Path(root)/'input.mp4'
        writer=cv2.VideoWriter(str(self.video),cv2.VideoWriter_fourcc(*'mp4v'),10,(100,200))
        for _ in range(30): writer.write(np.zeros((200,100,3),np.uint8))
        writer.release()
        self.session=self.client.post('/api/sessions',json={'upper_clothing_color':'green'}).json()['session_id']
        self.base=f'/api/sessions/{self.session}'
        response=self.client.post(self.base+'/video',files={'file':('input.mp4',self.video.read_bytes(),'video/mp4')})
        self.assertEqual(response.status_code,200,response.text)

    def run_worker(self, detector=FakeDetector):
        self.assertEqual(self.client.post(self.base+'/analyze').status_code,200)
        with patch.object(agentic_loop,'PersonDetector',detector):
            self.assertTrue(analysis_worker.AnalysisWorker().run_once())

    def test_processing_feedback_report_and_provenance(self):
        self.run_worker()
        status=self.client.get(self.base+'/status').json()
        self.assertEqual(status['status'],'completed',status)
        tracks=self.client.get(self.base+'/tracks').json()
        self.assertEqual(len(tracks),1)
        self.assertEqual(tracks[0]['classification'],'strong_match')
        self.assertEqual(tracks[0]['model_version'],'synthetic-test')
        self.assertGreaterEqual(len(tracks[0]['attributes']['upper_clothing']['evidence_timestamps']),2)
        response=self.client.post(self.base+'/tracks/1/feedback',json={'status':'rejected','notes':'Test decision'})
        self.assertEqual(response.status_code,200,response.text)
        report=self.client.get(self.base+'/report')
        self.assertEqual(report.status_code,200)
        self.assertIn('Rejected by operator',report.text)
        self.assertIn('Test decision',report.text)
        self.assertEqual(self.client.post(self.base+'/analyze').status_code,409)

    def test_missing_altitude_upload_and_lookup(self):
        content='1\n00:00:00,000 --> 00:00:01,000\n[latitude: 45] [longitude: -75]\n'
        response=self.client.post(self.base+'/telemetry',files={'file':('test.srt',content,'text/plain')})
        self.assertEqual(response.status_code,200,response.text)
        points=self.client.get(self.base+'/telemetry').json()
        self.assertIsNone(points[0]['altitude_m'])

    def test_queue_pause_resume_cancel(self):
        self.assertEqual(self.client.post(self.base+'/analyze').status_code,200)
        self.assertEqual(self.client.post(self.base+'/analyze').status_code,409)
        self.assertEqual(self.client.post(self.base+'/pause').json()['status'],'paused')
        self.assertEqual(self.client.post(self.base+'/resume').json()['status'],'queued')
        self.assertEqual(self.client.post(self.base+'/cancel').json()['status'],'cancelled')
        self.assertFalse(analysis_worker.AnalysisWorker().run_once())

    def test_detector_failure_stops_job(self):
        def fail(**kwargs): raise RuntimeError('model missing test')
        self.run_worker(fail)
        status=self.client.get(self.base+'/status').json()
        self.assertEqual(status['status'],'error')
        self.assertIn('model missing',status['error_message'])
        self.assertEqual(self.client.get(self.base+'/tracks').json(),[])

    def test_zero_people_completes_without_candidates(self):
        class EmptyDetector(FakeDetector):
            def detect_in_frame(self, **kwargs): return []
        self.run_worker(EmptyDetector)
        self.assertEqual(self.client.get(self.base+'/status').json()['status'],'completed')
        self.assertEqual(self.client.get(self.base+'/tracks').json(),[])

    def test_old_telemetry_migration_retains_coordinates(self):
        with database.get_db_connection() as conn:
            conn.execute('DROP TABLE telemetry')
            conn.execute('CREATE TABLE telemetry(session_id TEXT, timestamp_seconds REAL, latitude REAL, longitude REAL, altitude_m REAL NOT NULL, relative_altitude_m REAL)')
            conn.execute('INSERT INTO telemetry VALUES (?,0,45,-75,100,NULL)',(self.session,))
        database.init_db()
        database.init_db()
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute('SELECT altitude_m FROM telemetry').fetchone()[0],100)
            conn.execute('INSERT INTO telemetry VALUES (?,1,45,-75,NULL,NULL)',(self.session,))

if __name__ == '__main__': unittest.main()
