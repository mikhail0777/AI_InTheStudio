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
        "sessions": {"run_id": "TEXT", "error_message": "TEXT", "search_query": "JSON",
                     "search_id": "TEXT", "index_id": "TEXT", "playback_url": "TEXT",
                     "proxy_status": "TEXT", "proxy_error": "TEXT"},
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            search_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            index_id TEXT, status TEXT NOT NULL, processing_mode TEXT NOT NULL DEFAULT 'balanced',
            query_json JSON NOT NULL, parser_provenance JSON,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, started_at TEXT, finished_at TEXT,
            error_message TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS searches_by_session ON searches(session_id, created_at)")
    search_columns = {row[1] for row in cursor.execute("PRAGMA table_info(searches)")}
    if "metrics_json" not in search_columns:
        cursor.execute("ALTER TABLE searches ADD COLUMN metrics_json JSON")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_results (
            search_id TEXT NOT NULL, result_id TEXT NOT NULL,
            start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
            classification TEXT NOT NULL, overall_score REAL NOT NULL,
            payload JSON NOT NULL, human_feedback TEXT, human_notes TEXT,
            PRIMARY KEY(search_id, result_id),
            FOREIGN KEY(search_id) REFERENCES searches(search_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS results_by_rank ON search_results(search_id, overall_score DESC)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_assets (
            media_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL UNIQUE,
            canonical_path TEXT NOT NULL, metadata JSON NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_indexes (
            index_id TEXT PRIMARY KEY, media_id TEXT NOT NULL,
            status TEXT NOT NULL, processing_mode TEXT NOT NULL,
            config_hash TEXT NOT NULL, index_version TEXT NOT NULL,
            model_manifest JSON NOT NULL, artifact_manifest_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
            error_message TEXT,
            UNIQUE(media_id, config_hash),
            FOREIGN KEY(media_id) REFERENCES media_assets(media_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS indexes_by_media ON video_indexes(media_id, status)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenes (
            index_id TEXT NOT NULL, scene_id TEXT NOT NULL,
            start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
            PRIMARY KEY(index_id, scene_id),
            FOREIGN KEY(index_id) REFERENCES video_indexes(index_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexed_frames (
            index_id TEXT NOT NULL, frame_id TEXT NOT NULL,
            frame_idx INTEGER NOT NULL, timestamp_seconds REAL NOT NULL,
            scene_id TEXT NOT NULL, image_path TEXT NOT NULL,
            quality_score REAL NOT NULL, metadata JSON,
            PRIMARY KEY(index_id, frame_id),
            UNIQUE(index_id, frame_idx),
            FOREIGN KEY(index_id) REFERENCES video_indexes(index_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS frames_by_time ON indexed_frames(index_id, timestamp_seconds)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexed_clips (
            index_id TEXT NOT NULL, clip_id TEXT NOT NULL,
            start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
            representative_frame_id TEXT NOT NULL, artifact_path TEXT,
            metadata JSON,
            PRIMARY KEY(index_id, clip_id),
            FOREIGN KEY(index_id) REFERENCES video_indexes(index_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS clips_by_time ON indexed_clips(index_id, start_seconds, end_seconds)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            index_id TEXT NOT NULL, owner_kind TEXT NOT NULL, owner_id TEXT NOT NULL,
            provider TEXT NOT NULL, model_version TEXT NOT NULL,
            dimension INTEGER NOT NULL, vector BLOB NOT NULL, metadata JSON,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(index_id, owner_kind, owner_id, provider, model_version),
            FOREIGN KEY(index_id) REFERENCES video_indexes(index_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS embeddings_by_index ON embeddings(index_id, provider, model_version)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_candidates (
            search_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            owner_kind TEXT NOT NULL, owner_id TEXT NOT NULL,
            semantic_similarity REAL NOT NULL, rank INTEGER NOT NULL,
            payload JSON NOT NULL,
            PRIMARY KEY(search_id, candidate_id),
            FOREIGN KEY(search_id) REFERENCES searches(search_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS candidates_by_rank ON search_candidates(search_id, rank)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_sightings (
            sighting_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            search_id TEXT NOT NULL,
            requested_plate TEXT NOT NULL,
            observed_plate TEXT NOT NULL,
            plate_match_mode TEXT NOT NULL,
            match_kind TEXT NOT NULL,
            ocr_confidence REAL NOT NULL,
            similarity REAL NOT NULL,
            first_seen_seconds REAL NOT NULL,
            last_seen_seconds REAL NOT NULL,
            best_timestamp_seconds REAL NOT NULL,
            captured_at TEXT,
            after_hours INTEGER,
            camera_name TEXT,
            camera_role TEXT NOT NULL DEFAULT 'unknown',
            event_type TEXT NOT NULL DEFAULT 'observed',
            vehicle_make TEXT,
            vehicle_model TEXT,
            vehicle_year INTEGER,
            vehicle_color TEXT,
            vehicle_body_type TEXT,
            vehicle_detection_confidence REAL,
            vehicle_color_confidence REAL,
            requested_vehicle_make TEXT,
            requested_vehicle_model TEXT,
            requested_vehicle_year INTEGER,
            requested_vehicle_color TEXT,
            requested_vehicle_body_type TEXT,
            vehicle_attribute_state TEXT,
            vehicle_attribute_candidates_json JSON,
            source_filename TEXT,
            evidence_frame TEXT,
            evidence_clip TEXT,
            review_status TEXT,
            review_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id),
            FOREIGN KEY(search_id) REFERENCES searches(search_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS vehicle_sightings_by_plate ON vehicle_sightings(observed_plate, requested_plate)")
    cursor.execute("CREATE INDEX IF NOT EXISTS vehicle_sightings_by_time ON vehicle_sightings(captured_at, best_timestamp_seconds)")
    sighting_columns = {row[1] for row in cursor.execute("PRAGMA table_info(vehicle_sightings)")}
    if "after_hours" not in sighting_columns:
        cursor.execute("ALTER TABLE vehicle_sightings ADD COLUMN after_hours INTEGER")
    sighting_additions = {
        "vehicle_detection_confidence": "REAL",
        "vehicle_color_confidence": "REAL",
        "requested_vehicle_make": "TEXT",
        "requested_vehicle_model": "TEXT",
        "requested_vehicle_year": "INTEGER",
        "requested_vehicle_color": "TEXT",
        "requested_vehicle_body_type": "TEXT",
        "corrected_plate": "TEXT",
        "consensus_plate": "TEXT",
        "consensus_state": "TEXT",
        "consensus_details_json": "JSON",
        "best_plate_crop": "TEXT",
        "enhanced_plate_crop": "TEXT",
        "vehicle_attribute_state": "TEXT",
        "vehicle_attribute_candidates_json": "JSON",
    }
    for column, sql_type in sighting_additions.items():
        if column not in sighting_columns:
            cursor.execute(f"ALTER TABLE vehicle_sightings ADD COLUMN {column} {sql_type}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sighting_revisions (
            revision_id TEXT PRIMARY KEY,
            sighting_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'local_operator',
            previous_value JSON,
            new_value JSON,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sighting_id) REFERENCES vehicle_sightings(sighting_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS revisions_by_sighting ON sighting_revisions(sighting_id, created_at)")

    cursor.execute("""CREATE TABLE IF NOT EXISTS plate_ocr_observations (
        observation_id TEXT PRIMARY KEY, sighting_id TEXT NOT NULL,
        frame_idx INTEGER NOT NULL, timestamp_seconds REAL NOT NULL,
        source_frame_reference TEXT NOT NULL, detected_bbox_json JSON NOT NULL,
        raw_plate_crop_reference TEXT, enhanced_plate_crop_reference TEXT,
        quality_metrics_json JSON NOT NULL DEFAULT '{}',
        ocr_candidates_json JSON NOT NULL DEFAULT '[]',
        model_manifest_json JSON NOT NULL DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sighting_id) REFERENCES vehicle_sightings(sighting_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS plate_observations_by_sighting ON plate_ocr_observations(sighting_id,frame_idx)")
    for action in ("UPDATE", "DELETE"):
        cursor.execute(f"""CREATE TRIGGER IF NOT EXISTS plate_ocr_observations_immutable_{action.lower()}
            BEFORE {action} ON plate_ocr_observations
            BEGIN SELECT RAISE(ABORT, 'plate OCR observations are immutable'); END""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proxy_jobs (
            session_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            error_message TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS proxy_jobs_by_status ON proxy_jobs(status, created_at)")

    cursor.execute("""CREATE TABLE IF NOT EXISTS dealerships (
        dealership_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('viewer','reviewer','manager','administrator','auditor')),
        password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS cameras (
        camera_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'unknown', location TEXT, timezone TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id))""")
    camera_columns = {row[1] for row in cursor.execute("PRAGMA table_info(cameras)")}
    camera_additions = {
        "stream_url": "TEXT", "credential_blob": "BLOB", "onvif_device_url": "TEXT",
        "onvif_profile_token": "TEXT", "capture_fps": "REAL NOT NULL DEFAULT 15",
        "inference_fps": "REAL NOT NULL DEFAULT 3", "evidence_enabled": "INTEGER NOT NULL DEFAULT 1",
        "evidence_segment_seconds": "INTEGER NOT NULL DEFAULT 60",
        "evidence_retention_hours": "INTEGER NOT NULL DEFAULT 168",
        "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }
    for column, definition in camera_additions.items():
        if column not in camera_columns:
            cursor.execute(f"ALTER TABLE cameras ADD COLUMN {column} {definition}")
    cursor.execute("""CREATE TABLE IF NOT EXISTS camera_runtime_events (
        runtime_event_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, event_type TEXT NOT NULL,
        status TEXT NOT NULL, detail TEXT, metrics_json JSON NOT NULL DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(camera_id) REFERENCES cameras(camera_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS camera_runtime_by_camera ON camera_runtime_events(camera_id,created_at DESC)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, normalized_plate TEXT,
        vin TEXT, stock_number TEXT, make TEXT, model TEXT, year INTEGER,
        color TEXT, body_type TEXT, status TEXT NOT NULL DEFAULT 'active', notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS vehicles_by_plate ON vehicles(dealership_id, normalized_plate)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS plate_aliases (
        alias_id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL, normalized_plate TEXT NOT NULL,
        valid_from TEXT, valid_to TEXT, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS sighting_vehicle_links (
        sighting_id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL, linked_by TEXT NOT NULL,
        reason TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sighting_id) REFERENCES vehicle_sightings(sighting_id),
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id), FOREIGN KEY(linked_by) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS audit_events (
        event_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, actor_user_id TEXT,
        action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
        previous_value JSON, new_value JSON, reason TEXT, source_identifiers JSON,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id),
        FOREIGN KEY(actor_user_id) REFERENCES users(user_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS audit_by_entity ON audit_events(entity_type, entity_id, created_at)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS retention_policies (
        dealership_id TEXT PRIMARY KEY, source_video_days INTEGER NOT NULL DEFAULT 90,
        derived_media_days INTEGER NOT NULL DEFAULT 90, sightings_days INTEGER NOT NULL DEFAULT 365,
        audit_days INTEGER NOT NULL DEFAULT 2555, updated_by TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id), FOREIGN KEY(updated_by) REFERENCES users(user_id))""")

    # Tenant ownership was introduced after the original investigation tables.
    # Existing local rows remain readable but new authenticated work is always scoped.
    for table in ("sessions", "vehicle_sightings"):
        columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
        if "dealership_id" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN dealership_id TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS sessions_by_dealership ON sessions(dealership_id, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS sightings_by_dealership ON vehicle_sightings(dealership_id, created_at)")

    cursor.execute("""CREATE TABLE IF NOT EXISTS inspections (
        inspection_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, vehicle_id TEXT NOT NULL,
        inspection_type TEXT NOT NULL CHECK(inspection_type IN ('arrival','departure')),
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','completed','reopened')),
        camera_id TEXT, device_label TEXT, operator_user_id TEXT NOT NULL, notes TEXT,
        captured_at TEXT NOT NULL, completed_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id),
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id), FOREIGN KEY(camera_id) REFERENCES cameras(camera_id),
        FOREIGN KEY(operator_user_id) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS inspection_media (
        media_id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL, viewpoint TEXT NOT NULL,
        source_filename TEXT NOT NULL, storage_path TEXT NOT NULL, mime_type TEXT NOT NULL,
        sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
        captured_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(inspection_id) REFERENCES inspections(inspection_id))""")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS inspection_viewpoint ON inspection_media(inspection_id, viewpoint)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS condition_annotations (
        annotation_id TEXT PRIMARY KEY, media_id TEXT NOT NULL, x REAL NOT NULL, y REAL NOT NULL,
        width REAL NOT NULL, height REAL NOT NULL, damage_type TEXT NOT NULL, severity TEXT NOT NULL,
        assessment TEXT NOT NULL CHECK(assessment IN ('pre_existing','possible_change','unchanged','repaired','inconclusive')),
        notes TEXT, review_status TEXT NOT NULL DEFAULT 'requires_review', actor_user_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(media_id) REFERENCES inspection_media(media_id),
        FOREIGN KEY(actor_user_id) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, vehicle_id TEXT,
        title TEXT NOT NULL, summary TEXT, priority TEXT NOT NULL DEFAULT 'normal',
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','requires_review','approved','closed')),
        created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id), FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id),
        FOREIGN KEY(created_by) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS incident_evidence (
        evidence_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, evidence_type TEXT NOT NULL,
        entity_id TEXT NOT NULL, note TEXT, added_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id), FOREIGN KEY(added_by) REFERENCES users(user_id))""")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS incident_evidence_unique ON incident_evidence(incident_id,evidence_type,entity_id)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS incident_notes (
        note_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, note TEXT NOT NULL, actor_user_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(incident_id) REFERENCES incidents(incident_id),
        FOREIGN KEY(actor_user_id) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS incident_attachments (
        attachment_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, source_filename TEXT NOT NULL,
        storage_path TEXT NOT NULL, mime_type TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
        added_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id), FOREIGN KEY(added_by) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS incident_approvals (
        approval_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, action TEXT NOT NULL,
        reason TEXT NOT NULL, actor_user_id TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id), FOREIGN KEY(actor_user_id) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS evidence_holds (
        hold_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, reason TEXT NOT NULL, placed_by TEXT NOT NULL,
        placed_at TEXT DEFAULT CURRENT_TIMESTAMP, released_by TEXT, released_at TEXT,
        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id), FOREIGN KEY(placed_by) REFERENCES users(user_id),
        FOREIGN KEY(released_by) REFERENCES users(user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS evidence_exports (
        export_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
        archive_sha256 TEXT NOT NULL, storage_path TEXT NOT NULL, created_by TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(incident_id) REFERENCES incidents(incident_id),
        FOREIGN KEY(created_by) REFERENCES users(user_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS inspections_by_vehicle ON inspections(vehicle_id,captured_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS incidents_by_dealership ON incidents(dealership_id,updated_at)")
    retention_columns={row[1] for row in cursor.execute("PRAGMA table_info(retention_policies)").fetchall()}
    for column,default in (("inspections_days",1095),("incidents_days",2555)):
        if column not in retention_columns:cursor.execute(f"ALTER TABLE retention_policies ADD COLUMN {column} INTEGER NOT NULL DEFAULT {default}")

    # Milestone A: configured gate crossings and immutable inventory events.
    cursor.execute("""CREATE TABLE IF NOT EXISTS camera_boundaries (
        boundary_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL, name TEXT NOT NULL,
        boundary_type TEXT NOT NULL CHECK(boundary_type IN ('entrance','exit')),
        x1 REAL NOT NULL, y1 REAL NOT NULL, x2 REAL NOT NULL, y2 REAL NOT NULL,
        travel_direction TEXT NOT NULL CHECK(travel_direction IN ('negative_to_positive','positive_to_negative')),
        min_vehicle_width REAL NOT NULL DEFAULT 0.08, min_vehicle_height REAL NOT NULL DEFAULT 0.08,
        min_visible_fraction REAL NOT NULL DEFAULT 0.65, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(camera_id,name), FOREIGN KEY(camera_id) REFERENCES cameras(camera_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS vehicle_events (
        event_id TEXT PRIMARY KEY, dealership_id TEXT NOT NULL, camera_id TEXT NOT NULL,
        boundary_id TEXT NOT NULL, session_id TEXT, track_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('arrival','departure')),
        occurred_at TEXT NOT NULL, timezone TEXT NOT NULL, direction_of_travel TEXT NOT NULL,
        consensus_plate TEXT, plate_match_state TEXT NOT NULL,
        matched_vehicle_id TEXT, review_state TEXT NOT NULL CHECK(review_state IN ('confirmed','requires_review')),
        review_reason TEXT, recording_reference TEXT, best_vehicle_crop TEXT, best_plate_crop TEXT,
        ocr_candidates_json JSON NOT NULL DEFAULT '[]', evidence_json JSON NOT NULL DEFAULT '{}',
        model_manifest_json JSON NOT NULL DEFAULT '{}', idempotency_key TEXT NOT NULL UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(dealership_id) REFERENCES dealerships(dealership_id),
        FOREIGN KEY(camera_id) REFERENCES cameras(camera_id),
        FOREIGN KEY(boundary_id) REFERENCES camera_boundaries(boundary_id),
        FOREIGN KEY(session_id) REFERENCES sessions(session_id),
        FOREIGN KEY(matched_vehicle_id) REFERENCES vehicles(vehicle_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS vehicle_events_by_dealership ON vehicle_events(dealership_id,occurred_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS vehicle_events_by_vehicle ON vehicle_events(matched_vehicle_id,occurred_at DESC)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS vehicle_event_observations (
        event_id TEXT NOT NULL, observation_index INTEGER NOT NULL,
        timestamp_seconds REAL NOT NULL, center_x REAL NOT NULL, center_y REAL NOT NULL,
        width REAL NOT NULL, height REAL NOT NULL, visible_fraction REAL NOT NULL,
        frame_reference TEXT, vehicle_crop_reference TEXT, plate_crop_reference TEXT,
        PRIMARY KEY(event_id,observation_index), FOREIGN KEY(event_id) REFERENCES vehicle_events(event_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS vehicle_status_transitions (
        transition_id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL, event_id TEXT NOT NULL UNIQUE,
        previous_status TEXT NOT NULL, new_status TEXT NOT NULL CHECK(new_status IN ('on_lot','off_lot')),
        occurred_at TEXT NOT NULL, evidence_json JSON NOT NULL DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id), FOREIGN KEY(event_id) REFERENCES vehicle_events(event_id))""")
    cursor.execute("CREATE INDEX IF NOT EXISTS status_transitions_by_vehicle ON vehicle_status_transitions(vehicle_id,occurred_at DESC)")
    for table in ("vehicle_events","vehicle_event_observations","vehicle_status_transitions"):
        cursor.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_update
            BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END""")
        cursor.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete
            BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END""")

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
