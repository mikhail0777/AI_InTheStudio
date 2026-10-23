# LotTrace

Local dealership vehicle-arrival, departure, and evidence software for recorded security footage.

LotTrace processes a recording into a reviewable timeline of every supported vehicle. Licence plates are the primary identity; colour and ranked make/model/year candidates provide supporting evidence. It is an operator-review tool, not an autonomous identification or enforcement system.

## MVP workflow

1. Upload an MP4, MOV, or MKV recording exported from an existing camera/NVR.
2. Identify the camera and its role (lot/service entry, exit, or general area) and optionally set the recording's real start time.
3. Start analysis. LotTrace detects every supported vehicle; there is no required plate or vehicle search target.
4. Repeated detections are grouped into a timeline, while adaptive frame selection favours clear, independent plate views.
5. Review vehicle, plate, colour, and make/model evidence against the original footage.
6. Search the persistent sighting ledger, review arrival/departure events, and inspect vehicle history.
7. Delete a recording analysis when its approved retention period ends; this removes its upload and generated evidence.

Plate searches use a dedicated dense scan rather than semantic keyframe retrieval. Full frames and overlapping tiles are read locally, OCR observations are grouped into time-based sightings, and common OCR confusions are shown as possible matches without being relabelled as exact reads. A guarded second pass can recover weak reads from mirrored camera footage; the transformation is retained in the evidence record. A supported plate result also requires the plate to be associated with a detected vehicle.

When no plate is known, a second dense path detects cars, trucks, buses, and motorcycles, groups repeated observations, and filters by mask-derived colour and coarse vehicle category. It does not use the plate filename, requested profile, or another answer key as detector input.

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

## Current stage

Milestones A and B are development-complete for the current prototype, not production-certified. Existing plate-box localization measured 97.55% precision, 91.71% recall, and 94.54% F1. The frozen 451-image exact complete-plate OCR benchmark measured 91.13% (411/451); the high-confidence accepted subset measured 98.55% (340/345) at 76.50% coverage. Multi-frame performance still requires a labelled dealership-video benchmark.

Milestone C is active. VMMRdb tooling is included for research and plumbing validation, but the source images require a separate commercial-rights review before production use. Live camera/RTSP ingestion remains a Milestone D task.

Set `AIEYE_PLATE_SCAN_FPS` to override the plate cadence (0.1–15 FPS). Set `AIEYE_PLATE_REVIEW_SIMILARITY` to tune which non-exact OCR strings enter the review queue; the default is `0.78`. `AIEYE_PLATE_MIRROR_FALLBACK` enables the guarded mirrored-camera pass, and `AIEYE_PLATE_MIRROR_THRESHOLD` controls when it runs (default `0.72`). These settings affect recall, runtime, and the number of false review candidates. They do not change the definition of an exact match.

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

Shared generic detector, evidence, and clip utilities remain in the backend as compatibility internals. They are not part of the LotTrace interface and should be extracted before the remaining legacy runtime is removed.

Vehicle presence, a coarse detector category, and mask-derived colour are machine observations. Make/model/year candidates appear only when a local vehicle-attribute model is configured and remain reviewable. Automatic damage comparison is a separate workflow with its own validation requirements.

## Repository map

| Path | Purpose |
| --- | --- |
| `backend/app/services/vehicle_*` | Vehicle scanning, attributes, sightings, records, and events |
| `backend/app/services/plate_*` | OCR evidence, ranking, and multi-frame consensus |
| `frontend/src/workspace` | Dealership ledgers and review screens |
| `frontend/src/components` | Recording analysis components |
| `scripts` | Evaluation, dataset-audit, and training commands |
| `evaluation` | Measured outputs and benchmark manifests, never runtime data |
| `docs` | Current architecture, milestone, licensing, and evaluation reports |
| `datasets`, `runs`, `videos` | Ignored local data and generated artifacts |

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
