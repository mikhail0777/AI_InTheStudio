"""Build the private one-folder Python backend used by the desktop shell."""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def validate() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError(
            "PyInstaller is missing. Install backend/requirements-desktop.txt in the build environment."
        )
    required = [
        ROOT / "backend" / "desktop_entry.py",
        ROOT / "backend" / "models" / "yolo11s-seg.pt",
        ROOT / "frontend" / "dist" / "index.html",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Desktop build inputs are missing:\n- " + "\n- ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate inputs without building.")
    args = parser.parse_args()
    try:
        validate()
        if not args.check:
            subprocess.run(
                [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "desktop/lottrace_backend.spec"],
                cwd=ROOT,
                check=True,
            )
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
