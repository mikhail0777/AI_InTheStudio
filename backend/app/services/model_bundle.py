"""Fail-closed model bundle verification for packaged offline runtimes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = BACKEND_ROOT / "model_bundle_manifest.json"


def load_manifest(path=None):
    data = json.loads(Path(path or MANIFEST_PATH).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("assets"), list):
        raise RuntimeError("The runtime model manifest is invalid.")
    return data


def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk:=source.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(root=None, *, commercial=True):
    root=Path(root or os.environ.get("LOTTRACE_MODEL_BUNDLE_DIR",BACKEND_ROOT)).resolve()
    manifest=load_manifest()
    checks=[]
    for asset in manifest["assets"]:
        if not asset.get("required"):continue
        relative=asset.get("expected_installed_path")
        path=(root/relative).resolve() if relative else None
        within=bool(path and (path==root or root in path.parents))
        exists=bool(within and path.is_file())
        actual=sha256_file(path) if exists else None
        checksum_ok=bool(actual and actual.lower()==str(asset.get("sha256") or "").lower())
        redistribution_ok=asset.get("redistribution_status") in ("approved","permitted")
        checks.append({"component":asset["component"],"path":str(path) if path else None,"exists":exists,"checksum_ok":checksum_ok,"actual_sha256":actual,"redistribution_ok":redistribution_ok})
    errors=[]
    for check in checks:
        if not check["exists"]:errors.append(f"{check['component']}: missing")
        elif not check["checksum_ok"]:errors.append(f"{check['component']}: checksum mismatch")
        if commercial and not check["redistribution_ok"]:errors.append(f"{check['component']}: redistribution not approved")
    return {"ok":not errors,"commercial_profile":commercial,"root":str(root),"checks":checks,"errors":errors}


def enforce_offline_environment():
    os.environ["HF_HUB_OFFLINE"]="1"
    os.environ["TRANSFORMERS_OFFLINE"]="1"
    os.environ["HF_DATASETS_OFFLINE"]="1"
    os.environ["ULTRALYTICS_OFFLINE"]="true"


def require_packaged_bundle():
    enforce_offline_environment()
    result=verify_bundle(commercial=True)
    if not result["ok"]:
        raise RuntimeError("Packaged model bundle is unavailable or unapproved: "+"; ".join(result["errors"]))
    return result
