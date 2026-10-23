# LotTrace Canadian OCR specialization report

Date: 2026-10-22

## Outcome

The 95% exact full-plate target is **not met**. The best measured LotTrace
single-crop result remains the validation-only YOLO/PARSeq ranking experiment at
85.53% (136/159), with 62.16% (23/37) on the repeatedly inspected development
regression split. The production default remains the existing FastALPR
`cct-xs-v2-global-model`; no experimental reader was promoted.

There is no untouched, fully transcribed Ontario/Quebec final test set. The
available OCR crops do not have trustworthy province or plate-class labels, so
Ontario, Quebec, standard/special-class, and final-test accuracy cannot be
reported without inventing metadata. UC3M masked strings remain excluded from
full-plate truth.

## Verified baselines

- Plate localization on 1,020 images: precision 97.55%, recall 91.71%, F1
  94.54%. This is localization, not OCR.
- UC3M published-position sequence accuracy: approximately 82.69%; two
  characters per plate are masked.
- YOLO 640 character reader: validation 82.39% (131/159), character accuracy
  95.78%; development regression 59.46% (22/37).
- YOLO/PARSeq length-ranked research result: validation 85.53% (136/159);
  development regression 62.16% (23/37).
- The 37-image split is development regression data, not a final test.

## Data and split audit

The nine supplied archives, checksums, label types, licences/permission status,
and usage restrictions remain inventoried in
`LOTTRACE_EXTERNAL_DATA_TRAINING_REPORT.md`. Extracted data and model outputs
remain ignored by Git. The current usable OCR sources are:

| Source | Full-text basis | Region labels | Permitted use | Split role |
|---|---|---|---|---|
| 36-class plate OCR | Spatial character boxes corroborated against filename tokens | None | CC BY 4.0 | Train, validation, development regression |
| 31-class plate OCR | Spatial character boxes; full-string truth not independently reliable | None | Owner-authorized local school research | Training only |
| UC3M-LP | Two masked characters per plate | Country-level source only | ODbL-1.0 | Localization and published-position OCR only |
| 1,020-image plate set | Plate boxes, no transcription | None | Existing evaluation use | Localization only |

`audit_ocr_split_manifest.py` now rejects missing provenance, masked full-plate
truth, invalid transcriptions, and leakage across plate identity, exact image,
vehicle, event, recording, camera/date, or site/date. It also detects
cross-split perceptual near-duplicates. This procedure is ready for a future
Ontario/Quebec collection, but no untouched final split is claimed now.

## FastPlateOCR investigation

All local comparisons used the same 159 validation crops and normalization.

| Official pretrained reader | Local validation exact | Local character accuracy | Decision |
|---|---:|---:|---|
| Legacy global MobileViT v2 | 57.86% (92/159) | 87.51% | Rejected |
| CCT-S v2 global | 52.20% (83/159) | 85.27% | Experimental only |
| CCT-XS v2 global | 47.80% (76/159) | 83.56% | Existing production component, not promoted as a crop benchmark winner |

