import sqlite3
import json
import os
from typing import Dict, Any, List, Optional

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DB_DIR, "aerofind.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
        altitude_m REAL NOT NULL,
        relative_altitude_m REAL,
        PRIMARY KEY (session_id, timestamp_seconds),
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    )
    """)

    conn.commit()
    conn.close()

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
