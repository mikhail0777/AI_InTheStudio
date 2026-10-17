# LotTrace dealership MVP architecture

## Active product path

1. A recorded camera file and structured case metadata create a session.
2. `VehicleInvestigationManager` samples frames at the selected scan depth.
3. `LicensePlateReader` returns plate text, confidence, and bounding boxes.
4. Repeated observations are grouped into a sighting and saved with evidence.
5. `vehicle_sightings` is the cross-recording audit ledger used for vehicle history.
6. The printable report packages timestamps, camera context, annotated frames, clips, and review notes.

Camera roles create explicit event semantics (`entered_lot`, `left_lot`,
`entered_service`, or `left_service`). The system does not infer direction when
the operator has not configured the camera role.

Make, model, year, colour, and body type are currently operator-supplied case
metadata. They are deliberately not described as machine-verified evidence.

## Compatibility code

The generic object and earlier person-analysis services remain in the backend
for API compatibility and regression coverage. They are no longer exposed by
the dealership UI. Remove them only as a separate migration after stored legacy
sessions and their report contracts are no longer needed.

## Live-video extension point

The persistent sighting ledger is intentionally independent from file scanning.
An RTSP/on-premise camera worker can later write the same normalized sighting
records without changing history, review, or reporting.

The live milestone should add:

- a camera registry with encrypted RTSP credentials;
- a bounded frame queue with reconnect/backoff and health status;
- per-camera sampling policies and business-hours rules;
- idempotent event keys to prevent duplicate sightings;
- short rolling evidence buffers so each alert includes pre/post-event video;
- retention, role-based access, and audit logging before multi-user deployment.

Automatic damage comparison is a separate model and workflow. It needs paired
arrival/departure views, consistent camera angles, labelled damage data, and a
calibrated evaluation set before it can be presented as evidence.
