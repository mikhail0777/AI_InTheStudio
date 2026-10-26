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

## Remaining milestones

- D2: connect live/recorded tracking output automatically to boundary events.
- D3: finish legal redistribution inventory and checksum-enforced offline bundle.
- D4: add certified backup/restore, upgrade rollback, crash recovery and diagnostics.
- D5: rebuild and smoke-test the installer; configure but do not claim Authenticode
  signing without the production certificate.

## Certification gates

The held-out dealership-video event benchmark, physical cameras/network, clean
Windows VM, code-signing certificate, and commercially redistributable make/model
asset remain unavailable or incomplete. LotTrace remains a development prototype.
