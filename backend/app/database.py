import sqlite3
import json
import os
from typing import Dict, Any, List, Optional

DB_DIR = os.path.abspath(os.environ.get("AIEYE_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")))
DB_PATH = os.path.join(DB_DIR, "aerofind.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL,
        progress_percent REAL DEFAULT 0.0,
        current_stage TEXT DEFAULT 'idle',
        target_config JSON,
        search_plan JSON,
        video_metadata JSON,
        has_telemetry INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detections (
        detection_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        frame_idx INTEGER NOT NULL,
        timestamp_seconds REAL NOT NULL,
        bbox JSON NOT NULL,
        confidence REAL NOT NULL,
        crop_path TEXT,
        quality_score REAL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracks (
        session_id TEXT NOT NULL,
        track_id INTEGER NOT NULL,
        first_seen_seconds REAL,
        last_seen_seconds REAL,
        best_timestamp_seconds REAL,
        classification TEXT,
        person_detection_confidence REAL,
        appearance_similarity REAL,
        evidence_quality REAL,
        final_ranking_score REAL,
        observations_analyzed INTEGER,
        attributes JSON,
        matching_evidence JSON,
        conflicting_evidence JSON,
        unknown_attributes JSON,
        requires_human_review INTEGER,
        explanation TEXT,
        best_frame_path TEXT,
        cropped_samples JSON,
        human_feedback TEXT,
        human_notes TEXT,
        gps_location JSON,
        PRIMARY KEY (session_id, track_id),
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        step TEXT NOT NULL,
        message TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        session_id TEXT NOT NULL,
        timestamp_seconds REAL NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        altitude_m REAL,
        relative_altitude_m REAL,
        PRIMARY KEY (session_id, timestamp_seconds),
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    # Older databases required altitude even though valid SRT cues may omit it.
    if any(row[1] == 'altitude_m' and row[3] for row in cursor.execute('PRAGMA table_info(telemetry)')):
        cursor.execute('ALTER TABLE telemetry RENAME TO telemetry_with_required_altitude')
        cursor.execute('''CREATE TABLE telemetry (
            session_id TEXT NOT NULL, timestamp_seconds REAL NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL, altitude_m REAL,
            relative_altitude_m REAL, PRIMARY KEY(session_id, timestamp_seconds),
            FOREIGN KEY(session_id) REFERENCES sessions(session_id))''')
        cursor.execute('INSERT INTO telemetry SELECT * FROM telemetry_with_required_altitude')
        cursor.execute('DROP TABLE telemetry_with_required_altitude')

    # Additive migrations retain earlier flights and their human review decisions.
    migrations = {
        "sessions": {"run_id": "TEXT", "error_message": "TEXT"},
        "detections": {"run_id": "TEXT", "payload": "JSON"},
        "tracks": {"payload": "JSON"},
    }
    for table, columns in migrations.items():
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT, finished_at TEXT, error_message TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_session
        ON analysis_runs(session_id) WHERE status IN ('queued', 'analyzing', 'paused')
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS frame_samples (
            run_id TEXT NOT NULL, frame_idx INTEGER NOT NULL,
            timestamp_seconds REAL NOT NULL, stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            PRIMARY KEY(run_id, frame_idx),
            FOREIGN KEY(run_id) REFERENCES analysis_runs(run_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS detections_by_session ON detections(session_id, run_id)")

    conn.commit()
    conn.close()

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
