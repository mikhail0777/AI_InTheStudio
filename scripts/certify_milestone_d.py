"""Generate an evidence-backed Milestone D release-gate report.

The command reads committed evaluation summaries and source capabilities.  It
never substitutes software-test results or model confidence for labelled
accuracy.  Missing evidence remains an explicit failed/unmeasured gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _gate(name: str, target: str, value, status: str, evidence: str, note: str) -> dict:
    return {
        "name": name,
        "target": target,
        "measured_value": value,
        "status": status,
        "evidence": evidence,
        "note": note,
    }


def build_report(verification: dict | None = None) -> dict:
    detection_path = "evaluation/license_plate_recognition_v13_detection_results.json"
    ocr_path = "evaluation/LOTTRACE_OPENALPR_300_OCR_2026-10-22.json"
    vehicle_path = "evaluation/LOTTRACE_MAKE_MODEL_TEST_2026-10-24.json"
    coco_path = "evaluation/coco_vehicle_results.json"
    detection, ocr, vehicle, coco = map(_load, (detection_path, ocr_path, vehicle_path, coco_path))
    plate_box = detection["metrics"]["iou_0.50"]
    ocr_final = ocr["final_confirmation_metrics"]
    make_model = vehicle["metrics"]
    general_vehicle = coco["metrics"]["operating_point_iou_0.50"]

    gates = [
        _gate(
            "Eligible vehicle crossing event recall", ">=99%", None, "unmeasured", "none",
            "Requires held-out dealership video with labelled crossings.",
        ),
        _gate(
            "Plate localization recall on eligible events", ">=99%", None, "unmeasured", detection_path,
            f"Still-image plate-box recall is {plate_box['recall']:.2%}; it is not an event-level video result.",
        ),
        _gate(
            "OCR character accuracy", ">=99%", ocr_final["character_accuracy"], "below_target", ocr_path,
            "Measured on 451 held-out cropped plates, not dealership-video events.",
        ),
        _gate(
            "Exact full-plate event accuracy", ">=99%", None, "unmeasured", ocr_path,
            f"Single-crop exact accuracy is {ocr_final['exact_plate_accuracy']:.2%}; multi-frame event accuracy is unmeasured.",
        ),
        _gate(
            "Plate-to-vehicle association precision", ">=99%", None, "unmeasured", "none",
            "No labelled dealership-video association benchmark exists.",
        ),
        _gate(
            "Plate-to-vehicle association recall", ">=98%", None, "unmeasured", "none",
            "No labelled dealership-video association benchmark exists.",
        ),
        _gate(
            "False exact assignments / false sightings per hour", "reported", None, "unmeasured", "none",
            "Requires negative and positive dealership footage with labelled duration.",
        ),
        _gate(
            "Make + model top-1", ">=95% development objective", make_model["make_model_top1"],
            "below_target", vehicle_path,
            "Closed-set research still-image result; dealership-video and unknown-vehicle performance remain unmeasured.",
        ),
        _gate(
            "General vehicle detector recall", ">=99% eligible crossings", general_vehicle["recall"],
            "not_comparable_below_target", coco_path,
            "COCO still-image recall is not the declared eligible dealership-crossing metric.",
        ),
    ]
    source = (ROOT / "backend/app/services/analysis_worker.py").read_text(encoding="utf-8")
    automatic_event_wiring = "create_crossing_event" in source
    capabilities = {
        "recorded_video_analysis": True,
        "durable_job_queue_and_restart_recovery": True,
        "multi_frame_ocr_consensus": True,
        "vehicle_make_model_recognition": True,
        "immutable_events_and_status_transitions": True,
        "authentication_roles_audit_retention_exports": True,
        "desktop_application_shell": True,
        "installable_windows_build": True,
        "automatic_worker_to_crossing_event_wiring": automatic_event_wiring,
        "live_camera_ingestion": False,
        "backup_restore_certified": False,
        "deployment_security_certified": False,
        "signed_self_contained_windows_installer": False,
    }
    blockers = [label for label, available in capabilities.items() if not available]
    blockers += [gate["name"] for gate in gates if gate["status"] != "passed"]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "milestone": "D - production certification",
        "production_certified": False,
        "decision": "not_ready_for_production",
        "capabilities": capabilities,
        "release_gates": gates,
        "blockers": blockers,
        "evidence_files": {
            path: _sha256(path) for path in (detection_path, ocr_path, vehicle_path, coco_path)
        },
        "functional_verification": verification or {},
        "interpretation": (
            "Functional software tests and healthy runtime checks do not prove model accuracy. "
            "Certification remains false until every declared dealership-video gate is measured and passed."
        ),
    }


def markdown(report: dict) -> str:
    lines = [
        "# LotTrace Milestone D production-readiness report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "**Decision: NOT READY FOR PRODUCTION.**",
        "",
        report["interpretation"],
    ]
    if report.get("functional_verification"):
        verification = report["functional_verification"]
        lines += [
            "",
            "## Functional verification run",
            "",
            f"- Backend: {verification['backend_tests']} tests passed",
            f"- Frontend unit: {verification['frontend_tests']} tests passed",
            f"- Browser end-to-end: {verification['browser_tests']} tests passed",
            f"- Production frontend build: {verification['frontend_build']}",
            "",
            "These prove tested software behavior only; they do not change the recognition accuracy gates.",
        ]
    lines += [
        "",
        "## Capability audit",
        "",
        "| Capability | Status |",
        "| --- | --- |",
    ]
    lines += [f"| {name.replace('_', ' ').title()} | {'Implemented' if value else 'Missing / uncertified'} |"
              for name, value in report["capabilities"].items()]
    lines += [
        "",
        "## Release gates",
        "",
        "| Gate | Target | Measured | Status | Note |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for gate in report["release_gates"]:
        value = gate["measured_value"]
        shown = "Not measured" if value is None else f"{value:.2%}"
        lines.append(f"| {gate['name']} | {gate['target']} | {shown} | {gate['status']} | {gate['note']} |")
    lines += [
        "",
        "## Required before certification",
        "",
        "1. Wire recording/live tracked observations into configured boundaries and event creation.",
        "2. Add and harden live camera ingestion with encrypted credentials, reconnect/backoff, bounded queues, and rolling evidence.",
        "3. Certify backup/restore, TLS deployment, rate limiting, resource limits, and failure recovery.",
        "4. Stage only redistributable model assets, validate the generated installer on a clean Windows VM, and code-sign it.",
        "5. Freeze and run a held-out dealership-video benchmark separated by site, camera, vehicle, and date.",
        "6. Pass every declared event, plate, association, false-positive, and resource-use gate.",
        "",
        "## Evidence integrity",
        "",
    ]
    lines += [f"- `{path}` — SHA-256 `{digest}`" for path, digest in report["evidence_files"].items()]
    lines = [line.replace("\u00e2\u20ac\u201d", "-") for line in lines]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    parser.add_argument("--backend-tests", type=int)
    parser.add_argument("--frontend-tests", type=int)
    parser.add_argument("--browser-tests", type=int)
    parser.add_argument("--frontend-build", choices=("passed", "failed"))
    args = parser.parse_args()
    supplied = (args.backend_tests, args.frontend_tests, args.browser_tests, args.frontend_build)
    if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
        parser.error("Supply all functional verification values or none of them.")
    verification = ({
        "backend_tests": args.backend_tests,
        "frontend_tests": args.frontend_tests,
        "browser_tests": args.browser_tests,
        "frontend_build": args.frontend_build,
    } if all(value is not None for value in supplied) else None)
    report = build_report(verification)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown_path:
        args.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_path.write_text(markdown(report), encoding="utf-8")
    if not args.json_path and not args.markdown_path:
        print(markdown(report), end="")


if __name__ == "__main__":
    main()
