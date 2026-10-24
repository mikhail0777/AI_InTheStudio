# LotTrace Milestone C make/model result - 2026-10-24

## Decision

LotTrace now treats visual vehicle recognition as a make/model task. Visual year
prediction is omitted. A confirmed year may still come from a plate-linked
dealership record.

The 95% all-vehicle target was not reached. The selected make/model model scored
92.10% on the frozen regression test, improving the prior 91.35% result by 0.75
percentage points and 19 correct vehicles. The result must not be described as
95% accurate or production-certified.

## Measured result

| Frozen test | Images | Make + model top-1 | Make top-1 | Make + model top-5 |
| --- | ---: | ---: | ---: | ---: |
| Combined | 2,532 | **92.10% (2,332/2,532)** | 94.15% | 98.22% |
| Older VMMRdb regression | 1,803 | **89.02% (1,605/1,803)** | 91.90% | 97.62% |
| DVM late-2010s subset | 729 | **99.73% (727/729)** | 99.73% | 99.73% |

The 95% Wilson interval for combined top-1 make/model accuracy is
90.99%-93.09%.

Previous make/model baseline: 91.35% (2,313/2,532).

Selected development result: 92.47% (2,283/2,469). Model choice and training
were based on development data. The frozen regression test was run after the
candidate was selected.

## What changed

- Collapsed 140 make/model/year-range answers into 79 normalized make/model
  classes without moving any image between train, development, and test.
- Initialized the make/model model from the existing EfficientNet-B0 visual
  backbone.
- Trained a new make/model head, then ran one bounded full-network fine-tuning
  epoch selected without test feedback.
- Added probability grouping across duplicate year-range classes as a tested
  alternative. It reached 91.74% on development and was not selected.
- Updated the runtime provider to support both a direct make/model model and
  grouped make/model probability output.
- Make/model candidates now return `year_start: null` and `year_end: null`.
- Added reproducible manifest collapsing, grouped evaluation, and review-gate
  calibration tools.

## Review-gate result

A confidence threshold was selected on development data to target at least 95%
accuracy among automatically accepted predictions.

| Gate measure | Development | Frozen test |
| --- | ---: | ---: |
| Accuracy among accepted predictions | 95.03% | **94.35%** |
| Automatic coverage | 95.38% | 95.81% |
| Review rate | 4.62% | 4.19% |
| False accepted assignments | 117 | 137 |

The gate failed to maintain 95% on the frozen test, so it is not enabled. The
threshold was not changed after observing the test result.

## Product behavior

Visual output should be presented as:

`Possible vehicle: Honda Civic`

It should not visually claim an exact year. If the plate confidently matches a
dealership record, that record may supply the confirmed make, model, and year.
The licence plate remains the primary identity; visual make/model is supporting
evidence and a consistency check.

## Milestone boundary

The bounded make/model objective for Milestone C is implemented and measured.
It can be frozen at 92.10% while work moves to Milestone D. It is not a production
accuracy certification because:

- The 95% target was missed.
- The benchmark uses web/dealer still images rather than dealership cameras.
- The source datasets are research-only or have conflicting commercial rights.
- Unknown-vehicle rejection remains below the required standard.
- Real camera footage is still required for final domain validation.

Milestone D should preserve this measured limitation and use plate/database
identity whenever available. Make/model refinement can resume after legally
usable dealership images and camera footage are collected.

## Reproducibility

- Collapsed manifest SHA-256:
  `70837b1b8b83b050e56029d7f4446f0c588d382244db5afb64a7fcf15abc92d4`
- Selected model SHA-256:
  `dab4077244263aafecb3c5d55da09665bb3dd7e6e146225ab16287b523fdcc08`
- `scripts/collapse_vehicle_make_model_manifest.py`
- `scripts/evaluate_grouped_vehicle_make_model.py`
- `scripts/evaluate_make_model_review_gate.py`
- `evaluation/LOTTRACE_MAKE_MODEL_TEST_2026-10-24.json`
- `evaluation/LOTTRACE_MAKE_MODEL_REVIEW_GATE_2026-10-24.json`

The local manifest, training images, and model weights remain ignored artifacts
and are not committed to Git.
