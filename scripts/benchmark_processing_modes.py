"""Benchmark bounded processing modes against one local video and print reproducible JSON."""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import uuid


def percentile(values, quantile):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("query")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 20:
        raise ValueError("--repeats must be between 2 and 20")
    os.environ["AIEYE_DATA_DIR"] = str(args.data_dir.resolve())

    from app import database
    from app.models.schemas import TargetConfiguration
    from app.services.unified_search import UnifiedSearchManager
    from app.services.video_service import VideoService

    video = VideoService.inspect_video(str(args.video.resolve()))
    database.init_db()
    runs = []
    for mode in ("fast", "balanced", "thorough"):
        for repeat in range(args.repeats):
            session_id = "benchmark_" + uuid.uuid4().hex[:12]
            run_id = "run_" + uuid.uuid4().hex[:12]
            target = TargetConfiguration(free_text_description=args.query, processing_mode=mode)
            with database.get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO sessions(session_id,status,run_id,target_config,video_metadata) VALUES (?,?,?,?,?)",
                    (session_id, "analyzing", run_id, target.model_dump_json(), video.model_dump_json()),
                )
                conn.execute(
                    "INSERT INTO analysis_runs(run_id,session_id,status,started_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                    (run_id, session_id, "analyzing"),
                )
            results = UnifiedSearchManager.execute_analysis(
                session_id, target, run_id=run_id, checkpoint=lambda: None,
            )
            with database.get_db_connection() as conn:
                row = conn.execute(
                    "SELECT metrics_json FROM searches WHERE search_id=(SELECT search_id FROM sessions WHERE session_id=?)",
                    (session_id,),
                ).fetchone()
            metrics = json.loads(row["metrics_json"])
            runs.append({
                "session_id": session_id, "mode": mode, "repeat": repeat + 1,
                "result_count": len(results),
                "classifications": {
                    name: sum(result.classification == name for result in results)
                    for name in ("strong_match", "possible_match", "unlikely_match", "insufficient_visibility")
                },
                **metrics,
            })

    stage_names = sorted({name for run in runs for name in run["stage_timings"]})
    summary = {}
    for mode in ("fast", "balanced", "thorough"):
        selected = [run for run in runs if run["mode"] == mode]
        summary[mode] = {
            name: {
                "p50_seconds": round(statistics.median([run["stage_timings"][name] for run in selected]), 3),
                "p95_seconds": round(percentile([run["stage_timings"][name] for run in selected], .95), 3),
            } for name in stage_names
        }
        summary[mode]["repeat_search_seconds"] = round(selected[-1]["stage_timings"]["total"], 3)
    print(json.dumps({
        "video": video.model_dump(mode="json"), "query": args.query,
        "repeats_per_mode": args.repeats, "runs": runs, "summary": summary,
    }, indent=2))


if __name__ == "__main__":
    main()
