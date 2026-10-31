"""In-memory island state + simplified Hakoniwa Islands 2–inspired turn loop.

v1 deepen: catalog place costs, terrain commands (整地／填海／植林／伐採／造山／掘削),
forest tree growth + timber→funds, farm／工場／採掘場 production with labor
assignment (農場優先), optional population stub, visitor guestbook (name + text),
color-block monster events (飛彈 stub), village/town/city terrain evolution +
fire/typhoon/quake/volcano/tsunami disaster stubs, 防衛設施／飛彈基地 color-block
buildings (spawn/stomp/missile stubs), 港灣／造船所／貿易輸出（臨海色塊；糧食→資金）,
紀念碑色塊＋簡易島分數／安穩（國威；抗踩踏；抑火災如森）,
山岳地形＋採掘場色塊（僅山上；產資）,
防波堤色塊（臨海；減海嘯）＋海底油田（掘削／探油；被動產資；枯竭）,
銀行／超市／神社色塊（變體：資金緩衝、買糧、分數／安穩加成）,
公園色塊＋誘致活動（都市計畫：安穩／生村加成；定本誘致 1000）,
空港色塊＋觀光訪客增益（交通／觀光收入／留言小費／誘致加成）,
ロケット基地色塊＋觀測衛星發射（減震／海嘯／噴火；變體啟發費用）,
酒店／賭場色塊＋娛樂觀光收入（變體：住宿／賭場觀光名所；費用估算見常數）,
大學／研究所色塊＋輕量研究 buff（變體：下一科技折扣／減災；費用估算見常數）.
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
COST_QUARRY = 300       # 採掘場整備（定本 300 億；僅山上）
COST_LANDFILL = 150     # 埋め立て：海→淺灘 or 淺灘→荒地
COST_LEVEL = 5          # 整地：荒地→平地（亦可清建築；山→荒地）
COST_RAISE = 100        # 造山／隆起 stub：荒地／平地→山（本機短局；定本多靠噴火）
COST_EXCAVATE = 200     # 掘削：陸→淺灘／淺灘→海；海上掘削可找海底油田
COST_AFFOREST = 50      # 植林：平地→森
COST_HARVEST = 0        # 伐採：森→平地（免費；木材瞬售）
COST_MISSILE = 20       # ミサイル発射 stub（定本 20 億／發；無基地時）
COST_MISSILE_CHEAP = 10 # 有飛彈基地時較便宜
COST_MISSILE_BASE = 300 # ミサイル基地（定本 300 億）
COST_DEFENSE = 1000     # 防衛施設（定本 1000 億）
COST_HARBOR = 800       # 港灣（變體／改造常見 800 億；須臨海）
COST_SHIPYARD = 500     # 造船所（變體常見 500 億；須臨海）
COST_BREAKWATER = 200   # 防波堤（變體／防災；臨海；減海嘯）
COST_MONUMENT = 9999    # 記念碑建造（定本 9999 億；國威／順位用）
COST_BANK = 500         # 銀行（變體／App：超上限存款緩衝）
COST_SUPERMARKET = 300  # 超市（變體：資金買糧食）
COST_SHRINE = 800       # 神社（變體：島分數／安穩加成）
COST_PARK = 250         # 公園（變體／都市計畫：安穩＋誘發村落）
COST_ATTRACT = 1000     # 誘致活動（定本 1000 億；當回合人口更易增）
# 空港：目錄費用為「?」（島あげます交通設施）。本機採箱庭2／變體常見區間估算：
# 高於港灣(800)／神社(800)、近防衛(1000)、遠低於紀念碑(9999) → 1500。
COST_AIRPORT = 1500     # 空港（交通／觀光樞紐色塊；平地）
# ロケット基地：目錄／變體常為「?」或紀念碑附屬台。本機估算：
# 高於空港(1500)、近究想「宇宙衛星建設」2000、遠低於紀念碑(9999) → 2000。
COST_ROCKET_BASE = 2000  # ロケット基地（平地色塊；解鎖衛星發射）
# 發射：箱庭諸島2 Ex「觀測衛星」800（需基地）；本機同額發射指令。
COST_ROCKET_LAUNCH = 800  # 觀測衛星發射（不推進回合；需 ≥1 ロケット基地）
# 酒店：目錄「海之家／民宿／度假村」費用為「?」。本機估算：
# 高於公園(250)／超市(300)、低於神社(800)／港灣(800) → 600。
COST_HOTEL = 600  # 酒店（住宿觀光色塊；平地）
# 賭場：目錄「賭場／觀光名所」「遊樂園」費用為「?」。本機採賭場色塊：
# 高於酒店(600)／神社(800)、低於空港(1500)／ロケット(2000) → 1100。
COST_CASINO = 1100  # 賭場（娛樂觀光色塊；平地；依人口加碼收入）
# 大學：目錄「大學」費用為「?」（島あげます發展設施）。本機估算：
# 高於酒店(600)、低於神社(800)／港灣(800) → 700。
COST_UNIVERSITY = 700  # 大學（教育／研究色塊；平地；下一科技折扣）
# 研究所：目錄「研究所」費用為「?」。本機估算：
# 高於神社(800)、低於賭場(1100)／空港(1500) → 950。
COST_RESEARCH_LAB = 950  # 研究所（研究色塊；平地；輕量減災）

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

# Soft funds cap (定本約 9999 億捨棄)；有銀行則溢出進存款緩衝.
FUNDS_SOFT_CAP = 9999
BANK_TRANSFER_LOT = 100  # 手動存／提一批
# 超市買糧：比貿易輸出略貴（防無限套利；100 噸≈8 資金）.
FOOD_BUY_LOT = 100
FUNDS_PER_FOOD_BUY = 8

# Defense / missile-base interaction stubs (hex radius; catalog 周圍 2).
DEFENSE_RADIUS = 2
DEFENSE_SPAWN_FACTOR = 0.25   # spawn chance × this when any land near a defense
DEFENSE_STOMP_SAVE_CHANCE = 0.65  # near defense: chance stomp skips building/terrain wipe

# Placeable building kinds on 平地（港灣／造船所另須臨海）.
PLACEABLE_BUILDINGS = frozenset(
    {
        "farm",
        "factory",
        "quarry",
        "defense",
        "missile_base",
        "harbor",
        "shipyard",
        "breakwater",
        "monument",
        "bank",
        "supermarket",
        "shrine",
        "park",
        "airport",
        "rocket_base",
        "hotel",
        "casino",
        "university",
        "research_lab",
    }
)
COASTAL_BUILDINGS = frozenset({"harbor", "shipyard", "breakwater"})
# Catalog: 採掘場僅能整備在山上.
MOUNTAIN_ONLY_BUILDINGS = frozenset({"quarry"})
# Catalog: 紀念碑抗怪獸踩踏、抑火災如森（鄰居減火）.
MONSTER_PROOF_BUILDINGS = frozenset({"monument"})
# Water-like terrains (海嘯鄰接／臨海判定；油田算海域).
WATER_TERRAINS = frozenset({"sea", "shallow", "oilfield"})

# Island score weights (local ranking stub; 順位／國威簡易統計).
SCORE_PER_POP = 1
SCORE_PER_LAND = 10
SCORE_PER_MONUMENT = 2000
SCORE_PER_FARM = 20
SCORE_PER_FACTORY = 50
SCORE_PER_QUARRY = 70
SCORE_PER_MOUNTAIN = 15
SCORE_PER_HARBOR = 80
SCORE_PER_SHIPYARD = 60
SCORE_PER_BREAKWATER = 50
SCORE_PER_OILFIELD = 120
SCORE_PER_DEFENSE = 40
SCORE_PER_MISSILE_BASE = 30
SCORE_PER_BANK = 90
SCORE_PER_SUPERMARKET = 40
SCORE_PER_SHRINE = 800
SCORE_PER_PARK = 150
SCORE_PER_AIRPORT = 500  # 交通設施：島分數權重高於港灣
SCORE_PER_ROCKET_BASE = 400  # 宇宙設施：略低於空港
SCORE_PER_SATELLITE = 300  # 在軌觀測衛星（發射後）
SCORE_PER_HOTEL = 200  # 住宿觀光：低於空港／賭場
SCORE_PER_CASINO = 320  # 娛樂觀光：介於公園與空港之間
SCORE_PER_UNIVERSITY = 280  # 教育設施：介於酒店與賭場
SCORE_PER_RESEARCH_LAB = 380  # 研究設施：介於賭場與ロケット
SCORE_PER_VILLAGE = 30
SCORE_PER_TOWN = 80
SCORE_PER_CITY = 150
SCORE_FUNDS_DIV = 20
SCORE_FOOD_DIV = 10
# Soft happiness／安穩：每座紀念碑／神社／公園餵飽時人口成長加成（輕量）.
HAPPINESS_POP_PER_MONUMENT = 5
HAPPINESS_POP_PER_SHRINE = 8
HAPPINESS_POP_PER_PARK = 6
# 公園鄰格提高平地→村機率（都市計畫 stub）.
PARK_SETTLEMENT_SPAWN_BONUS = 0.15
# 誘致活動：下一次 next_turn 餵飽時額外人頭.
ATTRACT_POP_BONUS = 40
# 空港＋誘致：有空港時誘致再加人口（觀光 inbound stub）.
ATTRACT_AIRPORT_EXTRA = 20
# 空港觀光收入（每座／回合；再依人口加碼）與訪客留言小費.
TOURISM_FUNDS_BASE = 12
TOURISM_FUNDS_PER_100_POP = 3
VISITOR_TIP_FUNDS = 20  # 留言板小費（需 ≥1 空港或酒店）
# 酒店住宿觀光收入（每座／回合；再依人口加碼；低於空港）.
HOTEL_TOURISM_BASE = 8
HOTEL_TOURISM_PER_100_POP = 2
# 賭場娛樂觀光收入（每座／回合；再依人口加碼；高於酒店）.
CASINO_TOURISM_BASE = 18
CASINO_TOURISM_PER_100_POP = 5
# 觀測衛星：地震／海嘯／噴火機率 × 此係數（Ex 約 1/4；本機同量級）.
SATELLITE_DISASTER_FACTOR = 0.25
# 大學研究 buff：有 ≥1 大學時觀測衛星發射折扣（科技 stub；發射 800→600）.
UNIVERSITY_TECH_DISCOUNT = 200
# 研究所減災：地震／海嘯／噴火機率 × 此係數（輕於衛星 0.25；可與衛星疊乘）.
RESEARCH_LAB_DISASTER_FACTOR = 0.7

# Turn yields (simplified short loop; not server-accurate).
FOOD_PER_FARM = 100     # ~100 人農場 → 100 噸／回合
FUNDS_PER_FACTORY = 10   # catalog ~1 億／千人；本機短局用 ×10 回饋
FUNDS_PER_QUARRY = 8    # catalog 採掘場產資；本機短局略低於工場
FUNDS_PER_OILFIELD = 50  # catalog 海底油田約千億級；本機短局被動產資
FOOD_PER_500_POP = 100  # 人口每 500 人／回合耗約 100 噸
MIN_FOOD_NEED = 20      # 小島 soft floor
# 海上掘削發現油田機率（定本約 1%/次×數量；短局提高可玩性）.
OIL_DISCOVER_CHANCE = 0.55
OIL_DEPLETION_CHANCE = 0.08  # 油田枯竭→海

# Labor slots (catalog: 農場優先填滿；工場／採掘場分剩餘人口).
LABOR_PER_FARM = 100
LABOR_PER_FACTORY = 1000
LABOR_PER_QUARRY = 500   # catalog 初雇約 5 千；短局縮為 500

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
VOLCANO_BASE_CHANCE = 0.04  # 噴火：隨機陸格→山（可整備採掘場）
TSUNAMI_BASE_CHANCE = 0.04  # 海嘯：臨海設施→荒地
TSUNAMI_PER_SEA_NEIGHBOR = 0.03  # 鄰海域越多越危險
FOREST_FIRE_FACTOR = 0.25     # any adjacent 森 → fire chance × this
FOREST_TYPHOON_FACTOR = 0.35  # any adjacent 森 → typhoon chance × this
BREAKWATER_TSUNAMI_FACTOR = 0.25  # adjacent 防波堤 → tsunami chance × this

# Terrain kinds — map paints flat top textures (dirt／grass／sea) via tiles.py;
# ``color`` remains fallback / tint basis. Opening map: 中央 7 泥／草, rest 海.
TERRAIN = {
    "sea": {"label": "海", "color": (42, 110, 168), "land": False},
    "shallow": {"label": "淺灘", "color": (72, 148, 176), "land": False},
    "oilfield": {"label": "海底油田", "color": (48, 52, 58), "land": False},
    "dirt": {"label": "荒地", "color": (139, 90, 43), "land": True},
    "grass": {"label": "平地", "color": (74, 143, 60), "land": True},
    "forest": {"label": "森", "color": (36, 96, 48), "land": True},
    "mountain": {"label": "山", "color": (110, 100, 88), "land": True},
    # 居住地形（泥地貼圖＋色洗；建築仍色塊）
    "village": {"label": "村", "color": (186, 150, 96), "land": True},
    "town": {"label": "町", "color": (168, 118, 72), "land": True},
    "city": {"label": "都市", "color": (128, 96, 110), "land": True},
}

# Buildings as solid color blocks on 平地（採掘場在山上）.
BUILDINGS = {
    None: {"label": "（無）", "color": None, "cost": 0},
    "farm": {"label": "農場", "color": (210, 190, 60), "cost": COST_FARM},
    "factory": {"label": "工場", "color": (120, 120, 130), "cost": COST_FACTORY},
        # tall=True：用戶美術（如 quarry.png 山體）可向上超出北尖；足跡仍在菱形內
    "quarry": {
        "label": "採掘場",
        "color": (150, 110, 70),
        "cost": COST_QUARRY,
        "tall": True,
    },
    # 軍事色塊佔位（定本費用；美術後補）
    "defense": {"label": "防衛設施", "color": (48, 88, 160), "cost": COST_DEFENSE},
    "missile_base": {"label": "飛彈基地", "color": (160, 72, 48), "cost": COST_MISSILE_BASE},
    # 港灣／造船所／防波堤色塊（臨海；美術後補）
    "harbor": {"label": "港灣", "color": (40, 140, 168), "cost": COST_HARBOR},
    "shipyard": {"label": "造船所", "color": (56, 72, 112), "cost": COST_SHIPYARD},
    "breakwater": {"label": "防波堤", "color": (128, 138, 152), "cost": COST_BREAKWATER},
    # 紀念碑色塊（定本國威；美術後補；塔狀美術可向上超出北尖）
    "monument": {
        "label": "紀念碑",
        "color": (168, 140, 72),
        "cost": COST_MONUMENT,
        "tall": True,
    },
    # 變體民生／信仰色塊（銀行緩衝／超市買糧／神社分數；美術後補）
    "bank": {"label": "銀行", "color": (72, 120, 168), "cost": COST_BANK},
    "supermarket": {"label": "超市", "color": (200, 100, 80), "cost": COST_SUPERMARKET},
    "shrine": {"label": "神社", "color": (180, 60, 70), "cost": COST_SHRINE},
    # 都市計畫色塊（公園：安穩／生村；美術後補）
    "park": {"label": "公園", "color": (72, 168, 96), "cost": COST_PARK},
    # 交通／觀光色塊（空港：分數＋觀光收入／訪客小費；美術後補）
    "airport": {"label": "空港", "color": (88, 148, 200), "cost": COST_AIRPORT},
    # 宇宙色塊（ロケット基地：解鎖觀測衛星發射；美術後補；立體火箭可超出北尖）
    "rocket_base": {
        "label": "ロケット基地",
        "color": (64, 108, 128),
        "cost": COST_ROCKET_BASE,
        "tall": True,
    },
    # 住宿／娛樂觀光色塊（酒店・賭場：分數＋回合觀光收入；美術後補）
    "hotel": {"label": "酒店", "color": (196, 128, 88), "cost": COST_HOTEL},
    "casino": {"label": "賭場", "color": (168, 72, 96), "cost": COST_CASINO},
    # 教育／研究色塊（大學・研究所：分數＋科技折扣／輕量減災；美術後補）
    "university": {
        "label": "大學",
        "color": (56, 100, 148),
        "cost": COST_UNIVERSITY,
    },
    "research_lab": {
        "label": "研究所",
        "color": (72, 132, 108),
        "cost": COST_RESEARCH_LAB,
    },
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
BUILDABLE = frozenset({"grass"})  # 平地 only（村／町／都市請先整地；採掘場除外）
SAVE_VERSION = 15


def timber_funds(trees: int) -> int:
    """Instant-sale funds for a tree stock (catalog 100本≈5億；floor lots)."""
    if trees <= 0:
        return 0
    return (int(trees) // TIMBER_LOT) * FUNDS_PER_TIMBER_LOT


def food_export_funds(lots: int) -> int:
    """Funds gained for exporting ``lots`` food batches."""
    return max(0, int(lots)) * FUNDS_PER_FOOD_LOT


def food_buy_cost(lots: int) -> int:
    """Funds spent buying ``lots`` supermarket food batches."""
    return max(0, int(lots)) * FUNDS_PER_FOOD_BUY


def tourism_funds(
    airports: int,
    population: int,
    hotels: int = 0,
    casinos: int = 0,
) -> int:
    """Per-turn tourism income from 空港／酒店／賭場 (base + pop tier)."""
    pop = max(0, int(population))
    total = 0
    n_air = max(0, int(airports))
    if n_air > 0:
        pop_tier = (pop // 100) * TOURISM_FUNDS_PER_100_POP
        total += n_air * (TOURISM_FUNDS_BASE + pop_tier)
    n_hotel = max(0, int(hotels))
    if n_hotel > 0:
        pop_tier = (pop // 100) * HOTEL_TOURISM_PER_100_POP
        total += n_hotel * (HOTEL_TOURISM_BASE + pop_tier)
    n_casino = max(0, int(casinos))
    if n_casino > 0:
        pop_tier = (pop // 100) * CASINO_TOURISM_PER_100_POP
        total += n_casino * (CASINO_TOURISM_BASE + pop_tier)
    return total


def clamp_trees(trees: int) -> int:
    return max(0, min(TREE_MAX, int(trees)))


def scaled_yield(full_yield: int, labor: int, slots: int) -> int:
    """Proportional production; full when labor fills all slots."""
    if slots <= 0 or full_yield <= 0 or labor <= 0:
        return 0
    return (int(full_yield) * int(labor)) // int(slots)


def assign_labor(
    population: int, farms: int, factories: int, quarries: int
) -> Tuple[int, int, int, int, int, int]:
    """Allocate workers: 農場 first, then 工場, then 採掘場.

    Returns (farm_labor, factory_labor, quarry_labor,
             farm_slots, factory_slots, quarry_slots).
    """
    farm_slots = max(0, int(farms)) * LABOR_PER_FARM
    factory_slots = max(0, int(factories)) * LABOR_PER_FACTORY
    quarry_slots = max(0, int(quarries)) * LABOR_PER_QUARRY
    avail = max(0, int(population))
    farm_labor = min(avail, farm_slots)
    avail -= farm_labor
    factory_labor = min(avail, factory_slots)
    avail -= factory_labor
    quarry_labor = min(avail, quarry_slots)
    return (
        farm_labor,
        factory_labor,
        quarry_labor,
        farm_slots,
        factory_slots,
        quarry_slots,
    )


def compute_island_score(
    *,
    population: int,
    funds: int,
    food: int,
    land: int,
    monuments: int,
    farms: int,
    factories: int,
    quarries: int,
    mountains: int,
    harbors: int,
    shipyards: int,
    breakwaters: int,
    oilfields: int,
    defenses: int,
    missile_bases: int,
    villages: int,
    towns: int,
    cities: int,
    banks: int = 0,
    supermarkets: int = 0,
    shrines: int = 0,
    parks: int = 0,
    airports: int = 0,
    rocket_bases: int = 0,
    hotels: int = 0,
    casinos: int = 0,
    universities: int = 0,
    research_labs: int = 0,
    satellite_active: bool = False,
    bank_deposit: int = 0,
) -> int:
    """簡易島分數（順位／國威 stub；紀念碑／神社／公園／空港／宇宙／觀光／研究權重大）."""
    liquid = max(0, int(funds)) + max(0, int(bank_deposit))
    return (
        max(0, int(population)) * SCORE_PER_POP
        + max(0, int(land)) * SCORE_PER_LAND
        + max(0, int(monuments)) * SCORE_PER_MONUMENT
        + max(0, int(farms)) * SCORE_PER_FARM
        + max(0, int(factories)) * SCORE_PER_FACTORY
        + max(0, int(quarries)) * SCORE_PER_QUARRY
        + max(0, int(mountains)) * SCORE_PER_MOUNTAIN
        + max(0, int(harbors)) * SCORE_PER_HARBOR
        + max(0, int(shipyards)) * SCORE_PER_SHIPYARD
        + max(0, int(breakwaters)) * SCORE_PER_BREAKWATER
        + max(0, int(oilfields)) * SCORE_PER_OILFIELD
        + max(0, int(defenses)) * SCORE_PER_DEFENSE
        + max(0, int(missile_bases)) * SCORE_PER_MISSILE_BASE
        + max(0, int(banks)) * SCORE_PER_BANK
        + max(0, int(supermarkets)) * SCORE_PER_SUPERMARKET
        + max(0, int(shrines)) * SCORE_PER_SHRINE
        + max(0, int(parks)) * SCORE_PER_PARK
        + max(0, int(airports)) * SCORE_PER_AIRPORT
        + max(0, int(rocket_bases)) * SCORE_PER_ROCKET_BASE
        + (SCORE_PER_SATELLITE if satellite_active else 0)
        + max(0, int(hotels)) * SCORE_PER_HOTEL
        + max(0, int(casinos)) * SCORE_PER_CASINO
        + max(0, int(universities)) * SCORE_PER_UNIVERSITY
        + max(0, int(research_labs)) * SCORE_PER_RESEARCH_LAB
        + max(0, int(villages)) * SCORE_PER_VILLAGE
        + max(0, int(towns)) * SCORE_PER_TOWN
        + max(0, int(cities)) * SCORE_PER_CITY
        + liquid // SCORE_FUNDS_DIV
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
    bank_deposit: int = 0  # 銀行緩衝（超 FUNDS_SOFT_CAP 溢出；無銀行則捨棄）
    attract_pending: bool = False  # 誘致活動：下一次 next_turn 額外人口
    satellite_active: bool = False  # 觀測衛星在軌：減震／海嘯／噴火
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
        """True if any neighbor is 海／淺灘／油田 (coastal land for 港灣／防波堤)."""
        for ni, nj in neighbors(i, j, self.size):
            if self.cell(ni, nj).terrain in WATER_TERRAINS:
                return True
        return False

    def _sea_neighbor_count(self, i: int, j: int) -> int:
        """How many adjacent water cells (海嘯風險 stub)."""
        return sum(
            1
            for ni, nj in neighbors(i, j, self.size)
            if self.cell(ni, nj).terrain in WATER_TERRAINS
        )

    def _has_breakwater_neighbor(self, i: int, j: int) -> bool:
        """Adjacent 防波堤 mitigates tsunami (self breakwater also counts)."""
        if self.cell(i, j).building == "breakwater":
            return True
        return any(
            self.cell(ni, nj).building == "breakwater"
            for ni, nj in neighbors(i, j, self.size)
        )

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

    def has_bank(self) -> bool:
        return self.building_count("bank") > 0

    def has_supermarket(self) -> bool:
        return self.building_count("supermarket") > 0

    def shrine_count(self) -> int:
        return self.building_count("shrine")

    def park_count(self) -> int:
        return self.building_count("park")

    def airport_count(self) -> int:
        return self.building_count("airport")

    def has_airport(self) -> bool:
        return self.airport_count() > 0

    def rocket_base_count(self) -> int:
        return self.building_count("rocket_base")

    def has_rocket_base(self) -> bool:
        return self.rocket_base_count() > 0

    def hotel_count(self) -> int:
        return self.building_count("hotel")

    def has_hotel(self) -> bool:
        return self.hotel_count() > 0

    def casino_count(self) -> int:
        return self.building_count("casino")

    def has_casino(self) -> bool:
        return self.casino_count() > 0

    def university_count(self) -> int:
        return self.building_count("university")

    def has_university(self) -> bool:
        return self.university_count() > 0

    def research_lab_count(self) -> int:
        return self.building_count("research_lab")

    def has_research_lab(self) -> bool:
        return self.research_lab_count() > 0

    def has_satellite(self) -> bool:
        return bool(self.satellite_active)

    def rocket_launch_cost(self) -> int:
        """觀測衛星發射費用；有大學則享研究折扣（科技 stub）."""
        cost = COST_ROCKET_LAUNCH
        if self.has_university():
            cost = max(0, cost - UNIVERSITY_TECH_DISCOUNT)
        return cost

    def terrain_count(self, kind: str) -> int:
        return sum(1 for row in self.cells for c in row if c.terrain == kind)

    def can_trade_export(self) -> bool:
        """貿易輸出：島上須有港灣或造船所。"""
        return self.has_harbor() or self.has_shipyard()

    def can_buy_food(self) -> bool:
        """超市買糧：島上須有超市。"""
        return self.has_supermarket()

    def can_bank_transfer(self) -> bool:
        """銀行存提：島上須有銀行。"""
        return self.has_bank()

    def island_score(self) -> int:
        """簡易島分數（順位／國威 stub；紀念碑／神社權重大）."""
        return compute_island_score(
            population=self.population,
            funds=self.funds,
            food=self.food,
            land=self.land_count(),
            monuments=self.monument_count(),
            farms=self.building_count("farm"),
            factories=self.building_count("factory"),
            quarries=self.building_count("quarry"),
            mountains=self.terrain_count("mountain"),
            harbors=self.building_count("harbor"),
            shipyards=self.building_count("shipyard"),
            breakwaters=self.building_count("breakwater"),
            oilfields=self.terrain_count("oilfield"),
            defenses=self.building_count("defense"),
            missile_bases=self.building_count("missile_base"),
            villages=self.terrain_count("village"),
            towns=self.terrain_count("town"),
            cities=self.terrain_count("city"),
            banks=self.building_count("bank"),
            supermarkets=self.building_count("supermarket"),
            shrines=self.shrine_count(),
            parks=self.park_count(),
            airports=self.airport_count(),
            rocket_bases=self.rocket_base_count(),
            hotels=self.hotel_count(),
            casinos=self.casino_count(),
            universities=self.university_count(),
            research_labs=self.research_lab_count(),
            satellite_active=self.has_satellite(),
            bank_deposit=self.bank_deposit,
        )

    def happiness_bonus(self) -> int:
        """安穩 stub：紀念碑＋神社＋公園帶來的輕量人口成長加成。"""
        return (
            self.monument_count() * HAPPINESS_POP_PER_MONUMENT
            + self.shrine_count() * HAPPINESS_POP_PER_SHRINE
            + self.park_count() * HAPPINESS_POP_PER_PARK
        )

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
        """整地：荒地→平地、清建築、森／村／町／都市→平地；山→荒地。"""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        if c.terrain not in LAND_TERRAINS:
            return False
        if c.building is not None:
            return True
        if c.terrain in ("dirt", "forest", "mountain") or c.terrain in SETTLEMENT_TERRAINS:
            return True
        return False  # empty 平地 — nothing to do

    def can_raise_mountain(self, i: int, j: int) -> bool:
        """造山／隆起：空的荒地或平地→山。"""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        return c.terrain in ("dirt", "grass") and c.building is None

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
        if c.building is not None:
            return False
        if kind in MOUNTAIN_ONLY_BUILDINGS:
            return c.terrain == "mountain"
        if c.terrain not in BUILDABLE:
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
        if c.building is not None:
            return "此格已有建築（請先移除或整地）"
        if kind in MOUNTAIN_ONLY_BUILDINGS:
            if c.terrain != "mountain":
                return "採掘場只能建在山上（請先造山或等噴火）"
        elif c.terrain not in BUILDABLE:
            return "只能在平地上建設（請先整地）"
        if kind in COASTAL_BUILDINGS and not self._adjacent_to_sea(i, j):
            label = BUILDINGS[kind]["label"]
            return f"{label}須建在臨海的平地（鄰接海／淺灘／油田）"
        cost = int(BUILDINGS[kind]["cost"])
        if self.funds < cost:
            return f"資金不足（需要 {cost}）"
        self.funds -= cost
        c.building = kind
        label = BUILDINGS[kind]["label"]
        self._log(f"回合 {self.turn}：在 ({i},{j}) 建設{label}（−{cost} 資金）")
        return "ok"

    def can_excavate(self, i: int, j: int) -> bool:
        """掘削：空陸→淺灘；淺灘→海；海→探油（可能變海底油田）."""
        if self.monster_at(i, j) is not None:
            return False
        c = self.cell(i, j)
        if c.building is not None:
            return False
        if c.terrain == "sea":
            return True
        if c.terrain == "shallow":
            return True
        if c.terrain in LAND_TERRAINS and c.terrain != "oilfield":
            return True
        return False

    def excavate(self, i: int, j: int) -> str:
        """掘削／探油 stub（定本海上掘削找油田；本機短局發現率提高）."""
        if not self.can_excavate(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法掘削"
            return "此格無法掘削（須為空陸地、淺灘或海）"
        if self.funds < COST_EXCAVATE:
            return f"資金不足（掘削需要 {COST_EXCAVATE}）"
        c = self.cell(i, j)
        prev = c.terrain
        self.funds -= COST_EXCAVATE
        if prev == "sea":
            if random.random() < OIL_DISCOVER_CHANCE:
                self.cells[i][j] = Cell("oilfield")
                self._log(
                    f"回合 {self.turn}：掘削探油 ({i},{j}) 發現海底油田！"
                    f"（−{COST_EXCAVATE} 資金）"
                )
            else:
                self._log(
                    f"回合 {self.turn}：掘削探油 ({i},{j}) 未發現油田"
                    f"（−{COST_EXCAVATE} 資金）"
                )
            return "ok"
        if prev == "shallow":
            self.cells[i][j] = Cell("sea")
            step = "淺灘→海"
        else:
            # Land (incl. mountain／森／村…) → shallow.
            self.cells[i][j] = Cell("shallow")
            step = f"{TERRAIN[prev]['label']}→淺灘"
        self._log(
            f"回合 {self.turn}：掘削 ({i},{j}) {step}（−{COST_EXCAVATE} 資金）"
        )
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

    def buy_food(self, lots: int = 1) -> str:
        """超市買糧：資金→糧食（需超市；不推進回合）."""
        if not self.can_buy_food():
            return "需要超市才能買糧"
        try:
            lots = int(lots)
        except (TypeError, ValueError):
            lots = 1
        if lots < 1:
            return "購買批數須至少 1"
        cost = food_buy_cost(lots)
        if self.funds < cost:
            return f"資金不足（買 {lots} 批需 {cost} 資金）"
        gain = lots * FOOD_BUY_LOT
        self.funds -= cost
        self.food += gain
        self._log(
            f"回合 {self.turn}：超市買糧 {gain} 噸（−{cost} 資金，{lots} 批）"
        )
        return "ok"

    def deposit_funds(self, amount: Optional[int] = None) -> str:
        """銀行存款：流動資金→銀行緩衝（需銀行；預設一批 BANK_TRANSFER_LOT）."""
        if not self.can_bank_transfer():
            return "需要銀行才能存款"
        if amount is None:
            amount = BANK_TRANSFER_LOT
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            amount = BANK_TRANSFER_LOT
        if amount < 1:
            return "存款額須至少 1"
        if self.funds < amount:
            return f"流動資金不足（存款需 {amount}）"
        self.funds -= amount
        self.bank_deposit += amount
        self._log(
            f"回合 {self.turn}：銀行存款 +{amount}（流動 {self.funds}／存 {self.bank_deposit}）"
        )
        return "ok"

    def withdraw_funds(self, amount: Optional[int] = None) -> str:
        """銀行提款：銀行緩衝→流動資金（需銀行；預設一批 BANK_TRANSFER_LOT）."""
        if not self.can_bank_transfer():
            return "需要銀行才能提款"
        if amount is None:
            amount = BANK_TRANSFER_LOT
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            amount = BANK_TRANSFER_LOT
        if amount < 1:
            return "提款額須至少 1"
        if self.bank_deposit < amount:
            return f"銀行存款不足（提款需 {amount}，現存 {self.bank_deposit}）"
        self.bank_deposit -= amount
        self.funds += amount
        self._log(
            f"回合 {self.turn}：銀行提款 +{amount}（流動 {self.funds}／存 {self.bank_deposit}）"
        )
        return "ok"

    def attract_population(self) -> str:
        """誘致活動：定本 1000；標記下一次 next_turn 人口更易增（不推進回合）."""
        if self.attract_pending:
            return "本島已安排誘致活動（請先推進回合）"
        if self.funds < COST_ATTRACT:
            return f"資金不足（誘致活動需要 {COST_ATTRACT}）"
        self.funds -= COST_ATTRACT
        self.attract_pending = True
        self._log(
            f"回合 {self.turn}：誘致活動（−{COST_ATTRACT} 資金）"
            f" — 下回合餵飽時人口更易增加"
        )
        return "ok"

    def launch_rocket(self) -> str:
        """觀測衛星發射：需ロケット基地；−rocket_launch_cost()；不推進回合.

        成功後永久標記 satellite_active（減震／海嘯／噴火）。已在軌不可重射。
        有大學時費用較低（研究 buff／下一科技折扣 stub）。
        """
        if not self.has_rocket_base():
            return "需要ロケット基地"
        if self.satellite_active:
            return "觀測衛星已在軌（無需再發射）"
        cost = self.rocket_launch_cost()
        if self.funds < cost:
            return f"資金不足（發射需要 {cost}）"
        self.funds -= cost
        self.satellite_active = True
        discount_note = ""
        if self.has_university() and cost < COST_ROCKET_LAUNCH:
            discount_note = f"；大學研究折扣 −{COST_ROCKET_LAUNCH - cost}"
        self._log(
            f"回合 {self.turn}：ロケット發射觀測衛星"
            f"（−{cost} 資金{discount_note}）— 地震／海嘯／噴火機率下降"
        )
        return "ok"

    def _satellite_disaster_factor(self) -> float:
        """觀測衛星在軌時回傳減災係數，否則 1.0."""
        return SATELLITE_DISASTER_FACTOR if self.satellite_active else 1.0

    def _disaster_mitigation_factor(self) -> float:
        """地震／海嘯／噴火綜合減災：衛星與研究所可疊乘."""
        factor = self._satellite_disaster_factor()
        if self.has_research_lab():
            factor *= RESEARCH_LAB_DISASTER_FACTOR
        return factor

    def _apply_funds_cap(self) -> List[str]:
        """流動資金軟上限：有銀行→溢出進存款；無銀行→捨棄（定本超額捨棄 stub）."""
        notes: List[str] = []
        if self.funds <= FUNDS_SOFT_CAP:
            return notes
        excess = self.funds - FUNDS_SOFT_CAP
        self.funds = FUNDS_SOFT_CAP
        if self.has_bank():
            self.bank_deposit += excess
            notes.append(f"銀行緩衝存款 +{excess}（流動上限 {FUNDS_SOFT_CAP}）")
        else:
            notes.append(f"資金超上限捨棄 −{excess}（無銀行；上限 {FUNDS_SOFT_CAP}）")
        return notes

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
        """整地：荒地／森／村／町／都市→平地；山→荒地；並清除建築。"""
        if not self.can_level(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法整地（請先發射飛彈）"
            return "此格無需整地（須為荒地、山、森、村／町／都市、或有建築的陸地）"
        if self.funds < COST_LEVEL:
            return f"資金不足（整地需要 {COST_LEVEL}）"
        c = self.cell(i, j)
        self.funds -= COST_LEVEL
        cleared = c.building
        c.building = None
        prev = c.terrain
        prev_trees = c.trees
        if prev == "mountain":
            # Catalog 掘削-lite：山→荒地（再整地→平地）.
            c.terrain = "dirt"
            c.trees = 0
        elif prev in ("dirt", "forest") or prev in SETTLEMENT_TERRAINS:
            c.terrain = "grass"
            c.trees = 0
        # grass + building: terrain stays grass after clear
        parts = [f"({i},{j})"]
        if prev != c.terrain:
            if prev == "forest" and prev_trees:
                parts.append(f"森（{prev_trees}本）→平地")
            elif prev == "mountain":
                parts.append("山→荒地")
            else:
                parts.append(f"{TERRAIN[prev]['label']}→平地")
        if cleared:
            parts.append(f"清除{BUILDINGS[cleared]['label']}")
        self._log(
            f"回合 {self.turn}：整地 {' '.join(parts)}（−{COST_LEVEL} 資金）"
        )
        return "ok"

    def raise_mountain(self, i: int, j: int) -> str:
        """造山／隆起 stub：空的荒地或平地→山（定本多靠噴火；本機可主動整備）."""
        if not self.can_raise_mountain(i, j):
            if self.monster_at(i, j) is not None:
                return "此格有怪獸，無法造山"
            return "只能在空的荒地或平地上造山"
        if self.funds < COST_RAISE:
            return f"資金不足（造山需要 {COST_RAISE}）"
        c = self.cell(i, j)
        prev = c.terrain
        self.funds -= COST_RAISE
        self.cells[i][j] = Cell("mountain")
        self._log(
            f"回合 {self.turn}：造山 ({i},{j}) "
            f"{TERRAIN[prev]['label']}→山（−{COST_RAISE} 資金）"
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
        """Empty 平地 near 農場／公園 or 村／町／都市 can grow a village."""
        for ni, nj in neighbors(i, j, self.size):
            c = self.cell(ni, nj)
            if c.building in ("farm", "park"):
                return True
            if c.terrain in SETTLEMENT_TERRAINS:
                return True
        return False

    def _near_park(self, i: int, j: int) -> bool:
        """True if any neighbor has a 公園 (都市計畫生村加成)."""
        return any(
            self.cell(ni, nj).building == "park"
            for ni, nj in neighbors(i, j, self.size)
        )

    def _evolve_settlements(self) -> List[str]:
        """村／町／都市 terrain evolution on plain land near farms/parks (simplified)."""
        notes: List[str] = []
        # Spawn: empty 平地 adjacent to farm/park/settlement → 村 (~20%/turn；近公園更高).
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
            chance = SETTLEMENT_SPAWN_CHANCE
            if self._near_park(i, j):
                chance = min(1.0, chance + PARK_SETTLEMENT_SPAWN_BONUS)
            if random.random() >= chance:
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
        """Fire / typhoon / quake / tsunami stubs; forest／防波堤／衛星／研究所 mitigate some."""
        notes: List[str] = []
        sat = self._disaster_mitigation_factor()
        if self.satellite_active:
            notes.append("觀測衛星減災中（地震／海嘯／噴火）")
        if self.has_research_lab():
            notes.append("研究所減災中（地震／海嘯／噴火）")

        # Fire: 町／都市／工場 → 荒地（鄰森／紀念碑則不易發生；衛星不減火）
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

        # Typhoon: 農場 → 平地（清建築；鄰森則較耐；紀念碑／衛星不減颱風）
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

        # Quake: 工場／採掘場／都市 → 荒地（stub；森不減震；衛星減）
        for i in range(self.size):
            for j in range(self.size):
                c = self.cell(i, j)
                quakable = (
                    c.terrain == "city"
                    or c.building in ("factory", "quarry")
                )
                if not quakable:
                    continue
                if random.random() >= QUAKE_BASE_CHANCE * sat:
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

        # Tsunami: coastal land facilities／settlements → 荒地（鄰海越多越險；防波堤／衛星減災）
        # Master off when TSUNAMI_BASE_CHANCE <= 0 (tests silence disasters this way).
        if TSUNAMI_BASE_CHANCE > 0:
            for i in range(self.size):
                for j in range(self.size):
                    c = self.cell(i, j)
                    if c.terrain not in LAND_TERRAINS:
                        continue
                    sea_n = self._sea_neighbor_count(i, j)
                    if sea_n <= 0:
                        continue
                    # 防波堤自身不受海嘯摧毀（防災設施）
                    if c.building == "breakwater":
                        continue
                    vulnerable = (
                        c.building is not None or c.terrain in SETTLEMENT_TERRAINS
                    )
                    if not vulnerable:
                        continue
                    chance = (
                        TSUNAMI_BASE_CHANCE + sea_n * TSUNAMI_PER_SEA_NEIGHBOR
                    ) * sat
                    if self._has_breakwater_neighbor(i, j):
                        chance *= BREAKWATER_TSUNAMI_FACTOR
                    if random.random() >= chance:
                        continue
                    parts = []
                    if c.building is not None:
                        parts.append(BUILDINGS[c.building]["label"])
                        c.building = None
                    if c.terrain in LAND_TERRAINS and c.terrain != "dirt":
                        parts.append(TERRAIN[c.terrain]["label"])
                        c.terrain = "dirt"
                        c.trees = 0
                    label = "、".join(parts) if parts else "臨海設施"
                    notes.append(f"海嘯！{label}→荒地 ({i},{j})")

        # Volcano: one random land cell may become 山 (center stub; clears building).
        land_cells = [
            (i, j)
            for i in range(self.size)
            for j in range(self.size)
            if self.is_land(i, j) and self.cell(i, j).terrain != "mountain"
        ]
        if land_cells and random.random() < VOLCANO_BASE_CHANCE * sat:
            vi, vj = random.choice(land_cells)
            c = self.cell(vi, vj)
            prev = c.terrain
            cleared = c.building
            c.terrain = "mountain"
            c.building = None
            c.trees = 0
            detail = TERRAIN[prev]["label"]
            if cleared:
                detail += f"／{BUILDINGS[cleared]['label']}"
            notes.append(f"噴火！{detail}→山 ({vi},{vj})")

        return notes

    def _oilfield_income_and_depletion(self) -> List[str]:
        """海底油田被動產資；機率枯竭→海（定本枯竭 stub）."""
        notes: List[str] = []
        oilfields = self.terrain_count("oilfield")
        if oilfields <= 0:
            return notes
        gain = oilfields * FUNDS_PER_OILFIELD
        self.funds += gain
        notes.append(f"海底油田×{oilfields} 產資 +{gain}")
        depleted: List[Coord] = []
        for i in range(self.size):
            for j in range(self.size):
                if self.cell(i, j).terrain != "oilfield":
                    continue
                if random.random() >= OIL_DEPLETION_CHANCE:
                    continue
                self.cells[i][j] = Cell("sea")
                depleted.append((i, j))
        for i, j in depleted:
            notes.append(f"油田枯竭→海 ({i},{j})")
        return notes

    def next_turn(self) -> List[str]:
        """Advance one turn: economy → forests → settlements → disasters → monsters."""
        notes: List[str] = []
        farms = self.building_count("farm")
        factories = self.building_count("factory")
        quarries = self.building_count("quarry")

        (
            farm_labor,
            factory_labor,
            quarry_labor,
            farm_slots,
            factory_slots,
            quarry_slots,
        ) = assign_labor(self.population, farms, factories, quarries)
        notes.append(
            f"勞動：農場 {farm_labor}/{farm_slots}、"
            f"工場 {factory_labor}/{factory_slots}、"
            f"採掘場 {quarry_labor}/{quarry_slots}"
        )

        food_gain = scaled_yield(farms * FOOD_PER_FARM, farm_labor, farm_slots)
        factory_funds = scaled_yield(
            factories * FUNDS_PER_FACTORY, factory_labor, factory_slots
        )
        quarry_funds = scaled_yield(
            quarries * FUNDS_PER_QUARRY, quarry_labor, quarry_slots
        )
        funds_gain = factory_funds + quarry_funds
        food_need = max(0, (self.population // 500) * FOOD_PER_500_POP)
        if food_need == 0 and self.population > 0:
            food_need = MIN_FOOD_NEED

        self.food += food_gain
        self.funds += funds_gain
        notes.append(
            f"農場×{farms} 產糧 +{food_gain}；"
            f"工場×{factories} 產資 +{factory_funds}；"
            f"採掘場×{quarries} 產資 +{quarry_funds}"
        )

        # 海底油田：被動產資（無勞動）＋枯竭機率.
        notes.extend(self._oilfield_income_and_depletion())

        # 觀光收入（空港／酒店／賭場；依人口加碼）.
        airports = self.airport_count()
        hotels = self.hotel_count()
        casinos = self.casino_count()
        tour_gain = tourism_funds(
            airports, self.population, hotels=hotels, casinos=casinos
        )
        if tour_gain > 0:
            self.funds += tour_gain
            tour_bits = []
            if airports:
                tour_bits.append(f"空港×{airports}")
            if hotels:
                tour_bits.append(f"酒店×{hotels}")
            if casinos:
                tour_bits.append(f"賭場×{casinos}")
            notes.append(f"{'／'.join(tour_bits)} 觀光收入 +{tour_gain}")

        # 流動資金軟上限：有銀行緩衝／無銀行捨棄.
        notes.extend(self._apply_funds_cap())

        # 誘致活動：本回合消耗標記；僅餵飽時生效；有空港再加 inbound.
        attract_bonus = 0
        if self.attract_pending:
            attract_bonus = ATTRACT_POP_BONUS
            if airports > 0:
                attract_bonus += ATTRACT_AIRPORT_EXTRA * airports
            self.attract_pending = False
            notes.append(f"誘致活動生效（人口加成 +{attract_bonus}）")

        if self.food >= food_need:
            self.food -= food_need
            notes.append(f"人口 {self.population} 消耗糧食 −{food_need}")
            # Soft population stub: fed + farms/land → gentle growth.
            # 紀念碑／神社／公園安穩＋誘致：輕量人口加成.
            growth = 0
            happy = self.happiness_bonus()
            if farms > 0 or self.land_count() >= 7 or happy > 0 or attract_bonus > 0:
                growth = random.randint(0, 20) + farms * 5 + happy + attract_bonus
            self.population = min(20000, self.population + growth)
            if growth:
                bits = []
                if happy:
                    bits.append(f"安穩 +{happy}")
                if attract_bonus:
                    bits.append(f"誘致 +{attract_bonus}")
                if bits:
                    notes.append(
                        f"人口 stub +{growth}（含{'／'.join(bits)}）"
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
            if attract_bonus:
                notes.append("誘致活動因糧食不足未能增人")

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
        shrines = self.shrine_count()
        parks = self.park_count()
        airports_n = self.airport_count()
        rockets_n = self.rocket_base_count()
        hotels_n = self.hotel_count()
        casinos_n = self.casino_count()
        univ_n = self.university_count()
        lab_n = self.research_lab_count()
        score_bits = []
        if monuments:
            score_bits.append(f"紀念碑×{monuments}")
        if shrines:
            score_bits.append(f"神社×{shrines}")
        if parks:
            score_bits.append(f"公園×{parks}")
        if airports_n:
            score_bits.append(f"空港×{airports_n}")
        if rockets_n:
            score_bits.append(f"ロケット基地×{rockets_n}")
        if self.satellite_active:
            score_bits.append("觀測衛星")
        if hotels_n:
            score_bits.append(f"酒店×{hotels_n}")
        if casinos_n:
            score_bits.append(f"賭場×{casinos_n}")
        if univ_n:
            score_bits.append(f"大學×{univ_n}")
        if lab_n:
            score_bits.append(f"研究所×{lab_n}")
        notes.append(
            f"島分數 {score}"
            + (f"（{'／'.join(score_bits)}）" if score_bits else "")
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
        tip = 0
        if self.has_airport() or self.has_hotel():
            tip = VISITOR_TIP_FUNDS
            self.funds += tip
            hub = "空港" if self.has_airport() else "酒店"
            self._log(
                f"訪客留言：{clean_name}（{hub}觀光小費 +{tip}）"
            )
        else:
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
            "bank_deposit": int(self.bank_deposit),
            "attract_pending": bool(self.attract_pending),
            "satellite_active": bool(self.satellite_active),
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
        raw_deposit = data.get("bank_deposit")
        raw_attract = data.get("attract_pending")
        raw_sat = data.get("satellite_active")
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
            bank_deposit=int(raw_deposit) if raw_deposit is not None else 0,
            attract_pending=bool(raw_attract) if raw_attract is not None else False,
            satellite_active=bool(raw_sat) if raw_sat is not None else False,
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
