"""JSON save/load for local scaffold (online NAS sync comes later)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from .model import IslandState

PathLike = Union[str, Path]


def default_save_path(config_dir: PathLike) -> Path:
    """Prefer Data/ next to config (gitignored); create on save."""
    base = Path(config_dir)
    return base / "Data" / "hakoniwa_island.json"


def save_island(state: IslandState, path: PathLike) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
    return target


def load_island(path: PathLike) -> Optional[IslandState]:
    target = Path(path)
    if not target.exists():
        return None
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    return IslandState.from_dict(data)
