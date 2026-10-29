"""In-memory island state + simplified Hakoniwa Islands 2–inspired turn loop.

v1 scaffold only: funds/food, place/remove farm & factory, landfill expand.
Numbers are catalog-inspired but tuned for a short local play loop (not server-accurate).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .grid import GRID_SIZE, center_cluster, neighbors

# Terrain kinds (same-layer placeholders until user art lands).
TERRAIN = {
    "sea": {"label": "海", "color": (42, 110, 168)},
    "dirt": {"label": "泥地", "color": (139, 90, 43)},
    "grass": {"label": "草地", "color": (74, 143, 60)},
}

# Buildings as solid color blocks on land.
BUILDINGS = {
    None: {"label": "（無）", "color": None, "cost": 0},
    "farm": {"label": "農場", "color": (210, 190, 60), "cost": 20},
    "factory": {"label": "工場", "color": (120, 120, 130), "cost": 100},
}

LANDFILL_COST = 150
START_FUNDS = 1000
START_FOOD = 500
START_POP = 100

Coord = Tuple[int, int]


@dataclass
class Cell:
    terrain: str = "sea"
    building: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"terrain": self.terrain, "building": self.building}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Cell":
        terrain = data.get("terrain", "sea")
        if terrain not in TERRAIN:
            terrain = "sea"
        building = data.get("building")
        if building not in BUILDINGS or building is None:
            building = None
        elif building == "none":
            building = None
        return cls(terrain=terrain, building=building)


@dataclass
class IslandState:
    size: int = GRID_SIZE
    turn: int = 1
    funds: int = START_FUNDS
    food: int = START_FOOD
    population: int = START_POP
    name: str = "箱庭島"
    cells: List[List[Cell]] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = self._new_map()
            self._log("島已生成：中央 7 格陸地，其餘為海。")

    def _new_map(self) -> List[List[Cell]]:
        grid = [[Cell("sea") for _ in range(self.size)] for _ in range(self.size)]
        land = center_cluster(self.size)
        # First cell dirt, rest alternate dirt/grass for readable placeholders.
        for idx, (i, j) in enumerate(land):
            grid[i][j] = Cell("dirt" if idx % 2 == 0 else "grass")
        return grid

    def _log(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 80:
            self.log = self.log[-80:]

    def cell(self, i: int, j: int) -> Cell:
        return self.cells[i][j]

    def is_land(self, i: int, j: int) -> bool:
        return self.cell(i, j).terrain in ("dirt", "grass")

    def land_count(self) -> int:
        return sum(
            1
            for row in self.cells
            for c in row
            if c.terrain in ("dirt", "grass")
        )

    def building_count(self, kind: str) -> int:
        return sum(1 for row in self.cells for c in row if c.building == kind)

    def can_landfill(self, i: int, j: int) -> bool:
        c = self.cell(i, j)
        if c.terrain != "sea":
            return False
        return any(self.is_land(ni, nj) for ni, nj in neighbors(i, j, self.size))

    def place_building(self, i: int, j: int, kind: str) -> str:
        if kind not in ("farm", "factory"):
            return "未知建築"
        c = self.cell(i, j)
        if not self.is_land(i, j):
            return "只能在陸地上建設"
        if c.building is not None:
            return "此格已有建築（請先移除）"
        cost = BUILDINGS[kind]["cost"]
        if self.funds < cost:
            return f"資金不足（需要 {cost}）"
        self.funds -= cost
        c.building = kind
        label = BUILDINGS[kind]["label"]
        self._log(f"回合 {self.turn}：在 ({i},{j}) 建設{label}（−{cost} 資金）")
        return "ok"

    def remove_building(self, i: int, j: int) -> str:
        c = self.cell(i, j)
        if c.building is None:
            return "此格沒有建築"
        label = BUILDINGS[c.building]["label"]
        c.building = None
        self._log(f"回合 {self.turn}：移除 ({i},{j}) 的{label}")
        return "ok"

    def landfill(self, i: int, j: int) -> str:
        if not self.can_landfill(i, j):
            return "只能填與陸地相鄰的海"
        if self.funds < LANDFILL_COST:
            return f"資金不足（填海需要 {LANDFILL_COST}）"
        self.funds -= LANDFILL_COST
        # New land starts as dirt placeholder.
        self.cells[i][j] = Cell("dirt")
        self._log(f"回合 {self.turn}：填海 ({i},{j})（−{LANDFILL_COST} 資金）")
        return "ok"

    def next_turn(self) -> List[str]:
        """Advance one turn: produce, consume, light population drift."""
        notes: List[str] = []
        farms = self.building_count("farm")
        factories = self.building_count("factory")

        food_gain = farms * 100
        funds_gain = factories * 10
        # Catalog-ish: ~100 food per 500 pop; keep a soft floor for tiny islands.
        food_need = max(0, (self.population // 500) * 100)
        if food_need == 0 and self.population > 0:
            food_need = 20

        self.food += food_gain
        self.funds += funds_gain
        notes.append(f"農場×{farms} 產糧 +{food_gain}；工場×{factories} 產資 +{funds_gain}")

        if self.food >= food_need:
            self.food -= food_need
            notes.append(f"人口 {self.population} 消耗糧食 −{food_need}")
            # Gentle growth when fed and housing/land exists.
            growth = 0
            if farms > 0 or self.land_count() >= 7:
                growth = random.randint(0, 20) + farms * 5
            self.population = min(20000, self.population + growth)
            if growth:
                notes.append(f"人口 +{growth} → {self.population}")
        else:
            # Starvation: eat remaining food, shrink population.
            starved = self.food
            self.food = 0
            loss = max(10, self.population // 10)
            self.population = max(0, self.population - loss)
            notes.append(f"糧食不足（僅 {starved}）！人口 −{loss} → {self.population}")

        self.turn += 1
        for n in notes:
            self._log(f"回合 {self.turn - 1}→{self.turn}：{n}")
        return notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "name": self.name,
            "size": self.size,
            "turn": self.turn,
            "funds": self.funds,
            "food": self.food,
            "population": self.population,
            "cells": [[c.to_dict() for c in row] for row in self.cells],
            "log": list(self.log[-40:]),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IslandState":
        size = int(data.get("size") or GRID_SIZE)
        raw_cells = data.get("cells")
        parsed: List[List[Cell]] = []
        ok = isinstance(raw_cells, list) and len(raw_cells) == size
        if ok:
            for row in raw_cells:
                if not isinstance(row, list) or len(row) != size:
                    ok = False
                    break
                parsed.append(
                    [
                        Cell.from_dict(c if isinstance(c, dict) else {})
                        for c in row
                    ]
                )
        state = cls(
            size=size,
            turn=int(data.get("turn") or 1),
            funds=int(data.get("funds") if data.get("funds") is not None else START_FUNDS),
            food=int(data.get("food") if data.get("food") is not None else START_FOOD),
            population=int(
                data.get("population")
                if data.get("population") is not None
                else START_POP
            ),
            name=str(data.get("name") or "箱庭島"),
            cells=parsed if ok else [],
            log=[str(x) for x in (data.get("log") or [])][-80:],
        )
        return state

    @classmethod
    def new_game(cls) -> "IslandState":
        return cls()
