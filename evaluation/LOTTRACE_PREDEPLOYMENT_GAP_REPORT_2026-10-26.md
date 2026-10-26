# LotTrace pre-deployment gap report — 2026-10-26

This is a live engineering gap report, not a production certificate.

## D1 — live ingestion

Implemented locally: RTSP configuration, Windows DPAPI credential protection,
WS-Discovery device discovery, independent camera workers, start/pause/resume/stop,
capped exponential reconnect with jitter, stalled/corrupt-frame handling, bounded
processing and evidence queues, explicit drop/failure metrics, capture/inference
rate separation, source and receipt timestamps, rolling evidence segments,
retention, graceful shutdown, and an operator status/configuration screen.

Verified with deterministic simulated capture tests. Physical ONVIF profile SOAP
negotiation, camera-specific codec behavior, firewall behavior, source timestamp
quality, and long-duration evidence integrity still require clean-machine and
dealership-camera tests. ONVIF discovery returns device service endpoints; profile
selection currently relies on operator-provided profile/RTSP values.

## D2 — automatic events

Implemented locally: completed recorded-video vehicle tracks are normalized to
camera coordinates and submitted to each configured boundary. The existing
immutable transaction performs directed finite-line crossing checks, multi-frame
plate consensus, unique vehicle matching, safe inventory transitions, audit
records, retry idempotency, and review routing. A three-second same-source,
same-boundary, same-plate guard suppresses duplicate fragmented tracks without
merging unrelated observations. Missing camera mappings or absolute recording
times fail closed.

Verified with focused automatic-event, event persistence, and vehicle-scan tests.
The live-camera worker still needs the production detector/tracker callback wired
and measured against real camera streams; this remains a release blocker rather
than being represented as complete field validation.

## Remaining milestones

## D3 — offline model bundle

Implemented locally: a machine-readable asset inventory, exact checksums, installed
paths, loaders, benchmark references, offline environment enforcement, and a
fail-closed commercial packaging gate. The build specification includes only
assets explicitly marked both packageable and redistribution-approved. The
research make/model checkpoint is excluded and the feature remains operator
supplied.

The commercial bundle gate intentionally fails today. Ultralytics YOLO requires
AGPL compliance or an Enterprise licence for the intended proprietary commercial
distribution, while exact model-weight redistribution terms for the FastALPR
detector/OCR assets have not been established in repository evidence. No model
was relabelled or silently bundled to make the gate green. Offline installed-app
inference is therefore blocked pending replacement assets or documented rights.

- D4: add certified backup/restore, upgrade rollback, crash recovery and diagnostics.
- D5: rebuild and smoke-test the installer; configure but do not claim Authenticode
  signing without the production certificate.

## Certification gates

The held-out dealership-video event benchmark, physical cameras/network, clean
Windows VM, code-signing certificate, and commercially redistributable make/model
asset remain unavailable or incomplete. LotTrace remains a development prototype.
