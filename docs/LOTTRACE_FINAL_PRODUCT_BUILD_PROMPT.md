# LotTrace final-product implementation brief

Use this brief to finish LotTrace as a production dealership operations system. Extend the existing React, FastAPI, SQLite, OpenCV, FastALPR, and Ultralytics codebase. Preserve working backend behavior and migrations. Do not replace functional code with static demonstrations.

## Product outcome

Build a local-first, multi-camera vehicle evidence platform for dealerships. Staff must be able to answer:

1. Which vehicles entered or left, and when?
2. Where and when was a particular vehicle seen?
3. What source footage supports a sighting?
4. Did the recorded condition appear to change between arrival and departure?
5. What evidence, corrections, notes, and approvals belong to an incident?

The system supports investigation. It must never claim driver identity, responsibility, damage causation, theft, or fraud without human review and external evidence.

## Current baseline that must remain truthful

- Recorded-video upload and asynchronous processing exist.
- Plate-first and vehicle-description searches exist.
- Plate readings, vehicle observations, clips, frames, feedback, and a cross-recording sighting ledger exist.
- A sample workspace demonstrates history and condition review, but its vehicles, images, users, damage record, and incident are fictional and are not connected to the production database.
- Current plate-box benchmark on the 1,020-image License Plate Recognition v13 test set: precision 97.55%, recall 91.71%, and F1 94.54% at IoU 0.50.
- That dataset has no plate transcription labels. The existing 96% plausible-reading rate is OCR coverage, not text accuracy.
- A five-clip daylight parking benchmark reproduced exact target-plate retrieval in 5/5 clips and exact text in 90/95 sampled frames where any plate was read (94.7%). It is a small smoke test, not a deployment accuracy claim.
- Current vehicle association coverage is 160 of 978 plate readings on this plate-focused dataset. This is not vehicle-detection accuracy because the dataset has no vehicle boxes and often crops out the car.
- Make, model, and year entered in the search form are requested metadata, not machine-verified observations.
- Automatic damage detection, fraud detection, live-camera ingestion, production authentication, and a real incident database are not complete.

Never turn these limitations into marketing claims or invented percentages.

## Required product workflows

### 1. Recordings and cameras

- Upload MP4, MOV, and MKV files with visible validation, progress, cancellation, and retry.
- Generate a browser-compatible H.264/AAC proxy when the source codec cannot play in the browser. Preserve the original file for analysis and evidence.
- Provide reliable play, pause, seek, frame-step, playback speed, volume, fullscreen, and jump-to-sighting controls.
- Never move the page scroll position during polling or activity-log updates.
- Record camera name, camera role, location, timezone, recording start time, and business hours.
- Add a camera registry and health page before live ingestion. A later milestone may add RTSP streams with encrypted credentials, reconnect/backoff, bounded queues, and rolling pre/post-event buffers.

### 2. Vehicle search

- Plate search must support exact, partial, uncertain, and corrected readings.
- Vehicle-only search must be equally visible and support colour, coarse vehicle category, make, model, year, camera, direction, and date/time.
- Clearly distinguish requested attributes, observed attributes, model-derived attributes, and human-corrected values.
- Do not claim make/model/year detection until a separately evaluated model provides it.
- Results must show a source frame, plate crop when available, timestamp, camera, movement event, review state, and a link to playable source footage.
- Provide explicit loading, empty, backend-offline, unsupported-codec, corrupt-file, and processing-failed states.

### 3. Sighting review

- Review the source video and frame together.
- Show vehicle and plate boxes only when they come from stored model output.
- Allow confirm, reject, reopen, correct plate, link/unlink a vehicle, add a note, and jump between nearby sightings.
- Store original model output separately from human corrections.
- Record actor, timestamp, previous value, new value, reason, model versions, and source identifiers in an append-only audit log.
- Never display a raw model confidence as accuracy. If confidence is shown, label it model confidence and pair it with measured calibration documentation.

### 4. Vehicle records and history

- Add a real vehicle table, not fixture data. Minimum fields: internal ID, normalized plate, plate aliases/history, VIN when authorized, stock number, make, model, year, colour, body type, status, and notes.
- Link sightings to vehicles through reviewed associations.
- Build a chronological timeline of entries, exits, other sightings, inspections, corrections, notes, incidents, preserved clips, and approvals.
- Derive on-site status only from reviewed entry/exit events and show uncertainty when camera coverage is incomplete.
- Support duplicate-vehicle merging and plate changes without destroying evidence history.

### 5. Condition capture and damage review

- Replace the current fictional condition screen with database-backed inspections.
- Define guided arrival and departure capture sets: front, rear, left, right, four corners, wheels, windscreen, roof when available, and close-ups.
- Record camera/device, operator, timestamp, vehicle, viewpoint, file hash, and source file for every image.
- Align paired viewpoints and provide side-by-side, overlay, zoom, and synchronized pan.
- Staff must be able to mark a region, choose damage type and severity, add notes, attach media, and mark pre-existing, new/possible, unchanged, repaired, or inconclusive.
- Automatic comparison may propose a changed region only after training and evaluation on dealership-specific paired images. It must use “possible change” and “requires review.”
- Evaluate damage localization and classification separately by panel, damage type, lighting, weather, viewpoint error, dirt/reflections, and severity. Include false-change rate because false accusations are costly.
- Preserve both originals and all derived annotations. Never overwrite source media.

### 6. Incidents and suspected fraud indicators

