"""Persistent island store for the NAS container (JSON on disk)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from hakoniwa.model import IslandState


class IslandStore:
    """Thread-safe IslandState + JSON persistence under data_dir."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "island.json"
        self._lock = threading.RLock()
        self._state: IslandState = IslandState.new_game()
        self.load_or_create()

    def load_or_create(self) -> IslandState:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._state = IslandState.from_dict(data)
                        return self._state
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
            self._state = IslandState.new_game()
            self._persist_unlocked()
            return self._state

    def _persist_unlocked(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def snapshot(self) -> dict:
        with self._lock:
            return self._state.to_dict()

    def get_state(self) -> IslandState:
        with self._lock:
            return self._state

    def replace(self, state: IslandState) -> dict:
        with self._lock:
            self._state = state
            self._persist_unlocked()
            return self._state.to_dict()

    def reset(self) -> dict:
        with self._lock:
            self._state = IslandState.new_game()
            self._persist_unlocked()
            return self._state.to_dict()

    def place(self, i: int, j: int, kind: str) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.place_building(i, j, kind)
            if msg == "ok":
                self._persist_unlocked()
            return msg, self._state.to_dict()

    def remove(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.remove_building(i, j)
            if msg == "ok":
                self._persist_unlocked()
            return msg, self._state.to_dict()

    def landfill(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.landfill(i, j)
            if msg == "ok":
                self._persist_unlocked()
            return msg, self._state.to_dict()

    def level(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.level_land(i, j)
            if msg == "ok":
                self._persist_unlocked()
            return msg, self._state.to_dict()

    def afforest(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.afforest(i, j)
            if msg == "ok":
                self._persist_unlocked()
            return msg, self._state.to_dict()

    def next_turn(self) -> tuple[list[str], dict]:
        with self._lock:
            notes = self._state.next_turn()
            self._persist_unlocked()
            return notes, self._state.to_dict()
