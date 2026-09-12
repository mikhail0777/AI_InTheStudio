import os
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from app.models.schemas import SARReport, TrackResult, TargetConfiguration, SearchPlan, VideoMetadata

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
        reports_dir: str
    ) -> Tuple[SARReport, str]:
        os.makedirs(reports_dir, exist_ok=True)
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Sort tracks by final ranking score descending
        ranked_tracks = sorted(tracks, key=lambda t: t.final_ranking_score, reverse=True)
        people_detected = sum(t.observations_analyzed for t in tracks)

        # Generate Actionable Recommendations
        recommendations = []
        strong_matches = [t for t in ranked_tracks if t.classification == "strong_match"]
        possible_matches = [t for t in ranked_tracks if t.classification == "possible_match"]
        unclear_tracks = [t for t in ranked_tracks if t.classification == "insufficient_visibility"]

        if strong_matches:
            top = strong_matches[0]
            gps_str = f" at GPS ({top.gps_location.latitude}, {top.gps_location.longitude})" if top.gps_location else ""
            recommendations.append(f"CRITICAL: Dispatch SAR ground team immediately to verify Track {top.track_id}{gps_str} seen at timestamp {int(top.best_timestamp_seconds//60):02d}:{int(top.best_timestamp_seconds%60):02d}.")
        elif possible_matches:
            top = possible_matches[0]
            gps_str = f" (GPS: {top.gps_location.latitude}, {top.gps_location.longitude})" if top.gps_location else ""
            recommendations.append(f"PRIORITY REVIEW: Human operator confirm sighting at timestamp {int(top.best_timestamp_seconds//60):02d}:{int(top.best_timestamp_seconds%60):02d}{gps_str}. Upper clothing and backpack match target profile.")

        if unclear_tracks:
            recommendations.append(f"FLIGHT RECOMMENDATION: Re-fly region near timestamp {int(unclear_tracks[0].best_timestamp_seconds//60):02d}:{int(unclear_tracks[0].best_timestamp_seconds%60):02d} at lower altitude (30m) with 45-degree oblique camera angle to resolve heavy canopy/shadow occlusion.")

        if not strong_matches and not possible_matches:
            recommendations.append("SEARCH EXPANSION: No conclusive appearance match found in this recording. Recommend broadening target description parameters (e.g. allow alternative clothing color shades) or expanding flight search grid.")

        # Identify unsearched / low-visibility intervals
        unsearched_intervals = []
        if video_info.duration_seconds > 0:
            last_end = 0.0
            for t in sorted(tracks, key=lambda x: x.first_seen_seconds):
                if t.first_seen_seconds - last_end > 60.0:  # gap > 1 min
                    unsearched_intervals.append({"start_seconds": last_end, "end_seconds": t.first_seen_seconds})
                last_end = max(last_end, t.last_seen_seconds)
            if video_info.duration_seconds - last_end > 60.0:
                unsearched_intervals.append({"start_seconds": last_end, "end_seconds": video_info.duration_seconds})

        sar_report = SARReport(
            session_id=session_id,
            mission_name=f"SAR Mission {session_id[:8]}",
            generated_at=generated_at,
            target_description=target_config,
            search_plan=search_plan,
            video_info=video_info,
            total_frames_sampled=total_sampled_frames,
            total_people_detected=people_detected,
            unique_tracks_count=len(tracks),
            ranked_sightings=ranked_tracks,
            has_telemetry=has_telemetry,
            unsearched_intervals=unsearched_intervals,
            actionable_recommendations=recommendations
        )

        # Write HTML Report
        html_filename = f"report_{session_id}.html"
        html_path = os.path.join(reports_dir, html_filename)
        html_content = ReportGenerator.render_html_report(sar_report)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return sar_report, f"/reports/{html_filename}"

    @staticmethod
    def render_html_report(report: SARReport) -> str:
        tracks_html = ""
        for t in report.ranked_sightings:
            badge_color = "#10B981" if t.classification == "strong_match" else ("#F59E0B" if t.classification == "possible_match" else "#EF4444")
            gps_info = f"<b>GPS:</b> {t.gps_location.latitude}, {t.gps_location.longitude} (Alt: {t.gps_location.altitude_m}m)" if t.gps_location else "<b>GPS:</b> N/A"
            
            matching_items = "".join([f"<li>✅ {item}</li>" for item in t.matching_evidence])
            conflicting_items = "".join([f"<li>⚠️ {item}</li>" for item in t.conflicting_evidence])
            unknown_items = "".join([f"<li>❓ {item}</li>" for item in t.unknown_attributes])

            tracks_html += f"""
            <div class="card">
                <div class="card-header">
                    <span class="badge" style="background:{badge_color};">{t.classification.replace('_', ' ').title()}</span>
                    <h3>Track #{t.track_id} - Best Timestamp: {int(t.best_timestamp_seconds//60):02d}:{int(t.best_timestamp_seconds%60):02d} ({t.best_timestamp_seconds}s)</h3>
                </div>
                <div class="card-body">
                    <div class="grid-2">
                        <div>
                            <p><b>Final Ranking Score:</b> {int(t.final_ranking_score * 100)}%</p>
                            <p><b>Detection Conf:</b> {int(t.person_detection_confidence * 100)}% | <b>Appearance Similarity:</b> {int(t.appearance_similarity * 100)}%</p>
                            <p>{gps_info}</p>
                            <p><b>Observations Analyzed:</b> {t.observations_analyzed} frames ({t.first_seen_seconds}s to {t.last_seen_seconds}s)</p>
                            <p><b>Explanation:</b> {t.explanation}</p>
                        </div>
                        <div>
                            <h4>Evidence Summary</h4>
                            <ul>{matching_items} {conflicting_items} {unknown_items}</ul>
                        </div>
                    </div>
                </div>
            </div>
            """

        recs_html = "".join([f"<li>{r}</li>" for r in report.actionable_recommendations])

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI(EYE) in the sky SAR Post-Flight Search Report - {report.session_id}</title>
    <style>
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1, h2, h3 {{ color: #38bdf8; margin-top: 0; }}
        .header {{ border-bottom: 2px solid #334155; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; }}
        .card {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; margin-bottom: 1.5rem; padding: 1rem; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
        .recs-box {{ background: rgba(56, 189, 248, 0.1); border-left: 4px solid #38bdf8; padding: 1rem; border-radius: 4px; margin-bottom: 1.5rem; }}
        ul {{ padding-left: 1.2rem; }}
        li {{ margin-bottom: 0.4rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛸 AI(EYE) in the sky - Post-Flight SAR Search Report</h1>
            <p><b>Mission ID:</b> {report.session_id} | <b>Generated:</b> {report.generated_at}</p>
        </div>

        <div class="recs-box">
            <h2>🚨 Actionable SAR Recommendations</h2>
            <ul>{recs_html}</ul>
        </div>

        <h2>🎯 Missing Person Search Profile</h2>
        <div class="card">
            <p><b>Target Summary:</b> {report.search_plan.target_summary}</p>
            <p><b>High-Value Attributes:</b> {", ".join(report.search_plan.high_value_attributes)}</p>
            <p><b>Supporting Attributes:</b> {", ".join(report.search_plan.supporting_attributes)}</p>
        </div>

        <h2>📹 Video Flight Telemetry</h2>
        <div class="card">
            <p><b>File:</b> {report.video_info.filename} ({report.video_info.file_size_mb} MB)</p>
            <p><b>Duration:</b> {report.video_info.duration_seconds}s | <b>Resolution:</b> {report.video_info.width}x{report.video_info.height} @ {report.video_info.fps} FPS</p>
            <p><b>Total Sampled Frames:</b> {report.total_frames_sampled} | <b>Unique Person Tracks:</b> {report.unique_tracks_count}</p>
        </div>

        <h2>🔍 Ranked Candidate Sightings</h2>
        {tracks_html}
    </div>
</body>
</html>
"""
