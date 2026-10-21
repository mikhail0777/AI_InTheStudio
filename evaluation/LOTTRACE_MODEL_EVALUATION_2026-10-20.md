# LotTrace model evaluation — 2026-10-20

## Decision

**The evaluated models are not yet production-certified.** Plate localization is strong on two public image sets, but full-plate OCR accuracy remains unmeasured because the OCR-labelled set masks two characters per plate. General COCO vehicle detection is materially below a production evidence threshold and is weakest on trucks and small vehicles. These still-image sets do not represent dealership video.

No accuracy number below was inferred from model confidence. No synthetic data or unlabelled examples were scored as ground truth.

## Labelled accuracy results

| Capability | Dataset and denominator | Result | Interpretation |
|---|---|---|---|
| Plate localization @ IoU 0.50 | Existing held-out plate-box set: 1,020 images / 1,085 plates | P 97.55%; R 91.71%; F1 94.54% | Box localization only; no text labels |
| Production-path plate localization @ IoU 0.50 | UC3M held-out test: 395 images / 491 plates | P 96.56%; R 97.15%; F1 96.85% | Spanish/European still images |
| Published-position OCR sequence | UC3M held-out test: 491 plates | 82.69% (406/491) | Released positions only; not exact full-plate accuracy |
| Published-character error rate | UC3M held-out test: 2,458 released characters | 6.02% CER | Two masked positions per plate are excluded |
| Vehicle mAP @ IoU 0.50 | COCO val2017: 5,000 images / 2,982 vehicle boxes | 66.98% | General car/motorcycle/bus/truck detection |
| Vehicle mAP @ IoU 0.50:0.95 | Same 5,000 images | 43.36% | Stricter localization |
| Vehicle operating point @ confidence 0.25 | Same 5,000 images | P 69.24%; R 65.90%; F1 67.53% | Current deployed threshold |

Plate localization was exercised on 2,995 labelled images across the existing plate-box set and UC3M. This is not thousands of fully transcribed plates: the first set has no text labels, and UC3M masks two characters in every plate.

## Plate OCR, localization, and search

The complete UC3M production-path run covered 1,975 images and 2,547 plates. On its official held-out test, read coverage was 97.15%; published-position sequence accuracy was 82.69% with a 95% Wilson interval of 79.09%–85.78%.

**Full exact-plate OCR and top-k full-plate accuracy are unavailable.** UC3M replaces two privacy-sensitive characters in every string with `*`; the existing 1,020-image set has no text labels. A transcription-labelled, legally usable, target-region held-out set is still required.

Two-character partial search on the UC3M held-out test produced P 68.46%, R 95.03%, and F1 79.58% across 399 queries. Exact search cannot be labelled from masked strings.

### OCR candidate selection

Four OCR checkpoints were compared on 2,056 official training plates using ground-truth crops. The current `cct-xs-v2-global-model` ranked first at 81.42% published-position sequence accuracy and 4.93% CER. Confirmation on 491 held-out crops produced 81.47% sequence accuracy and 4.27% CER. The current OCR model was retained; all three alternatives regressed on the selection set.

## Vehicle detection

The full COCO evaluation used all 5,000 validation images, including 4,204 images with no target-class annotation. AP used a 0.001 prediction floor; operating values used confidence 0.25 and NMS IoU 0.50.

| Class | Ground truth | AP50 | AP50–95 | Precision @ .25 | Recall @ .25 | F1 @ .25 |
|---|---:|---:|---:|---:|---:|---:|
| car | 1,918 | 71.51% | 48.17% | 69.19% | 67.21% | 68.18% |
| motorcycle | 367 | 70.09% | 39.97% | 73.80% | 66.76% | 70.10% |
| bus | 283 | 75.57% | 52.24% | 78.99% | 71.73% | 75.19% |
| truck | 414 | 50.75% | 33.06% | 59.07% | 55.07% | 57.00% |

Recall by COCO size was small 55.74% (801/1437), medium 75.73%, and large 74.76%. There were 44 detections across 4,204 negative images (0.0105 per negative image). This cannot be converted into false sightings per hour.

### Improvement experiments

Threshold 0.30 maximized F1 on the 2,500-image tuning half, but on the 2,500-image confirmation half it scored 67.37% F1 versus 67.97% at 0.25. The 0.25 production threshold was retained.

