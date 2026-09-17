"""A durable local queue with one cooperative worker, independent of HTTP requests."""
import json
import os
import threading
import uuid
from app.database import DB_DIR, get_db_connection


class AnalysisStopped(RuntimeError):
    pass


class AnalysisWorker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        self._lock_file = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        # Hold an OS lock for the worker lifetime, including during inference.
        # This prevents another uvicorn process from recovering/rerunning live jobs.
        os.makedirs(DB_DIR, exist_ok=True)
        handle = open(os.path.join(DB_DIR, "analysis-worker.lock"), "a+b")
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            # Another process owns the worker; queued requests are durable in SQLite.
            return
        self._lock_file = handle
        self.stop_event.clear()
        self.recover_interrupted()
        self.thread = threading.Thread(target=self._run, name="analysis-worker", daemon=True)
        self.thread.start()

    @staticmethod
    def recover_interrupted():
        with get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            reason = "Processing was interrupted by a server restart. Existing evidence was retained; start a new session to reprocess."
            conn.execute("UPDATE analysis_runs SET status='error', error_message=?, finished_at=CURRENT_TIMESTAMP WHERE status IN ('analyzing','paused') AND started_at IS NOT NULL", (reason,))
            conn.execute("UPDATE sessions SET status='error', current_stage='interrupted', error_message=? WHERE status IN ('analyzing','paused') AND (run_id IS NULL OR run_id IN (SELECT run_id FROM analysis_runs WHERE status='error'))", (reason,))
            conn.execute("UPDATE sessions SET status=CASE WHEN video_metadata IS NULL THEN 'created' ELSE 'uploaded' END WHERE status='uploading'")
            # A paused job that never started is safe to retain in the queue.

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        # If inference has not returned, keep the OS lock until the process exits.
        if not self.thread or not self.thread.is_alive():
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None

    def checkpoint(self, session_id, run_id):
        while True:
            if self.stop_event.is_set():
                raise AnalysisStopped("Server stopped processing. Existing evidence was retained.")
            with get_db_connection() as conn:
                row = conn.execute("SELECT status,run_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row or row["run_id"] != run_id or row["status"] not in ("analyzing", "paused"):
                raise AnalysisStopped("Analysis cancelled by the operator.")
            if row["status"] == "analyzing":
                return
            self.stop_event.wait(0.2)

    def run_once(self):
        from app.models.schemas import TargetConfiguration
        from app.services.agentic_loop import AgenticLoopManager
        with get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            job = conn.execute("SELECT r.run_id, r.session_id, s.target_config FROM analysis_runs r JOIN sessions s ON s.session_id=r.session_id AND s.run_id=r.run_id WHERE r.status='queued' AND s.status='queued' ORDER BY r.created_at,r.rowid LIMIT 1").fetchone()
            if not job:
                return False
            conn.execute("UPDATE analysis_runs SET status='analyzing', started_at=CURRENT_TIMESTAMP WHERE run_id=?", (job["run_id"],))
            conn.execute("UPDATE sessions SET status='analyzing',current_stage='starting',error_message=NULL WHERE session_id=?", (job["session_id"],))
        try:
            AgenticLoopManager.execute_analysis(
                job["session_id"], TargetConfiguration(**json.loads(job["target_config"])),
                run_id=job["run_id"], checkpoint=lambda: self.checkpoint(job["session_id"], job["run_id"])
            )
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            with get_db_connection() as conn:
                row = conn.execute("SELECT status FROM sessions WHERE session_id=?", (job["session_id"],)).fetchone()
                terminal = "cancelled" if row and row["status"] == "cancelled" else "error"
                conn.execute("UPDATE sessions SET status=?,current_stage=?,error_message=? WHERE session_id=? AND run_id=?", (terminal, terminal, message, job["session_id"], job["run_id"]))
                conn.execute("UPDATE analysis_runs SET status=?,error_message=?,finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (terminal, message, job["run_id"]))
            AgenticLoopManager.log_agent_event(job["session_id"], "STOPPED", message, "warning")
        return True

    def _run(self):
        try:
            while not self.stop_event.is_set():
                try:
                    worked = self.run_once()
                except Exception:
                    import logging
                    logging.exception("Analysis queue failure")
                    worked = False
                if not worked:
                    self.wake_event.wait(0.5)
                    self.wake_event.clear()
        finally:
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None


worker = AnalysisWorker()


def queue_analysis(session_id, target_config=None):
    """Atomically reserve a run; returns id, or raises for a missing/unsafe session."""
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            raise LookupError("Session not found.")
        if row["status"] in ("queued", "analyzing", "paused", "uploading"):
            raise RuntimeError("This session already has an active analysis.")
        if row["status"] == "completed" or conn.execute("SELECT 1 FROM tracks WHERE session_id=? LIMIT 1", (session_id,)).fetchone():
            raise RuntimeError("This session already has results. Create a new session to reanalyze and preserve review history.")
        if not row["video_metadata"] or not os.path.isfile(json.loads(row["video_metadata"])["filepath"]):
            raise ValueError("Upload a valid video before starting analysis.")
        run_id = uuid.uuid4().hex
        config_json = json.dumps(target_config.model_dump(mode="json")) if target_config else row["target_config"]
        conn.execute("INSERT INTO analysis_runs(run_id,session_id,status) VALUES (?,?,'queued')", (run_id,session_id))
        conn.execute("UPDATE sessions SET run_id=?,status='queued',current_stage='queued',progress_percent=0,error_message=NULL,target_config=? WHERE session_id=?", (run_id, config_json, session_id))
    worker.wake_event.set()
    return run_id


def control_analysis(session_id, action):
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT s.*,r.started_at FROM sessions s LEFT JOIN analysis_runs r ON r.run_id=s.run_id WHERE s.session_id=?", (session_id,)).fetchone()
        if not row:
            raise LookupError("Session not found.")
        valid = {"pause": ("queued", "analyzing"), "resume": ("paused",), "cancel": ("queued", "analyzing", "paused")}
        if row["status"] not in valid[action]:
            raise RuntimeError(f"Cannot {action} a session with status {row['status']}.")
        status = "paused" if action == "pause" else ("cancelled" if action == "cancel" else ("analyzing" if row["started_at"] else "queued"))
        conn.execute("UPDATE sessions SET status=?,current_stage=? WHERE session_id=?", (status, status, session_id))
        conn.execute("UPDATE analysis_runs SET status=? WHERE run_id=?", (status, row["run_id"]))
        if action == "cancel":
            conn.execute("UPDATE analysis_runs SET finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (row["run_id"],))
    worker.wake_event.set()
    return status
