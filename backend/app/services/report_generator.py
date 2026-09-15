"""Evidence reports: observed coverage, human decisions, and explicit limits."""

import base64
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

from app.models.schemas import SARReport, TrackResult, TargetConfiguration, SearchPlan, VideoMetadata


def _text(value) -> str:
    return escape(str(value), quote=True)


def _time(seconds: float) -> str:
    minutes, remainder = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{remainder:06.3f}"


def _sample_times(values: Optional[List[float]], duration: float) -> List[float]:
    return sorted({float(value) for value in (values or []) if math.isfinite(value) and 0 <= value <= duration})


class ReportGenerator:
    @staticmethod
    def generate_report(
        session_id: str,
        target_config: TargetConfiguration,
        search_plan: SearchPlan,
        video_info: VideoMetadata,
        total_sampled_frames: int,
        tracks: List[TrackResult],
        has_telemetry: bool,
        reports_dir: str,
        *,
        sampled_timestamps: Optional[List[float]] = None,
        total_people_detected: Optional[int] = None,
        run_id: Optional[str] = None,
        failed_timestamps: Optional[List[float]] = None,
    ) -> Tuple[SARReport, str]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise ValueError("Invalid session identifier for report generation.")
        if total_sampled_frames < 0:
            raise ValueError("Analyzed frame count cannot be negative.")
        os.makedirs(reports_dir, exist_ok=True)
        ranked_tracks = sorted(tracks, key=lambda track: track.final_ranking_score, reverse=True)
        times = _sample_times(sampled_timestamps, video_info.duration_seconds)
        failed_times = _sample_times(failed_timestamps, video_info.duration_seconds)
        limitations = [
            "Automated detections and attribute comparisons are candidates for human review; internal ranking values are not identity probabilities.",
            "Sampling does not inspect every video frame. A missing detection does not establish that a person was absent.",
            "SRT positions describe the aircraft at capture time, not the ground location of a person. No target geolocation is calculated.",
            "An obscured or unreadable attribute is unknown, not a confirmed match or conflict.",
        ]
        if not has_telemetry:
            limitations.append("No usable aircraft telemetry is attached to this analysis.")
        if sampled_timestamps is None:
            coverage = f"{total_sampled_frames} frames recorded as analyzed. Per-frame sampling history is unavailable for this historical run."
        elif times:
            coverage = f"{total_sampled_frames} frames analyzed; recorded sample times span {_time(times[0])} to {_time(times[-1])}. This span is not continuous coverage."
        else:
            coverage = f"{total_sampled_frames} frames recorded as analyzed; no valid sample timestamps are recorded."
        if failed_times:
            limitations.append(f"{len(failed_times)} requested sample frames could not be decoded. These failures do not establish visibility in neighboring frames.")
        if total_people_detected is None:
            total_people_detected = sum(track.observations_analyzed for track in tracks)
            limitations.append("Historical detection count includes retained track observations only; full detector totals are unavailable.")

        review_pending = [track for track in ranked_tracks if track.requires_human_review and track.human_feedback != "rejected"]
        recommendations = []
        if review_pending:
            recommendations.append(f"Review original footage and supporting crops for {len(review_pending)} candidate tracks before drawing an operational conclusion.")
        if any(track.human_feedback == "confirmed" for track in ranked_tracks):
            recommendations.append("Operator-confirmed candidates are recorded separately from automated assessments; consult the review notes and source footage.")
        if not tracks:
            recommendations.append("No candidate tracks were retained. This does not establish that no person was present in the recording.")
        if not recommendations:
            recommendations.append("Review recorded operator decisions and unresolved attributes alongside the original footage.")

        revision = uuid4().hex
        report = SARReport(
            session_id=session_id,
            mission_name=f"Footage review {session_id}",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            target_description=target_config,
            search_plan=search_plan,
            video_info=video_info,
            total_frames_sampled=total_sampled_frames,
            total_people_detected=total_people_detected,
            unique_tracks_count=len(tracks),
            ranked_sightings=ranked_tracks,
            has_telemetry=has_telemetry,
            # Object detection gaps cannot establish unsearched intervals.
            unsearched_intervals=[],
            actionable_recommendations=recommendations,
            analysis_run_id=run_id,
            analyzed_timestamps_seconds=times,
            failed_sample_timestamps_seconds=failed_times,
            coverage_summary=coverage,
            limitations=limitations,
            report_revision=revision,
        )
        html_path = os.path.join(reports_dir, f"report_{session_id}.html")
        html_content = ReportGenerator.render_html_report(report, evidence_root=Path(reports_dir).parent / "crops")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=reports_dir, suffix=".tmp", delete=False) as output:
                temporary_path = output.name
                output.write(html_content)
            os.replace(temporary_path, html_path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return report, f"/api/sessions/{session_id}/report?revision={revision}"

    @staticmethod
    def _thumbnail(track: TrackResult, evidence_root: Optional[Path]) -> str:
        """Embed only local raster crops belonging to this session, with a size cap."""
        if evidence_root is None or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", track.session_id):
            return ""
        prefix = f"/crops/{track.session_id}/"
        if not track.best_frame_path.startswith(prefix):
            return ""
        relative = track.best_frame_path[len(prefix):]
        if not relative or any(part in relative for part in ("\\", "?", "#", "%", "\x00")):
            return ""
        session_root = (Path(evidence_root) / track.session_id).resolve()
        candidate = (session_root / relative).resolve()
        if not candidate.is_relative_to(session_root) or not candidate.is_file():
            return ""
        try:
            if candidate.stat().st_size > 2_000_000:
                return ""
            payload = candidate.read_bytes()
        except OSError:
            return ""
        if payload.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            return ""
        return f'<img class="crop" src="data:{mime};base64,{base64.b64encode(payload).decode("ascii")}" alt="Evidence crop for track {_text(track.track_id)}">'

    @staticmethod
    def render_html_report(report: SARReport, evidence_root: Optional[Path] = None) -> str:
        cards = []
        for track in report.ranked_sightings:
            classification = {
                "strong_match": "Candidate for review",
                "possible_match": "Possible candidate",
                "unlikely_match": "Low relevance",
                "insufficient_visibility": "Insufficient evidence",
            }.get(track.classification, "Candidate for review")
            review = {"confirmed": "Confirmed by operator", "rejected": "Rejected by operator", "needs_research": "More review requested"}.get(track.human_feedback, "Awaiting human review")
            gps = track.gps_location
            if gps:
                gps_info = f"{gps.latitude:.6f}, {gps.longitude:.6f}; SRT time {_time(gps.timestamp_seconds)}"
                if gps.altitude_m is not None:
                    gps_info += f"; absolute altitude {gps.altitude_m:g} m"
                if gps.relative_altitude_m is not None:
                    gps_info += f"; relative altitude {gps.relative_altitude_m:g} m"
                if gps.telemetry_match_offset_seconds is not None:
                    gps_info += f"; telemetry alignment gap {gps.telemetry_match_offset_seconds:g} s"
            else:
                gps_info = "No sufficiently close SRT position available"
            rows = "".join(
                f"<tr><th>{_text(name.replace('_', ' ').title())}</th><td>{_text(attribute.expected)}</td><td>{_text(attribute.observed)}</td><td>{_text(attribute.visibility.replace('_', ' '))}</td></tr>"
                for name, attribute in track.attributes.items()
            )
            sections = "".join(
                f"<h4>{label}</h4><ul>" + "".join(f"<li>{_text(item)}</li>" for item in items) + "</ul>"
                for label, items in (("Supporting evidence", track.matching_evidence), ("Conflicting evidence", track.conflicting_evidence), ("Unknown attributes", track.unknown_attributes)) if items
            )
            notes = f"<p><b>Operator notes:</b> {_text(track.human_notes)}</p>" if track.human_notes else ""
            cards.append(f"""<article class="card">
                <div class="badge">{_text(classification)}</div><h3>Track #{_text(track.track_id)} · {_time(track.best_timestamp_seconds)}</h3>
                <p class="review">{_text(review)}</p>
                <div class="evidence">{ReportGenerator._thumbnail(track, evidence_root)}<div>
                <p><b>Aircraft capture position:</b> {_text(gps_info)}</p>
                <p><b>Reviewed observations:</b> {track.observations_analyzed}; {_time(track.first_seen_seconds)}–{_time(track.last_seen_seconds)}</p>
                <p>{_text(track.explanation)}</p>{notes}</div></div>
                <div class="table-wrap"><table><thead><tr><th>Attribute</th><th>Requested</th><th>Observed</th><th>Visibility</th></tr></thead><tbody>{rows}</tbody></table></div>
                {sections}</article>""")
        tracks_html = "".join(cards) or '<div class="card">No candidate tracks retained. Check the coverage and limitations below.</div>'
        recs = "".join(f"<li>{_text(item)}</li>" for item in report.actionable_recommendations)
        limits = "".join(f"<li>{_text(item)}</li>" for item in report.limitations)
        failed = report.failed_sample_timestamps_seconds
        failures = ""
        if failed:
            failures = f'<p><b>Failed sample times:</b> {_text(", ".join(_time(value) for value in failed[:20]))}{" (first 20 shown)" if len(failed) > 20 else ""}</p>'
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Footage review · {_text(report.session_id)}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f7;color:#17212c;font:15px/1.6 system-ui,sans-serif;padding:32px 16px}}main{{max-width:960px;margin:auto}}
header{{margin-bottom:28px}}h1{{font-size:32px;letter-spacing:-1px;margin:4px 0}}h2{{font-size:21px;margin-top:32px}}h3{{margin:8px 0}}h4{{margin-bottom:4px}}
.muted{{color:#536171}}.card{{background:white;border:1px solid #dce2e8;border-radius:14px;padding:24px;margin:16px 0;break-inside:avoid}}
.badge{{display:inline-block;color:#204b65;background:#edf5fa;border-radius:20px;padding:3px 12px;font-size:13px}}.review{{font-weight:600}}
.evidence{{display:flex;gap:24px;align-items:flex-start}}.crop{{width:160px;max-height:280px;object-fit:contain;border-radius:8px;background:#edf0f3}}
.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:16px}}th,td{{text-align:left;border-bottom:1px solid #e4e8ee;padding:10px;vertical-align:top}}
li{{margin-bottom:8px}}p{{overflow-wrap:anywhere}}@media(max-width:600px){{.evidence{{display:block}}.card{{padding:16px}}}}
@media print{{body{{background:white;padding:0}}.card{{border-color:#ccc}}}}
</style></head><body><main>
<header><p class="muted">AI(EYE) IN THE SKY · EVIDENCE REVIEW</p><h1>Post-flight footage review</h1>
<p class="muted">Session {_text(report.session_id)} · Generated {_text(report.generated_at)}</p></header>
<section class="card"><h2>Search description</h2><p>{_text(report.target_description.free_text_description)}</p>
<p><b>Configured search:</b> {_text(report.search_plan.target_summary)}</p><ul>{recs}</ul></section>
<h2>Candidate evidence</h2>{tracks_html}
<section class="card"><h2>Recording and analyzed samples</h2>
<p><b>Recording:</b> {_text(report.video_info.filename)} · {report.video_info.width} × {report.video_info.height} · {report.video_info.duration_seconds:g} seconds</p>
<p><b>Analyzed frames:</b> {report.total_frames_sampled} · <b>Person detector observations:</b> {report.total_people_detected} · <b>Retained tracks:</b> {report.unique_tracks_count}</p>
<p>{_text(report.coverage_summary)}</p>{failures}
<p><b>Telemetry:</b> {"SRT aircraft positions available" if report.has_telemetry else "Not available"}</p></section>
<section class="card"><h2>Interpretation limits</h2><ul>{limits}</ul></section>
<footer class="muted">Run {_text(report.analysis_run_id or "historical / unspecified")} · Revision {_text(report.report_revision)}</footer>
</main></body></html>"""
