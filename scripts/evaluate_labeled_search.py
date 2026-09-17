"""Evaluate persisted search results against an operator-supplied label manifest."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["AIEYE_DATA_DIR"] = str(args.data_dir.resolve())

    from app import database
    from app.services.evaluation import GroundTruthEvent, evaluate_results
    from app.services.generic_search import load_search_results

    if args.manifest.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Evaluation manifest exceeds the 10 MiB limit.")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(payload.get("cases"), list) or not payload["cases"]:
        raise ValueError("Evaluation manifest must contain at least one case.")
    if len(payload["cases"]) > 100:
        raise ValueError("Evaluation manifest cannot contain more than 100 cases.")
    reports = []
    for case in payload["cases"]:
        session_id = str(case.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("Every evaluation case requires a session_id.")
        event_payloads = case.get("ground_truth_events", [])
        if not isinstance(event_payloads, list) or len(event_payloads) > 10000:
            raise ValueError("Each evaluation case must contain at most 10,000 ground-truth events.")
        events = [GroundTruthEvent(**item) for item in event_payloads]
        with database.get_db_connection() as conn:
            session = conn.execute(
                """SELECT s.search_id,s.search_query,q.processing_mode,q.metrics_json
                   FROM sessions s LEFT JOIN searches q ON q.search_id=s.search_id
                   WHERE s.session_id=?""", (session_id,),
            ).fetchone()
            if not session or not session["search_id"]:
                raise LookupError(f"Completed search session not found: {session_id}")
            candidates = conn.execute(
                "SELECT payload FROM search_candidates WHERE search_id=? ORDER BY rank", (session["search_id"],),
            ).fetchall()
        candidate_times = [json.loads(row["payload"])["timestamp_seconds"] for row in candidates]
        report = evaluate_results(events, load_search_results(session_id), candidate_times)
        reports.append({
            "case_id": case.get("case_id", session_id), "session_id": session_id,
            "query": json.loads(session["search_query"] or "{}").get("original_text", ""),
            "processing_mode": session["processing_mode"],
            "search_metrics": json.loads(session["metrics_json"] or "{}"),
            "report": report.model_dump(mode="json"),
        })
    output = {"manifest": str(args.manifest.resolve()), "cases": reports}
    encoded = json.dumps(output, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
