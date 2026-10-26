"""Runtime health and capability facts for production-readiness reviews.

This module deliberately separates operational health from measured model
accuracy.  A healthy process is not evidence that the recognition targets
have been met.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from app import database
from app.services.analysis_worker import worker


def _database_health() -> dict:
    try:
        with database.get_db_connection() as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            queued = conn.execute(
                "SELECT COUNT(*) FROM analysis_runs WHERE status IN ('queued','analyzing','paused')"
            ).fetchone()[0]
            proxy = conn.execute(
                "SELECT COUNT(*) FROM proxy_jobs WHERE status IN ('queued','processing')"
            ).fetchone()[0]
        return {
            "ok": integrity == "ok",
            "integrity": integrity,
            "active_analysis_jobs": queued,
            "active_proxy_jobs": proxy,
        }
    except Exception as error:
        return {"ok": False, "integrity": "unavailable", "error": str(error)}


def _storage_health() -> dict:
    root = Path(database.DB_DIR).resolve()
    try:
        usage = shutil.disk_usage(root)
        writable = os.access(root, os.W_OK)
        free_percent = usage.free / usage.total * 100 if usage.total else 0.0
        return {
            "ok": writable and usage.free >= 1024**3,
            "path": str(root),
            "writable": writable,
            "free_bytes": usage.free,
            "free_percent": round(free_percent, 2),
            "minimum_free_bytes": 1024**3,
        }
    except Exception as error:
        return {"ok": False, "path": str(root), "error": str(error)}


def runtime_readiness() -> dict:
    """Return observable runtime state without claiming production accuracy."""
    database_health = _database_health()
    storage_health = _storage_health()
    worker_alive = bool(worker.thread and worker.thread.is_alive())
    checks = {
        "database": database_health,
        "storage": storage_health,
        "analysis_worker": {
            "ok": worker_alive,
            "running_in_this_process": worker_alive,
            "note": (
                "This process owns the durable analysis worker."
                if worker_alive
                else "The worker may be owned by another server process; queued jobs remain in SQLite."
            ),
        },
    }
    capabilities = {
        "recorded_video_upload": True,
        "durable_analysis_queue": True,
        "human_review_and_audit": True,
        "immutable_crossing_events": True,
        "desktop_application_shell": True,
        "live_camera_ingestion": True,
        "automatic_track_to_crossing_event": False,
        "dealership_video_accuracy_certified": False,
    }
    blockers = [
        "The recording worker does not yet submit tracked observations to configured camera boundaries.",
        "Live-camera ingestion is implemented with simulated coverage; physical ONVIF/RTSP cameras and dealership network conditions remain unverified.",
        "The declared release gates have not been measured on held-out dealership video.",
        "Backup/restore, deployment TLS, and rate limiting are not certified; camera credentials use Windows DPAPI but still require installed-build verification.",
        "The downloadable Windows installer still needs a redistributable packaged model/runtime set and code signing.",
    ]
    healthy = database_health.get("ok") is True and storage_health.get("ok") is True
    return {
        "runtime_status": "healthy" if healthy else "degraded",
        "production_certified": False,
        "checks": checks,
        "capabilities": capabilities,
        "release_blockers": blockers,
        "accuracy_note": "Runtime health is not model accuracy. See the frozen evaluation reports for measured results.",
    }
