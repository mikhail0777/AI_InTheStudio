# LotTrace exact-plate OCR experiment report

Date: 2026-10-22

## Decision

The existing 640-pixel YOLO character-sequence model remains the standalone OCR baseline. It measured 82.39% exact full-plate accuracy (131/159) on validation and 59.46% (22/37) on the small regression split. None of the newly trained standalone sequence readers exceeded it, so none replaced it.

A region-configured research ensemble improved validation to 85.53% (136/159) and regression to 62.16% (23/37) by using a fine-tuned PARSeq reading only when YOLO returned the wrong configured character count. This is an experimental candidate-ranking result, not a production release result. The 37-image split has been inspected repeatedly, the constraint applies only to explicitly configured seven-character regions, and the result does not measure full video events.

The 99% exact-plate release gate is not met. There is still no fully labelled, untouched dealership-video event benchmark measuring crossings, multi-frame consensus, plate association, or false sightings per hour.

## Protected data policy

The merged research derivative uses 2,273 eligible single-row training crops. Validation contains 159 primary-source crops. The 37-image regression split remained unused during model training and validation threshold selection, but it is now a development regression set because prior experiments and their failures have been inspected. Supplemental validation and test images remain reserved. No uploaded archive, extracted image, trained checkpoint, or detailed prediction file is tracked in Git.

## Measured experiments

| Reader | Validation exact | Validation character | Regression exact | Decision |
|---|---:|---:|---:|---|
| YOLO11n character detector, 640 px | 82.39% (131/159) | 95.78% | 59.46% (22/37) | Retain standalone baseline |
| Expanded-data YOLO11n, 640 px | 79.25% (126/159) | 94.79% | Not run | Reject before regression |
| FastPlateOCR global MobileViT v2 | 57.86% (92/159) | 87.51% | 29.73% (11/37) | Reject |
| From-scratch CRNN/CTC | 0.00% (0/159) | 7.46% | Not run | Reject before regression |
| Official pretrained PARSeq | 25.16% (40/159) | 80.50% | Not run | Reject before regression |
| PARSeq, first fine-tune stage | 66.67% (106/159) | 92.63% | 54.05% (20/37) | Reject as standalone |
| PARSeq, lower-rate continuation | 72.33% (115/159) | 93.80% | Not run | Reject before regression |
| PARSeq, realistic-augmentation continuation | 72.96% (116/159) | 93.98% | Not run | Reject before regression |
| YOLO + length-ranked PARSeq experiment | 85.53% (136/159) | 96.50% | 62.16% (23/37) | Research candidate only |

The open-source comparison also evaluated the available FastPlateOCR CCT variants. The table shows the best of those pretrained models. Open-source availability did not make a reader accurate on this dataset without domain adaptation.

PaddleOCR and LPRNet were not represented as completed benchmarks. The current runtime is Python 3.14 on CPU, no compatible local PaddlePaddle installation is present, and no licensed pretrained LPRNet checkpoint with matching character vocabulary was supplied. Inventing numbers or comparing differently labelled outputs would not be a valid benchmark.

## Failure analysis

The retained YOLO validation baseline missed 28 of 159 complete plates. Diagnostic alignment counted 28 substitutions, 12 missing characters, and 7 extra characters; one failed plate can contribute more than one edit category. `I` to `T` was the only aligned substitution observed twice; the remaining leading substitutions occurred once each. Deterministic image checks did not mark these 28 crops as small, dark, bright, low-contrast, or low-sharpness under the current thresholds. Rain, glare, skew, occlusion, and plate style were not guessed because those conditions lack human labels.

PARSeq and YOLO were complementary on validation: PARSeq correctly read 10 YOLO failures, while YOLO correctly read 35 PARSeq failures. An oracle choosing the correct reader would reach only 141/159 (88.68%), demonstrating that this pair alone cannot reach 99%.

## Review calibration and multi-frame safety

Raw OCR confidence did not support a 99% auto-accept policy. At a conservative minimum-character confidence of 0.85, the YOLO validation reader accepted 102/159 crops with 94.12% exact precision (96/102), and the 95% Wilson lower bound was 87.76%. No tested threshold with at least 20 accepted examples had a 95% lower bound of 99%, so no production auto-accept threshold was selected.

Multi-frame consensus now requires the same exact normalized string on at least two independent frames, adequate weighted OCR support, and no similarly supported competitor. Repeated low-confidence readings remain `uncertain`. Near matches and confusion variants are preserved as review-only alternatives and never silently rewritten into a confirmed identity.

## Reproducibility

Tracked tools now reproduce:

- official PARSeq inference and fine-tuning;
- exact plate and character metrics with Wilson intervals;
- validation-selected, fixed-threshold ensemble evaluation;
- substitution, missing-character, extra-character, and image-quality diagnostics;
- confidence/coverage calibration for `requires review` routing.

Detailed predictions, model checkpoints, training histories, and generated audit JSON remain under ignored `datasets/extracted` paths. The best augmented PARSeq checkpoint SHA-256 is `fc3743bea5127aa62f9a460b967134e6316905a2afff923d6cd1147aa8b77c72`.

## Next evidence needed

Further gains require human adjudication of the 480 disputed OCR crops, more target-region fully transcribed plates, and multiple independently labelled frames for each vehicle track. A genuinely untouched dealership-video test split must be held back by site, camera, vehicle, and recording date. The next video benchmark must report exact event-level plate accuracy, crossing recall, association precision/recall, duplicate events, review rate, and false sightings per hour. Until that exists and passes the declared gates, LotTrace must not be called 99% accurate or production-certified.

## Software verification

- Backend and tooling: 206 passed; one existing Starlette/httpx deprecation warning.
- Frontend behavior: 17 passed. Vite logged a recoverable sandbox cache-cleanup `EPERM`; the test command passed.
- Browser end-to-end: 7 passed in headless Chrome.
- TypeScript and Vite production build: passed; 1,481 modules transformed.

These tests verify software behavior. They do not increase or substitute for labelled OCR or dealership-video accuracy.
