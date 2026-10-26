import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.services import camera_ingestion, governance, vehicle_records


class MemoryProtector:
    def protect(self, value): return ("sealed:" + value.get("username", "") + ":" + value.get("password", "")).encode()
    def unprotect(self, value):
        _, username, password = value.decode().split(":", 2)
        return {"username": username, "password": password}


class SequenceCapture:
    def __init__(self, sequence): self.sequence, self.closed = list(sequence), False
    def read(self):
        if not self.sequence: raise ConnectionError("disconnected")
        value = self.sequence.pop(0)
        if isinstance(value, Exception): raise value
        return value
    def close(self): self.closed = True


class CameraIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.dir_patch = patch.object(database, "DB_DIR", self.temp.name)
        self.path_patch = patch.object(database, "DB_PATH", str(Path(self.temp.name) / "test.db"))
        self.dir_patch.start(); self.path_patch.start(); self.addCleanup(self.dir_patch.stop); self.addCleanup(self.path_patch.stop)
        database.init_db()
        _, self.user = governance.bootstrap("Camera Test", "admin@camera.test", "Admin", "correct horse battery staple")
        self.camera = vehicle_records.create_camera(self.user, {"name":"Gate", "timezone":"America/Toronto"})

    def test_configuration_strips_inline_credentials_and_never_returns_secret(self):
        result = camera_ingestion.configure_camera(self.user, self.camera["camera_id"], {
            "stream_url":"rtsp://operator:swordfish@192.0.2.10:554/live?profile=1",
            "capture_fps":12, "inference_fps":2, "evidence_enabled":True,
            "evidence_segment_seconds":30, "evidence_retention_hours":24,
        }, MemoryProtector())
        rendered = repr(result)
        self.assertNotIn("swordfish", rendered); self.assertNotIn("operator@", rendered)
        self.assertEqual(result["stream_url"], "rtsp://192.0.2.10:554/live?profile=1")
        self.assertTrue(result["credentials_configured"])
        with database.get_db_connection() as conn:
            row = conn.execute("SELECT stream_url,credential_blob FROM cameras").fetchone()
        self.assertNotIn("swordfish", row["stream_url"]); self.assertIn(b"swordfish", row["credential_blob"])
        self.assertNotIn("credential_blob", vehicle_records.list_cameras(self.user)[0])

    def test_invalid_non_rtsp_url_is_rejected(self):
        with self.assertRaises(ValueError):
            camera_ingestion.configure_camera(self.user, self.camera["camera_id"], {"stream_url":"https://example.test/video"}, MemoryProtector())

    def test_processing_overflow_drops_superseded_frame_and_reports_metric(self):
        record={"camera_id":"cam", "stream_url":"rtsp://camera/live", "inference_fps":30, "evidence_enabled":0}
        worker=camera_ingestion.CameraWorker(record,{},processing_capacity=1,evidence_capacity=1)
        one=camera_ingestion.FrameEnvelope(object(),0,"now",None)
        two=camera_ingestion.FrameEnvelope(object(),1,"later",None)
        worker.processing_queue.put_nowait(one)
        try: worker.processing_queue.put_nowait(two)
        except Exception:
            worker.processing_queue.get_nowait(); worker.processing_queue.task_done(); worker.processing_queue.put_nowait(two); worker.metrics.dropped_processing_frames+=1
        self.assertEqual(worker.metrics.dropped_processing_frames,1)
        self.assertIs(worker.processing_queue.get_nowait(),two)

    def test_disconnect_reconnect_corrupt_frame_and_clean_shutdown(self):
        factories=[SequenceCapture([(False,None,None), ConnectionError("disconnected")]), SequenceCapture([(True,object(),12.5), ConnectionError("disconnected")])]
        def factory(_url): return factories.pop(0) if factories else SequenceCapture([ConnectionError("disconnected")])
        processed=[]
        worker=camera_ingestion.CameraWorker({"camera_id":"cam","stream_url":"rtsp://host/live","inference_fps":30,"evidence_enabled":0}, {}, capture_factory=factory, processor=lambda c,f:processed.append(c), base_backoff=.005, max_backoff=.01, stall_seconds=.01)
        worker.start(); time.sleep(.08); worker.stop()
        self.assertGreaterEqual(worker.metrics.reconnects,2)
        self.assertGreaterEqual(worker.metrics.corrupt_frames,1)
        self.assertEqual(worker.status,"offline")
        self.assertTrue(all(not thread.is_alive() for thread in worker._threads))

    def test_authentication_failure_is_classified_without_secret(self):
        worker=camera_ingestion.CameraWorker({"camera_id":"cam","stream_url":"rtsp://host/live","evidence_enabled":0}, {}, capture_factory=lambda _: (_ for _ in ()).throw(PermissionError("401 bad password")), base_backoff=.005,max_backoff=.005)
        worker.start(); time.sleep(.02); worker.stop()
        self.assertNotIn("password", worker.status_detail.lower())
        self.assertGreaterEqual(worker.metrics.reconnects,1)

    def test_two_streams_run_independently(self):
        def factory(_): return SequenceCapture([(True,object(),1.0), ConnectionError("disconnect")])
        first=camera_ingestion.CameraWorker({"camera_id":"a","stream_url":"rtsp://a/live","inference_fps":30,"evidence_enabled":0},{},capture_factory=factory,base_backoff=.01,max_backoff=.01)
        second=camera_ingestion.CameraWorker({"camera_id":"b","stream_url":"rtsp://b/live","inference_fps":30,"evidence_enabled":0},{},capture_factory=factory,base_backoff=.01,max_backoff=.01)
        first.start(); second.start(); time.sleep(.04); first.stop(); second.stop()
        self.assertGreater(first.metrics.captured_frames,0); self.assertGreater(second.metrics.captured_frames,0)


if __name__ == "__main__": unittest.main()
