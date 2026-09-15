# AI(EYE) in the sky

Local post-flight person detection and evidence review with optional DJI SRT telemetry.

## Run

Python 3.10+ and Node.js are required. From the repository root:

```powershell
python -m pip install -r backend/requirements.txt
python backend/download_models.py
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open http://localhost:5173. The main workflow is one description field, a required video,
and optional matching SRT telemetry. After installation, `run_aieye.bat` starts both services.
The segmentation model is already installed in this workspace. Runtime does not download
models or switch detectors. Missing weights or inference failures stop the job explicitly.

## Matching behavior

- YOLO detects people and backpacks. Zero people is a valid result; there is no HOG fallback.
- Backpack masks are excluded from approximate upper/lower clothing bands. These bands
  are estimates for upright people, not garment recognition. Occluded, small, or wide
  silhouettes can remain unknown. Stationary people are eligible for review.
- Up to six quality-ranked crops, separated by at least 0.75 seconds, support each track.
  Temporal separation limits neighboring frames; it does not prove independent views.
- Person evidence must pass a separate gate. Color or sharpness cannot compensate for
  insufficient person evidence. Visible conflicts block promotion.
- The configured `min_alert_confidence` is an internal color-support threshold, not a
  measured accuracy or identity probability. It applies to both candidate categories.
- The interface shows supported candidates and operator-flagged tracks only. Low-similarity
  and limited-evidence tracks remain internal. One card represents one track; track
  fragmentation can still produce separate cards for the same person.
- Simple descriptions can supply clothing colors/backpack attributes; selected fields
  override those extractions. Hair, identity, gender, and garment styles are not evaluated.
  Arbitrary required/negative constraints remain explicit and prevent automatic promotion.
- Each assessed attribute links to its supporting crops. Scores and model provenance remain
  available through the API; the operator UI uses evidence labels instead of percentages.
- SRT coordinates locate the aircraft, not the person's ground position. Missing altitude
  is preserved as unknown. Existing flights and review decisions are retained.

Large frames are analyzed once in full and again as overlapping native-resolution tiles.
This preserves scene context while improving recall for distant people without lowering the
person-confidence gate. Duplicate detections from overlapping views are removed class-wise.

Configuration: `AIEYE_MODEL_PATH`, `AIEYE_IMAGE_SIZE` (default 1280),
`AIEYE_ENABLE_TILING` (default true), `AIEYE_TILE_OVERLAP` (default 0.20),
`AIEYE_CPU_THREADS` (default 4), and `AIEYE_DATA_DIR` (default backend/data).
The application is intended for a local workstation and has no account login system.

## Verify

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -v
cd frontend
npm.cmd run build
```

`test_e2e.py` is an optional HTTP smoke test against a running backend and generated demo
video. Synthetic drawings are not a detector accuracy benchmark. Before operational use,
label representative real recordings (including tires, stationary people, occlusions,
and empty scenes) and measure missed people and false candidate alerts per video hour.
No measured precision/recall claim is made by this implementation.
