# LotTrace modern-vehicle recognition experiment — 2026-10-23

## Outcome

The expanded EfficientNet-B0 candidate recognizes 140 closed-set make/model/year-range classes: 100 VMMRdb classes from 1995–2012 and 40 DVM-Car classes grouped as 2016–2018. It is a research candidate, not a production-certified or commercially cleared model.

| Frozen test | Images | Exact make + model + range | Top-5 exact | Make + model | Make | Year range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Combined | 2,532 | **76.82% (1,945/2,532)** | 94.47% | 91.35% | 93.76% | 79.66% |
| Older VMMRdb regression | 1,803 | **67.61% (1,219/1,803)** | 92.35% | 88.02% | 91.35% | 71.44% |
| Added DVM 2016–2018 classes | 729 | **99.59% (726/729)** | 99.73% | 99.59% | 99.73% | Not independently measurable |

The prior 100-class candidate scored 67.78% exact on the same 1,803 older images. The expanded candidate is 0.17 percentage points lower there (three fewer exact results) while adding 40 late-2010s classes. This is a coverage improvement, not proof of a universally more accurate model.

The DVM subset has only one year-range label, 2016–2018. Its 99.59% result therefore measures make/model within that band; it does **not** prove exact-year or year-range discrimination. The combined year result is driven by the multiple older VMMRdb ranges.

## Data controls

- The DVM archive MD5 matched the publisher value: `c103301f316fe9e59d1b3621c644a88c`.
- All 61,827 archive names parsed into make, model, year, colour, view, listing ID, and image ID.
- The experiment selected 40 classes and at most 120 images per class.
- Only one image from each advertised-vehicle listing was retained.
- Listing groups never cross train, development, and test.
- Images below 224 pixels, blurred images, low-contrast images, extreme exposures, byte-identical duplicates, and exact perceptual duplicates were rejected before training.
- Output filenames are anonymous and do not reveal the label.
- The frozen 4,800-image DVM subset contains 3,397 train, 674 development, and 729 test images. Its manifest SHA-256 is `36a64d9cec454c08f3829a42c7e3a273ebb7e2bf149e28ceaa83fa6c572374d1`.
- The combined 16,800-image manifest contains 11,799 train, 2,469 development, and 2,532 test images. Its SHA-256 is `50c8822551ab6e3ea9c1ff4becdb30aa24980ed7ef0f8d11e82ac1caa6b2c090`.
- The selected model SHA-256 is `fd8be3c8164dd79583615fd50233181eddfaca6fc9337073ad2af10691918390`.

## Human visual audit

The first audit inspected five deterministic examples from every modern class (200 images). After test evaluation, all 729 frozen modern-test images were rendered into 37 contact sheets and inspected without changing the frozen benchmark.

Two definite source defects were found:

1. `ead5bc923937e9048e26` is labelled Mazda CX-3 but visibly shows a Toyota Yaris.
2. `f22e4537f23ad8dd524c` is a rear Jaguar F-Type view inside a publisher set named “Confirmed Fronts.”

Both remain in the official denominator. The model's three modern-test errors were Fiesta→Focus, F-Type→Mustang, and the mislabeled Yaris→Yaris-like prediction. Removing the proven bad label post-test would inflate the score, so no adjusted score is promoted.

## Rights and deployment boundary

The DVM project page says the data is for non-commercial research and education under CC BY-NC 4.0, while the Figshare item displays CC BY 4.0. That conflict must be resolved with the rights holder before images or derived weights are used commercially. The candidate is therefore not enabled as the production LotTrace default.

- DVM project: https://deepvisualmarketing.github.io/
- DVM Figshare item: https://figshare.com/articles/figure/DVM-CAR_Dataset/19586296/1

The repository now also includes a Wikimedia Commons collector that retains per-file author, source URL, licence, checksums, quality measurements, and human-review state. Its allowlist accepts only CC0, public-domain, CC BY, and CC BY-SA files and rejects NC/ND licences. Commons ingestion was not completed in this run because the remote API was too slow; no accuracy is claimed for that source.

## Remaining gaps

- The new source is mostly 2016–2018, not 2020–2026.
- Clean frontal dealer photos differ sharply from fixed dealership entrance video.
- Unknown/unsupported vehicle rejection is not measured.
- Exact year is not visually defensible for many adjacent model years; LotTrace should continue returning ranges.
- A commercially cleared, held-out dealership-video set grouped by vehicle/site/camera/date is still required before deployment.

## Reproducible artifacts

- `scripts/prepare_dvm_modern_benchmark.py`
- `scripts/prepare_combined_vehicle_benchmark.py`
- `scripts/train_vmmr_vehicle_classifier.py`
- `scripts/evaluate_vmmr_vehicle_classifier.py`
- `scripts/render_vehicle_benchmark_contact_sheets.py`
- `scripts/collect_commons_vehicle_images.py`
- `evaluation/LOTTRACE_MODERN_COMMONS_VEHICLE_SOURCES_2026-10-23.json`
