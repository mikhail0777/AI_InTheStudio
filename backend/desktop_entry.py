"""Entry point used by the packaged LotTrace desktop backend."""
from __future__ import annotations

import os

import uvicorn
from app.services.model_bundle import require_packaged_bundle

if os.environ.get("LOTTRACE_ENFORCE_MODEL_BUNDLE", "1") == "1":
    require_packaged_bundle()

from app.main import app


def main() -> None:
    host = os.environ.get("LOTTRACE_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("LOTTRACE_BACKEND_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
