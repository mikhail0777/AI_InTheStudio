# LotTrace

Local dealership video investigation for finding vehicles in recorded security footage.

LotTrace is an operator-review tool, not an autonomous identification or enforcement system. Its first commercial slice is intentionally narrow: upload a dealership recording, search for a full or partial licence plate, review timestamped sightings, build a cross-recording vehicle history, and export an evidence report.

## MVP workflow

1. Upload an MP4, MOV, or MKV recording exported from an existing camera/NVR.
2. Enter a full plate or a known fragment and optional make, model, year, colour, and body type.
3. Identify the camera and its role (lot/service entry, exit, or general area) and optionally set the recording's real start time.
4. Select Fast, Balanced, or Thorough scan depth and an optional time window.
5. Review supported and review-only OCR sightings against the original footage.
6. Search the persistent sighting ledger by partial plate and vehicle profile, then export a printable evidence report.
7. Delete the case from the header when its approved retention period ends; this removes the uploaded recording, ledger entries, and generated evidence.

Plate searches use a dedicated dense scan rather than semantic keyframe retrieval. Full frames and overlapping tiles are read locally, OCR observations are grouped into time-based sightings, and common OCR confusions are shown as possible matches without being relabelled as exact reads. A supported result requires repeated or high-confidence full/partial plate evidence.

## Run locally

Python 3.10–3.14 and Node.js are supported. From the repository root:

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

Open `http://localhost:5173`. After dependencies and models are installed, `run_aieye.bat` can start both services.

## Scan depth

- **Fast:** 1 sampled frame per second; no tiled OCR.
- **Balanced:** 2 sampled frames per second with tiled OCR.
- **Thorough:** 4 sampled frames per second with tiled OCR.

Set `AIEYE_PLATE_SCAN_FPS` to override the selected cadence (0.1–15 FPS). Set `AIEYE_PLATE_REVIEW_SIMILARITY` to tune which non-exact OCR strings enter the review queue; the default is `0.78`. These settings affect recall, runtime, and the number of false review candidates. They do not change the definition of an exact match.

## Evidence policy

- Exact, partial, and review-candidate OCR reads remain distinct in stored evidence.
- Repeated reads must come from distinct sampled frames.
- Every sighting links to the original timestamp, an annotated frame, and a saved clip.
- Operator confirmations and rejections are retained with the investigation.
- “No result” means no supported sighting was found at the selected scan depth; it does not prove absence.
- No facial recognition is used by the dealership MVP.

## Pilot limitations

This is a local pilot build, not a network-ready multi-tenant service. It binds to localhost and has no account system. Do not expose it directly to a LAN or the internet. Before operational use:

- obtain written authorization for the footage and document the business purpose;
- define access, retention, deletion, and disclosure policies;
- benchmark representative dealership footage across day, night, glare, rain, snow, temporary plates, dealer plates, camera angles, and vehicle speeds;
- measure plate-search recall and false review candidates per video hour;
- require an operator to verify evidence before contacting a customer, employee, insurer, or law-enforcement agency.

The existing generic person/object research pipeline remains in the backend for regression compatibility, but it is not part of the LotTrace MVP interface.

Make, model, year, colour, and body type are currently operator-supplied metadata, not machine-verified attributes. Automatic damage comparison is also not implemented; it requires paired views, controlled camera geometry, labelled data, and its own validation. See `docs/DEALERSHIP_MVP_ARCHITECTURE.md` for the live-camera extension boundary and production roadmap.

## Commercial licensing

The generic colour-only vehicle path currently uses Ultralytics YOLO. Review its AGPL/commercial licensing requirements before any proprietary deployment. The plate-first path uses FastALPR and its model dependencies; maintain a complete third-party software and model licence inventory before selling or distributing the product. This repository does not yet include a product licence or legal terms.

## Verify

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -v
cd frontend
npm.cmd run build
```

The test suite uses synthetic media and mocked detections. It verifies application behavior, not real-world recognition accuracy. Real accuracy claims require labelled dealership recordings and the evaluation workflow under `evaluation/` and `scripts/evaluate_labeled_search.py`.
