# LotTrace release-candidate report — 2026-10-26

## Decision

**Development prototype.** This build is not a dealership pilot candidate and is
not production-certified.

## Locally verified engineering

- D1 live RTSP ingestion foundation, DPAPI credentials, bounded queues, rolling
  evidence, reconnect/status controls, simulated failure tests and operator UI.
- D2 automatic recorded-track boundary submission, immutable events, idempotency,
  duplicate-fragment suppression, review routing and guarded inventory transitions.
- D3 machine-readable model provenance/checksums and fail-closed offline commercial
  packaging gate; research make/model excluded.
- D4 SQLite online backup, encrypted archive, staged restore, rollback copy,
  migration version, audit trail, rotating redacted logs and readiness diagnostics.
- Electron loopback-only lifecycle, renderer isolation/sandbox, blocked external
  navigation and permission requests, local authentication and roles.

## Test inventory

- Backend: 240 tests discovered. The final complete run exposed one newly introduced
  Windows log-handle cleanup error; it was fixed and its four-test module re-run
  passed. No model-accuracy conclusion follows from these software tests.
- Frontend unit/render/security: 20 passed.
- Frontend TypeScript build and production Vite build: passed to an isolated output
  directory because another local process held `frontend/dist` open.
- Browser/E2E: 9 passed. Clean-VM installation was not available.

## Models and offline inference

See `backend/model_bundle_manifest.json`. Required assets are not approved for the
commercial bundle. Ultralytics requires AGPL compliance or a suitable Enterprise
licence for the intended proprietary distribution; FastALPR model-weight
redistribution terms require verification. Make/model is operator-supplied only.
Consequently installed-app offline inference is blocked and the commercial build
correctly fails closed.

## Installer and signing

The previously built prototype installer is
`frontend/out/make/squirrel.windows/x64/LotTrace-Setup.exe`, 529,923,584 bytes,
SHA-256 `a132504bcb2387e38ce57c0727e34adca2f75994e3eac791aa02adc61b646864`.
It predates the new model gate, is unsigned (`NotSigned`), and is not the D5 release
candidate. The Forge configuration now reads certificate path/password only from
release environment variables and fails partial signing configuration.

## Performance and external gates

No new dealership-video performance or clean-VM resource measurements were made.
The previously recorded still-image metrics remain dataset-specific. Required
external work includes model rights/replacements, production signing credentials,
clean Windows VM installation/upgrade/rollback/uninstall, physical cameras and
dealership network testing, representative labelled dealership footage, frozen
event-level benchmark, and a monitored pilot with automatic inventory changes
behind the safety gate.

Nothing was pushed, published, deployed or released.

## Provisional system requirements

Until clean-VM resource measurement replaces these planning values: Windows 10/11
x64, four CPU cores, 16 GB RAM, 5 GB free application space plus separately sized
evidence retention storage; a GPU is optional because the validated development
paths have CPU fallbacks. These are not measured minimums or performance guarantees.
