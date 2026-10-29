"""In-memory island state + simplified Hakoniwa Islands 2–inspired turn loop.

v1 deepen: catalog place costs, terrain commands (整地／填海／植林／伐採),
forest tree growth + timber→funds, farm food + factory funds turn processing,
optional population stub, visitor guestbook (name + text), color-block monster
events (飛彈 stub), village/town/city terrain evolution + fire/typhoon/quake
disaster stubs, 防衛設施／飛彈基地 color-block buildings (spawn/stomp/missile stubs),
港灣／造船所／貿易輸出（臨海色塊；糧食→資金）,
紀念碑色塊＋簡易島分數／安穩（國威；抗踩踏；抑火災如森）.
Color-block placeholders only — user art later.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .grid import GRID_SIZE, center_cluster, neighbors

# Visitor guestbook limits (島際留言板 v1).
MAX_GUEST_NAME = 24
MAX_GUEST_TEXT = 200
MAX_GUEST_COMMENTS = 100

# ---------------------------------------------------------------------------
# Catalog-inspired costs (箱庭諸島2 定本；億円／噸 units as soft placeholders)
# See docs/hakoniwa-content-catalog.md
# ---------------------------------------------------------------------------
COST_FARM = 20          # 農場整備
COST_FACTORY = 100      # 工場建設
COST_LANDFILL = 150     # 埋め立て：海→淺灘 or 淺灘→荒地
COST_LEVEL = 5          # 整地：荒地→平地（亦可清建築）
COST_AFFOREST = 50      # 植林：平地→森
COST_HARVEST = 0        # 伐採：森→平地（免費；木材瞬售）
COST_MISSILE = 20       # ミサイル発射 stub（定本 20 億／發；無基地時）
COST_MISSILE_CHEAP = 10 # 有飛彈基地時較便宜
COST_MISSILE_BASE = 300 # ミサイル基地（定本 300 億）
COST_DEFENSE = 1000     # 防衛施設（定本 1000 億）
COST_HARBOR = 800       # 港灣（變體／改造常見 800 億；須臨海）
COST_SHIPYARD = 500     # 造船所（變體常見 500 億；須臨海）
COST_MONUMENT = 9999    # 記念碑建造（定本 9999 億；國威／順位用）

# Forest tree stock (catalog 木 100～20000；+100／回合；新植林 100).
TREE_MIN = 100
TREE_MAX = 20000
TREE_GROWTH_PER_TURN = 100
# Timber instant-sale: 100 本 ≈ 5 億；不入庫.
TIMBER_LOT = 100
FUNDS_PER_TIMBER_LOT = 5

# Food export (定本 10000 噸≈10 億；本機短局縮為 100 噸≈5 資金).
# 需島上有港灣或造船所；不推進回合.
FOOD_EXPORT_LOT = 100
FUNDS_PER_FOOD_LOT = 5

# Defense / missile-base interaction stubs (hex radius; catalog 周圍 2).
DEFENSE_RADIUS = 2
DEFENSE_SPAWN_FACTOR = 0.25   # spawn chance × this when any land near a defense
DEFENSE_STOMP_SAVE_CHANCE = 0.65  # near defense: chance stomp skips building/terrain wipe

# Placeable building kinds on 平地（港灣／造船所另須臨海）.
PLACEABLE_BUILDINGS = frozenset(
    {
        "farm",
        "factory",
        "defense",
        "missile_base",
        "harbor",
        "shipyard",
        "monument",
    }
)
COASTAL_BUILDINGS = frozenset({"harbor", "shipyard"})
# Catalog: 紀念碑抗怪獸踩踏、抑火災如森（鄰居減火）.
MONSTER_PROOF_BUILDINGS = frozenset({"monument"})

# Island score weights (local ranking stub; 順位／國威簡易統計).
SCORE_PER_POP = 1
SCORE_PER_LAND = 10
SCORE_PER_MONUMENT = 2000
SCORE_PER_FARM = 20
SCORE_PER_FACTORY = 50
SCORE_PER_HARBOR = 80
SCORE_PER_SHIPYARD = 60
SCORE_PER_DEFENSE = 40
SCORE_PER_MISSILE_BASE = 30
SCORE_PER_VILLAGE = 30
SCORE_PER_TOWN = 80
SCORE_PER_CITY = 150
SCORE_FUNDS_DIV = 20
SCORE_FOOD_DIV = 10
# Soft happiness／安穩：每座紀念碑餵飽時人口成長加成（輕量）.
HAPPINESS_POP_PER_MONUMENT = 5

# Turn yields (simplified short loop; not server-accurate).
FOOD_PER_FARM = 100     # ~100 人農場 → 100 噸／回合
FUNDS_PER_FACTORY = 10  # catalog ~1 億／千人；本機短局用 ×10 回饋
FOOD_PER_500_POP = 100  # 人口每 500 人／回合耗約 100 噸
MIN_FOOD_NEED = 20      # 小島 soft floor

START_FUNDS = 1000
START_FOOD = 500
START_POP = 100

# Monster event thresholds (local short loop — catalog ~人口 10 萬 scaled down).
MONSTER_MIN_POP = 150
MONSTER_MIN_TURN = 3
MONSTER_BASE_CHANCE = 0.12
MONSTER_CHANCE_PER_LAND = 0.01
MONSTER_MAX_CHANCE = 0.45
MONSTER_REWARD = 30     # 殘骸換資金 stub
MAX_MONSTERS = 1        # v1: one color-block 怪獸 at a time

# Settlement evolution (catalog 村／町／都市; pop thresholds scaled for short loop).
# Catalog: 平地 near farm/settlement → 村 ~20%/turn; 村→町@3000, 町→都市@10000.
SETTLEMENT_SPAWN_CHANCE = 0.20
VILLAGE_TO_TOWN_POP = 300    # simplified (catalog ~3000)
TOWN_TO_CITY_POP = 1000      # simplified (catalog ~10000)

# Disaster stubs (per-candidate cell chance; forest neighbors mitigate fire/typhoon).
FIRE_BASE_CHANCE = 0.08
TYPHOON_BASE_CHANCE = 0.06
QUAKE_BASE_CHANCE = 0.05
FOREST_FIRE_FACTOR = 0.25     # any adjacent 森 → fire chance × this
FOREST_TYPHOON_FACTOR = 0.35  # any adjacent 森 → typhoon chance × this

# Terrain kinds — map paints flat top textures (dirt／grass／sea) via tiles.py;
# ``color`` remains fallback / tint basis. Opening map: 中央 7 泥／草, rest 海.
TERRAIN = {
    "sea": {"label": "海", "color": (42, 110, 168), "land": False},
    "shallow": {"label": "淺灘", "color": (72, 148, 176), "land": False},
    "dirt": {"label": "荒地", "color": (139, 90, 43), "land": True},
    "grass": {"label": "平地", "color": (74, 143, 60), "land": True},
    "forest": {"label": "森", "color": (36, 96, 48), "land": True},
    # 居住地形（泥地貼圖＋色洗；建築仍色塊）
    "village": {"label": "村", "color": (186, 150, 96), "land": True},
    "town": {"label": "町", "color": (168, 118, 72), "land": True},
    "city": {"label": "都市", "color": (128, 96, 110), "land": True},
}

# Buildings as solid color blocks on 平地.
BUILDINGS = {
    None: {"label": "（無）", "color": None, "cost": 0},
    "farm": {"label": "農場", "color": (210, 190, 60), "cost": COST_FARM},
    "factory": {"label": "工場", "color": (120, 120, 130), "cost": COST_FACTORY},
    # 軍事色塊佔位（定本費用；美術後補）
    "defense": {"label": "防衛設施", "color": (48, 88, 160), "cost": COST_DEFENSE},
    "missile_base": {"label": "飛彈基地", "color": (160, 72, 48), "cost": COST_MISSILE_BASE},
    # 港灣／造船所色塊（臨海；美術後補）
    "harbor": {"label": "港灣", "color": (40, 140, 168), "cost": COST_HARBOR},
    "shipyard": {"label": "造船所", "color": (56, 72, 112), "cost": COST_SHIPYARD},
    # 紀念碑色塊（定本國威；美術後補）
    "monument": {"label": "紀念碑", "color": (168, 140, 72), "cost": COST_MONUMENT},
}

# Monsters as solid color-block placeholders (squares on map; art later).
MONSTERS = {
    "inora": {
        "label": "伊諾拉",
        "color": (70, 200, 90),  # 綠怪色塊
        "hp": 1,
    },
}

# Back-compat aliases used by older scaffold call sites / tests.
LANDFILL_COST = COST_LANDFILL

Coord = Tuple[int, int]
LAND_TERRAINS = frozenset(k for k, v in TERRAIN.items() if v["land"])
SETTLEMENT_TERRAINS = frozenset({"village", "town", "city"})
BUILDABLE = frozenset({"grass"})  # 平地 only（村／町／都市請先整地）
SAVE_VERSION = 7


def timber_funds(trees: int) -> int:
    """Instant-sale funds for a tree stock (catalog 100本≈5億；floor lots)."""
    if trees <= 0:
        return 0
    return (int(trees) // TIMBER_LOT) * FUNDS_PER_TIMBER_LOT


def food_export_funds(lots: int) -> int:
    """Funds gained for exporting ``lots`` food batches."""
    return max(0, int(lots)) * FUNDS_PER_FOOD_LOT


def clamp_trees(trees: int) -> int:
    return max(0, min(TREE_MAX, int(trees)))


def compute_island_score(
    *,
    population: int,
    funds: int,
    food: int,
    land: int,
    monuments: int,
    farms: int,
    factories: int,
    harbors: int,
    shipyards: int,
    defenses: int,
    missile_bases: int,
    villages: int,
    towns: int,
    cities: int,
) -> int:
    """簡易島分數（順位／國威 stub；紀念碑權重大）."""
    return (
        max(0, int(population)) * SCORE_PER_POP
        + max(0, int(land)) * SCORE_PER_LAND
        + max(0, int(monuments)) * SCORE_PER_MONUMENT
        + max(0, int(farms)) * SCORE_PER_FARM
        + max(0, int(factories)) * SCORE_PER_FACTORY
        + max(0, int(harbors)) * SCORE_PER_HARBOR
        + max(0, int(shipyards)) * SCORE_PER_SHIPYARD
        + max(0, int(defenses)) * SCORE_PER_DEFENSE
        + max(0, int(missile_bases)) * SCORE_PER_MISSILE_BASE
        + max(0, int(villages)) * SCORE_PER_VILLAGE
        + max(0, int(towns)) * SCORE_PER_TOWN
        + max(0, int(cities)) * SCORE_PER_CITY
        + max(0, int(funds)) // SCORE_FUNDS_DIV
        + max(0, int(food)) // SCORE_FOOD_DIV
    )


@dataclass
class Cell:
    terrain: str = "sea"
    building: Optional[str] = None
    trees: int = 0  # only meaningful on 森；植林起點 TREE_MIN

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "terrain": self.terrain,
            "building": self.building,
        }
        if self.terrain == "forest" or self.trees:
            data["trees"] = int(self.trees)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Cell":
        terrain = data.get("terrain", "sea")
        if terrain not in TERRAIN:
            # Legacy / unknown → sea
            terrain = "sea"
        building = data.get("building")
        if building in (None, "none") or building not in BUILDINGS:
            building = None
        try:
            trees = int(data.get("trees") or 0)
        except (TypeError, ValueError):
            trees = 0
        if terrain == "forest":
            # Legacy saves without trees → treat as newly planted stock.
            trees = clamp_trees(trees if trees > 0 else TREE_MIN)
        else:
            trees = 0
        return cls(terrain=terrain, building=building, trees=trees)


@dataclass
class GuestbookEntry:
    """One visitor message on the island bulletin board."""

    id: str
    name: str
    text: str
    at: str  # ISO-ish UTC timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "text": self.text,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["GuestbookEntry"]:
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or "").strip()
        text = str(data.get("text") or "").strip()
        if not name or not text:
            return None
        entry_id = str(data.get("id") or "").strip() or uuid.uuid4().hex[:12]
        at = str(data.get("at") or "").strip() or _utc_now_iso()
        return cls(
            id=entry_id[:32],
            name=name[:MAX_GUEST_NAME],
            text=text[:MAX_GUEST_TEXT],
            at=at[:40],
        )


@dataclass
class Monster:
    """Color-block 怪獸 placeholder on a land cell (user art later)."""

    kind: str = "inora"
    i: int = 0
    j: int = 0
    hp: int = 1

    def label(self) -> str:
        meta = MONSTERS.get(self.kind) or MONSTERS["inora"]
        return str(meta["label"])

    def color(self) -> Tuple[int, int, int]:
        meta = MONSTERS.get(self.kind) or MONSTERS["inora"]
        return tuple(meta["color"])  # type: ignore[return-value]

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "i": self.i, "j": self.j, "hp": self.hp}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["Monster"]:
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind") or "inora").strip()
        if kind not in MONSTERS:
            kind = "inora"
        try:
            i = int(data.get("i"))
            j = int(data.get("j"))
            hp = int(data.get("hp") if data.get("hp") is not None else MONSTERS[kind]["hp"])
        except (TypeError, ValueError):
            return None
        if hp <= 0:
            return None
        return cls(kind=kind, i=i, j=j, hp=hp)


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_comments(raw: Any) -> List[GuestbookEntry]:
    if not isinstance(raw, list):
        return []
    out: List[GuestbookEntry] = []
    for item in raw:
        entry = GuestbookEntry.from_dict(item if isinstance(item, dict) else {})
        if entry is not None:
            out.append(entry)
    return out[-MAX_GUEST_COMMENTS:]


def _parse_monsters(raw: Any, size: int) -> List[Monster]:
    if not isinstance(raw, list):
        return []
    out: List[Monster] = []
    for item in raw:
        m = Monster.from_dict(item if isinstance(item, dict) else {})
        if m is None:
            continue
        if not (0 <= m.i < size and 0 <= m.j < size):
            continue
        out.append(m)
        if len(out) >= MAX_MONSTERS:
            break
    return out


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
    comments: List[GuestbookEntry] = field(default_factory=list)
    monsters: List[Monster] = field(default_factory=list)
    island_id: str = "home"  # multi-island catalog id (home | demo-* | …)

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

    def _adjacent_to_sea(self, i: int, j: int) -> bool:
        """True if any neighbor is 海 or 淺灘 (coastal land for 港灣／造船所)."""
        for ni, nj in neighbors(i, j, self.size):
            if self.cell(ni, nj).terrain in ("sea", "shallow"):
                return True
        return False

    def cells_within(self, i: int, j: int, radius: int) -> List[Coord]:
        """Hex BFS: all in-bounds cells within ``radius`` steps (includes self)."""
        if radius < 0:
            return []
        seen = {(i, j)}
        frontier: List[Coord] = [(i, j)]
        for _ in range(radius):
            nxt: List[Coord] = []
            for ci, cj in frontier:
                for ni, nj in neighbors(ci, cj, self.size):
                    if (ni, nj) not in seen:
                        seen.add((ni, nj))
                        nxt.append((ni, nj))
            frontier = nxt
        return list(seen)

    def defense_positions(self) -> List[Coord]:
        return [
            (i, j)
            for i in range(self.size)
            for j in range(self.size)
            if self.cell(i, j).building == "defense"
        ]

    def has_missile_base(self) -> bool:
        return self.building_count("missile_base") > 0

    def has_harbor(self) -> bool:
        return self.building_count("harbor") > 0

    def has_shipyard(self) -> bool:
        return self.building_count("shipyard") > 0

    def monument_count(self) -> int:
        return self.building_count("monument")

    def terrain_count(self, kind: str) -> int:
        return sum(1 for row in self.cells for c in row if c.terrain == kind)

    def can_trade_export(self) -> bool:
        """貿易輸出：島上須有港灣或造船所。"""
        return self.has_harbor() or self.has_shipyard()

    def island_score(self) -> int:
        """簡易島分數（順位／國威 stub；紀念碑權重大）."""
        return compute_island_score(
            population=self.population,
            funds=self.funds,
            food=self.food,
            land=self.land_count(),
            monuments=self.monument_count(),
            farms=self.building_count("farm"),
            factories=self.building_count("factory"),
            harbors=self.building_count("harbor"),
            shipyards=self.building_count("shipyard"),
            defenses=self.building_count("defense"),
            missile_bases=self.building_count("missile_base"),
            villages=self.terrain_count("village"),
            towns=self.terrain_count("town"),
            cities=self.terrain_count("city"),
        )

    def happiness_bonus(self) -> int:
        """安穩 stub：紀念碑帶來的輕量人口成長加成。"""
        return self.monument_count() * HAPPINESS_POP_PER_MONUMENT

    def missile_cost(self) -> int:
        """Cheaper 飛彈 when ≥1 飛彈基地 exists (local-first stub)."""
        return COST_MISSILE_CHEAP if self.has_missile_base() else COST_MISSILE

    def protected_by_defense(self, i: int, j: int) -> bool:
        """True if (i,j) is within DEFENSE_RADIUS of any 防衛設施."""
        for di, dj in self.defense_positions():
            if (i, j) in self.cells_within(di, dj, DEFENSE_RADIUS):
                return True
        return False

    def has_monster(self) -> bool:
        return bool(self.monsters)

    def monster_at(self, i: int, j: int) -> Optional[Monster]:
        for m in self.monsters:
            if m.i == i and m.j == j:
                return m
        return None

    def can_landfill(self, i: int, j: int) -> bool:
        """填海：海→淺灘 or 淺灘→荒地；須鄰陸。"""
        c = self.cell(i, j)
        if c.terrain not in ("sea", "shallow"):
            return False
        return self._adjacent_to_land(i, j)

    def can_level(self, i: int, j: int) -> bool:
        """整地：荒地→平地、清建築、森／村／町／都市→平地。"""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        if c.terrain not in LAND_TERRAINS:
            return False
        if c.building is not None:
            return True
        if c.terrain in ("dirt", "forest") or c.terrain in SETTLEMENT_TERRAINS:
            return True
        return False  # empty 平地 — nothing to do

    def can_afforest(self, i: int, j: int) -> bool:
        """植林：空平地→森。"""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        return c.terrain == "grass" and c.building is None

    def can_harvest(self, i: int, j: int) -> bool:
        """伐採：森→平地並瞬售木材。"""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        return c.terrain == "forest"

    def can_place_building(self, i: int, j: int, kind: str) -> bool:
        """Whether ``kind`` can be placed at (i,j) ignoring funds."""
        if kind not in PLACEABLE_BUILDINGS:
            return False
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        if c.terrain not in BUILDABLE or c.building is not None:
            return False
        if kind in COASTAL_BUILDINGS and not self._adjacent_to_sea(i, j):
            return False
        return True

    def place_building(self, i: int, j: int, kind: str) -> str:
        if kind not in PLACEABLE_BUILDINGS:
            return "未知建築"
        if self.monster_at(i, j) is not None:
            return "此格有怪獸，無法建設"
        c = self.cell(i, j)
        if c.terrain not in BUILDABLE:
            return "只能在平地上建設（請先整地）"
        if c.building is not None:
            return "此格已有建築（請先移除或整地）"
        if kind in COASTAL_BUILDINGS and not self._adjacent_to_sea(i, j):
            label = BUILDINGS[kind]["label"]
            return f"{label}須建在臨海的平地（鄰接海／淺灘）"
        cost = int(BUILDINGS[kind]["cost"])
        if self.funds < cost:
            return f"資金不足（需要 {cost}）"
        self.funds -= cost
        c.building = kind
        label = BUILDINGS[kind]["label"]
        self._log(f"回合 {self.turn}：在 ({i},{j}) 建設{label}（−{cost} 資金）")
        return "ok"

    def export_food(self, lots: int = 1) -> str:
        """貿易輸出：糧食→資金（需港灣或造船所；不推進回合）."""
        if not self.can_trade_export():
            return "需要港灣或造船所才能貿易輸出"
        try:
            lots = int(lots)
        except (TypeError, ValueError):
            lots = 1
        if lots < 1:
            return "輸出批數須至少 1"
        need = lots * FOOD_EXPORT_LOT
        if self.food < need:
            return f"糧食不足（輸出 {lots} 批需 {need} 噸）"
        gain = food_export_funds(lots)
        self.food -= need
        self.funds += gain
        via = []
        if self.has_harbor():
            via.append("港灣")
        if self.has_shipyard():
            via.append("造船所")
        route = "／".join(via) if via else "貿易"
        self._log(
            f"回合 {self.turn}：貿易輸出 {need} 噸糧食→+{gain} 資金"
            f"（經{route}，{lots} 批）"
        )
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
        """整地 placeholder：荒地／森／村／町／都市→平地；並清除建築。"""
        if not self.can_level(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法整地（請先發射飛彈）"
            return "此格無需整地（須為荒地、森、村／町／都市、或有建築的陸地）"
        if self.funds < COST_LEVEL:
            return f"資金不足（整地需要 {COST_LEVEL}）"
        c = self.cell(i, j)
        self.funds -= COST_LEVEL
        cleared = c.building
        c.building = None
        prev = c.terrain
        prev_trees = c.trees
        if c.terrain in ("dirt", "forest") or c.terrain in SETTLEMENT_TERRAINS:
            c.terrain = "grass"
            c.trees = 0
        # grass + building: terrain stays grass after clear
        parts = [f"({i},{j})"]
        if prev != c.terrain:
            if prev == "forest" and prev_trees:
                parts.append(f"森（{prev_trees}本）→平地")
            else:
                parts.append(f"{TERRAIN[prev]['label']}→平地")
        if cleared:
            parts.append(f"清除{BUILDINGS[cleared]['label']}")
        self._log(
            f"回合 {self.turn}：整地 {' '.join(parts)}（−{COST_LEVEL} 資金）"
        )
        return "ok"

    def afforest(self, i: int, j: int) -> str:
        """植林：空平地→森（新林 TREE_MIN 本）。"""
        if not self.can_afforest(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法植林"
            return "只能在空的平地上植林"
        if self.funds < COST_AFFOREST:
            return f"資金不足（植林需要 {COST_AFFOREST}）"
        self.funds -= COST_AFFOREST
        self.cells[i][j] = Cell("forest", trees=TREE_MIN)
        self._log(
            f"回合 {self.turn}：植林 ({i},{j}) → 森（{TREE_MIN}本）"
            f"（−{COST_AFFOREST} 資金）"
        )
        return "ok"

    def harvest(self, i: int, j: int) -> str:
        """伐採：森→平地；木材瞬售成資金（不入庫）。"""
        if not self.can_harvest(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法伐採"
            return "只能伐採森林"
        c = self.cell(i, j)
        trees = clamp_trees(c.trees if c.trees > 0 else TREE_MIN)
        sold = timber_funds(trees)
        c.terrain = "grass"
        c.building = None
        c.trees = 0
        self.funds += sold
        self._log(
            f"回合 {self.turn}：伐採 ({i},{j}) 森（{trees}本）→平地"
            f"（木材瞬售 +{sold} 資金）"
        )
        return "ok"

    def fire_missile(self, i: int, j: int) -> str:
        """飛彈 stub：對選格發射；有飛彈基地則較便宜。命中怪獸則擊破。

        防衛設施周圍：落空飛彈的「附帶傷害」無效（本機無落空毀陸時僅記 log）。
        """
        cost = self.missile_cost()
        if self.funds < cost:
            return f"資金不足（飛彈需要 {cost}）"
        self.funds -= cost
        base_note = "（有飛彈基地）" if self.has_missile_base() else ""
        m = self.monster_at(i, j)
        if m is None:
            # Miss stub: near defense → no collateral (missile damage nullified).
            if self.protected_by_defense(i, j):
                self._log(
                    f"回合 {self.turn}：飛彈落空於 ({i},{j}){base_note}"
                    f" — 防衛設施無效化附帶傷害（−{cost} 資金）"
                )
            else:
                self._log(
                    f"回合 {self.turn}：飛彈落空於 ({i},{j}){base_note}"
                    f"（−{cost} 資金）"
                )
            return "ok"
        m.hp -= 1
        if m.hp <= 0:
            self.monsters = [x for x in self.monsters if x is not m]
            self.funds += MONSTER_REWARD
            self._log(
                f"回合 {self.turn}：飛彈擊破 ({i},{j}) 的{m.label()}{base_note}"
                f"（−{cost}／殘骸 +{MONSTER_REWARD} 資金）"
            )
        else:
            self._log(
                f"回合 {self.turn}：飛彈命中 ({i},{j}) 的{m.label()}{base_note}"
                f"（HP→{m.hp}，−{cost} 資金）"
            )
        return "ok"

    def wait_monster(self) -> str:
        """觀望／待機：本回合不攻擊怪獸（怪獸下回合會行動）。"""
        if not self.monsters:
            return "島上沒有怪獸"
        labels = "、".join(
            f"{m.label()}({m.i},{m.j})" for m in self.monsters
        )
        self._log(f"回合 {self.turn}：對怪獸觀望（{labels}）— 未發射飛彈")
        return "ok"

    def spawn_monster(
        self,
        i: Optional[int] = None,
        j: Optional[int] = None,
        kind: str = "inora",
    ) -> Optional[Monster]:
        """Place a color-block monster on land (tests / forced events)."""
        if len(self.monsters) >= MAX_MONSTERS:
            return None
        if kind not in MONSTERS:
            kind = "inora"
        if i is None or j is None:
            land = self._spawn_candidate_cells()
            if not land:
                return None
            i, j = random.choice(land)
        if not self.is_land(i, j) or self.monster_at(i, j) is not None:
            return None
        meta = MONSTERS[kind]
        m = Monster(kind=kind, i=i, j=j, hp=int(meta["hp"]))
        self.monsters.append(m)
        self._log(
            f"回合 {self.turn}：怪獸出現！{m.label()} 色塊於 ({i},{j})"
        )
        return m

    def _monster_spawn_chance(self) -> float:
        if self.population < MONSTER_MIN_POP or self.turn < MONSTER_MIN_TURN:
            return 0.0
        if len(self.monsters) >= MAX_MONSTERS:
            return 0.0
        chance = MONSTER_BASE_CHANCE + self.land_count() * MONSTER_CHANCE_PER_LAND
        chance = min(MONSTER_MAX_CHANCE, chance)
        # Any 防衛設施 covering land → lower island spawn pressure (simple).
        if self.defense_positions():
            chance *= DEFENSE_SPAWN_FACTOR
        return chance

    def _spawn_candidate_cells(self) -> List[Coord]:
        """Land cells for monster spawn; prefer cells not under defense cover."""
        land = [
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.is_land(x, y) and self.monster_at(x, y) is None
        ]
        open_land = [(x, y) for x, y in land if not self.protected_by_defense(x, y)]
        return open_land if open_land else land

    def _stomp_cell(self, i: int, j: int, monster: Monster) -> List[str]:
        """Monster steps onto a land cell: clear building, land → 荒地.

        防衛設施：踩到則自爆清怪；周圍 2 格則有機率減免踩踏傷害。
        """
        notes: List[str] = []
        c = self.cell(i, j)

        # Catalog: stepping on 防衛施設 → self-destruct clears the monster.
        if c.building == "defense":
            c.building = None
            if c.terrain in LAND_TERRAINS and c.terrain != "dirt":
                c.terrain = "dirt"
            c.trees = 0
            self.monsters = [x for x in self.monsters if x is not monster]
            notes.append(
                f"{monster.label()}踩到防衛設施！自爆清除 ({i},{j})"
            )
            return notes

        # Catalog: 紀念碑抗怪獸踩踏（建物保留；格仍可被踏平為荒地以外的情況除外）.
        if c.building in MONSTER_PROOF_BUILDINGS:
            blabel = BUILDINGS[c.building]["label"]
            notes.append(
                f"{monster.label()}踩上{blabel} ({i},{j}) — 紀念碑屹立不搖"
            )
            return notes

        # Near defense: chance to shrug off stomp damage (simple nearby mitigation).
        if self.protected_by_defense(i, j) and random.random() < DEFENSE_STOMP_SAVE_CHANCE:
            notes.append(
                f"防衛設施減免傷害：{monster.label()}於 ({i},{j}) 未能毀壞"
            )
            return notes

        if c.building is not None:
            blabel = BUILDINGS[c.building]["label"]
            c.building = None
            notes.append(f"{monster.label()}踩毀{blabel} ({i},{j})")
        if c.terrain in LAND_TERRAINS and c.terrain != "dirt":
            prev = TERRAIN[c.terrain]["label"]
            if c.terrain == "forest" and c.trees:
                prev = f"森（{c.trees}本）"
            c.terrain = "dirt"
            c.trees = 0
            notes.append(f"{monster.label()}踏平 {prev}→荒地 ({i},{j})")
        elif not notes:
            notes.append(f"{monster.label()}停留於 ({i},{j})")
        return notes

    def _advance_monsters(self) -> List[str]:
        """Existing monsters move to a random land neighbor (or stay) and stomp."""
        notes: List[str] = []
        for m in list(self.monsters):
            opts = [
                (ni, nj)
                for ni, nj in neighbors(m.i, m.j, self.size)
                if self.is_land(ni, nj) and self.monster_at(ni, nj) is None
            ]
            if opts and random.random() < 0.75:
                ni, nj = random.choice(opts)
                m.i, m.j = ni, nj
            notes.extend(self._stomp_cell(m.i, m.j, m))
        return notes

    def _maybe_spawn_monster(self) -> List[str]:
        chance = self._monster_spawn_chance()
        if chance <= 0 or random.random() >= chance:
            return []
        m = self.spawn_monster()
        if m is None:
            return []
        # spawn_monster already logged; surface a short note for the turn dialog.
        return [f"怪獸出現！{m.label()} 於 ({m.i},{m.j})"]

    def _has_forest_neighbor(self, i: int, j: int) -> bool:
        """Adjacent 森 or 紀念碑 mitigates fire (catalog)；森仍減颱風."""
        return any(
            self.cell(ni, nj).terrain == "forest"
            or self.cell(ni, nj).building == "monument"
            for ni, nj in neighbors(i, j, self.size)
        )

    def _has_forest_for_typhoon(self, i: int, j: int) -> bool:
        """Typhoon mitigation stays 森-only (紀念碑只抑火災)."""
        return any(
            self.cell(ni, nj).terrain == "forest"
            for ni, nj in neighbors(i, j, self.size)
        )

    def _near_farm_or_settlement(self, i: int, j: int) -> bool:
        """Empty 平地 near 農場 or 村／町／都市 can grow a village."""
        for ni, nj in neighbors(i, j, self.size):
            c = self.cell(ni, nj)
            if c.building == "farm":
                return True
            if c.terrain in SETTLEMENT_TERRAINS:
                return True
        return False

    def _evolve_settlements(self) -> List[str]:
        """村／町／都市 terrain evolution on plain land near farms (simplified)."""
        notes: List[str] = []
        # Spawn: empty 平地 adjacent to farm/settlement → 村 (~20%/turn).
        spawn_sites: List[Coord] = []
        for i in range(self.size):
            for j in range(self.size):
                if self.monster_at(i, j) is not None:
                    continue
                c = self.cell(i, j)
                if c.terrain != "grass" or c.building is not None:
                    continue
                if self._near_farm_or_settlement(i, j):
                    spawn_sites.append((i, j))
        for i, j in spawn_sites:
            if random.random() >= SETTLEMENT_SPAWN_CHANCE:
                continue
            self.cell(i, j).terrain = "village"
            notes.append(f"平地出現村落 ({i},{j})")

        # Upgrade by island population thresholds (short-loop scaled).
        for i in range(self.size):
            for j in range(self.size):
                c = self.cell(i, j)
                if c.terrain == "village" and self.population >= VILLAGE_TO_TOWN_POP:
                    c.terrain = "town"
                    notes.append(f"村→町 ({i},{j})（人口 {self.population}）")
                elif c.terrain == "town" and self.population >= TOWN_TO_CITY_POP:
                    c.terrain = "city"
                    notes.append(f"町→都市 ({i},{j})（人口 {self.population}）")
        return notes

    def _grow_forests(self) -> List[str]:
        """Each 森 gains TREE_GROWTH_PER_TURN trees up to TREE_MAX."""
        grown = 0
        capped = 0
        for row in self.cells:
            for c in row:
                if c.terrain != "forest":
                    c.trees = 0
                    continue
                before = clamp_trees(c.trees if c.trees > 0 else TREE_MIN)
                after = clamp_trees(before + TREE_GROWTH_PER_TURN)
                c.trees = after
                if after > before:
                    grown += 1
                elif before >= TREE_MAX:
                    capped += 1
        if grown == 0 and capped == 0:
            return []
        parts = []
        if grown:
            parts.append(f"{grown} 片森各 +{TREE_GROWTH_PER_TURN}本")
        if capped:
            parts.append(f"{capped} 片已達上限 {TREE_MAX}")
        return ["林木生長：" + "；".join(parts)]

    def _apply_disasters(self) -> List[str]:
        """Fire / typhoon / quake stubs; forest neighbors reduce fire & typhoon."""
        notes: List[str] = []

        # Fire: 町／都市／工場 → 荒地（鄰森／紀念碑則不易發生）
        for i in range(self.size):
            for j in range(self.size):
                c = self.cell(i, j)
                flammable = c.terrain in ("town", "city") or c.building == "factory"
                if not flammable:
                    continue
                chance = FIRE_BASE_CHANCE
                if self._has_forest_neighbor(i, j):
                    chance *= FOREST_FIRE_FACTOR
                if random.random() >= chance:
                    continue
                parts: List[str] = []
                if c.building is not None:
                    parts.append(BUILDINGS[c.building]["label"])
                    c.building = None
                if c.terrain in LAND_TERRAINS and c.terrain != "dirt":
                    parts.append(TERRAIN[c.terrain]["label"])
                    c.terrain = "dirt"
                    c.trees = 0
                label = "、".join(parts) if parts else "目標"
                notes.append(f"火災！{label}→荒地 ({i},{j})")

        # Typhoon: 農場 → 平地（清建築；鄰森則較耐；紀念碑不減颱風）
        for i in range(self.size):
            for j in range(self.size):
                c = self.cell(i, j)
                if c.building != "farm":
                    continue
                chance = TYPHOON_BASE_CHANCE
                if self._has_forest_for_typhoon(i, j):
                    chance *= FOREST_TYPHOON_FACTOR
                if random.random() >= chance:
                    continue
                c.building = None
                if c.terrain != "grass":
                    c.terrain = "grass"
                c.trees = 0
                notes.append(f"颱風！農場→平地 ({i},{j})")

        # Quake: 工場／都市 → 荒地（stub；森不減震）
        for i in range(self.size):
            for j in range(self.size):
                c = self.cell(i, j)
                quakable = c.terrain == "city" or c.building == "factory"
                if not quakable:
                    continue
                if random.random() >= QUAKE_BASE_CHANCE:
                    continue
                parts = []
                if c.building is not None:
                    parts.append(BUILDINGS[c.building]["label"])
                    c.building = None
                if c.terrain in LAND_TERRAINS and c.terrain != "dirt":
                    parts.append(TERRAIN[c.terrain]["label"])
                    c.terrain = "dirt"
                    c.trees = 0
                label = "、".join(parts) if parts else "目標"
                notes.append(f"地震！{label}→荒地 ({i},{j})")

        return notes

    def next_turn(self) -> List[str]:
        """Advance one turn: economy → forests → settlements → disasters → monsters."""
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
            # 紀念碑安穩：輕量人口加成（happiness stub）.
            growth = 0
            happy = self.happiness_bonus()
            if farms > 0 or self.land_count() >= 7 or happy > 0:
                growth = random.randint(0, 20) + farms * 5 + happy
            self.population = min(20000, self.population + growth)
            if growth:
                if happy:
                    notes.append(
                        f"人口 stub +{growth}（含紀念碑安穩 +{happy}）"
                        f" → {self.population}"
                    )
                else:
                    notes.append(f"人口 stub +{growth} → {self.population}")
        else:
            starved = self.food
            self.food = 0
            loss = max(10, self.population // 10)
            self.population = max(0, self.population - loss)
            notes.append(
                f"糧食不足（僅 {starved}）！人口 −{loss} → {self.population}"
            )

        # Forest growth (catalog +100本／回合，上限 TREE_MAX).
        notes.extend(self._grow_forests())

        # Settlement growth / tier upgrades (local-first color-block terrains).
        notes.extend(self._evolve_settlements())

        # Disaster stubs (fire / typhoon / quake).
        notes.extend(self._apply_disasters())

        # Monster phase: existing monsters act; otherwise chance to appear.
        if self.monsters:
            notes.extend(self._advance_monsters())
        else:
            notes.extend(self._maybe_spawn_monster())

        # Island score snapshot for status/log (順位／國威簡易統計).
        score = self.island_score()
        monuments = self.monument_count()
        notes.append(
            f"島分數 {score}"
            + (f"（紀念碑×{monuments}）" if monuments else "")
        )

        self.turn += 1
        for n in notes:
            # spawn_monster already wrote its own log line; avoid duplicate.
            if n.startswith("怪獸出現"):
                continue
            self._log(f"回合 {self.turn - 1}→{self.turn}：{n}")
        return notes

    def list_comments(self) -> List[GuestbookEntry]:
        return list(self.comments)

    def add_comment(self, name: str, text: str) -> str:
        """Post a visitor guestbook message. Returns 'ok' or an error string."""
        clean_name = (name or "").strip()
        clean_text = (text or "").strip()
        if not clean_name:
            return "請輸入名字"
        if not clean_text:
            return "請輸入留言"
        if len(clean_name) > MAX_GUEST_NAME:
            return f"名字過長（最多 {MAX_GUEST_NAME} 字）"
        if len(clean_text) > MAX_GUEST_TEXT:
            return f"留言過長（最多 {MAX_GUEST_TEXT} 字）"
        entry = GuestbookEntry(
            id=uuid.uuid4().hex[:12],
            name=clean_name,
            text=clean_text,
            at=_utc_now_iso(),
        )
        self.comments.append(entry)
        if len(self.comments) > MAX_GUEST_COMMENTS:
            self.comments = self.comments[-MAX_GUEST_COMMENTS:]
        self._log(f"訪客留言：{clean_name}")
        return "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SAVE_VERSION,
            "id": self.island_id,
            "name": self.name,
            "size": self.size,
            "turn": self.turn,
            "funds": self.funds,
            "food": self.food,
            "population": self.population,
            "cells": [[c.to_dict() for c in row] for row in self.cells],
            "log": list(self.log[-40:]),
            "comments": [c.to_dict() for c in self.comments],
            "monsters": [m.to_dict() for m in self.monsters],
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
        raw_id = data.get("id") or data.get("island_id") or "home"
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
            comments=_parse_comments(data.get("comments")),
            monsters=_parse_monsters(data.get("monsters"), size),
            island_id=str(raw_id).strip() or "home",
        )
        # Drop monsters that somehow landed on non-land (corrupt save).
        state.monsters = [
            m for m in state.monsters if state.is_land(m.i, m.j)
        ]
        return state

    @classmethod
    def new_game(cls, island_id: str = "home", name: str = "箱庭島") -> "IslandState":
        return cls(island_id=island_id, name=name)
