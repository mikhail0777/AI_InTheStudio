# Phase 10: evaluation and hardening

## Scope and acceptance criteria

This phase adds an honest, repeatable evaluation boundary and hardens failure behavior without
changing the product's search scope. Acceptance requires label-driven retrieval, event,
localization, ranking, false-positive, and condition metrics with explicit denominators;
coverage of corrupt/empty media, CPU-only execution, duplicates, unsupported evidence,
occlusion, lighting, angle, distance, unrelated objects, and multi-frame actions; preservation
of both flagship vertical slices; complete regression and frontend build gates; and no model
accuracy claim where representative labels do not exist.

## Label-driven evaluator

`scripts/evaluate_labeled_search.py` evaluates completed persisted searches against an
operator-authored JSON manifest. Ground-truth intervals can require entity labels, carry
condition tags, and include timestamped boxes. Invalid intervals and zero-area/reversed boxes
fail validation. A prediction must be promoted, overlap the event, and contain every required
label before it can match. Greedy one-to-one matching prevents one prediction from satisfying
multiple labels.

The report exposes raw counts next to candidate retrieval recall, event recall, promoted
false-positive rate, temporal IoU, box recall at IoU 0.5, mean box IoU, mean reciprocal rank,
and per-condition recall. A metric is `null` with an explanatory note when it lacks a valid
denominator. The output also preserves the search's processing mode, stage timings, cache
state, workload counts, and inference device.

Example:

```powershell
$env:PYTHONPATH='backend'
python scripts/evaluate_labeled_search.py evaluation/manifest.example.json `
  --data-dir backend/data --output evaluation/report.json
```

## Real labeled result

The manually reviewed label for `DJI_0178.MP4` covers the visible red Tesla over the full
2.135-second clip and a car box at 2.002 seconds. It tags the event as daylight, high-angle,
and medium-distance. The evaluator replayed persisted CPU fast-mode search
`benchmark_c953b7c9e2ab` (`a red car`) rather than substituting test fixtures.
The versioned label and generated result are `evaluation/phase10_real_red_car_label.json` and
`evaluation/phase10_real_red_car_report.json`; the source MP4 and search database remain local.

| Measure | Count or value |
|---|---:|
| Ground-truth / retrieved / matched events | 1 / 1 / 1 |
| Promoted / false-positive results | 1 / 0 |
| Candidate retrieval recall | 1.0 |
| Event recall | 1.0 |
| Promoted false-positive rate | 0.0 |
| Temporal IoU | 0.99999999998 |
| Box recall at IoU 0.5 | 1.0 (1/1) |
| Mean box IoU | 0.9870 |
| Mean reciprocal rank | 1.0 |
| Daylight / high-angle / medium-distance recall | 1/1 each |

This is one labeled event, not a population estimate. It demonstrates that the evaluation
path, persisted evidence, localization, and ranking agree for that reviewed case only.

The stroller validation remains the real positive interaction case: one strong event at
20.522-39.106 seconds, best frame 30.030 seconds, with zero promoted false events after visual
review. The two supplied yellow-car searches retained all 40 localized tracks as unlikely;
the supplied footage contains no confirmed yellow car, so real yellow-car positive recall is
still not measured. Deterministic image/mask tests cover the yellow positive gate.

## Hardening and scenario coverage

The machine-readable inventory is `evaluation/scenario_matrix.json`. New regressions ensure
nonempty corrupt media cannot fabricate metadata, automatic device selection records an
explicit CPU fallback, visible red remains stable under deterministic bright/dim transforms,
and tiny or heavily occluded color regions remain unsupported. A discovered dim-red defect was
fixed by preventing the brown hue family from consuming pure red pixels near hue zero.

Existing regressions cover empty media, adjacent/tiled duplicate suppression, irrelevant and
stationary nearby entities, single-frame action rejection, coordinated multi-frame motion,
negated entities/actions/relationships, missing required entities, unsupported constraints,
and event fragmentation. The prior real runs cover CPU execution, cold/warm indexes, and all
three processing modes.

No labeled real set was supplied for low light, long distance, low camera angle, or severe
occlusion. Those conditions therefore have component-level regression coverage or are explicitly
unmeasured; the application makes no recall or precision claim for them. Similarly, two timing
samples per processing mode are reproducibility observations rather than robust latency
percentiles.

## Verification and review

- Backend: `python -m unittest discover -s tests -v` — 116 tests passed.
- Frontend: `npm.cmd run build` — TypeScript and the Vite production build passed.
- Real inference evidence: Phase 5 red/yellow runs, Phase 7 stroller run, Phase 8 two-person
  query, Phase 9 mode benchmark, and the Phase 10 labeled replay above.
- Security review: label manifests are parsed into bounded typed structures; database access
  remains parameterized; evidence paths retain existing traversal and local-file checks;
  queries do not trigger network model downloads; and processing/result caps remain bounded.
- Regression review: the only production inference change is the narrow hue-boundary fix.
  Evaluation code is offline/read-only except for an explicitly requested report path.
