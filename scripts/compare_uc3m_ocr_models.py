"""Compare FastALPR OCR candidates on labelled UC3M-LP plate crops.

Use the official training split for model selection. Run the selected model once
on the untouched test split before changing production configuration.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.license_plate_reader import normalize_plate
from scripts.evaluate_uc3m_alpr import annotation, masked_edit_distance
from scripts.evaluation_metrics import levenshtein, wilson_interval

DEFAULT_MODELS = [
    "cct-xs-v2-global-model",
    "cct-s-v2-global-model",
    "european-plates-mobile-vit-v2-model",
    "global-plates-mobile-vit-v2-model",
]


def samples(dataset: Path, split: str, limit: int | None) -> list[tuple[Path, list[float], str]]:
    output = []
    directory = dataset.resolve() / split
    for label_path in sorted(directory.glob("*.json")):
        plates, _declared_image_name = annotation(label_path)
        image_path = label_path.with_suffix(".jpg")
        for plate in plates:
            output.append((image_path, plate["bbox"], plate["template"]))
            if limit and len(output) >= limit:
                return output
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--split", choices=["train", "test"], default="train")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "uc3m_ocr_model_comparison.json")
    args = parser.parse_args()
    labelled = samples(args.dataset, args.split, args.limit)
    if not labelled:
        raise SystemExit("No fully labelled UC3M-LP plates found.")
    from fast_alpr.default_ocr import DefaultOCR
    results = {}
    for model_name in args.models:
        recognizer = DefaultOCR(hub_ocr_model=model_name, device="cpu")
        exact = edits = characters = invalid = 0
        confusion = Counter()
        started = time.perf_counter()
        for index, (image_path, bbox, template) in enumerate(labelled, start=1):
            image = cv2.imread(str(image_path))
            if image is None:
                invalid += 1
                continue
            x1, y1, x2, y2 = (int(value) for value in bbox)
            crop = image[max(0, y1):min(image.shape[0], y2), max(0, x1):min(image.shape[1], x2)]
            result = recognizer.predict(crop)
            observed = normalize_plate(result.text if result else "")
            exact += int(masked_edit_distance(template, observed) == 0)
            edits += masked_edit_distance(template, observed)
            characters += sum(char != "*" for char in template)
            for expected_char, observed_char in zip(template, observed):
                if expected_char != "*" and expected_char != observed_char:
                    confusion[(expected_char, observed_char)] += 1
            if index % 100 == 0:
                print(f"{model_name}: {index}/{len(labelled)}", file=sys.stderr, flush=True)
        evaluated = len(labelled) - invalid
        elapsed = time.perf_counter() - started
        results[model_name] = {
            "plates_evaluated": evaluated, "invalid_images": invalid,
            "published_position_exact_matches": exact,
            "published_position_plate_accuracy": exact / evaluated if evaluated else 0.0,
            "published_position_plate_accuracy_wilson_95": wilson_interval(exact, evaluated),
            "published_character_edits": edits, "published_ground_truth_characters": characters,
            "published_character_error_rate": edits / characters if characters else 0.0,
            "published_normalized_edit_similarity": 1 - edits / characters if characters else 0.0,
            "elapsed_seconds": elapsed,
            "plates_per_second": evaluated / elapsed if elapsed else 0.0,
            "common_substitutions": [
                {"expected": pair[0], "observed": pair[1], "count": count}
                for pair, count in confusion.most_common(20)
            ],
        }
    ranked = sorted(results, key=lambda name: (
        results[name]["published_position_plate_accuracy"], -results[name]["published_character_error_rate"]
    ), reverse=True)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "UC3M-LP", "split": args.split,
        "selection_policy": (
            "Select only on train. Confirm the selected model once on untouched test; "
            "do not select or tune on test."
        ),
        "crop_policy": "Axis-aligned ground-truth plate box; OCR-only diagnostic, not end-to-end ALPR.",
        "label_limitation": "UC3M-LP masks two characters per plate; selection uses published positions only.",
        "runtime": {"python": sys.version, "platform": platform.platform(), "device": "cpu"},
        "ranking": ranked, "models": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
