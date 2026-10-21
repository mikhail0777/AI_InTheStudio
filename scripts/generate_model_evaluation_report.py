"""Compatibility entry point for the corrected LotTrace evaluation report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing required result: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def percent(value: float) -> str:
    return f"{100 * value:.2f}%"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plate-box", type=Path,
                        default=ROOT / "evaluation" / "license_plate_recognition_v13_detection_results.json")
    parser.add_argument("--plate-full-frame", type=Path,
                        default=ROOT / "evaluation" / "uc3m_alpr_full_frame_all.json")
    parser.add_argument("--plate-production-test", type=Path,
                        default=ROOT / "evaluation" / "uc3m_alpr_production_test.json")
    parser.add_argument("--vehicle", type=Path,
                        default=ROOT / "evaluation" / "coco_vehicle_results.json")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "evaluation" / "datasets" / "manifest.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "evaluation" / "LOTTRACE_MODEL_EVALUATION_2026-10-20.md")
    args = parser.parse_args()
    plate_box = load(args.plate_box)
    plate_all = load(args.plate_full_frame)
    plate_test = load(args.plate_production_test)
    vehicle = load(args.vehicle)
    manifest = load(args.manifest)
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unavailable"
    code_files = [
        ROOT / "scripts" / "evaluation_metrics.py",
        ROOT / "scripts" / "evaluate_uc3m_alpr.py",
        ROOT / "scripts" / "evaluate_coco_vehicle_detection.py",
    ]
    box50 = plate_box["metrics"]["iou_0.50"]
    uc50 = plate_test["localization"]["iou_0.50"]
    ocr = plate_test["ocr"]
    coco = vehicle["metrics"]
    lines = [
        "# LotTrace model evaluation — 2026-10-20",
        "",
        "## Decision",
        "",
        "**LotTrace is not yet certified as production-accurate.** The public benchmarks below are "
        "real, labelled, reproducible tests, but neither UC3M-LP nor COCO represents the required "
        "dealership cameras, geography, weather, motion, retention pipeline, or complete-video event "
        "distribution. Scores are evidence about model behavior, not a deployment guarantee.",
        "",
        "## Results at a glance",
        "",
        "| Claim | Dataset / denominator | Result | What it proves |",
        "|---|---:|---:|---|",
        f"| Plate-box localization @ IoU 0.50 | Existing held-out set: {plate_box['images_evaluated']:,} images / "
        f"{plate_box['ground_truth_plates']:,} plates | P {percent(box50['precision'])}, "
        f"R {percent(box50['recall'])}, F1 {percent(box50['f1'])} | Plate boxes only; no text labels |",
        f"| Production-path plate localization @ IoU 0.50 | UC3M test: "
        f"{plate_test['dataset']['images_evaluated']:,} images / {plate_test['dataset']['ground_truth_plates']:,} plates | "
        f"P {percent(uc50['precision'])}, R {percent(uc50['recall'])}, F1 {percent(uc50['f1'])} | "
        "External European-plate generalization |",
        f"| Exact plate OCR | UC3M test: {ocr['eligible_fully_labelled_plates']:,} fully labelled plates | "
        f"{percent(ocr['exact_plate_accuracy'])} ({ocr['exact_matches']:,} exact) | End-to-end transcription accuracy |",
        f"| Character error rate | UC3M test: {ocr['ground_truth_characters']:,} labelled characters | "
        f"{percent(ocr['character_error_rate'])} | Character-level edit error |",
        f"| Vehicle mAP @ IoU 0.50 | COCO val2017: {vehicle['dataset']['images_evaluated']:,} images / "
        f"{vehicle['dataset']['ground_truth_vehicle_instances']:,} vehicle boxes | "
        f"{percent(coco['mean_ap_iou_0.50'])} | General COCO car/truck/bus/motorcycle detection |",
        f"| Vehicle mAP @ IoU 0.50:0.95 | same | {percent(coco['mean_ap_iou_0.50_0.95'])} | Stricter localization quality |",
        "",
        "## Plate OCR and search",
        "",
        f"UC3M-LP supplies {plate_all['dataset']['images_evaluated']:,} evaluated images in this run and "
        f"{plate_all['dataset']['ground_truth_plates']:,} annotated plates. Exact OCR/CER omit labels containing "
        "`*`, which the publisher uses for unreadable or occluded characters.",
        "",
        f"- Held-out exact OCR: **{percent(ocr['exact_plate_accuracy'])}**; 95% Wilson interval "
        f"{percent(ocr['exact_plate_accuracy_wilson_95'][0])}–{percent(ocr['exact_plate_accuracy_wilson_95'][1])}.",
        f"- Held-out read coverage: **{percent(ocr['read_coverage'])}**.",
        f"- Held-out CER: **{percent(ocr['character_error_rate'])}**; normalized edit similarity "
        f"**{percent(ocr['normalized_edit_similarity'])}**.",
        f"- Exact search: P {percent(plate_test['search']['exact']['precision'])}, "
        f"R {percent(plate_test['search']['exact']['recall'])} across "
        f"{plate_test['search']['exact']['queries']:,} unique queries.",
        f"- Four-character partial search: P {percent(plate_test['search']['partial_4_character']['precision'])}, "
        f"R {percent(plate_test['search']['partial_4_character']['recall'])} across "
        f"{plate_test['search']['partial_4_character']['queries']:,} unique queries.",
        "- Top-k equals top-1 because the production OCR returns one transcription per localized plate.",
        "",
        "## Vehicle detection",
        "",
        "The vehicle evaluator uses all selected COCO validation images, including images with no labelled "
        "car, truck, bus, or motorcycle. AP uses a 0.001 prediction floor; operating-point P/R/F1 uses "
        "LotTrace's 0.25 production threshold.",
        "",
        "| Class | Ground-truth boxes | AP50 | AP50–95 | Precision @ .25 | Recall @ .25 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, item in coco["per_class"].items():
        operating = item["operating_point_iou_0.50"]
        lines.append(
            f"| {label} | {item['ground_truth_instances']:,} | {percent(item['ap_iou_0.50'])} | "
            f"{percent(item['ap_iou_0.50_0.95'])} | {percent(operating['precision'])} | "
            f"{percent(operating['recall'])} |"
        )
    lines += [
        "",
        f"False detections on {vehicle['dataset']['negative_images']:,} negative images at the production "
        f"threshold: {coco['false_detections_on_negative_images']:,} "
        f"({coco['false_detections_per_negative_image']:.4f} per negative image).",
        "",
        "The COCO model recognizes only **car, truck, bus, and motorcycle**. It does not recognize make, "
        "model, or year. COCO does not label LotTrace colour output, tracking, plate-to-vehicle association, "
        "or false sightings per hour, so this report makes no accuracy claim for those functions.",
        "",
        "## Required deployment benchmark still missing",
        "",
        "A production decision still requires a separately labelled dealership-video test set, isolated by "
        "site/camera/vehicle/date, with day/night, weather, glare, blur, distance, angle, occlusion, front/rear, "
        "stationary/moving, negative video, track identity, event timestamps, plate-to-vehicle links, and colour. "
        "That set must report false positives per hour, false sightings per hour, event recall, timestamp error, "
        "track continuity, duplicate tracks, association P/R, and peak resource use.",
        "",
        "## Reproducibility and provenance",
        "",
        f"- Repository base revision: `{revision}` (evaluation files may be uncommitted).",
        f"- UC3M archive SHA-256: `{manifest['uc3m']['assets'][0]['sha256']}`; publisher MD5: "
        f"`{manifest['uc3m']['assets'][0]['md5']}`; ODbL-1.0.",
        f"- COCO archives: " + ", ".join(f"`{item['name']}` `{item['sha256']}`" for item in manifest['coco']['assets']) + ".",
        f"- Plate model: `{plate_test['model']['model_name']}` (`fast-alpr` 0.4.0), CPU.",
        f"- Vehicle model SHA-256: `{vehicle['model']['sha256']}`, CPU, image size "
        f"{vehicle['model']['image_size']}, confidence {vehicle['model']['operating_confidence_threshold']}, "
        f"NMS IoU {vehicle['model']['nms_iou']}.",
    ]
    for path in code_files:
        lines.append(f"- Evaluation code `{path.relative_to(ROOT)}` SHA-256: `{file_hash(path)}`.")
    lines += [
        "",
        "Dataset sources: [UC3M-LP](https://github.com/ramajoballester/UC3M-LP), "
        "[UC3M-LP Zenodo record](https://zenodo.org/records/17152029), and "
        "[COCO](https://cocodataset.org/#download).",
        "",
    ]
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    from generate_model_evaluation_report_v2 import main as corrected_main
    raise SystemExit(corrected_main())
