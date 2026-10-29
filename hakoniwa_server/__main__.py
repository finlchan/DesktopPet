"""Run: python -m hakoniwa_server  (dev) or via uvicorn in Docker."""

from __future__ import annotations

import os

import uvicorn

from .app import DEFAULT_PORT


def main() -> None:
    host = os.environ.get("HAKONIWA_HOST", "0.0.0.0")
    port = int(os.environ.get("HAKONIWA_PORT") or DEFAULT_PORT)
    uvicorn.run("hakoniwa_server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
