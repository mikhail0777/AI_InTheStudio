"""Printable, timestamped evidence report for dealership investigations."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

from app import database
from app.services.generic_search import load_search_results


def _safe_url(value):
    value = value or ""
    return value if value.startswith("/evidence/") and ".." not in value else ""


def generate_generic_report(session_id: str) -> str:
    with database.get_db_connection() as conn:
        session = conn.execute(
            """SELECT s.search_query,s.target_config,s.video_metadata,q.processing_mode,q.metrics_json
               FROM sessions s LEFT JOIN searches q ON q.search_id=s.search_id WHERE s.session_id=?""",
            (session_id,),
        ).fetchone()
        sighting_rows = conn.execute(
            "SELECT * FROM vehicle_sightings WHERE session_id=?", (session_id,),
        ).fetchall()
    if not session or not session["search_query"]:
        raise ValueError("Search report inputs are missing.")
    query = json.loads(session["search_query"])
    target = json.loads(session["target_config"] or "{}")
    video = json.loads(session["video_metadata"] or "{}")
    results = load_search_results(session_id)
    sightings = {row["sighting_id"]: dict(row) for row in sighting_rows}
    metrics = json.loads(session["metrics_json"] or "{}")
    timing_items = "".join(
        f"<li>{escape(name.replace('_', ' ').title())}: {float(value):.3f} seconds</li>"
        for name, value in metrics.get("stage_timings", {}).items()
    )
    cards = []
    for result in results:
        sighting = sightings.get(result.result_id, {})
        image, clip = _safe_url(result.best_frame_path), _safe_url(result.clip_path)
        evidence = "".join(
            f"<li><b>{escape(item.kind.title())}:</b> {escape(item.assessment)} — {escape(item.explanation)}</li>"
            for item in result.evidence
        )
        absolute_time = sighting.get("captured_at") or "Recording start time not supplied"
        camera = " · ".join(filter(None, [sighting.get("camera_name"),
                                           sighting.get("event_type", "").replace("_", " ")]))
        vehicle = " · ".join(str(value) for value in (
            sighting.get("vehicle_year"), sighting.get("vehicle_color"), sighting.get("vehicle_make"),
            sighting.get("vehicle_model"), sighting.get("vehicle_body_type"),
        ) if value)
        cards.append(f"""
        <article><h2>{escape(result.classification.replace('_', ' ').title())}</h2>
        <p><b>OCR:</b> {escape(str(sighting.get('observed_plate') or 'not recorded'))} ·
           <b>Requested:</b> {escape(str(sighting.get('requested_plate') or ''))}</p>
        <p><b>Time:</b> {escape(str(absolute_time))} ({result.best_timestamp_seconds:.2f}s into recording)</p>
        {f'<p><b>Camera event:</b> {escape(camera)}</p>' if camera else ''}
        {('<p><b>Business-hours status:</b> After hours</p>' if sighting.get('after_hours') == 1 else
          '<p><b>Business-hours status:</b> Within configured hours</p>' if sighting.get('after_hours') == 0 else '')}
        {f'<p><b>Operator-supplied vehicle profile:</b> {escape(vehicle)}</p>' if vehicle else ''}
        <p>{result.start_seconds:.2f}s–{result.end_seconds:.2f}s · {escape(result.explanation)}</p>
        {f'<img src="{escape(image)}" alt="Annotated evidence">' if image else ''}
        {f'<video controls src="{escape(clip)}"></video>' if clip else ''}
        <ul>{evidence}</ul></article>""")
    no_results = "<p>No supported sighting was found at the selected scan depth. This does not establish absence from the complete video.</p>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Vehicle investigation report</title>
    <style>body{{font:15px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#243044}}
    article{{border:1px solid #ccd4df;padding:20px;margin:20px 0}}img,video{{max-width:100%;display:block;margin:14px 0}}
    small{{color:#667085}}</style></head><body><h1>Dealership vehicle investigation report</h1>
    <p><b>Case:</b> {escape(session_id)}</p>
    <p><b>Search:</b> {escape(query.get('original_text',''))}</p>
    <p><b>Recording:</b> {escape(video.get('filename',''))}</p>
    <p><b>Case plate:</b> {escape(str(target.get('plate_number') or ''))} ({escape(str(target.get('plate_match_mode') or 'exact'))} mode)</p>
    <p><b>Scan depth:</b> {escape((session['processing_mode'] or 'unknown').title())}</p>
    {f'<h2>Processing timings</h2><ul>{timing_items}</ul>' if timing_items else ''}
    <small>Generated {escape(datetime.now(timezone.utc).isoformat())}. OCR and automated evidence require review against the original footage before action. Vehicle profile values are operator-supplied unless explicitly identified as machine evidence.</small>
    {''.join(cards) if cards else no_results}</body></html>"""
    reports = Path(database.DB_DIR) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"report_{session_id}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)