The [official model zoo](https://ankandrew.github.io/fast-plate-ocr/latest/inference/model_zoo/)
calls CCT-S v2 the recommended default and defines the legacy worldwide
MobileViT result as 93.3% `plate_acc` on its own benchmark. The official release
JSON files contain Canada rows:

| Official artifact | Canada `plate_acc` | Published Canada denominator |
|---|---:|---:|
| CCT-S v2 global | 96.27% | Not present |
| CCT-XS v2 global | 95.36% | Not present |
| Legacy global MobileViT v2 | 90.79% | Not present |

The release contains metric dictionaries but no global validation split or
per-country sample counts. It does not identify Ontario/Quebec composition.
Consequently these values are not reproducible Canadian denominated results and
are not LotTrace accuracy evidence. FastPlateOCR defines `plate_acc` as exact
full-string accuracy in its [metrics documentation](https://ankandrew.github.io/fast-plate-ocr/latest/training/metrics/).

## Ontario and Quebec profiles

LotTrace now has explicit `unknown`, `ontario`, and `quebec` profiles. They:

- preserve each raw OCR string and separately store normalized text;
- retain top-k candidates, raw confidence, exact independent-frame support,
  profile name, format contribution, and review decision;
- use common standard-passenger layouts only as a small ranking contribution;
- never substitute O/0, I/1, B/8, S/5, Z/2, G/6, or T/7;
- route unmatched, ambiguous, multi-row, vanity, commercial, trailer, historic,
  temporary, diplomatic, and other unsupported formats to review;
- default to `unknown`, so enabling a regional profile is explicit.

These common-layout references are not described as learned or validated
Ontario/Quebec accuracy. New formats must be enabled only after labelled data
supports them.

## Preprocessing ablation

The validation-only ablation evaluates raw, padded, guarded perspective
rectification, grayscale, CLAHE, exposure normalization, denoising, sharpening,
2x/4x resizing, and a blur-gated deblur candidate. Derivatives are stored apart
from raw crops. Enhancement variants from one frame are never counted as
independent consensus votes.

On the same 159 validation crops with CCT-S v2, raw input scored 52.20%
(83/159) exact, 85.27% character accuracy, and 100% read coverage. CLAHE was
best at 54.09% (86/159) exact with a 95% Wilson interval of 46.34%-61.65%,
86.16% character accuracy, and 13.84% CER. Two-times resizing tied at 86/159
exact but had lower character accuracy (85.53%). Four-times resizing scored
85/159; all other variants were at or below 83/159. No blur-gated deblur
candidate was emitted because no crop crossed the objective low-sharpness
threshold. CLAHE improves this reader by three plates but remains far below the
YOLO baseline, so it is not promoted.

## Fine-tuning status

The official FastPlateOCR CSV structure was prepared reproducibly from permitted
data: 3,982 training crops and 159 validation crops. The source 37-image test
split was excluded. No `plate_region` column was fabricated. The stricter 2,273
single-row subset remains the sequence-model training subset described in the
earlier experiment report; the larger CSV includes the permitted supplemental
character-box training source.

Training did not start in the production Python environment. Only Python 3.14.8
is installed, no Keras/TensorFlow/JAX training backend is present, and the
official training CLI is unavailable. Per the isolation rule, production
dependencies were not disrupted. A separate Python 3.12 environment and the
official pretrained Keras weights are required before the CCT-S fine-tune can be
attempted. Therefore there is no new checkpoint, ONNX export, training history,
or checkpoint hash to report.

## Integration and rollback

`AIEYE_PLATE_OCR_MODE` defaults to `existing` (CCT-XS). An explicit
`fastplate-cct-s-experiment` comparison mode records its model name, SHA-256,
and underperformed status in the model manifest. `AIEYE_PLATE_REGION_PROFILE`
defaults to `unknown`; the selected profile and ranking-only policy are persisted
in the scan manifest. The YOLO/PARSeq ensemble was not wired into production
because it did not meet the stated promotion criterion.

## Release decision and next experiment

Production certification remains false. Freeze no final-test architecture yet.
The next defensible experiment is to install an isolated Python 3.12 training
environment, fine-tune CCT-S v2 on the prepared training CSV with validation-only
checkpoint selection, and then compare YOLO, CCT-S, PARSeq, and candidate-level
ensembles on the same validation inputs. Separately collect a legally usable,
province-labelled dealership-video corpus grouped by vehicle/event/site/camera/date
and reserve its final-test groups before any inspection.

## Development-regression readability review

The project owner visually reviewed the 37 raw regression crops and marked 16
unreadable, two challenging (`FZO4A16` and `GDC7I31`), and 19 clearly readable.
This was not blind because expected text is encoded in filenames. Original
labels were not changed, and model predictions were joined only after the
readability categories were supplied.

The ensemble remains 23/37 (62.16%) on all crops. Excluding only the 16
unreadable crops gives 19/21 (90.48%, Wilson 95% CI 71.09%-97.35%) with 98.64%
character accuracy. The clearly readable subset is 19/19, but its 95% interval
is only 83.18%-100%, and the subset is post-hoc development data. It must not be
reported as a final or production 100% result. Four of the 16 visually
unreadable crops happened to match their encoded labels; those matches are not
independently verifiable plate evidence. The quality review supports adding an
abstention/readability gate, not deleting hard examples from the primary score.
