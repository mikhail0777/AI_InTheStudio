import os
import cv2
import numpy as np

def generate_demo_assets(output_dir: str = "."):
    os.makedirs(output_dir, exist_ok=True)
    video_path = os.path.join(output_dir, "demo_drone_search.mp4")
    srt_path = os.path.join(output_dir, "demo_drone_search.SRT")

    width, height = 1920, 1080
    fps = 24.0
    duration_sec = 45.0
    total_frames = int(fps * duration_sec)

    print(f"[DemoGen] Generating synthetic aerial drone search footage ({total_frames} frames @ 1080p)...")

    # FourCC codec: mp4v
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

    # Base GPS coordinates for simulated SAR search sector
    base_lat = 37.774900
    base_lon = -122.419400
    base_alt = 48.0

    srt_entries = []

    for f_idx in range(total_frames):
        t_sec = f_idx / fps

        # Background: Aerial grass/dirt search grid texture
        # Base green terrain
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (34, 75, 42)  # Dark green foliage

        # Add subtle dirt path diagonal across frame
        path_pts = np.array([[100, 1080], [400, 1080], [1800, 0], [1500, 0]], np.int32)
        cv2.fillPoly(frame, [path_pts], (45, 65, 85))  # Brownish dirt path

        # Add some foliage texture noise/circles
        np.random.seed(f_idx % 30)
        for _ in range(15):
            rx = (f_idx * 17 + _ * 120) % width
            ry = (f_idx * 13 + _ * 90) % height
            cv2.circle(frame, (rx, ry), 25, (25, 55, 30), -1)

        # Subject 2: Distractor (Green Jacket, Blue Pants) - visible t=4.0s to 18.0s
        if 4.0 <= t_sec <= 18.0:
            progress = (t_sec - 4.0) / 14.0
            sx = int(300 + progress * 500)
            sy = int(700 - progress * 200)

            # Draw person (top-down view)
            # Legs (Blue)
            cv2.rectangle(frame, (sx - 12, sy + 15), (sx + 12, sy + 35), (180, 50, 40), -1)
            # Upper body (Green Jacket)
            cv2.ellipse(frame, (sx, sy), (22, 18), 0, 0, 360, (50, 180, 60), -1)
            # Head (Hair)
            cv2.circle(frame, (sx, sy - 5), 10, (40, 50, 60), -1)

        # Subject 1: TARGET MATCH (Red Hoodie, Dark Pants, Blue Backpack) - visible t=10.0s to 32.0s
        if 10.0 <= t_sec <= 32.0:
            progress = (t_sec - 10.0) / 22.0
            sx = int(600 + progress * 700)
            sy = int(850 - progress * 550)

            # Lower body (Dark Pants)
            cv2.rectangle(frame, (sx - 14, sy + 18), (sx + 14, sy + 40), (20, 20, 20), -1)
            # Upper body (RED HOODIE)
            cv2.ellipse(frame, (sx, sy), (26, 20), 0, 0, 360, (30, 30, 220), -1)
            # BLUE BACKPACK on upper rear
            cv2.rectangle(frame, (sx - 12, sy - 18), (sx + 12, sy - 2), (210, 120, 30), -1)
            # Head (Short dark hair)
            cv2.circle(frame, (sx, sy + 2), 9, (20, 25, 30), -1)

        # Subject 3: Distractor 2 (Yellow Shirt, Dark Shorts) - visible t=25.0s to 42.0s
        if 25.0 <= t_sec <= 42.0:
            progress = (t_sec - 25.0) / 17.0
            sx = int(1400 - progress * 400)
            sy = int(300 + progress * 450)

            # Lower body (Shorts)
            cv2.rectangle(frame, (sx - 12, sy + 15), (sx + 12, sy + 30), (40, 40, 40), -1)
            # Upper body (Yellow Shirt)
            cv2.ellipse(frame, (sx, sy), (22, 18), 0, 0, 360, (20, 220, 240), -1)
            # Head
            cv2.circle(frame, (sx, sy - 4), 9, (30, 40, 50), -1)

        out.write(frame)

        # Generate SRT Telemetry every 1 second (every 24 frames)
        if f_idx % int(fps) == 0:
            sec_idx = int(t_sec)
            start_tc = f"00:00:{sec_idx:02d},000"
            end_tc = f"00:00:{sec_idx+1:02d},000"

            lat_val = base_lat + (sec_idx * 0.00003)
            lon_val = base_lon + (sec_idx * 0.00004)
            rel_alt = base_alt + np.sin(sec_idx * 0.1) * 2.0

            srt_block = f"{sec_idx + 1}\n{start_tc} --> {end_tc}\nHOME({base_lon:.6f},{base_lat:.6f}) 2026.09.12 14:00:{sec_idx:02d}\n[iso : 100] [shutter : 1/500] [latitude: {lat_val:.6f}] [longitude: {lon_val:.6f}] [rel_alt: {rel_alt:.1f} abs_alt: {rel_alt+100.0:.1f}]\n"
            srt_entries.append(srt_block)

    out.release()
    print(f"[DemoGen] Created demo video: {video_path}")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    print(f"[DemoGen] Created demo SRT telemetry: {srt_path}")

if __name__ == "__main__":
    generate_demo_assets(".")
