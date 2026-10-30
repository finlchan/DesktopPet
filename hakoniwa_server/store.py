"""Persistent island store for the NAS container (JSON on disk).

Home island stays at data_dir/island.json (backward compatible).
Tourism catalog: data_dir/islands/{id}.json — seeded with 1–2 demos if empty.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from hakoniwa.demos import island_summary, make_demo_coral, make_demo_pine
from hakoniwa.model import IslandState


HOME_ID = "home"


class IslandStore:
    """Thread-safe home IslandState + multi-island tourism catalog."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "island.json"
        self.islands_dir = self.data_dir / "islands"
        self._lock = threading.RLock()
        self._state: IslandState = IslandState.new_game()
        # Non-home islands keyed by id (demos / future guests).
        self._others: Dict[str, IslandState] = {}
        self.load_or_create()

    def load_or_create(self) -> IslandState:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.islands_dir.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._state = IslandState.from_dict(data)
                        self._state.island_id = HOME_ID
                        self._load_others_unlocked()
                        self._seed_demos_if_empty_unlocked()
                        return self._state
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
            self._state = IslandState.new_game(island_id=HOME_ID, name="箱庭島")
            self._persist_home_unlocked()
            self._load_others_unlocked()
            self._seed_demos_if_empty_unlocked()
            return self._state

    def _island_path(self, island_id: str) -> Path:
        safe = "".join(ch for ch in island_id if ch.isalnum() or ch in "-_")
        if not safe or safe != island_id:
            raise ValueError(f"invalid island id: {island_id!r}")
        return self.islands_dir / f"{safe}.json"

    def _persist_home_unlocked(self) -> None:
        self._state.island_id = HOME_ID
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def _persist_other_unlocked(self, state: IslandState) -> None:
        island_id = state.island_id
        if not island_id or island_id == HOME_ID:
            raise ValueError("other island needs a non-home id")
        self.islands_dir.mkdir(parents=True, exist_ok=True)
        path = self._island_path(island_id)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def _persist_unlocked(self) -> None:
        self._persist_home_unlocked()

    def _load_others_unlocked(self) -> None:
        self._others = {}
        if not self.islands_dir.exists():
            return
        for path in sorted(self.islands_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                state = IslandState.from_dict(data)
                iid = state.island_id or path.stem
                if iid == HOME_ID:
                    continue
                state.island_id = iid
                self._others[iid] = state
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue

    def _seed_demos_if_empty_unlocked(self) -> None:
        if self._others:
            return
        demos = [make_demo_coral(), make_demo_pine()]
        for demo in demos:
            self._others[demo.island_id] = demo
            self._persist_other_unlocked(demo)

    def snapshot(self) -> dict:
        with self._lock:
            return self._state.to_dict()

    def get_state(self) -> IslandState:
        with self._lock:
            return self._state

    def replace(self, state: IslandState) -> dict:
        with self._lock:
            state.island_id = HOME_ID
            self._state = state
            self._persist_home_unlocked()
            return self._state.to_dict()

    def reset(self) -> dict:
        with self._lock:
            self._state = IslandState.new_game(island_id=HOME_ID, name="箱庭島")
            self._persist_home_unlocked()
            return self._state.to_dict()

    def place(self, i: int, j: int, kind: str) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.place_building(i, j, kind)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def remove(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.remove_building(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def landfill(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.landfill(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def level(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.level_land(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def raise_mountain(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.raise_mountain(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def excavate(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.excavate(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def afforest(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.afforest(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def harvest(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.harvest(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def missile(self, i: int, j: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.fire_missile(i, j)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def wait_monster(self) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.wait_monster()
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def export_food(self, lots: int = 1) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.export_food(lots)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def buy_food(self, lots: int = 1) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.buy_food(lots)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def deposit_funds(self, amount: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.deposit_funds(amount)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def withdraw_funds(self, amount: int) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.withdraw_funds(amount)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def attract_population(self) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.attract_population()
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def launch_rocket(self) -> tuple[str, dict]:
        with self._lock:
            msg = self._state.launch_rocket()
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, self._state.to_dict()

    def next_turn(self) -> tuple[list[str], dict]:
        with self._lock:
            notes = self._state.next_turn()
            self._persist_home_unlocked()
            return notes, self._state.to_dict()

    def list_comments(self) -> List[dict]:
        with self._lock:
            return [c.to_dict() for c in self._state.list_comments()]

    def add_comment(self, name: str, text: str) -> Tuple[str, List[dict]]:
        with self._lock:
            msg = self._state.add_comment(name, text)
            if msg == "ok":
                self._persist_home_unlocked()
            return msg, [c.to_dict() for c in self._state.list_comments()]

    # --- Multi-island tourism -----------------------------------------------

    def _resolve_unlocked(self, island_id: str) -> Optional[IslandState]:
        if island_id == HOME_ID:
            return self._state
        return self._others.get(island_id)

    def list_islands(self) -> List[dict]:
        with self._lock:
            rows = [island_summary(self._state)]
            for iid in sorted(self._others.keys()):
                rows.append(island_summary(self._others[iid]))
            return rows

    def get_island(self, island_id: str) -> Optional[dict]:
        with self._lock:
            state = self._resolve_unlocked(island_id)
            if state is None:
                return None
            return state.to_dict()

    def list_island_comments(self, island_id: str) -> Optional[List[dict]]:
        with self._lock:
            state = self._resolve_unlocked(island_id)
            if state is None:
                return None
            return [c.to_dict() for c in state.list_comments()]

    def add_island_comment(
        self, island_id: str, name: str, text: str
    ) -> Tuple[Optional[str], List[dict]]:
        """Returns (error_or_'ok', comments). error None means island missing."""
        with self._lock:
            state = self._resolve_unlocked(island_id)
            if state is None:
                return None, []
            msg = state.add_comment(name, text)
            if msg == "ok":
                if island_id == HOME_ID:
                    self._persist_home_unlocked()
                else:
                    self._persist_other_unlocked(state)
            return msg, [c.to_dict() for c in state.list_comments()]
