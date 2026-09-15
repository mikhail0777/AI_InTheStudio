# Pipeline continuation and validation

## Handoff audit

The workspace contained 23 modified tracked files plus a worker, frontend review helpers,
and report/telemetry tests, substantially more than the three files listed in the handoff.
Existing YOLO segmentation, tracking, queue, telemetry, report, and UI work was preserved.

The unfinished path consisted of missing visual_features.py and download_models.py,
an obsolete rectangle-based appearance analyzer, and a worker call passing an unsupported
detector argument. The missing files were restored from the supplied handoff. Appearance
analysis now consumes object-mask evidence and optionally refines selected crops with the
same model. Refinement requires overlap with the original person's mask.

Additional fixes connect attribute assessments, crop timestamps, and internal per-frame
observations; honor the alert threshold for every promoted category; keep insufficient
person evidence out of the default queue; handle simple negated descriptions conservatively;
and correct missing-altitude persistence and SQLite connection lifetime. Requirements and
run instructions are included. No existing flight was reprocessed in place.

## Validation

- 38 Python regression/integration tests pass: detector empty/failure behavior, mask-based
  shirt/backpack separation, stationary tracks, temporal spacing, conflicts, thresholds,
  description extraction, provenance, queued processing, cancellation, feedback/report
  regeneration, telemetry alignment, and legacy database migration.
- TypeScript and Vite production build pass.
- `git diff --check` passes.
- Installed yolo11s-seg.pt SHA256:
  `1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3`.
- Full real-video smoke test: DJI_0179.MP4, 39.11 seconds, 3840 x 2160,
  217 sampled frames, 1,118 person observations, 49 tracks. At an internal alert threshold
  of 0.65: two possible candidates, 12 low-similarity tracks, 35 limited-evidence tracks.
  Both candidate crops visibly show the green top and black backpack. Their selected
  timestamps are approximately 9.643 and 16.283 seconds.
- Three historical tire crops (old track IDs 27, 41, 47) were located in their exact source
  frames 419, 429, 599 using image-template correlation above 0.9998. No new person bounding
  box overlapped any of these three crop rectangles.
- Test artifacts and an HTML evidence report are under
  `backend/data/validation/full-run/`; this uses a separate database from saved flights.

## Remaining product validation

These checks establish the specific regression improvements, not measured field accuracy.
Garment bands remain approximate; shadows, occlusions, unusual poses, and missed bag masks
can still affect colors. Separated timestamps are not proof of independent viewpoints.
The target person generated two review cards after track fragmentation. Cross-gap identity
merging is intentionally not guessed. A labeled set of additional flights is still needed
to calibrate thresholds, quantify missed people/false alerts, and evaluate tracking changes.
Arbitrary required/negative constraints are shown as unevaluated and prevent automatic
promotion; hair, gender, identity, and clothing styles remain unevaluated.
