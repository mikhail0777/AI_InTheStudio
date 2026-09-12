import sys
import os
import time
import requests
import json

BASE_URL = "http://localhost:8000/api"

def run_e2e_test():
    print("==================================================")
    print("[E2E] AeroFind Agent - Automated System Integration Test")
    print("==================================================")

    # 1. Health check
    try:
        r = requests.get("http://localhost:8000/")
        assert r.status_code == 200, f"Backend status failed: {r.status_code}"
        print("[OK] Backend service is ONLINE.")
    except Exception as e:
        print(f"[ERR] Backend not responding on http://localhost:8000: {e}")
        return False

    # 2. Create Session
    target_payload = {
        "free_text_description": "Locate a missing hiker wearing a red hoodie, dark pants, and carrying a blue backpack.",
        "upper_clothing_color": "red",
        "upper_clothing_type": "hoodie",
        "lower_clothing_color": "black",
        "backpack": "blue backpack",
        "required_attributes": ["red upper clothing"],
        "optional_attributes": ["blue backpack", "black pants"],
        "min_alert_confidence": 0.60
    }

    r = requests.post(f"{BASE_URL}/sessions", json=target_payload)
    assert r.status_code == 200, f"Failed session creation: {r.text}"
    session = r.json()
    session_id = session["session_id"]
    print(f"[OK] Created Analysis Session: {session_id}")

    # 3. Upload Video
    video_file = "demo_drone_search.mp4"
    if not os.path.exists(video_file):
        print(f"[ERR] Demo video {video_file} not found. Run generate_demo_video.py first.")
        return False

    with open(video_file, "rb") as vf:
        r = requests.post(f"{BASE_URL}/sessions/{session_id}/video", files={"file": (video_file, vf, "video/mp4")})
    assert r.status_code == 200, f"Video upload failed: {r.text}"
    meta = r.json()["video_metadata"]
    print(f"[OK] Uploaded Drone Video: {meta['filename']} ({meta['duration_seconds']}s, {meta['width']}x{meta['height']} @ {meta['fps']} FPS)")

    # 4. Upload SRT Telemetry
    srt_file = "demo_drone_search.SRT"
    if os.path.exists(srt_file):
        with open(srt_file, "rb") as sf:
            r = requests.post(f"{BASE_URL}/sessions/{session_id}/telemetry", files={"file": (srt_file, sf, "text/plain")})
        assert r.status_code == 200, f"Telemetry upload failed: {r.text}"
        print(f"[OK] Uploaded DJI SRT Telemetry: Parsed {r.json()['gps_points_count']} GPS points.")

    # 5. Start Analysis
    r = requests.post(f"{BASE_URL}/sessions/{session_id}/analyze")
    assert r.status_code == 200, f"Start analysis failed: {r.text}"
    print("[OK] Autonomous Agent Analysis initiated.")

    # 6. Poll for completion
    print("[...] Polling agent analysis status...")
    completed = False
    for attempt in range(120):
        time.sleep(1.0)
        r = requests.get(f"{BASE_URL}/sessions/{session_id}/status")
        if r.status_code == 200:
            st = r.json()
            print(f"   [{st['current_stage']}] Progress: {st['progress_percent']:.1f}% | People Dets: {st['people_detected_count']} | Tracks: {st['unique_tracks_count']}")
            if st["status"] == "completed":
                completed = True
                break
            elif st["status"] == "error":
                print("[ERR] Analysis error reported.")
                return False

    if not completed:
        print("[ERR] Analysis timed out.")
        return False

    print("[OK] Analysis completed successfully!")

    # 7. Verify Tracks
    r = requests.get(f"{BASE_URL}/sessions/{session_id}/tracks")
    assert r.status_code == 200, f"Failed fetching tracks: {r.text}"
    tracks = r.json()
    print(f"[OK] Found {len(tracks)} ranked person tracks.")

    for tr in tracks:
        gps_str = f"GPS: ({tr['gps_location']['latitude']}, {tr['gps_location']['longitude']})" if tr.get('gps_location') else "No GPS"
        print(f"   Track #{tr['track_id']} [{tr['classification']}] Score: {int(tr['final_ranking_score']*100)}% | Time: {tr['best_timestamp_seconds']}s | {gps_str}")
        print(f"      Explanation: {tr['explanation']}")

    # 8. Submit Human Feedback on top track
    if tracks:
        top_track = tracks[0]
        fb_payload = {"status": "confirmed", "notes": "Confirmed visual match: Red hoodie and blue backpack clearly visible."}
        r = requests.post(f"{BASE_URL}/sessions/{session_id}/tracks/{top_track['track_id']}/feedback", json=fb_payload)
        assert r.status_code == 200, f"Feedback submission failed: {r.text}"
        print(f"[OK] Human feedback submitted for Track #{top_track['track_id']}: CONFIRMED.")

    # 9. Verify Post-Flight SAR Report
    r = requests.get(f"{BASE_URL}/sessions/{session_id}/status")
    print("\n[REPORT] Recent Agent Activity Feed:")
    for log in r.json()["agent_logs"][-8:]:
        print(f"   [{log['timestamp']}] [{log['step']}] {log['message']}")

    print("\n==================================================")
    print("[SUCCESS] AeroFind Agent E2E Integration Test PASSED!")
    print("==================================================")
    return True

if __name__ == "__main__":
    success = run_e2e_test()
    sys.exit(0 if success else 1)
