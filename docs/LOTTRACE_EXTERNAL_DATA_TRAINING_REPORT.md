# LotTrace external-data training report

Date: 2026-10-21

## Outcome

The uploaded archives were inventoried, hashed, checked for safe extraction, and classified by label and licence suitability. One OCR source supports a defensible character-detection experiment. Its leakage-safe derivative was trained and evaluated, improving held-out cropped-plate exact accuracy from 56.76% (21/37) at 320 pixels to 59.46% (22/37) at 640 pixels. Character accuracy improved from 88.42% to 89.19%.

This is **not** a production result. It is 22 exact reads on 37 selected, cropped, single-row plates—not vehicle crossings, tracks, multi-frame consensus, plate-to-vehicle associations, or negative video hours. The 99% release gates remain unmet and dealership-video gates remain unmeasured.

## Archive inventory

All archives and extracted data remain excluded from Git. SHA-256 values identify the exact local inputs.

| Archive | Bytes | SHA-256 |
|---|---:|---|
| `DETRAC-Images.zip` | 9,849,591,986 | `b8159ae798136ef7cdbb7dcbb76840b7aaff2545f130a7e3d1d73bc030feeb99` |
| `DETRAC-Test-Annotations-MAT.zip` | 2,096,385 | `8d32f42bbaf298f340dc92275641809bac493384063debd8454b34b8a58fa721` |
| `DETRAC-Test-Annotations-XML.zip` | 12,239,887 | `c274a7a96b33445e13693f2d0082d58acac34c94275ee89b8378c4348a6b3209` |
| `DETRAC-Train-Annotations-MAT.zip` | 3,415,321 | `a9f8829c901007842507dfeeb082a8561579e9b1e804de1fc9fac3828bdefd80` |
| `DETRAC-Train-Annotations-XML.zip` | 12,797,880 | `d6ce5dcf409680096fea289f4731e56d014cc7667a013f35a5eb6a8261cf8f0f` |
| `License Plate - OCR.v1i.yolov8.zip` | 77,105,743 | `0951ece823ec583183fd4a087c111e60e9b86b60d7794df6ce91d45e8b897e4d` |
| `license plate ocr.v1i.yolov8.zip` | 79,628,032 | `63dd62adad8a767ca0af7ac726afebc0cba43b696c2d7eb0e458a6a22c8c2f6e` |
| `videos.zip` | 2,807,640,228 | `ba3f17b26064f15dd97d204a781af4f6cb78b5e76657ad70c5812037b411bd91` |
| `VMMRdb.zip` | 12,354,779,003 | `162bcd8a3ba61d52b9529cba96bfa6ed031d8375c3306340d0fdc1e0c638014a` |

## Suitability decisions

| Source | Labels found | Licence/provenance finding | Current use |
|---|---|---|---|
| 36-class plate OCR | YOLO character boxes; filenames contain candidate full strings | Dataset declares CC BY 4.0 | Leakage-safe character training and exact cropped-plate evaluation |
| 31-class plate OCR | YOLO character boxes and class chart | Dataset metadata says Private; project owner attests owner permission for this school research | Permitted for local research training; still unsuitable as independent full-string test truth |
| UA-DETRAC | Vehicle boxes, track IDs, vehicle type, occlusion, truncation, illumination | Public terms were absent from supplied material; project owner attests research permission | Permitted for local research experiments; not represented as commercially cleared |
| VMMRdb | Make/model-labelled image hierarchy | Repository's MIT file covers software; project owner attests research permission for supplied images | Permitted for local school-research training/evaluation; redistribution remains excluded |
| OpenPK | Vehicle trajectories and video | Repository requests research permission; project owner attests that permission was obtained | Permitted for local research; machine-generated tracks remain distinct from human ground truth |

The permission record is in `docs/LOTTRACE_RESEARCH_DATA_PERMISSION.md`. Public download availability alone was not treated as permission; the updated research decision relies on the project owner's explicit attestation.

## OCR preparation

The source 36-class data contained competing filename tokens and five visibly inconsistent examples in its original 42-image test partition. `prepare_consensus_ocr_dataset.py` retained only single-row samples whose spatially ordered character labels agree with at least one plausible filename token. It then separated identical plate strings with test-first split priority so no plate identity crosses train, validation, or test.

The resulting derivative contains 1,307 train, 159 validation, and 37 test plates. Original files and labels were preserved. This filtering makes the experiment reproducible, but it also selects cleaner examples and therefore cannot represent unconstrained traffic video.

## Training and evaluation

The initial YOLO11n 320-pixel run trained for 30 CPU epochs. The 640-pixel run fine-tuned its best checkpoint for 15 CPU epochs using deterministic seed 0, no horizontal flip, small rotation/translation/scale augmentation, and validation checkpoint selection. The 640 run completed in 0.575 hours.

| Measurement | 320 model | 640 fine-tune |
|---|---:|---:|
| Validation box precision | 92.86% | 93.95% |
| Validation box recall | 92.38% | 95.27% |
| Validation mAP50 | 94.42% | 95.81% |
| Validation mAP50-95 | 77.18% | 78.40% |
| Validation exact plate | 67.30% (107/159), threshold 0.40 | 82.39% (131/159), threshold 0.50 |
| Test exact plate | 56.76% (21/37) | 59.46% (22/37) |
| Test character accuracy | 88.42% | 89.19% |
| Test read coverage | 100% | 100% |

The 640 test exact-plate 95% Wilson interval is 43.49%–73.65%. Its checkpoint SHA-256 is `776ce2829937f28a9441a90fec514b7a0db8f4a115ef9d780a1bcdafbf3bfcb3`; the 320 checkpoint hash is `2b4ea134f69dce2dc5d6fbbacad2fc2f6b83d7cfe094f45d67f565d60937607d`.

The threshold was selected once on validation and fixed at 0.50 before test inference. Model confidence was not reported as accuracy. Full per-image predictions stay in ignored local audit JSON files; the concise measured result is recorded in `evaluation/LOTTRACE_EXTERNAL_DATA_OCR_2026-10-21.json`.

## Release decision and next work

The 640 model is the stronger of these two experiments, but neither checkpoint should replace the production reader solely from this small proxy set. The next defensible OCR step is a larger, target-region, fully transcribed dealership-video corpus with independent frames grouped into vehicle events. The supplied datasets are now permitted for local school research under the owner's attestation. UA-DETRAC still has no readable plate truth and cannot close an exact-plate gate; OpenPK's machine-generated tracks cannot be reported as independent human ground truth. Commercial and redistribution rights remain a separate future review.

No model, dataset, accuracy result, or release gate was fabricated. No commit contains the uploaded archives or trained checkpoints.

## Verification

- Backend and tooling regression suite: 192 passed; one existing Starlette/httpx deprecation warning.
- Frontend behavior tests: 17 passed. Vite logged a recoverable sandbox cleanup `EPERM` during the test command; the command exited successfully.
- TypeScript and Vite production build: passed (1,481 modules transformed).
- OCR tooling subset, including the reproducible trainer validation: 10 passed.

Software test results establish functional behavior only. They are separate from the labelled OCR measurements above.
