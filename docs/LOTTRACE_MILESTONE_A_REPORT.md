# LotTrace Milestone A report

Date: 2026-10-21

## Verified starting gap table

This audit is based on the database schema, API and service code, automated tests, and the labelled evaluation report. A software test is not a model-accuracy measurement.

| Feature | Actually works | Partly works | Missing |
|---|---|---|---|
| Video upload and browser playback | MP4/MOV/MKV validation, preserved upload, proxy job, playback controls, cancellation and recovery tests | Proxy generation depends on local FFmpeg and browser tests use controlled fixtures | Deployment codec/hardware matrix |
| Exact and partial plate search | Stored-sighting filtering and dense recording search | Accuracy is supported only by limited or masked-label evaluations | Held-out exact full-plate dealership-video benchmark |
| Plate OCR and localization | Plate model pipeline and reproducible localization evaluations | Plate-box P/R/F1 is 97.55/91.71/94.54% on the 1,020-image set; UC3M masked-position OCR is about 82.69% | Verified full-plate accuracy and 99% release gates |
| Coarse vehicle detection | COCO car/truck/bus/motorcycle detector and stored observations | Current P/R/F1 at confidence .25 is 69.24/65.90/67.53%; association coverage was 16.36% | Dealership-video event benchmark |
| Colour detection | Heuristic observation is stored and labelled as model-derived | No trained, dealership-evaluated attribute model | Production colour model and benchmark |
| Make/model/year recognition | Known database records can provide confirmed attributes | Search-request metadata remains separate from observations | Evaluated visual recognition and year ranges |
| Cross-recording sightings | Persistent ledger, filters, source evidence and restart tests | Existing records are sightings, not necessarily gate crossings | Broader production-video validation |
| Correction and human review | Confirm/reject/reopen/correct/note APIs with append-only revisions | Event-specific correction workflow is not in Milestone A | Unified event review UI |
| Vehicle records and history | Tenant-scoped vehicles, aliases, sighting links, events, transitions and audit history | Legacy `active` inventory states require review before automatic transition | Duplicate-record merge workflow |
| Tracked entrance/departure events | Configured finite boundaries, directed crossing test, immutable event ledger, duplicate suppression and known-plate transitions | Track observations enter through the event-ingestion API; recording analysis is not yet wired to emit them automatically | Production tracker integration and operator boundary editor |
| Condition capture and damage comparison | Database-backed inspections and manual annotations | Manual comparison exists | Evaluated automatic comparison (intentionally absent) |
| Incidents and evidence holds | Persistent incidents, attachments, holds, approvals and hashed exports | Operational hardening remains | Pilot validation |
| Authentication, roles, audit, retention and exports | Server-enforced local accounts and roles, audit records, retention policy, held evidence and exports | Local-first security baseline | Deployment TLS/secrets/rate limiting and backup/restore certification |
| Live cameras | Camera registry | No ingestion or health monitoring | RTSP ingestion, bounded queues and encrypted credentials |

## Milestone A delivered

- Camera boundaries use normalized finite line segments, entrance/exit semantics, one permitted direction, and measurable minimum size/visibility eligibility.
- Crossing evaluation consumes ordered observations from one track. A reverse crossing, a crossing outside the finite segment, or an ineligible vehicle creates no event.
- Arrival/departure events retain camera, boundary, timezone, track, recording and crop references, original per-frame OCR candidates, evidence, and model manifests.
- Database triggers reject updates and deletes of events, raw event observations, and status transitions.
- A deterministic key based on dealership, camera, boundary, recording/session, track, and event type makes retries idempotent.
- A unique exact-consensus or reviewed plate may match a current vehicle or plate alias. Automatic status changes require a non-conflicting prior `on_lot`/`off_lot` state.
- Uncertain OCR, ambiguous plate matches, unknown inventory state, repeated arrival/departure state, and unmatched plates remain `requires_review` and do not change inventory.
- The authenticated API exposes boundary configuration, crossing ingestion, the event ledger, and event evidence. The local workspace now has an Arrival / departure ledger.

## Verification

- Focused Milestone A backend/API tests: 6 passed.
- Full backend regression suite: 172 passed.
- Frontend unit/render tests: 16 passed.
- TypeScript type-check: passed.
- Vite production build: passed when written to a fresh temporary output directory. The repository's existing `frontend/dist` directory could not be cleaned in this managed workspace because Windows returned `EPERM`; no product code failure was involved.

## Truthful limitation

Milestone A supplies the event foundation, not production certification. The current recording-analysis worker does not yet feed vehicle tracks into the boundary-event ingestion service, and there is no labelled dealership-video gate-crossing benchmark. The declared 99% release targets remain unmeasured and must not be claimed.
