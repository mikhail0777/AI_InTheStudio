# LotTrace modern-vehicle recognition experiment - 2026-10-23

## Decision

Do not promote the 151-class candidate. It expands modern-vehicle coverage, but
it did not improve the frozen accuracy result and its unknown-vehicle rejection
is not reliable enough for automatic assignment. The existing 140-class
candidate remains the research default.

## Frozen results

| Candidate / test | Images | Exact make + model + range | Make + model | Make | Year range |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing 140-class combined baseline | 2,532 | **76.82% (1,945/2,532)** | 91.35% | 93.76% | 79.66% |
| Expanded 151-class combined | 2,549 | **76.30% (1,945/2,549)** | 90.86% | 93.17% | 79.36% |
| Expanded candidate, older VMMR regression | 1,803 | **67.00% (1,208/1,803)** | 87.58% | 90.79% | 71.21% |
| Expanded candidate, DVM 2016-2018 | 729 | **99.59% (726/729)** | 99.59% | 99.59% | Not independently measurable |
| Expanded candidate, reviewed 2018-2026 Commons | 17 | **64.71% (11/17)** | 64.71% | 70.59% | 70.59% |

The modern subset's 95% Wilson interval is 41.30%-82.69%. Seventeen images are
enough to expose a coverage problem, but not enough to certify deployment.
Top-5 exact accuracy on that subset was 94.12% (16/17), which suggests the
visual features are useful but the top-1 classifier needs substantially more
training data.

The expanded model lost 11 exact answers on the older regression set while
adding 11 correct answers on the new modern set. Its total exact count therefore
stayed at 1,945 while the denominator increased. No post-test tuning was done
against the 17 opened modern test answers.

## Unknown-vehicle rejection

A maximum-softmax threshold was chosen only on development data while requiring
at least 90% known-class acceptance. The frozen result was:

| Measure | Result |
| --- | ---: |
| Known vehicles accepted | 91.84% (2,341/2,549) |
| Exact among accepted known vehicles | 80.35% (1,881/2,341) |
| Unsupported vehicles rejected | **58.82% (10/17)** |
| Unsupported vehicles falsely assigned a supported class | **7/17** |
| Total review rate in this constructed test | 8.50% |

This threshold is not enabled in a production manifest. The runtime now supports
an optional calibrated threshold and returns no make/model candidate below it,
but 58.82% unknown rejection is not an acceptable release result.

## Commercially reusable modern intake

- 240 candidate Commons files were checked by the automated intake.
- 148 passed per-file licence and image-quality gates.
- All 148 were visually reviewed before split freezing.
- 136 were accepted and 12 rejected.
- Eight Mazda CX-5 images were excluded because their proposed 2017-2026 label
  overlapped the existing 2016-2018 CX-5 answer.
- One 2025 fourth-generation Equinox was outside its proposed 2018-2024 range.
- Three crops showed only an interior or frunk and lacked sufficient identity
  evidence.
- The accepted set contains 103 supported examples across 11 current-generation
  classes and 33 unsupported examples across four held-out makes/models.
- Supported split: 69 train, 17 development, 17 test.
- Unsupported split: 16 development, 17 test.
- Capture groups never cross splits.
- Intake config SHA-256:
  `3985f699c962f4b3a6556b367850271a74f72a35934b6e66f9b64ec1795ae7e2`
- Frozen add-on manifest SHA-256:
  `f734fdae6689a25bf629ad0c1a65c567d50364324b1289e9df94c71eb9380bfb`
- Rejected candidate model SHA-256:
  `8a044b31734da869e81541cc9c3fa4f3bf40a950ba6a891b7de50f686d75c336`

Commons permits commercial reuse only under each file's licence terms. CC BY
requires attribution; CC BY-SA also requires share-alike treatment of
adaptations. The collector retains file URL, author/credit, licence, source hash,
and download hash. This is a technical compliance record, not a legal opinion.
The combined research model is still not commercially cleared because its base
training sources include restricted or conflicting research licences.

## What the age finding means

Age coverage was a major problem: the earlier model largely covered 1995-2012
plus a narrow 2016-2018 slice. It was not the only problem. The result also shows
that clean web photographs, small per-class sample counts, viewpoint imbalance,
unknown makes, and dealership-camera domain shift remain material.

The year output is a generation range, not an exact model year. Adjacent years
that are visually identical must continue to share a range.

## Milestone C status

Milestone C is not complete.

| Requirement | Status |
| --- | --- |
| Make/model/year candidate pipeline | Implemented and tested as research functionality |
| Current-generation coverage | Expanded by 11 classes, but only 64.71% on a 17-image test |
| Unknown result | Runtime support implemented; 58.82% rejection is too weak to enable |
| Trained colour model | Not complete; current colour evidence remains heuristic |
| Trained body-type model | Not complete; current category evidence is detector-derived |
| Dealership-owned visual retrieval | Not complete |
| Dealership-video benchmark | Waiting for real camera footage |
| Commercial production weights | Not cleared |

Milestone D preparation can begin in parallel (deployment configuration,
monitoring, restart/load/security tests, camera setup, and benchmark capture
protocol), but production certification cannot start until Milestone C's model
gaps are resolved and real dealership footage exists.

## Reproducible artifacts

- `scripts/collect_commons_vehicle_images.py`
- `scripts/freeze_commons_vehicle_benchmark.py`
- `scripts/append_vehicle_benchmark.py`
- `scripts/train_vmmr_vehicle_classifier.py`
- `scripts/evaluate_vmmr_vehicle_classifier.py`
- `scripts/evaluate_vehicle_unknown_rejection.py`
- `scripts/render_vehicle_benchmark_contact_sheets.py`
- `evaluation/LOTTRACE_MODERN_COMMONS_VEHICLE_SOURCES_2026-10-23.json`
- `evaluation/LOTTRACE_VEHICLE_151_TEST_2026-10-23.json`
- `evaluation/LOTTRACE_VEHICLE_UNKNOWN_REJECTION_2026-10-23.json`

The local images, frozen manifests, contact sheets, and candidate weights remain
ignored dataset artifacts. They are reproducible from the audited source
configuration and scripts and are not committed to Git.
