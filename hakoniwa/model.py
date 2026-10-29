"""In-memory island state + simplified Hakoniwa Islands 2–inspired turn loop.

v1 deepen: catalog place costs, terrain commands (整地／填海／植林),
farm food + factory funds turn processing, optional population stub.
Color-block placeholders only — user art later.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .grid import GRID_SIZE, center_cluster, neighbors

# ---------------------------------------------------------------------------
# Catalog-inspired costs (箱庭諸島2 定本；億円／噸 units as soft placeholders)
# See docs/hakoniwa-content-catalog.md
# ---------------------------------------------------------------------------
COST_FARM = 20          # 農場整備
COST_FACTORY = 100      # 工場建設
COST_LANDFILL = 150     # 埋め立て：海→淺灘 or 淺灘→荒地
COST_LEVEL = 5          # 整地：荒地→平地（亦可清建築）
COST_AFFOREST = 50      # 植林：平地→森

# Turn yields (simplified short loop; not server-accurate).
FOOD_PER_FARM = 100     # ~100 人農場 → 100 噸／回合
FUNDS_PER_FACTORY = 10  # catalog ~1 億／千人；本機短局用 ×10 回饋
FOOD_PER_500_POP = 100  # 人口每 500 人／回合耗約 100 噸
MIN_FOOD_NEED = 20      # 小島 soft floor

START_FUNDS = 1000
START_FOOD = 500
START_POP = 100

# Terrain kinds (same-layer color placeholders until user art lands).
# Opening map still uses dirt／grass per 箱庭斜視 prefs (中央 7 泥／草).
TERRAIN = {
    "sea": {"label": "海", "color": (42, 110, 168), "land": False},
    "shallow": {"label": "淺灘", "color": (72, 148, 176), "land": False},
    "dirt": {"label": "荒地", "color": (139, 90, 43), "land": True},
    "grass": {"label": "平地", "color": (74, 143, 60), "land": True},
    "forest": {"label": "森", "color": (36, 96, 48), "land": True},
}

# Buildings as solid color blocks on 平地.
BUILDINGS = {
    None: {"label": "（無）", "color": None, "cost": 0},
    "farm": {"label": "農場", "color": (210, 190, 60), "cost": COST_FARM},
    "factory": {"label": "工場", "color": (120, 120, 130), "cost": COST_FACTORY},
}

# Back-compat aliases used by older scaffold call sites / tests.
LANDFILL_COST = COST_LANDFILL

Coord = Tuple[int, int]
LAND_TERRAINS = frozenset(k for k, v in TERRAIN.items() if v["land"])
BUILDABLE = frozenset({"grass"})  # 平地 only


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
            # Legacy / unknown → sea
            terrain = "sea"
        building = data.get("building")
        if building in (None, "none") or building not in BUILDINGS:
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
            self._log("島已生成：中央 7 格陸地（泥／草），其餘為海。")

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
        return self.cell(i, j).terrain in LAND_TERRAINS

    def land_count(self) -> int:
        return sum(
            1 for row in self.cells for c in row if c.terrain in LAND_TERRAINS
        )

    def building_count(self, kind: str) -> int:
        return sum(1 for row in self.cells for c in row if c.building == kind)

    def _adjacent_to_land(self, i: int, j: int) -> bool:
        return any(self.is_land(ni, nj) for ni, nj in neighbors(i, j, self.size))

    def can_landfill(self, i: int, j: int) -> bool:
        """填海：海→淺灘 or 淺灘→荒地；須鄰陸。"""
        c = self.cell(i, j)
        if c.terrain not in ("sea", "shallow"):
            return False
        return self._adjacent_to_land(i, j)

    def can_level(self, i: int, j: int) -> bool:
        """整地：荒地→平地、清建築、或森→平地（伐採佔位）。"""
        c = self.cell(i, j)
        if c.terrain not in LAND_TERRAINS:
            return False
        if c.building is not None:
            return True
        if c.terrain in ("dirt", "forest"):
            return True
        return False  # empty 平地 — nothing to do

    def can_afforest(self, i: int, j: int) -> bool:
        """植林：空平地→森。"""
        c = self.cell(i, j)
        return c.terrain == "grass" and c.building is None

    def place_building(self, i: int, j: int, kind: str) -> str:
        if kind not in ("farm", "factory"):
            return "未知建築"
        c = self.cell(i, j)
        if c.terrain not in BUILDABLE:
            return "只能在平地上建設（請先整地）"
        if c.building is not None:
            return "此格已有建築（請先移除或整地）"
        cost = int(BUILDINGS[kind]["cost"])
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
        """填海造陸 placeholder：海→淺灘；淺灘→荒地。"""
        if not self.can_landfill(i, j):
            return "只能填與陸地相鄰的海／淺灘"
        if self.funds < COST_LANDFILL:
            return f"資金不足（填海需要 {COST_LANDFILL}）"
        c = self.cell(i, j)
        self.funds -= COST_LANDFILL
        if c.terrain == "sea":
            self.cells[i][j] = Cell("shallow")
            step = "海→淺灘"
        else:
            self.cells[i][j] = Cell("dirt")
            step = "淺灘→荒地"
        self._log(
            f"回合 {self.turn}：填海 ({i},{j}) {step}（−{COST_LANDFILL} 資金）"
        )
        return "ok"

    def level_land(self, i: int, j: int) -> str:
        """整地 placeholder：荒地／森→平地；並清除建築。"""
        if not self.can_level(i, j):
            return "此格無需整地（須為荒地、森、或有建築的陸地）"
        if self.funds < COST_LEVEL:
            return f"資金不足（整地需要 {COST_LEVEL}）"
        c = self.cell(i, j)
        self.funds -= COST_LEVEL
        cleared = c.building
        c.building = None
        prev = c.terrain
        if c.terrain in ("dirt", "forest"):
            c.terrain = "grass"
        # grass + building: terrain stays grass after clear
        parts = [f"({i},{j})"]
        if prev != c.terrain:
            parts.append(f"{TERRAIN[prev]['label']}→平地")
        if cleared:
            parts.append(f"清除{BUILDINGS[cleared]['label']}")
        self._log(
            f"回合 {self.turn}：整地 {' '.join(parts)}（−{COST_LEVEL} 資金）"
        )
        return "ok"

    def afforest(self, i: int, j: int) -> str:
        """植林 placeholder：平地→森。"""
        if not self.can_afforest(i, j):
            return "只能在空的平地上植林"
        if self.funds < COST_AFFOREST:
            return f"資金不足（植林需要 {COST_AFFOREST}）"
        self.funds -= COST_AFFOREST
        self.cells[i][j] = Cell("forest")
        self._log(f"回合 {self.turn}：植林 ({i},{j})（−{COST_AFFOREST} 資金）")
        return "ok"

    def next_turn(self) -> List[str]:
        """Advance one turn: farm food, factory funds, food need, pop stub."""
        notes: List[str] = []
        farms = self.building_count("farm")
        factories = self.building_count("factory")

        # Optional labor stub (display only — production stays flat for short loop).
        farm_slots = farms * 100
        factory_slots = factories * 1000
        avail = max(0, self.population)
        farm_labor = min(avail, farm_slots)
        avail -= farm_labor
        factory_labor = min(avail, factory_slots)
        notes.append(
            f"勞動 stub：農場 {farm_labor}/{farm_slots}、"
            f"工場 {factory_labor}/{factory_slots}（產能暫不扣減）"
        )

        food_gain = farms * FOOD_PER_FARM
        funds_gain = factories * FUNDS_PER_FACTORY
        food_need = max(0, (self.population // 500) * FOOD_PER_500_POP)
        if food_need == 0 and self.population > 0:
            food_need = MIN_FOOD_NEED

        self.food += food_gain
        self.funds += funds_gain
        notes.append(
            f"農場×{farms} 產糧 +{food_gain}；工場×{factories} 產資 +{funds_gain}"
        )

        if self.food >= food_need:
            self.food -= food_need
            notes.append(f"人口 {self.population} 消耗糧食 −{food_need}")
            # Soft population stub: fed + farms/land → gentle growth.
            growth = 0
            if farms > 0 or self.land_count() >= 7:
                growth = random.randint(0, 20) + farms * 5
            self.population = min(20000, self.population + growth)
            if growth:
                notes.append(f"人口 stub +{growth} → {self.population}")
        else:
            starved = self.food
            self.food = 0
            loss = max(10, self.population // 10)
            self.population = max(0, self.population - loss)
            notes.append(
                f"糧食不足（僅 {starved}）！人口 −{loss} → {self.population}"
            )

        self.turn += 1
        for n in notes:
            self._log(f"回合 {self.turn - 1}→{self.turn}：{n}")
        return notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 2,
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
