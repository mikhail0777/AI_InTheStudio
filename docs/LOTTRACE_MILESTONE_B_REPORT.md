# LotTrace Milestone B report

Date: 2026-10-21

## Outcome

Milestone B adds an auditable multi-frame plate-reading path and a strict held-out event evaluator. It does **not** establish production plate accuracy. LotTrace still lacks a legally usable, fully transcribed, held-out dealership-video benchmark, so the declared 99% release gates cannot be measured or passed from the data currently available.

## Implemented

- Every retained plate observation stores its source frame, bounding box, lossless raw crop, separately enhanced OCR derivative, quality measurements, raw OCR candidates, model names, versions, hashes, and thresholds.
- Enhancement includes exposure/contrast normalization, guarded perspective rectification, enlargement, and sharpening. The original frame and crop are never overwritten.
- Best-frame selection ranks sharpness, contrast, exposure, crop size, query similarity, and OCR support.
- Consensus counts an exact string at most once per frame. Multiple enhancement variants from one frame cannot manufacture temporal agreement.
- An exact consensus requires the same exact normalized string on at least two independent frames without a similarly supported competing candidate.
- O/0, I/1, B/8, S/5, and related confusions affect review ranking only. They never silently rewrite a plate or create an exact match.
- Immutable per-frame observations and the consensus decision persist in SQLite and are exposed through a tenant-scoped API.
- The saved-sighting review UI shows the raw and enhanced crops, ranked alternatives, independent-frame support, and review warning. Model confidence is not labelled as accuracy.
- `scripts/evaluate_plate_event_benchmark.py` reports denominators, Wilson intervals, event read recall, event-level exact full-plate accuracy, top-k accuracy, character error/accuracy, OCR confusions, difficult-condition breakdowns, false exact assignments, and false sightings per negative-video hour.
- The evaluator rejects undocumented licensing, placeholder provenance, mixed/non-final splits, missing site/camera/vehicle/date separation declarations, duplicate/unknown event IDs, and predictions without a model/threshold manifest.

## Release-gate status

| Gate | Target | Current evidence | Status |
|---|---:|---|---|
| Eligible crossing-event recall | at least 99% | No labelled dealership-video event set | Unmeasured |
| Plate localization recall on eligible events | at least 99% | 97.15% on the UC3M held-out still-image test; 91.71% on the existing 1,020-image set | Not met on available proxy datasets; production gate unmeasured |
| Character accuracy | at least 99% | UC3M published positions imply 93.98% character accuracy, but two characters per plate are masked | Not met on published positions; full-plate gate unmeasured |
| Event-level exact full-plate accuracy | at least 99% | Existing 1,020-image set has no transcription labels; UC3M masks two characters | Unmeasured |
| Plate-to-vehicle association precision | at least 99% | Existing 16.36% value is coverage, not precision | Unmeasured |
| Plate-to-vehicle association recall | at least 98% | No labelled dealership-video association set | Unmeasured |
| False exact assignments / false sightings per hour | report | No eligible labelled video-hours corpus | Unmeasured |

The small five-clip AGH parking smoke test and UC3M published-position results remain useful diagnostics, but neither is a dealership-video release benchmark.

## Verification

- Full backend regression suite: 182 tests passed after the final Milestone B change.
- Frontend tests: 17 passed.
- TypeScript type-check: passed.
- Vite production build: passed.
- Functional tests prove software behavior only; they are not model-accuracy results.

## Required external input before certification

Collect or provide a commercially usable dealership-video benchmark with full plate transcriptions, eligible crossing labels, track identities, plate-to-vehicle links, negative footage duration, difficult-condition tags, and final-test isolation by site, camera, vehicle, and recording date. Generate predictions once with a pinned model manifest, then run:

```powershell
python scripts/evaluate_plate_event_benchmark.py `
  --manifest evaluation/dealership_plate_event_manifest.json `
  --predictions evaluation/dealership_plate_event_predictions.json `
  --output evaluation/dealership_plate_event_report.json
```

Until that report exists and passes, LotTrace must route uncertain/conflicting plate evidence to review and must not claim 97% or 99% exact full-plate accuracy.
