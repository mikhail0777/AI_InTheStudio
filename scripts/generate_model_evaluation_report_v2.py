"""Generate the corrected, auditable LotTrace plate/vehicle evaluation report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"


def load(name: str) -> dict:
    path = EVAL / name
    if not path.is_file():
        raise SystemExit(f"Missing required result: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    box = load("license_plate_recognition_v13_detection_results.json")
    plate_all = load("uc3m_alpr_production_all.json")
    plate_test = load("uc3m_alpr_production_test.json")
    ocr_compare = load("uc3m_ocr_model_comparison_train.json")
    ocr_test = load("uc3m_ocr_selected_test.json")
    vehicle = load("coco_vehicle_results.json")
    small = load("coco_vehicle_yolo11s_tuning1000.json")
    medium = load("coco_vehicle_yolo11m_tuning1000.json")
    calibration = load("coco_vehicle_threshold_calibration.json")
    manifest = json.loads((EVAL / "datasets" / "manifest.json").read_text(encoding="utf-8"))
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"

    box50 = box["metrics"]["iou_0.50"]
    p50 = plate_test["localization"]["iou_0.50"]
    ocr = plate_test["ocr"]
    coco = vehicle["metrics"]
    op = coco["operating_point_iou_0.50"]
    winner = ocr_compare["ranking"][0]
    train_winner = ocr_compare["models"][winner]
    crop_test = ocr_test["models"][winner]
    new_threshold = calibration["confirmation_result"]["micro"]
    old_threshold = calibration["confirmation_at_previous_0.25"]["micro"]
    sm = small["metrics"]
    md = medium["metrics"]
    total_plate_images = box["images_evaluated"] + plate_all["dataset"]["images_evaluated"]

    lines = [
        "# LotTrace model evaluation — 2026-10-20",
        "",
        "## Decision",
        "",
        "**The evaluated models are not yet production-certified.** Plate localization is strong on two public image sets, but full-plate OCR accuracy remains unmeasured because the OCR-labelled set masks two characters per plate. General COCO vehicle detection is materially below a production evidence threshold and is weakest on trucks and small vehicles. These still-image sets do not represent dealership video.",
        "",
        "No accuracy number below was inferred from model confidence. No synthetic data or unlabelled examples were scored as ground truth.",
        "",
        "## Labelled accuracy results",
        "",
        "| Capability | Dataset and denominator | Result | Interpretation |",
        "|---|---|---|---|",
        f"| Plate localization @ IoU 0.50 | Existing held-out plate-box set: {box['images_evaluated']:,} images / {box['ground_truth_plates']:,} plates | P {pct(box50['precision'])}; R {pct(box50['recall'])}; F1 {pct(box50['f1'])} | Box localization only; no text labels |",
        f"| Production-path plate localization @ IoU 0.50 | UC3M held-out test: {plate_test['dataset']['images_evaluated']:,} images / {plate_test['dataset']['ground_truth_plates']:,} plates | P {pct(p50['precision'])}; R {pct(p50['recall'])}; F1 {pct(p50['f1'])} | Spanish/European still images |",
        f"| Published-position OCR sequence | UC3M held-out test: {ocr['plates_with_published_partial_transcription']:,} plates | {pct(ocr['published_position_plate_accuracy'])} ({ocr['published_position_exact_matches']}/{ocr['plates_with_published_partial_transcription']}) | Released positions only; not exact full-plate accuracy |",
        f"| Published-character error rate | UC3M held-out test: {ocr['published_ground_truth_characters']:,} released characters | {pct(ocr['published_character_error_rate'])} CER | Two masked positions per plate are excluded |",
        f"| Vehicle mAP @ IoU 0.50 | COCO val2017: {vehicle['dataset']['images_evaluated']:,} images / {vehicle['dataset']['ground_truth_vehicle_instances']:,} vehicle boxes | {pct(coco['mean_ap_iou_0.50'])} | General car/motorcycle/bus/truck detection |",
        f"| Vehicle mAP @ IoU 0.50:0.95 | Same 5,000 images | {pct(coco['mean_ap_iou_0.50_0.95'])} | Stricter localization |",
        f"| Vehicle operating point @ confidence 0.25 | Same 5,000 images | P {pct(op['precision'])}; R {pct(op['recall'])}; F1 {pct(op['f1'])} | Current deployed threshold |",
        "",
        f"Plate localization was exercised on {total_plate_images:,} labelled images across the existing plate-box set and UC3M. This is not thousands of fully transcribed plates: the first set has no text labels, and UC3M masks two characters in every plate.",
        "",
        "## Plate OCR, localization, and search",
        "",
        f"The complete UC3M production-path run covered {plate_all['dataset']['images_evaluated']:,} images and {plate_all['dataset']['ground_truth_plates']:,} plates. On its official held-out test, read coverage was {pct(ocr['read_coverage'])}; published-position sequence accuracy was {pct(ocr['published_position_plate_accuracy'])} with a 95% Wilson interval of {pct(ocr['published_position_plate_accuracy_wilson_95'][0])}–{pct(ocr['published_position_plate_accuracy_wilson_95'][1])}.",
        "",
        "**Full exact-plate OCR and top-k full-plate accuracy are unavailable.** UC3M replaces two privacy-sensitive characters in every string with `*`; the existing 1,020-image set has no text labels. A transcription-labelled, legally usable, target-region held-out set is still required.",
        "",
        f"Two-character partial search on the UC3M held-out test produced P {pct(plate_test['search']['partial_2_character']['precision'])}, R {pct(plate_test['search']['partial_2_character']['recall'])}, and F1 {pct(plate_test['search']['partial_2_character']['f1'])} across {plate_test['search']['partial_2_character']['queries']:,} queries. Exact search cannot be labelled from masked strings.",
        "",
        "### OCR candidate selection",
        "",
        f"Four OCR checkpoints were compared on 2,056 official training plates using ground-truth crops. The current `{winner}` ranked first at {pct(train_winner['published_position_plate_accuracy'])} published-position sequence accuracy and {pct(train_winner['published_character_error_rate'])} CER. Confirmation on 491 held-out crops produced {pct(crop_test['published_position_plate_accuracy'])} sequence accuracy and {pct(crop_test['published_character_error_rate'])} CER. The current OCR model was retained; all three alternatives regressed on the selection set.",
        "",
        "## Vehicle detection",
        "",
        "The full COCO evaluation used all 5,000 validation images, including 4,204 images with no target-class annotation. AP used a 0.001 prediction floor; operating values used confidence 0.25 and NMS IoU 0.50.",
        "",
        "| Class | Ground truth | AP50 | AP50–95 | Precision @ .25 | Recall @ .25 | F1 @ .25 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in coco["per_class"].items():
        item_op = item["operating_point_iou_0.50"]
        lines.append(f"| {label} | {item['ground_truth_instances']:,} | {pct(item['ap_iou_0.50'])} | {pct(item['ap_iou_0.50_0.95'])} | {pct(item_op['precision'])} | {pct(item_op['recall'])} | {pct(item_op['f1'])} |")
    sizes = coco["recall_by_coco_object_size_at_operating_threshold"]
    lines += [
        "",
        f"Recall by COCO size was small {pct(sizes['small']['recall'])} ({sizes['small']['matched']}/{sizes['small']['ground_truth']}), medium {pct(sizes['medium']['recall'])}, and large {pct(sizes['large']['recall'])}. There were {coco['false_detections_on_negative_images']} detections across {vehicle['dataset']['negative_images']:,} negative images ({coco['false_detections_per_negative_image']:.4f} per negative image). This cannot be converted into false sightings per hour.",
        "",
        "### Improvement experiments",
        "",
        f"Threshold 0.30 maximized F1 on the 2,500-image tuning half, but on the 2,500-image confirmation half it scored {pct(new_threshold['f1'])} F1 versus {pct(old_threshold['f1'])} at 0.25. The 0.25 production threshold was retained.",
        "",
        f"On a fixed 1,000-image comparison subset, YOLO11s-seg scored mAP50 {pct(sm['mean_ap_iou_0.50'])}, mAP50–95 {pct(sm['mean_ap_iou_0.50_0.95'])}, and F1 {pct(sm['operating_point_iou_0.50']['f1'])}. YOLO11m-seg scored {pct(md['mean_ap_iou_0.50'])}, {pct(md['mean_ap_iou_0.50_0.95'])}, and {pct(md['operating_point_iou_0.50']['f1'])}, while running at {medium['runtime']['new_images_per_second']:.2f} images/s versus {vehicle['runtime']['new_images_per_second']:.2f} images/s for the current model on the same CPU configuration. The small mAP gain did not justify roughly 3.2× slower inference; the medium model was not promoted.",
        "",
        "The COCO model detects only **car, motorcycle, bus, and truck**. It does not identify make, model, or year. COCO cannot evaluate colour, tracking, plate-to-vehicle association, or false sightings per hour.",
        "",
        "## Functional coverage is not labelled accuracy",
        "",
        "Automated backend, frontend, and browser tests verify software behavior and persistence; they do not establish model accuracy. The labelled values above establish accuracy only within their named datasets. The previously measured production-path plate-to-vehicle association was 160/978 (16.36%) on a plate-focused set; that is coverage, not accuracy. A separate 2026-10-20 slideshow diagnostic found a vehicle in 8/60 sampled frames and is diagnostic evidence, not a labelled benchmark.",
        "",
        "## Required deployment benchmark",
        "",
        "Production certification requires a separately collected and labelled dealership-video test set, isolated by site/camera/vehicle/date, with day/night, weather, glare, blur, distance, angle, occlusion, front/rear, stationary/moving, negative video, track identity, event timestamps, full plate transcriptions, plate-to-vehicle links, and colour labels. It must report event recall, exact full-plate accuracy, CER, false positives and false sightings per hour, timestamp error, track continuity, duplicate tracks, association precision/recall, and peak resource use. Fine-tuning must use a disjoint training set and predeclared acceptance thresholds.",
        "",
        "## Reproducibility and provenance",
        "",
        f"- Repository base revision: `{revision}`; evaluation work is uncommitted.",
        f"- UC3M archive: {manifest['uc3m']['assets'][0]['bytes']:,} bytes; SHA-256 `{manifest['uc3m']['assets'][0]['sha256']}`; publisher MD5 `{manifest['uc3m']['assets'][0]['md5']}`; ODbL-1.0.",
        "- COCO archives: " + "; ".join(f"`{item['name']}` SHA-256 `{item['sha256']}`" for item in manifest["coco"]["assets"]) + ".",
        f"- Plate pipeline: `{plate_test['model']['model_name']}`, fast-alpr {plate_test['model']['model_version']}, CPU; detector SHA-256 `888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8`; OCR SHA-256 `8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44`.",
        f"- Vehicle pipeline: YOLO11s-seg SHA-256 `{vehicle['model']['sha256']}`, CPU, image size {vehicle['model']['image_size']}, confidence {vehicle['model']['operating_confidence_threshold']}, NMS IoU {vehicle['model']['nms_iou']}.",
        f"- Environment: `{vehicle['runtime']['platform']}`; `{vehicle['runtime']['python'].splitlines()[0]}`; ultralytics 8.4.148; torch 2.14.1+cpu.",
    ]
    for relative in (
        "scripts/evaluation_metrics.py", "scripts/evaluate_uc3m_alpr.py",
        "scripts/compare_uc3m_ocr_models.py", "scripts/evaluate_coco_vehicle_detection.py",
        "scripts/tune_coco_vehicle_threshold.py",
    ):
        lines.append(f"- Evaluation code `{relative}` SHA-256 `{sha(ROOT / relative)}`.")
    lines += [
        "",
        "Sources: [UC3M-LP repository](https://github.com/ramajoballester/UC3M-LP), [UC3M-LP Zenodo record](https://zenodo.org/records/17152029), [COCO downloads](https://cocodataset.org/#download), and [official Ultralytics YOLO11 documentation](https://docs.ultralytics.com/models/yolo11).",
        "",
    ]
    output = EVAL / "LOTTRACE_MODEL_EVALUATION_2026-10-20.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