On a fixed 1,000-image comparison subset, YOLO11s-seg scored mAP50 70.36%, mAP50–95 46.76%, and F1 69.81%. YOLO11m-seg scored 70.53%, 47.51%, and 71.35%, while running at 1.21 images/s versus 3.84 images/s for the current model on the same CPU configuration. The small mAP gain did not justify roughly 3.2× slower inference; the medium model was not promoted.

The COCO model detects only **car, motorcycle, bus, and truck**. It does not identify make, model, or year. COCO cannot evaluate colour, tracking, plate-to-vehicle association, or false sightings per hour.

## Functional coverage is not labelled accuracy

Automated backend, frontend, and browser tests verify software behavior and persistence; they do not establish model accuracy. The labelled values above establish accuracy only within their named datasets. The previously measured production-path plate-to-vehicle association was 160/978 (16.36%) on a plate-focused set; that is coverage, not accuracy. A separate 2026-10-20 slideshow diagnostic found a vehicle in 8/60 sampled frames and is diagnostic evidence, not a labelled benchmark.

## Required deployment benchmark

Production certification requires a separately collected and labelled dealership-video test set, isolated by site/camera/vehicle/date, with day/night, weather, glare, blur, distance, angle, occlusion, front/rear, stationary/moving, negative video, track identity, event timestamps, full plate transcriptions, plate-to-vehicle links, and colour labels. It must report event recall, exact full-plate accuracy, CER, false positives and false sightings per hour, timestamp error, track continuity, duplicate tracks, association precision/recall, and peak resource use. Fine-tuning must use a disjoint training set and predeclared acceptance thresholds.

## Reproducibility and provenance

- Repository base revision: `43a6f70869315d29b4e5b91713fd4d37340856bf`; evaluation work is uncommitted.
- UC3M archive: 4,547,680,070 bytes; SHA-256 `3b7ad51067341540acc26ab77f0069f0033e91e6a5fbaf8f07468824aabb223d`; publisher MD5 `496e3b5e66b78d231f71d85c0e5e11a3`; ODbL-1.0.
- COCO archives: `val2017.zip` SHA-256 `4f7e2ccb2866ec5041993c9cf2a952bbed69647b115d0f74da7ce8f4bef82f05`; `annotations_trainval2017.zip` SHA-256 `113a836d90195ee1f884e704da6304dfaaecff1f023f49b6ca93c4aaae470268`.
- Plate pipeline: `yolo-v9-t-384-license-plate-end2end+cct-xs-v2-global-model`, fast-alpr 0.4.0, CPU; detector SHA-256 `888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8`; OCR SHA-256 `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`.
- Vehicle pipeline: YOLO11s-seg SHA-256 `1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3`, CPU, image size 1280, confidence 0.25, NMS IoU 0.5.
- Environment: `Windows-11-10.0.26300-SP0`; `3.14.8 (tags/v3.14.8:8e6e75d, Sep 30 2026, 18:19:33) [MSC v.1944 64 bit (AMD64)]`; ultralytics 8.4.148; torch 2.14.1+cpu.
- Evaluation code `scripts/evaluation_metrics.py` SHA-256 `154ffe4ff7a86bee7c46796f86954ae9fb5994b9c6bb96498d5ad9971058c883`.
- Evaluation code `scripts/evaluate_uc3m_alpr.py` SHA-256 `ca5256d5eed4f9860a6bf4a103fc0e0542e6e8ade5a107daa5e906957ab68dcd`.
- Evaluation code `scripts/compare_uc3m_ocr_models.py` SHA-256 `96b01c6113319927185f3737a84bff2afeb98742c946360205ce12bd142af0cf`.
- Evaluation code `scripts/evaluate_coco_vehicle_detection.py` SHA-256 `65caaed31e068da545ef1f4ee0cc1202afd016942855d1526b141982b873018c`.
- Evaluation code `scripts/tune_coco_vehicle_threshold.py` SHA-256 `9097dc96d05e258a418cf0089dd9fcaffc83f07d2a2e2544d6d9a3350731a3f1`.

Sources: [UC3M-LP repository](https://github.com/ramajoballester/UC3M-LP), [UC3M-LP Zenodo record](https://zenodo.org/records/17152029), [COCO downloads](https://cocodataset.org/#download), and [official Ultralytics YOLO11 documentation](https://docs.ultralytics.com/models/yolo11).
