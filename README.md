# AI(EYE) in the sky

Local post-flight natural-language video search and evidence review with optional DJI SRT telemetry.

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
The segmentation model is already installed in this workspace. The installer also fetches
the pinned SigLIP retrieval and OWLv2 grounding safetensors. Runtime does not download models
or switch providers. Missing weights or inference failures stop the job explicitly.

## Matching behavior

Queries whose primary entity is a supported generic class (the first vertical slice is a
color-qualified car) use semantic frame/clip retrieval followed by YOLO segmentation,
masked color evidence, track deduplication, and ranked clips. Required attributes are gates:
a high-confidence car with conflicting color evidence remains an unlikely match. Generic
results include annotated frames, playable clips, component evidence, model provenance,
and correct/incorrect feedback controls. `AIEYE_MAX_RESULT_TRACKS` bounds generated result
clips (default 10), and `AIEYE_RESULT_CLIP_WIDTH` bounds clip width (default 1280).

Interaction queries such as `a person pushing a stroller` also use the generic path. The
application combines YOLO person masks with OWLv2 phrase boxes, tracks both entities, and
requires repeated person-stroller contact plus coordinated multi-frame motion before calling
the action supported. Mere co-visibility or proximity remains uncertain or conflicting.
`AIEYE_MAX_EVENT_COMBINATIONS` bounds combinatorial event verification (default 500).

All searches now enter through one worker and publish the same structured query/result
contract. Person/clothing searches retain the established appearance verifier as an optional
specialist provider, while generic entities and interactions use the open-vocabulary path.
Legacy track, feedback, and report routes remain available during compatibility migration.

Structured generic queries support quantities, negative entities, per-entity colors,
spatial relationships, running, pushing, and carrying. Interaction claims require repeated
localized evidence; unsupported visible attributes remain explicitly uncertain instead of
being inferred from semantic similarity.

Choose `fast`, `balanced`, or `thorough` in the search form. These modes use progressively
denser reusable indexes and larger bounded retrieval, localization, batching, and result
budgets. Completed searches expose per-stage timings and device provenance; the result view
supports classification, entity, score, and time filters plus annotated frames, clip playback,
feedback, and evidence-report export.

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

The open-vocabulary index uses a revision-pinned local SigLIP model for frame and aggregated
clip embeddings. `python backend/download_models.py` installs its safetensor weights
explicitly; runtime inference is offline-only and never downloads a model. Configure
`AIEYE_EMBEDDING_BATCH_SIZE` to bound embedding memory (default 2 on CPU and 8 on CUDA).

Entities outside YOLO's fixed taxonomy use revision-pinned OWLv2 phrase grounding. Its
Apache-2.0 620 MB safetensor is stored under ignored `backend/models/owlv2`, hash-checked,
and loaded only when a query needs grounding. `AIEYE_GROUNDING_BATCH_SIZE` defaults to 2;
`AIEYE_GROUNDING_MODEL_PATH` can select another compatible, locally installed snapshot.

## Verify

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s tests -v
cd frontend
npm.cmd run build
```

Completed searches can be measured against operator labels with
`scripts/evaluate_labeled_search.py`; copy `evaluation/manifest.example.json` and supply the
search session ID, event intervals, required labels, condition tags, and optional boxes. Reports
retain explicit counts and return unavailable metrics as `null` rather than inventing accuracy.
See `docs/PHASE10_EVALUATION_HARDENING.md` for the measured example and limitations.

`test_e2e.py` is an optional HTTP smoke test against a running backend and generated demo
video. Synthetic drawings are not a detector accuracy benchmark. Before operational use,
label representative real recordings (including tires, stationary people, occlusions,
and empty scenes) and measure missed people and false candidate alerts per video hour.
No measured precision/recall claim is made by this implementation.
