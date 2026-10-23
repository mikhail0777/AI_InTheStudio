"""Collect auditable, quality-gated vehicle-generation images from Commons."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

import cv2
import numpy as np


USER_AGENT = "LotTraceVehicleDataset/1.0 (github.com/mikhail0777/AI_InTheStudio)"
API = "https://commons.wikimedia.org/w/api.php"
VEHICLE_CLASSES = {2, 3, 5, 7}  # COCO car, motorcycle, bus, truck


def plain(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def commercial_license_allowed(short_name: str) -> bool:
    normalized = plain(short_name).casefold()
    if "noncommercial" in normalized or "-nc" in normalized or "no derivatives" in normalized or "-nd" in normalized:
        return False
    return normalized == "cc0" or "public domain" in normalized or normalized.startswith("cc by")


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def category_files(category: str, limit: int) -> list[dict]:
    titles: list[str] = []
    continuation = None
    while len(titles) < limit * 2:
        params = {
            "action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
            "cmtype": "file", "cmlimit": "500",
        }
        if continuation:
            params["cmcontinue"] = continuation
        result = api(params)
        titles.extend(item["title"] for item in result.get("query", {}).get("categorymembers", []))
        continuation = result.get("continue", {}).get("cmcontinue")
        if not continuation:
            break
    batches = [titles[start:start + 40] for start in range(0, len(titles), 40)]

    def metadata_batch(batch: list[str]) -> dict:
        return api({
            "action": "query", "titles": "|".join(batch),
            "prop": "imageinfo", "iiprop": "url|size|mime|sha1|extmetadata",
            "iiurlwidth": "1280",
        })

    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(metadata_batch, batches))
    for result in results:
        for page in result.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            metadata = info.get("extmetadata") or {}
            get = lambda key: plain((metadata.get(key) or {}).get("value"))
            records.append({
                "page_id": page.get("pageid"), "title": page.get("title"),
                "page_url": info.get("descriptionurl"), "download_url": info.get("thumburl") or info.get("url"),
                "original_url": info.get("url"), "original_sha1": info.get("sha1"),
                "width": info.get("width"), "height": info.get("height"), "mime": info.get("mime"),
                "license": get("LicenseShortName"), "license_url": get("LicenseUrl"),
                "artist": get("Artist"), "credit": get("Credit"),
                "date_time_original": get("DateTimeOriginal"),
            })
    return records


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def download_candidate(item: dict) -> tuple[dict, bytes | None, str | None]:
    try:
        return item, download(item["download_url"]), None
    except Exception as exc:
        return item, None, f"download_error:{type(exc).__name__}"


def dhash(image: np.ndarray) -> str:
    gray = cv2.cvtColor(cv2.resize(image, (9, 8)), cv2.COLOR_BGR2GRAY)
    bits = gray[:, 1:] > gray[:, :-1]
    return f"{sum(int(bit) << index for index, bit in enumerate(bits.flat)):016x}"


def quality_metrics(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
        "mean_luma": round(float(gray.mean()), 3),
        "luma_stddev": round(float(gray.std()), 3),
        "dhash": dhash(image),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-per-class", type=int, default=40)
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--min-sharpness", type=float, default=80.0)
    parser.add_argument("--min-vehicle-area", type=float, default=.12)
    args = parser.parse_args()

    from ultralytics import YOLO
    config_bytes = args.sources.read_bytes()
    config = json.loads(config_bytes)
    args.output_root.mkdir(parents=True, exist_ok=True)
    originals = args.output_root / "originals"
    crops = args.output_root / "crops"
    originals.mkdir(exist_ok=True); crops.mkdir(exist_ok=True)
    detector = YOLO(str(args.detector))
    samples, rejected, seen_sha1, seen_dhash = [], [], set(), set()

    for class_id, label in enumerate(config["classes"]):
        accepted_for_class = 0
        eligible_metadata = []
        for item in category_files(label["category"], args.max_per_class):
            reason = None
            if not commercial_license_allowed(item["license"]): reason = "license_not_allowlisted"
            elif not item.get("download_url"): reason = "missing_download_url"
            elif min(int(item.get("width") or 0), int(item.get("height") or 0)) < 640: reason = "source_too_small"
            elif item.get("original_sha1") in seen_sha1: reason = "duplicate_source_sha1"
            if reason:
                rejected.append({**item, "class_id": class_id, "reason": reason}); continue
            eligible_metadata.append(item)
        with ThreadPoolExecutor(max_workers=8) as pool:
            downloaded = list(pool.map(download_candidate, eligible_metadata))
        for item, payload, download_error in downloaded:
            if download_error or payload is None:
                rejected.append({**item, "class_id": class_id, "reason": download_error}); continue
            image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                rejected.append({**item, "class_id": class_id, "reason": "decode_failed"}); continue
            metrics = quality_metrics(image)
            if metrics["sharpness"] < args.min_sharpness or metrics["luma_stddev"] < 25 or not 25 <= metrics["mean_luma"] <= 230:
                rejected.append({**item, "class_id": class_id, "reason": "image_quality", "quality": metrics}); continue
            if metrics["dhash"] in seen_dhash:
                rejected.append({**item, "class_id": class_id, "reason": "perceptual_duplicate", "quality": metrics}); continue
            results = detector.predict(image, verbose=False, save=False, classes=list(VEHICLE_CLASSES), conf=.30, imgsz=960)[0]
            boxes = []
            for box in results.boxes:
                x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
                area = max(0.0, x2 - x1) * max(0.0, y2 - y1) / (image.shape[0] * image.shape[1])
                boxes.append((area, float(box.conf.item()), (x1, y1, x2, y2)))
            boxes.sort(reverse=True)
            if not boxes or boxes[0][0] < args.min_vehicle_area:
                rejected.append({**item, "class_id": class_id, "reason": "no_dominant_vehicle", "quality": metrics}); continue
            if len(boxes) > 1 and boxes[1][0] > boxes[0][0] * .65:
                rejected.append({**item, "class_id": class_id, "reason": "multiple_similar_vehicles", "quality": metrics}); continue
            x1, y1, x2, y2 = boxes[0][2]
            margin_x, margin_y = (x2 - x1) * .08, (y2 - y1) * .08
            x1, y1 = max(0, int(x1 - margin_x)), max(0, int(y1 - margin_y))
            x2, y2 = min(image.shape[1], int(x2 + margin_x)), min(image.shape[0], int(y2 + margin_y))
            crop = image[y1:y2, x1:x2]
            sample_id = hashlib.sha256(f"commons:{item['page_id']}".encode()).hexdigest()[:16]
            original_path, crop_path = originals / f"{sample_id}.jpg", crops / f"{sample_id}.jpg"
            cv2.imwrite(str(original_path), image, [cv2.IMWRITE_JPEG_QUALITY, 94])
            cv2.imwrite(str(crop_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            capture_basis = "|".join((item.get("artist") or "unknown", item.get("date_time_original") or item["title"]))
            samples.append({
                "sample_id": sample_id, "class_id": class_id, "label": label,
                "source": item, "original_path": str(original_path.resolve()), "crop_path": str(crop_path.resolve()),
                "download_sha256": hashlib.sha256(payload).hexdigest(), "quality": metrics,
                "vehicle_detection": {"confidence": round(boxes[0][1], 6), "area_fraction": round(boxes[0][0], 6), "bbox": [x1, y1, x2, y2]},
                "capture_group": hashlib.sha256(capture_basis.encode()).hexdigest()[:16],
                "review": {"quality": "pending", "label_correct": None, "notes": ""},
            })
            seen_sha1.add(item.get("original_sha1")); seen_dhash.add(metrics["dhash"])
            accepted_for_class += 1
            if accepted_for_class >= args.max_per_class: break
        print(json.dumps({"class": f"{label['make']} {label['model']}", "accepted": accepted_for_class}), flush=True)

    manifest = {
        "schema_version": 1, "purpose": "modern_vehicle_intake_pending_review",
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "detector_sha256": hashlib.sha256(args.detector.read_bytes()).hexdigest(),
        "quality_policy": {
            "min_source_dimension": 640, "min_sharpness": args.min_sharpness,
            "min_luma_stddev": 25, "luma_range": [25, 230], "min_vehicle_area": args.min_vehicle_area,
            "reject_multiple_similar_vehicles": True, "exact_dhash_deduplication": True,
        },
        "classes": config["classes"], "samples": samples, "rejected": rejected,
        "counts": {"accepted_pending_review": len(samples), "rejected": len(rejected)},
    }
    (args.output_root / "intake_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