- Create real incident records with status, priority, vehicles, people/users, sightings, inspections, notes, attachments, preserved clips, and a chronological evidence timeline.
- Permit authorized staff to place an evidence hold that overrides routine retention.
- Support manager approval, reopening, export, and immutable audit events.
- Fraud-related functionality must only organize indicators such as conflicting timestamps, duplicate claims, inconsistent condition records, or repeated plate/vehicle mismatches.
- Use labels such as “inconsistency,” “possible duplicate,” and “requires review.” Never label a person or claim fraudulent, score criminality, infer protected traits, or automatically deny a claim.

### 7. Roles, security, and data governance

- Add real authentication and dealership tenancy.
- Roles: viewer, reviewer, manager, administrator, and auditor, with server-enforced permissions.
- Encrypt secrets and camera credentials, use TLS outside localhost, protect uploads, validate all paths and MIME/content, and rate-limit sensitive endpoints.
- Add configurable retention for source video, clips, crops, sightings, inspections, incidents, and audit records.
- Add evidence holds, export manifests, cryptographic hashes, backup/restore, database migrations, and deletion workflows.
- Do not rely on browser local storage for production records or authorization.

## Accuracy and evaluation requirements

### Licence-plate detection

- Maintain a versioned test split with plate bounding boxes.
- Report precision, recall, F1, average precision, localization IoU, misses per 1,000 plates, false positives per hour of video, and latency by camera condition.
- Break down results by day/night, glare, rain, blur, distance, angle, plate size, occlusion, front/rear, and regional plate style.
- Pin dataset version, model version/hash, thresholds, hardware, and evaluation code revision.

### OCR

- Obtain or create a legally usable transcription-labelled dataset.
- Report exact plate accuracy, character error rate, normalized edit distance, top-k accuracy, and error confusion pairs.
- Evaluate exact and partial search independently.
- Prevent train/test leakage by separating cameras, sites, vehicles, and recording dates.

### Vehicle detection and attributes

- Use a vehicle-labelled dataset containing full frames and dealership camera geometry.
- Report vehicle AP/precision/recall, track continuity, duplicate-track rate, plate-to-vehicle association precision/recall, and false sightings per hour.
- Evaluate colour accuracy separately. Do not score make/model/year until labels and a suitable model exist.
- Break down by category, size, occlusion, lighting, camera, angle, weather, and stationary versus moving vehicles.

### End-to-end evaluation

- Test complete recorded videos, not only cropped images.
- Measure event recall, timestamp error, entry/exit accuracy, search precision, review workload, processing speed, peak memory, and CPU/GPU behavior.
- Include negative videos with no target vehicle.
- Every metric must include its denominator and confidence interval where practical.
- Regression tests using mocks prove software behavior only; never present them as model accuracy.

## UX requirements

- Open directly into the operational workspace.
- Keep “Your recordings” and fictional “Sample records” visibly separated.
- Use readable 15–16 px body text, high-contrast labels, distinct field borders, clear disabled states, and keyboard-visible focus.
- Keep vehicle-only lookup visible without requiring users to discover a collapsed control.
- No decorative metrics, invented dealership statistics, fake live-camera states, fake confidence values, or dead-end controls.
- Desktop first, then tablet; meet WCAG 2.2 AA for contrast, keyboard use, dialogs, errors, and form labels.

## Engineering requirements

- Keep React components typed and route state deterministic.
- Use FastAPI schemas and service boundaries; do not let UI fixture types become database contracts.
- Add schema migrations and foreign keys for users, dealerships, cameras, vehicles, sightings, inspections, condition annotations, incidents, evidence links, approvals, audit events, and retention holds.
- Keep long processing in a durable worker with idempotent jobs, cancellation, retries, recovery after restart, and bounded resource use.
- Add structured logs, health checks, job metrics, model manifests, and user-visible failure IDs.
- Generate browser proxies and thumbnails asynchronously while keeping original media immutable.
- Add API, database, service, and browser end-to-end tests for every critical workflow.

## Required end-to-end tests

1. Upload a browser-compatible video, preview it, play/pause/seek, and start analysis without a page-scroll jump.
2. Upload a valid but browser-incompatible MOV/MKV, create a proxy, and play it while preserving the original.
3. Search a full plate, partial plate, uncertain plate, and vehicle attributes without a plate.
4. Confirm, correct, reject, reopen, and link a sighting; verify the audit log and original values remain intact.
5. Search saved sightings after restarting the application.
6. Create arrival and departure inspections, compare matching viewpoints, mark a possible condition change, and complete manager review.
7. Create an incident, attach sightings and inspections, preserve footage, approve it, reopen it, and export a hashed evidence manifest.
8. Verify staff cannot perform manager/admin actions through either the UI or direct API calls.
9. Verify retention deletes eligible data but never data under an evidence hold.
10. Verify offline/backend failure, corrupt media, missing model, full disk, interrupted processing, and application restart recovery.

## Delivery sequence

1. Stabilize upload, proxy playback, scrolling, real vehicle search, saved sightings, and review actions.
2. Build real vehicle records, audit log, roles, and unified history.
3. Build inspections, condition comparison, incidents, evidence holds, and exports.
4. Add camera registry and live ingestion.
5. Train/evaluate automatic damage comparison only after the manual workflow and labelled dataset exist.
6. Complete security hardening, retention, backup/restore, accessibility, load testing, and pilot deployment.

## Definition of done

LotTrace is not final until all visible controls work against real APIs; source video plays through a compatible proxy; records persist across restart; roles are server-enforced; evidence is traceable and exportable; plate, OCR, vehicle, and damage claims have reproducible labelled evaluations; failures are recoverable; and the sample workspace cannot be mistaken for production data.
