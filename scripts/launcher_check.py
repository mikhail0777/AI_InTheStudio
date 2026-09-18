"""Preflight and readiness checks used by the Windows development launcher."""
import argparse
import hashlib
from importlib import metadata
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
REQUIRED_PYTHON = (3, 10)
MODEL_HASHES = {
    "yolo": "1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3",
    "owlv2": "e1e130b9e404cf91a75ad45644c1da9d7fa5284085eecc864266a6923efb99e7",
    "siglip": "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8",
}
SIGLIP_MODEL_ID = "google/siglip-base-patch16-224"
SIGLIP_REVISION = "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected_hash: str, name: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"{name} is missing: {path}")
    if sha256(path) != expected_hash:
        raise RuntimeError(f"{name} failed its SHA-256 integrity check: {path}")


def pinned_requirements(path: Path) -> list[tuple[str, str]]:
    requirements = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if line and not line.startswith("#") and "==" in line:
            requirements.append(tuple(part.strip() for part in line.split("==", 1)))
    return requirements


def verify_python_packages() -> None:
    mismatches = []
    for package, expected in pinned_requirements(BACKEND / "requirements.txt"):
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{package} is not installed")
            continue
        if actual != expected:
            mismatches.append(f"{package} is {actual}; expected {expected}")
    for package in ("torch", "huggingface-hub"):
        try:
            metadata.version(package)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{package} is not installed")
    if mismatches:
        details = "\n  - ".join(mismatches)
        raise RuntimeError(
            "Python dependencies are incomplete or differ from backend/requirements.txt:\n"
            f"  - {details}\nRun: python -m pip install -r backend/requirements.txt"
        )


def siglip_cached_file(filename: str) -> Path:
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache(
            SIGLIP_MODEL_ID, filename, revision=SIGLIP_REVISION,
        )
    except (ImportError, OSError) as error:
        raise RuntimeError("The pinned SigLIP cache could not be inspected.") from error
    if not isinstance(cached, str):
        raise RuntimeError(f"The pinned SigLIP cache is missing {filename}.")
    return Path(cached)


def run_preflight() -> None:
    if sys.version_info < REQUIRED_PYTHON:
        raise RuntimeError(
            f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ is required; "
            f"found {sys.version.split()[0]}."
        )
    for path in (BACKEND / "app" / "main.py", ROOT / "frontend" / "package.json"):
        if not path.is_file():
            raise RuntimeError(f"Required application file is missing: {path}")

    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not node or not npm:
        raise RuntimeError("Node.js and npm were not found on PATH.")
    node_version = subprocess.run(
        [node, "-p", "process.versions.node"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    if int(node_version.split(".", 1)[0]) < 18:
        raise RuntimeError(f"Node.js 18+ is required; found {node_version}.")
    for command in ("vite.cmd", "tsc.cmd"):
        if not (ROOT / "frontend" / "node_modules" / ".bin" / command).is_file():
            raise RuntimeError("Frontend dependencies are missing. Run: cd frontend && npm.cmd install")

    verify_python_packages()
    yolo_path = Path(os.environ.get(
        "AIEYE_MODEL_PATH", str(BACKEND / "models" / "yolo11s-seg.pt"),
    )).resolve()
    owl_path = Path(os.environ.get(
        "AIEYE_GROUNDING_MODEL_PATH", str(BACKEND / "models" / "owlv2"),
    )).resolve()
    verify_file(yolo_path, MODEL_HASHES["yolo"], "YOLO model")
    verify_file(owl_path / "model.safetensors", MODEL_HASHES["owlv2"], "OWLv2 model")
    for filename in (
        "config.json", "preprocessor_config.json", "tokenizer_config.json",
        "special_tokens_map.json", "vocab.json", "merges.txt",
    ):
        if not (owl_path / filename).is_file():
            raise RuntimeError(f"The local OWLv2 model is missing {filename}.")
    siglip_weight = siglip_cached_file("model.safetensors")
    for filename in (
        "config.json", "preprocessor_config.json", "tokenizer_config.json",
        "special_tokens_map.json", "tokenizer.json", "spiece.model",
    ):
        siglip_cached_file(filename)
    verify_file(siglip_weight, MODEL_HASHES["siglip"], "SigLIP model")
    print(f"[OK] Python {sys.version.split()[0]}, Node.js {node_version}, npm, dependencies, and models verified.")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind((host, port))
        except OSError:
            return False
    return True


def wait_for_url(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return True
        except (OSError, URLError):
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    port_parser = subparsers.add_parser("port-free")
    port_parser.add_argument("host")
    port_parser.add_argument("port", type=int)
    wait_parser = subparsers.add_parser("wait-url")
    wait_parser.add_argument("url")
    wait_parser.add_argument("timeout", type=float)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            run_preflight()
            return 0
        if args.command == "port-free":
            if port_is_free(args.host, args.port):
                return 0
            print(f"Port {args.host}:{args.port} is already in use.", file=sys.stderr)
            return 1
        if wait_for_url(args.url, args.timeout):
            print(f"[OK] Ready: {args.url}")
            return 0
        print(f"Timed out waiting for {args.url}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
