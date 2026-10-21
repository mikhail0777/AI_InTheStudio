# LotTrace controlled-rebuild master prompt

You are taking over an existing local repository for LotTrace, a dealership vehicle-evidence platform. Treat this as a controlled product rebuild, not a greenfield rewrite and not a visual reskin.

Read `docs/LOTTRACE_FINAL_PRODUCT_BUILD_PROMPT.md` first. It is the product specification and definition of done.

## Non-negotiable working rules

- Do not commit, stage, push, publish, or delete existing work until I explicitly approve it.
- Inspect the repository, tests, database schema, API contracts, model code, evaluation artifacts, and current uncommitted changes before editing.
- Preserve the working FastAPI upload, durable queue, plate recognition, evidence, feedback, and sighting-ledger code unless a failing test proves a replacement is needed.
- Do not preserve a UI merely because it exists. Rebuild screens when their information architecture is wrong.
- Build operational software, not a marketing site or a static demonstration.
- Never use fictional records, generated images, hard-coded metrics, or raw model confidence as if they were production facts.
- Keep sample data isolated behind an explicit Sample Records mode.
- Every visible control must work against a real API or be omitted.
- Use “possible match,” “possible change,” and “requires review.” Never determine identity, liability, damage causation, theft, or fraud.
- After every bounded milestone, run relevant tests and show me the working result before expanding scope.

## First task: audit before changing code

Produce a short truth table with four columns: feature, actually works, partly works, missing. Verify it from code and tests, not README claims. Include:

- video upload and browser playback;
- exact and partial plate search;
- plate OCR and plate localization;
- coarse vehicle detection;
- colour detection;
- make/model/year recognition;
- cross-recording sightings;
- correction and human review;
- vehicle records and history;
- arrival/departure condition capture;
- damage comparison;
- incidents and evidence holds;
- authentication, roles, audit, retention, exports, and live cameras.

Explicitly acknowledge the current measured baseline:

- Full 1,020-image held-out plate-box test at IoU 0.50: precision 97.55%, recall 91.71%, F1 94.54%.
- That dataset has no plate text labels, so it cannot measure OCR character accuracy.
- The current COCO vehicle model detects only car, truck, bus, and motorcycle. It does not recognize make, model, or year.
- On the plate-focused dataset, the production-path evaluation associated only 160 of 978 plate readings with a detected vehicle (16.36%). This is coverage, not accuracy. A separate October 20, 2026 slideshow diagnostic found a vehicle in only 8 of 60 sampled frames.
- Damage and incident screens are currently demonstrations, not production workflows.

## Delivery strategy

Do not attempt the entire product in one uncontrolled pass. Deliver these vertical slices in order.

### Milestone 1: reliable investigation

- Fix upload and browser-compatible playback, including H.264 proxy generation for incompatible sources.
- Guarantee polling and activity logs never move the document scroll position.
- Make plate and vehicle-only search equally obvious.
- For vehicle search, expose only attributes the backend truly evaluates. Mark make/model/year unavailable until implemented.
- Connect results, playable footage, frame crops, correction, rejection, reopening, linking, notes, and saved sightings to real APIs.
- Add browser end-to-end tests for upload, play/pause/seek, scroll stability, exact plate, partial plate, vehicle-only search, review, and restart persistence.

Stop and show the milestone before continuing.

### Milestone 2: real records and governance

- Add real dealership, user, role, camera, vehicle, plate-alias, audit-event, and retention schemas with migrations.
- Implement server-enforced viewer, reviewer, manager, administrator, and auditor permissions.
- Replace sample history with a database-backed vehicle timeline.
- Keep original model output immutable and store human corrections as audited revisions.

Stop and show the milestone before continuing.

### Milestone 3: condition and incidents

- Add guided arrival/departure inspections with standardized viewpoints and immutable originals.
- Add manual damage-region annotation, type, severity, notes, attachments, and human review states.
- Add database-backed incidents, evidence links, approvals, reopening, evidence holds, and hashed exports.
- Do not add automatic damage claims until a labelled paired-image dataset and evaluator exist.

Stop and show the milestone before continuing.

### Milestone 4: evaluated automation

- Create a transcription-labelled plate OCR benchmark and report exact accuracy and character error rate.
- Create a full-frame, vehicle-labelled dealership benchmark and report AP, precision, recall, tracking, association, and false sightings per hour.
- Train or integrate make/model recognition only after defining labels and acceptance thresholds.
- Train/evaluate possible-damage localization only after the manual inspection workflow is stable.
- Add camera registry and live RTSP ingestion only after retention, security, health monitoring, and bounded queues exist.

## UI direction

Create a focused desktop operational tool with readable 15–16 px text, strong field boundaries, neutral surfaces, restrained slate/blue accents, evidence-first layouts, and clear empty/error/loading states. Avoid neon gradients, tiny grey type, decorative dashboards, fake statistics, promotional workflow sections, and excessive cards.

Primary navigation for the first milestone:

1. Analyse recording
2. Saved sightings
3. Vehicle records, only when backed by real data
4. Reviews, only when backed by real data

Do not add future pages to navigation before their backend workflows exist.

## Acceptance discipline

- Add reproducible scripts for every model benchmark.
- Separate regression tests, functional coverage, and labelled accuracy in all reports.
- Include denominators, dataset versions, model hashes, thresholds, hardware, and limitations.
- Run the full backend and frontend suites after each milestone.
- Do not call LotTrace production-ready until the definition of done in the final-product brief is met.
