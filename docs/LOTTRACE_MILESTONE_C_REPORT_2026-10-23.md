# LotTrace Milestone C vehicle-recognition report — 2026-10-23

## Outcome

The local make/model/year-range system is implemented end to end and connected
to recording-wide vehicle tracks. The first frozen research benchmark is also
complete. Its accuracy is not high enough to close Milestone C or enable
automatic vehicle identity decisions.

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

## Error diagnosis

Many of the largest errors retain the correct make and model but select an
adjacent three-year range. Examples include Nissan Maxima 2001–2003 versus
1998–2000, Toyota Corolla 2004–2006 versus 2001–2003, and Ford Explorer
2004–2006 versus 2001–2003. This supports presenting year as a range, but it
does not make the wrong range acceptable.

The 56.96% make/model result also shows that the limitation is not only model
year. More representative data, vehicle cropping, a stronger architecture,
generation-aware labels, and multi-view dealership tracks are required.

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
