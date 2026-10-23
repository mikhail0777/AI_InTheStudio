# LotTrace readable plate benchmark

Date prepared: 2026-10-22

## Purpose

This benchmark separates the first two plate-reading stages:

1. **Plate localization** measures whether the system finds the plate and places
   a sufficiently overlapping box around it.
2. **Plate OCR** measures character accuracy, character error rate, and exact
   full-string accuracy on ground-truth plate crops.

The existing localization benchmark remains the 1,020-image License Plate
Recognition v13 test set with 1,085 labelled plates. Its current IoU 0.50 result
is 97.55% precision, 91.71% recall, and 94.54% F1.

## New blinded OCR package

`scripts/prepare_readable_plate_benchmark.py` created 300 anonymous, full-colour
plate crops from ground-truth boxes in that test set. The deterministic source
pool contained 730 boxes with a minimum short side of 30 pixels. The selection
was checked against 3,982 OCR training images using exact and perceptual hashes;
no selected crop was rejected as overlapping those references.

The ignored local package is:

```text
datasets/extracted/readable_plate_benchmark_v1/
  images/                    300 anonymous PNG crops
  contact_sheets/            12 sheets, 25 crops per sheet
  plate_review.xlsx          editable visual review workbook
  review.csv                 canonical review data
  human_review_filled.xlsx   preserved submitted workbook
  private_provenance.json    source paths, boxes, hashes, and selection policy
```

The workbook and CSV contain no OCR predictions. A reviewer classifies each
crop before evaluation:

- `readable`: ordinary readable plate; primary OCR denominator;
- `challenging`: readable with blur, angle, glare, distance, or similar damage;
- `unreadable`: a human cannot reliably determine the complete string;
- `out_of_scope`: unsupported alphabet or layout for the declared A-Z/0-9 test.

Readable and challenging rows require an exact 2-10 character A-Z/0-9
transcription. Unreadable and out-of-scope rows must have blank transcription.
The plate filename and sample ID never contain the answer.

## Freeze before OCR

The workbook is the easiest review interface. After review, save its review
columns into the canonical `review.csv`, preserving these headers:

```text
sample_id,transcription,readability,vehicle_group_id,reviewer,notes
```

Then freeze the images and human labels:

```powershell
python scripts/prepare_readable_plate_benchmark.py freeze `
  --benchmark datasets/extracted/readable_plate_benchmark_v1
```

Freeze validation rejects incomplete labels, guessed unreadable strings,
duplicate or unknown IDs, and images changed since preparation. It creates
`frozen_manifest.json` and `FROZEN.sha256`.

Only after that succeeds may OCR be run:

```powershell
python scripts/evaluate_readable_plate_benchmark.py `
  --benchmark datasets/extracted/readable_plate_benchmark_v1 `
  --output datasets/extracted/audits/readable_plate_benchmark_v1_result.json
```

The primary Stage 2 result is exact full-string accuracy on the rows marked
`readable`. Challenging accuracy is reported separately. Unreadable plates are
measured as an abstention/review-routing problem, not treated as ordinary OCR
failures. Out-of-scope plates are reported and excluded from OCR denominators.

## Integrity limits

- Do not train, tune thresholds, select preprocessing, or choose an ensemble on
  these 300 crops after they are frozen. Use separate training/validation data.
- Do not run OCR before human transcription and difficulty classification are
  frozen.
- This measures crop-level OCR separately from localization. It does not by
  itself measure tracking, multi-frame consensus, or event-level accuracy.
- One reviewer is enough for a preliminary score. A second independent review
  of all disputed or challenging strings is recommended before calling the
  result final.

## Review received on 2026-10-22

The submitted workbook was preserved with SHA-256
`27fab57f7cbac6e075ad582cec0577513e678f2c82fe993f82c057f9b6876864`.
All 300 rows have a readability decision:

- readable: 271;
- challenging: 23;
- unreadable: 3;
- out of scope: 3.

The transcription cells are blank on all 300 rows. Therefore the 294 readable
or challenging rows still have no independent correct string, and the freeze
guard correctly refuses to create a scored manifest. Readability is preserved;
OCR must not be used to invent the missing truth labels because that would make
the evaluation circular.

## Ready-made external check

To provide an immediate independent check, a deterministic 300-image sample of
the official OpenALPR `seg_and_ocr` benchmark was frozen before inference and
evaluated with `scripts/evaluate_openalpr_ocr_benchmark.py`. The sample was
checked against 3,982 local LotTrace OCR training images: zero exact overlaps
and zero near-duplicate overlaps were found at dHash distance 1.

The first diagnostic incorrectly sent the known plate crops through the plate
detector again. It scored 233/300 exact (77.67%) and 92.22% character accuracy.
That is retained as a detector-plus-OCR diagnostic, not the isolated Stage 2
score. The corrected direct-crop OCR path uses the unmodified crop plus a
border-preserving padded derivative and never overwrites the source image.

Corrected development results on the already-cropped, full-colour US plates:

- OCR returned a string for 300/300 plates (100.00% read coverage);
- exact full-plate strings: 263/300 (87.67%);
- top-k exact full-plate strings: 264/300 (88.00%);
- correct characters: 96.30%;
- character error rate: 3.70% (66 edit operations across 1,786 truth
  characters);
- 95% Wilson interval for exact full-plate accuracy: 83.46%-90.92%.

For operational routing, a confidence threshold of 0.9995 was selected on this
development split and frozen before final evaluation. It automatically accepts
227/300 plates (75.67% coverage), of which 223/227 are exact (98.24%; 95%
Wilson interval 95.56%-99.31%). The other 73 go to review. This is accepted-read
precision, not overall OCR accuracy; the overall exact result remains 87.67%.

The frozen-manifest SHA-256 is
`64ece453527f190a27c1c309471a20235ce267007408fc10e2b7ec92a4caeb44`.
These 300 images are now explicitly the development split. The remaining 451
official images were locked as the final confirmation split and were not run
through the revised path until the model and acceptance policy were frozen.
This test proves no overlap with the known local fine-tuning folders, but a
public benchmark cannot prove that a third-party base model never encountered
the images during its own pretraining. It is also an OCR-crop test, not a
full-frame localization test.

## Frozen final confirmation

After the direct-crop model, preprocessing, and 0.9995 automatic-acceptance
threshold were frozen, the remaining 451 images were consumed once:

- OCR returned a string for 451/451 plates (100.00% read coverage);
- exact full-plate strings: 411/451 (91.13%; 95% Wilson interval
  88.15%-93.42%);
- top-k exact full-plate strings: 414/451 (91.80%);
- character accuracy: 97.79%; character error rate: 2.21%;
- automatic lane: 340/345 exact (98.55%; 95% Wilson interval
  96.65%-99.38%) at 76.50% coverage;
- review lane: 106/451 (23.50%);
- false exact assignments in the automatic lane: 5.

The final result confirms that the confidence gate exceeds 95% exact precision
for accepted single-crop reads. It does not establish 95% overall exact OCR:
the measured overall result is 91.13%. Production completion still requires a
labelled multi-frame dealership-video benchmark to measure event-level
consensus and its review rate.
