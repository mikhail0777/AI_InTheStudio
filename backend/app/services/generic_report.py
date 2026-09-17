"""Minimal evidence report for generic search results."""
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
        session = conn.execute("""SELECT s.search_query,s.video_metadata,q.processing_mode,q.metrics_json
            FROM sessions s LEFT JOIN searches q ON q.search_id=s.search_id WHERE s.session_id=?""",
            (session_id,)).fetchone()
    if not session or not session["search_query"]:
        raise ValueError("Generic search report inputs are missing.")
    query = json.loads(session["search_query"])
    video = json.loads(session["video_metadata"] or "{}")
    results = load_search_results(session_id)
    metrics = json.loads(session["metrics_json"] or "{}")
    timings = metrics.get("stage_timings", {})
    timing_items = "".join(
        f"<li>{escape(name.replace('_', ' ').title())}: {float(value):.3f} seconds</li>"
        for name, value in timings.items()
    )
    cards = []
    for result in results:
        image = _safe_url(result.best_frame_path)
        clip = _safe_url(result.clip_path)
        evidence = "".join(
            f"<li><b>{escape(item.kind.title())}:</b> {escape(item.assessment)} — {escape(item.explanation)}</li>"
            for item in result.evidence
        )
        cards.append(f"""
        <article><h2>{escape(result.classification.replace('_', ' ').title())}</h2>
        <p>{result.start_seconds:.2f}s–{result.end_seconds:.2f}s · {escape(result.explanation)}</p>
        {f'<img src="{escape(image)}" alt="Annotated evidence">' if image else ''}
        {f'<video controls src="{escape(clip)}"></video>' if clip else ''}
        <ul>{evidence}</ul></article>""")
    no_results = "<p>No matching event was found in the analyzed frames. This does not establish absence from the complete video.</p>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Video search report</title>
    <style>body{{font:15px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;color:#243044}}
    article{{border:1px solid #ccd4df;padding:20px;margin:20px 0}}img,video{{max-width:100%;display:block;margin:14px 0}}
    small{{color:#667085}}</style></head><body><h1>Open-vocabulary video search report</h1>
    <p><b>Query:</b> {escape(query.get('original_text',''))}</p>
    <p><b>Video:</b> {escape(video.get('filename',''))}</p>
    <p><b>Processing mode:</b> {escape((session['processing_mode'] or 'unknown').title())}</p>
    {f'<h2>Stage timings</h2><ul>{timing_items}</ul>' if timing_items else ''}
    <small>Generated {escape(datetime.now(timezone.utc).isoformat())}. Automated evidence requires human review.</small>
    {''.join(cards) if cards else no_results}</body></html>"""
    reports = Path(database.DB_DIR) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"report_{session_id}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)
