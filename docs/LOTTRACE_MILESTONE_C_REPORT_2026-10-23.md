# LotTrace Milestone C vehicle-recognition report — 2026-10-23

## Outcome

The local make/model/year-range system is implemented end to end and connected
to recording-wide vehicle tracks. A stronger clean EfficientNet-B0 model raised
exact frozen-test accuracy from 38.38% to 67.78%. Its accuracy is still not high
enough to close Milestone C or enable automatic vehicle identity decisions.

## Implemented system

- Local PyTorch Export inference; no paid recognition API.
- Ranked make/model/year-range candidates with model and manifest SHA-256.
- Multi-frame candidate consensus, `unknown`, and `conflicting` states.
- Candidate observations remain separate from confirmed dealership records.
- Recording-wide analysis runs the classifier on saved vehicle crops when a
  model is configured.
- The Windows launcher automatically discovers the locally trained research
  model, while its manifest preserves the research-only restriction.
- VMMR manifest creation, selective extraction, transfer learning, frozen-test
  evaluation, confidence intervals, macro-F1, and confusion reporting are
  reproducible scripts.

## Frozen research benchmark

Archive SHA-256:
`162bcd8a3ba61d52b9529cba96bfa6ed031d8375c3306340d0fdc1e0c638014a`

Frozen manifest SHA-256:
`e114b89214a4b98fb3cb91fcd0bb37a870801f0826fa61ff8d8f08629226796d`

- Labels: 100 make/model/three-year-range classes.
- Train: 8,402 images.
- Development: 1,795 images.
- Frozen test: 1,803 images.
- Total: 12,000 images.
- Model: ImageNet-initialized MobileNetV3 Small.
- Training: five epochs; classifier frozen for three, full network fine-tuned
  for two at a reduced learning rate.
- Best development exact top-1: 36.49%.
- Best development exact top-5: 72.03%.

## Frozen test results

### Selected EfficientNet-B0 upgrade

The replacement candidate was initialized from the official torchvision
ImageNet weights and trained only on the frozen manifest's 8,402 training
images. Model selection used the 1,795-image development split. The frozen test
was opened once after the candidate and training configuration were fixed.

- Training: 15 epochs; classifier frozen for two, then the full network was
  fine-tuned at a reduced learning rate.
- Best development exact top-1: 65.74%.
- Development exact top-5 at the final epoch: 92.20%.

| Metric | Improved result | Previous result |
| --- | ---: | ---: |
| Exact make + model + three-year range, top-1 | 1,222/1,803 — 67.78% | 38.38% |
| Exact make + model + three-year range, top-5 | 92.73% | 72.66% |
| Make, top-1 | 92.68% | 65.06% |
| Make + model, top-1 | 89.35% | 56.96% |
| Year range from top candidate | 70.94% | 51.08% |
| Exact-class macro-F1 | 66.61% | 36.34% |
| Exact top-1 95% Wilson interval | 65.58%–69.89% | 36.16%–40.65% |

The selected model SHA-256 is
`730ee9075c55f21be47f777113940ee873e6c18fe0befa45a6d819672d5f8a31`.
The machine-readable report is
`evaluation/LOTTRACE_VMMR_100_CLASS_EFFICIENTNET_TEST_2026-10-23.json`.
The Windows launcher now discovers this model before the previous MobileNet
artifact.

### Previous MobileNetV3 baseline

| Metric | Result |
| --- | ---: |
| Exact make + model + three-year range, top-1 | 692/1,803 — 38.38% |
| Exact make + model + three-year range, top-5 | 72.66% |
| Make, top-1 | 65.06% |
| Make + model, top-1 | 56.96% |
| Year range from top candidate | 51.08% |
| Exact-class macro-F1 | 36.34% |
| Exact top-1 95% Wilson interval | 36.16%–40.65% |

The model SHA-256 is
`f0b2165b8c96df37c390ca6fc17df0aa2268bfd557959b2796f2bee6db1926a0`.
The machine-readable report is
`evaluation/LOTTRACE_VMMR_100_CLASS_RESEARCH_TEST_2026-10-23.json`.

## Imported-model investigation

An MIT-labelled 8,949-class EfficientNet-B4 checkpoint published as
[`Jordo23/vehicle-classifier`](https://huggingface.co/Jordo23/vehicle-classifier)
at revision `7a0a0ee5584202b5eba858cf7464f5ca6b7341b3` was downloaded, hashed, loaded with PyTorch's
weights-only mode, and independently run through the development evaluator. It
measured 89.81% exact range, 98.77% make/model, and 99.61% make accuracy.

Those numbers are **not independent accuracy**: the checkpoint was trained on
the full VMMRdb collection, so it may have trained on the same images present
in this benchmark. It was therefore excluded from frozen-test selection and is
not the launcher default. Its development report is retained as
`evaluation/LOTTRACE_IMPORTED_VMMR_OVERLAP_DEVELOPMENT_2026-10-23.json`.

## Error diagnosis

With make/model now at 89.35%, many of the largest remaining errors retain the correct make and model but select an
adjacent three-year range. Examples include Nissan Maxima 2001–2003 versus
1998–2000, Toyota Corolla 2004–2006 versus 2001–2003, and Ford Explorer
2004–2006 versus 2001–2003. This supports presenting year as a range, but it
does not make the wrong range acceptable.

The stronger architecture substantially improved vehicle identity, but the
70.94% year-range result shows that appearance alone does not reliably separate
adjacent model years. More representative data, generation-aware labels, and
multi-view dealership tracks are required.

## Legal and benchmark limitations

The official VMMRdb repository applies an MIT licence to its repository, but
the associated paper says the images were collected from vehicle-sale pages.
Permission to commercially reuse those underlying third-party images is not
clearly established. This model therefore remains local and research-only.

VMMRdb does not provide vehicle identity, camera, site, or recording date.
Consequently, its hash split cannot prevent the same real vehicle or source
session from crossing splits. It also contains vehicles only through 2017 and
does not represent modern Canadian dealership entrance/exit video.

Vehicle-1M was rejected for production training because its official licence
explicitly permits academic use only and prohibits commercial use.

## Milestone decision

Milestone C functionality and repeatable research measurement are implemented,
but the milestone accuracy gate is **not passed**. The model may provide
reviewable supporting candidates; it must not automatically confirm make,
model, or year.

The next valid improvement requires dealership-owned or explicitly
commercially licensed images, generation-aware labels, and a held-out video
benchmark grouped by real vehicle, camera, site, and date. Confirmed dealership
inventory photos and reviewed LotTrace events are the preferred data source.
