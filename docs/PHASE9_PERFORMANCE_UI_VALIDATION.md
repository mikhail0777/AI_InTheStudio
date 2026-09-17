# Phase 9: performance modes and UI completion

## Scope and acceptance criteria

This phase makes `fast`, `balanced`, and `thorough` meaningful bounded workloads and completes
the generic review interface. Acceptance requires mode-specific indexing and query budgets,
batched CPU/GPU-aware providers, stage progress and persisted timings, result filters, highlighted
participants, clip playback, feedback, and generic report export. A real benchmark must report
cold/cache state, p50/p95 stage timings, repeat-search latency, workload counts, device, and result
quality without presenting two-run timing samples as a population-level performance claim.

## Implementation

- The selected mode travels from the form through `TargetConfiguration`, structured query,
  content-addressed index, search record, status API, report, and result UI.
- Profiles bound semantic candidates, unique localization frames, orchestration batches, retained
  tracks, and materialized results. Environment limits may lower these caps but cannot raise them.
- Search metrics persist index cache state, per-stage/total timings, counts, active profile, actual
  result cap, and inference device. Status and reports surface the relevant values.
- Progress identifies indexing, retrieval, localization, ranking, and completion. Providers retain
  automatic CUDA selection with CPU fallback and bounded internal batches.
- Generic result controls filter by classification, entity, minimum ranking score, and overlapping
  time interval. Cards show annotated evidence, participant track chips, score, explanations,
  feedback, original-video seek, and playable clips. Reports include mode and stage timings.

## Real CPU benchmark

Command:

```powershell
$env:PYTHONPATH='backend'
python scripts/benchmark_processing_modes.py videos/DJI_0178.MP4 "a red car" `
  --data-dir backend/data/phase9_benchmark_final --repeats 2
```

Source: `DJI_0178.MP4`, 3840x2160, 2.135 seconds. Device: CPU. Each mode ran once with a new
mode-specific index and once with an index cache hit. Values below are measured seconds.

| Mode | Results | Total p50 | Total p95 | Repeat | Localization p50/p95 | Ranking p50/p95 |
|---|---:|---:|---:|---:|---:|---:|
| Fast | 5 | 36.063 | 48.519 | 22.222 | 5.184 / 5.678 | 21.899 / 26.148 |
| Balanced | 10 | 25.661 | 28.640 | 22.351 | 2.464 / 2.519 | 20.714 / 21.640 |
| Thorough | 20 | 47.925 | 51.882 | 43.528 | 3.809 / 3.935 | 41.783 / 43.639 |

Fast localized 3 unique frames and 53 detections; balanced localized 4 frames and 71 detections;
thorough localized 6 frames and 107 detections. Every run ranked the clearly visible red Tesla as
one strong match. Fast returned four additional unlikely matches, balanced nine, and thorough
eighteen plus one insufficient-visibility result. Visual review of the top annotated frame from
each mode confirmed the same correctly localized red Tesla. No promoted false result was observed
among the top candidates.

These p95 values interpolate only two measurements per mode and are included to make the harness
and reporting format reproducible; they are not statistically robust latency estimates. Clip
materialization dominates ranking time, especially when thorough mode writes 20 review clips.
The modes ran sequentially in one process: the first fast run includes the process-cold SigLIP
load (15.632 seconds inside retrieval), while later modes reuse that immutable model. Therefore
repeat-search latency is the fairer cross-mode comparison; the table does not claim that a cold
fast run is slower by design than balanced. The final implementation loaded SigLIP once across all
six searches.

## Verification, security, and limitations

- Backend: `python -m unittest discover -s tests -v`
- Frontend: `npm.cmd run build`
- Tests cover increasing bounded profiles, invalid modes, mode propagation, additive metrics
  migration, timing/status/report exposure, batching compatibility, and prior regressions.
- Query length, file limits, evidence/report path validation, HTML escaping, local-only model
  loading, and bounded candidate/result counts remain intact. UI filters operate only on returned
  data and do not construct server queries or filesystem paths.

Performance remains hardware- and footage-dependent. Timing does not measure recall, dense 4K
footage remains expensive on CPU, and thorough mode intentionally prioritizes coverage over speed.
The formal scenario evaluation and hardening matrix belongs to Phase 10.
