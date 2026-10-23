# LotTrace multi-frame OCR and vehicle-intelligence progress — 2026-10-22

## Outcome

The software path for adaptive multi-frame plate consensus is implemented and connected to immutable crossing events. Milestone C now has provider-neutral, multi-frame vehicle make/model/year candidate handling plus a local TorchScript inference and training path. Neither change creates a new production accuracy claim.

## Multi-frame OCR implementation

- Frame count is adaptive, not fixed at 30.
- Short tracks retain all available independent observations.
- Longer tracks select up to ten clear, temporally diverse plate observations.
- Duplicate detections and enhancement variants from one source frame contribute only one temporal vote.
- Selection uses crop quality, OCR confidence and temporal diversity. It does not use an operator-supplied expected plate string.
- Exact automatic consensus still requires the same complete string on at least two independent frames with sufficient OCR support.
- Conflicting, near-match and weak evidence remains review-only.
- Crossing events can derive their plate, consensus state, best crop and review decision from raw frame observations.
- Original per-frame OCR candidates remain stored; the selected subset is marked separately.

This establishes functional behavior. Event-level exact plate accuracy remains unmeasured until a labelled multi-frame dealership-video benchmark is available.

## Vehicle-intelligence implementation

- Fine-grained outputs are ranked candidates rather than silently confirmed values.
- The same make/model must have independent multi-frame support.
- Year is represented as a range.
- Missing evidence produces `unknown`.
- Close competing candidates produce `conflicting` and require review.
- Candidate consensus is persisted separately from confirmed vehicle fields.
- A local PyTorch Export adapter validates label count, model/manifest hashes and provenance.
- Runtime model softmax is explicitly labelled model confidence, not measured accuracy.

## VMMRdb archive audit

Archive: `datasets/incoming/archives/VMMRdb.zip`

- Bytes: 12,354,779,003
- SHA-256: `162bcd8a3ba61d52b9529cba96bfa6ed031d8375c3306340d0fdc1e0c638014a`
- Images: 285,086
- Original folders: 9,169
- Parsed makes: 75
- Year labels: 1900–2017
- Minimum/maximum images per folder: 1 / 883
- Folders with fewer than two images: 1,187
- Folders with fewer than five images: 3,032

The local archive differs from the publisher's stated 291,752 images and 9,170 classes. The publisher reports that images were collected from vehicle-sale pages. Although the repository includes MIT text, ownership and commercial reuse permission for the underlying third-party images is not clearly established. Models trained from this archive must remain research-only until image rights are documented.

The labels also lack vehicle identity, site, camera and capture date. Therefore, this archive cannot supply a leakage-safe final dealership benchmark.

## Development manifest and smoke test

The non-extracted development manifest groups year folders into 695 make/model groups:

- Train: 239,662 images
- Development: 41,957 images
- Total: 281,619 images
- Final test: intentionally absent

A two-class, 120-image, one-epoch CPU smoke run verified ZIP reading, training, PyTorch export and runtime compatibility. It scored 13/34 top-1 (38.24%). This is not a useful model result and must not be presented as vehicle-recognition accuracy.

## Remaining Milestone C work

1. Confirm commercially usable training rights or replace VMMRdb with cleared current inventory imagery.
2. Add recent vehicles beyond 2017.
3. Train on a GPU and tune only against a development split.
4. Freeze a separate dealership-style final benchmark grouped by vehicle, camera, site and date.
5. Measure make/model top-1 and top-k accuracy, year-range accuracy, colour accuracy and macro-F1.
6. Calibrate candidate/review thresholds and measure review workload.
7. Integrate a trained body-type model; current COCO labels remain coarse categories only.

Live RTSP ingestion remains deferred to Milestone D as directed.
