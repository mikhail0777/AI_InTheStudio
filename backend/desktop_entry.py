"""Entry point used by the packaged LotTrace desktop backend."""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("LOTTRACE_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("LOTTRACE_BACKEND_PORT", "8765"))
    uvicorn.run("app.main:app", host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
