# LotTrace Milestone D production-readiness report

Generated: 2026-10-26T04:40:23.160158+00:00

**Decision: NOT READY FOR PRODUCTION.**

Functional software tests and healthy runtime checks do not prove model accuracy. Certification remains false until every declared dealership-video gate is measured and passed.

## Functional verification run

- Backend: 275 tests passed
- Frontend unit: 20 tests passed
- Browser end-to-end: 9 tests passed
- Production frontend build: passed

These prove tested software behavior only; they do not change the recognition accuracy gates.

## Capability audit

| Capability | Status |
| --- | --- |
| Recorded Video Analysis | Implemented |
| Durable Job Queue And Restart Recovery | Implemented |
| Multi Frame Ocr Consensus | Implemented |
| Vehicle Make Model Recognition | Implemented |
| Immutable Events And Status Transitions | Implemented |
| Authentication Roles Audit Retention Exports | Implemented |
| Desktop Application Shell | Implemented |
| Installable Windows Build | Implemented |
| Automatic Worker To Crossing Event Wiring | Missing / uncertified |
| Live Camera Ingestion | Missing / uncertified |
| Backup Restore Certified | Missing / uncertified |
| Deployment Security Certified | Missing / uncertified |
| Signed Self Contained Windows Installer | Missing / uncertified |

## Release gates

| Gate | Target | Measured | Status | Note |
| --- | ---: | ---: | --- | --- |
| Eligible vehicle crossing event recall | >=99% | Not measured | unmeasured | Requires held-out dealership video with labelled crossings. |
| Plate localization recall on eligible events | >=99% | Not measured | unmeasured | Still-image plate-box recall is 91.71%; it is not an event-level video result. |
| OCR character accuracy | >=99% | 97.79% | below_target | Measured on 451 held-out cropped plates, not dealership-video events. |
| Exact full-plate event accuracy | >=99% | Not measured | unmeasured | Single-crop exact accuracy is 91.13%; multi-frame event accuracy is unmeasured. |
| Plate-to-vehicle association precision | >=99% | Not measured | unmeasured | No labelled dealership-video association benchmark exists. |
| Plate-to-vehicle association recall | >=98% | Not measured | unmeasured | No labelled dealership-video association benchmark exists. |
| False exact assignments / false sightings per hour | reported | Not measured | unmeasured | Requires negative and positive dealership footage with labelled duration. |
| Make + model top-1 | >=95% development objective | 92.10% | below_target | Closed-set research still-image result; dealership-video and unknown-vehicle performance remain unmeasured. |
| General vehicle detector recall | >=99% eligible crossings | 65.90% | not_comparable_below_target | COCO still-image recall is not the declared eligible dealership-crossing metric. |

## Required before certification

1. Wire recording/live tracked observations into configured boundaries and event creation.
2. Add and harden live camera ingestion with encrypted credentials, reconnect/backoff, bounded queues, and rolling evidence.
3. Certify backup/restore, TLS deployment, rate limiting, resource limits, and failure recovery.
4. Stage only redistributable model assets, validate the generated installer on a clean Windows VM, and code-sign it.
5. Freeze and run a held-out dealership-video benchmark separated by site, camera, vehicle, and date.
6. Pass every declared event, plate, association, false-positive, and resource-use gate.

## Evidence integrity

- `evaluation/license_plate_recognition_v13_detection_results.json` — SHA-256 `34b7dac7119a478398dd80940ccc0e9c7ef845970c4e9f4aa017680701ae8a94`
- `evaluation/LOTTRACE_OPENALPR_300_OCR_2026-10-22.json` — SHA-256 `9fefffade20b6a76f51e30e8f8f59d608fa8c24f9744b641ba42e9d46387cd46`
- `evaluation/LOTTRACE_MAKE_MODEL_TEST_2026-10-24.json` — SHA-256 `de86802d7483c22ea4e5dbc3838840795be5781c5f66e8a8d1960e0818a5f414`
- `evaluation/coco_vehicle_results.json` — SHA-256 `b7a502f58f0f50d6109f0830404667d32feb35589bf0c70e6023484a33a8fe40`
