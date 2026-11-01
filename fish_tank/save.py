"""Local JSON save for Transparent Fish Tank (under Data/fish_tank/)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .model import TankState

SAVE_VERSION = 1


def default_save_path() -> Path:
    """Beside the running app: Data/fish_tank/tank.json (gitignored via Data/)."""
    # Prefer cwd Data/ (same convention as hakoniwa).
    return Path.cwd() / "Data" / "fish_tank" / "tank.json"


def load_tank(path: Optional[Path] = None) -> Optional[TankState]:
    p = path or default_save_path()
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    data = raw.get("tank", raw)
    if not isinstance(data, dict):
        return None
    try:
        return TankState.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None


def save_tank(state: TankState, path: Optional[Path] = None) -> Path:
    p = path or default_save_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SAVE_VERSION,
        "tank": state.to_dict(),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
