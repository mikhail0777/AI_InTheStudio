"""Run the generic search pipeline synchronously against one local video."""
import argparse
import json
import os
from pathlib import Path
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("query")
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    os.environ["AIEYE_DATA_DIR"] = str(args.data_dir.resolve())

    from app import database
    from app.models.schemas import TargetConfiguration
    from app.services.unified_search import UnifiedSearchManager
    from app.services.video_service import VideoService

    video = VideoService.inspect_video(str(args.video.resolve()))
    session_id = "validation_" + uuid.uuid4().hex[:12]
    run_id = "run_" + uuid.uuid4().hex[:12]
    target = TargetConfiguration(free_text_description=args.query)
    database.init_db()
    with database.get_db_connection() as conn:
        conn.execute(
            "INSERT INTO sessions(session_id,status,run_id,target_config,video_metadata) VALUES (?,?,?,?,?)",
            (session_id, "analyzing", run_id, target.model_dump_json(), video.model_dump_json()),
        )
        conn.execute(
            "INSERT INTO analysis_runs(run_id,session_id,status,started_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
            (run_id, session_id, "analyzing"),
        )
    started = time.perf_counter()
    results = UnifiedSearchManager.execute_analysis(
        session_id, target, run_id=run_id, checkpoint=lambda: None,
    )
    elapsed = time.perf_counter() - started
    print(json.dumps({
        "session_id": session_id,
        "video": video.model_dump(mode="json"),
        "query": args.query,
        "elapsed_seconds": round(elapsed, 3),
        "result_count": len(results),
        "classifications": {
            name: sum(result.classification == name for result in results)
            for name in ("strong_match", "possible_match", "unlikely_match", "insufficient_visibility")
        },
        "top_results": [{
            "classification": result.classification,
            "score": result.overall_score,
            "timestamp_seconds": result.best_timestamp_seconds,
            "color_support": result.component_scores.get("attribute_agreement"),
            "frame": result.best_frame_path,
            "clip": result.clip_path,
            "provenance": [item.model_dump(mode="json") for item in result.model_provenance],
        } for result in results[:5]],
    }, indent=2))


if __name__ == "__main__":
    main()
