# License Plate Recognition v13 detector benchmark

Dataset: [License Plate Recognition v13 on Roboflow Universe](https://universe.roboflow.com/roboflow-universe-projects/license-plate-recognition-rxg4e/dataset/13)

- Licence: CC BY 4.0
- Export date recorded by the dataset: January 23, 2026
- Held-out test images: 1,020
- Ground-truth plate boxes: 1,085
- Model: `yolo-v9-t-384-license-plate-end2end` through FastALPR 0.4.0
- Device: CPU
- Detector confidence threshold: 0.40

## Results

| Metric | IoU 0.50 | IoU 0.70 |
|---|---:|---:|
| True positives | 995 | 851 |
| False positives | 25 | 169 |
| False negatives | 90 | 234 |
| Precision | 97.55% | 83.43% |
| Recall | 91.71% | 78.43% |
| F1 | 94.54% | 80.86% |
| Mean matched IoU | 80.53% | 83.30% |

The model produced 1,020 plate detections across 984 images. OCR returned a
plausible 4–10 character string for 984 detections (96.47% of detections).
Processing took 17.2 seconds, or 59.3 images per second, on the local CPU.

## Interpretation

At the standard IoU 0.50 threshold, the current detector is strong on this
held-out image set. The lower IoU 0.70 result shows that bounding-box placement
is less precise when judged strictly. Recall of 91.71% also means approximately
8.29% of labelled plates were missed at IoU 0.50, so the detector is not ready
for claims of complete coverage.

This dataset labels only the location of a plate. It does not contain the actual
plate characters, so the 96.47% OCR coverage figure is not OCR accuracy. Exact
text accuracy must be measured with a separate transcription-labelled dataset.

The full machine-readable result is in
`evaluation/license_plate_recognition_v13_detection_results.json`.
