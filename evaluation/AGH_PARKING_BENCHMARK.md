# AGH Parking Database smoke benchmark

Source: AGH University of Science and Technology, Parking Database:
https://qoe.agh.edu.pl/parking-database/

The source site makes its parking-camera sequences available to the research
community free of charge and requests citation of the associated papers. This
sample is for evaluation, not model training or a commercial accuracy claim.

## Method

- Five original 1280x720 parking-camera sequences, approximately 20.5 seconds each.
- Published vehicle registration plates from the dataset CSV are ground truth.
- LotTrace/FastALPR ran on CPU in Fast mode: 1 sampled frame per second, no tiles.
- A clip succeeds if at least one sampled frame contains an exact full-plate read.
- The frame-level exact rate denominator includes only sampled frames where the
  model returned at least one plate read. This is not a plate-visibility recall
  metric because this older ground truth does not label per-frame visibility.

## Result

- Clip-level exact retrieval: 5/5 (100%).
- Sampled frames: 105.
- Frames with any plate read: 95.
- Frames with the exact labelled plate: 90.
- Aggregate exact rate among frames with a read: 90/95 (94.7%).
- Total footage: 102.68 seconds.
- Sum of timed frame-processing passes: 2.602 seconds on the local CPU (model initialization excluded).

These values were reproduced locally on October 20, 2026 with FastALPR 0.4.0.

This is a small, favourable daylight smoke benchmark. It does not establish
performance on Ontario plates, night footage, glare, snow, temporary plates,
dealer plates, distant vehicles, or the dealership's actual camera geometry.

## Reproduce

```powershell
python scripts/evaluate_plate_clip.py `
  --video videos/agh_src1_hrc0.mp4 `
  --plate KMI77EV `
  --fps 1 `
  --no-tiles
```

The five converted MP4 files are intentionally ignored by Git. Download the
original AVI files from the dataset page and convert them to MP4 for use in the
LotTrace upload interface.
