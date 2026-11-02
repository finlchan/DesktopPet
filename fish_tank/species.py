"""v1 species catalogue for Transparent Fish Tank (Phase 1).

Market / 圖鑑 naming locked in transparent-fish-tank-plan.md:
- Display (tank HUD): market names; aliases as ``主名 (別名)``.
- Scientific name: capture / 圖鑑 card (view 2) only.

HD 8-dir swim sheets (user-supplied 2026-11-01) drive most entries below.
Legacy RTS-only species (lionfish / spotted_scat / catfish) kept until HD art arrives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class SpeciesDef:
    """One fish species (or plant) definition."""

    key: str
    market_zh: str
    market_en: str
    aliases_zh: Tuple[str, ...]
    scientific: str
    # Base palette (R,G,B) for RTS pixel sheets / rare remap.
    base_colors: Tuple[Tuple[int, int, int], ...]
    # Rare = palette / marking variant only (same silhouette).
    rare_colors: Tuple[Tuple[int, int, int], ...]
    is_plant: bool = False
    # True when swim sheet is user HD 8-dir × cycle (vs legacy RTS single-row).
    hd_swim: bool = False

    def display_market_zh(self) -> str:
        if self.aliases_zh:
            alias = "／".join(self.aliases_zh)
            return f"{self.market_zh} ({alias})"
        return self.market_zh

    def display_market_bilingual(self) -> str:
        return f"{self.display_market_zh()} / {self.market_en}"


def _C(*rgb: Tuple[int, int, int]) -> Tuple[Tuple[int, int, int], ...]:
    return rgb


SPECIES: Dict[str, SpeciesDef] = {
    # --- User HD sheets (2026-11-01) ---
    "grouper": SpeciesDef(
        key="grouper",
        market_zh="青衣",
        market_en="Blackspot tuskfish",
        aliases_zh=(),
        scientific="Choerodon schoenleinii",
        base_colors=_C((40, 150, 140), (25, 95, 110), (235, 205, 55), (25, 25, 28)),
        rare_colors=_C((55, 100, 175), (30, 55, 110), (250, 170, 45), (20, 22, 30)),
        hd_swim=True,
    ),
    "mudskipper": SpeciesDef(
        key="mudskipper",
        market_zh="泥鯭",
        market_en="White-spotted spinefoot",
        aliases_zh=("泥猛",),
        scientific="Siganus canaliculatus",
        base_colors=_C((110, 120, 70), (70, 80, 50), (200, 200, 180), (40, 44, 36)),
        rare_colors=_C((70, 96, 120), (40, 58, 78), (210, 190, 140), (28, 36, 48)),
        hd_swim=True,
    ),
    "golden_threadfin": SpeciesDef(
        key="golden_threadfin",
        market_zh="紅衫魚",
        market_en="Golden threadfin bream",
        aliases_zh=(),
        scientific="Nemipterus virgatus",
        base_colors=_C((210, 110, 120), (180, 70, 80), (230, 200, 70), (40, 30, 32)),
        rare_colors=_C((120, 90, 180), (70, 50, 120), (240, 180, 60), (28, 24, 40)),
        hd_swim=True,
    ),
    "red_bigeye": SpeciesDef(
        key="red_bigeye",
        market_zh="大眼雞",
        market_en="Red bigeye",
        aliases_zh=(),
        scientific="Priacanthus macracanthus",
        base_colors=_C((200, 70, 70), (160, 40, 50), (230, 140, 110), (40, 24, 24)),
        rare_colors=_C((80, 100, 180), (40, 50, 120), (200, 160, 220), (24, 24, 40)),
        hd_swim=True,
    ),
    "red_seabream": SpeciesDef(
        key="red_seabream",
        market_zh="紅鯛",
        market_en="Red seabream",
        aliases_zh=("真鯛",),
        scientific="Pagrus major",
        base_colors=_C((210, 120, 130), (170, 70, 90), (80, 120, 170), (40, 28, 30)),
        rare_colors=_C((90, 140, 180), (50, 80, 120), (220, 180, 80), (24, 28, 40)),
        hd_swim=True,
    ),
    "goldstriped_seabream": SpeciesDef(
        key="goldstriped_seabream",
        market_zh="黃腳鯛",
        market_en="Goldstriped seabream",
        aliases_zh=("黃錫鯛",),
        scientific="Rhabdosargus sarba",
        base_colors=_C((180, 180, 170), (120, 120, 110), (220, 190, 70), (40, 40, 38)),
        rare_colors=_C((160, 120, 90), (100, 70, 50), (240, 200, 80), (36, 28, 24)),
        hd_swim=True,
    ),
    "yellow_croaker": SpeciesDef(
        key="yellow_croaker",
        market_zh="黃魚",
        market_en="Yellow croaker",
        aliases_zh=("小黃魚",),
        scientific="Larimichthys polyactis",
        base_colors=_C((220, 190, 80), (170, 140, 50), (190, 190, 180), (40, 36, 28)),
        rare_colors=_C((180, 100, 70), (120, 60, 40), (220, 200, 160), (36, 28, 24)),
        hd_swim=True,
    ),
    "japanese_threadfin": SpeciesDef(
        key="japanese_threadfin",
        market_zh="金線魚",
        market_en="Japanese threadfin bream",
        aliases_zh=(),
        scientific="Nemipterus japonicus",
        base_colors=_C((210, 120, 130), (170, 70, 85), (230, 200, 70), (40, 30, 32)),
        rare_colors=_C((100, 140, 180), (50, 80, 120), (240, 190, 70), (28, 30, 40)),
        hd_swim=True,
    ),
    "leopard_coral_grouper": SpeciesDef(
        key="leopard_coral_grouper",
        market_zh="東星斑",
        market_en="Leopard coral grouper",
        aliases_zh=("星斑",),
        scientific="Plectropomus leopardus",
        base_colors=_C((200, 60, 60), (150, 30, 40), (80, 140, 200), (30, 20, 22)),
        rare_colors=_C((60, 140, 100), (30, 90, 60), (220, 200, 80), (24, 28, 24)),
        hd_swim=True,
    ),
    "silver_tilefish": SpeciesDef(
        key="silver_tilefish",
        market_zh="馬頭魚",
        market_en="Silver tilefish",
        aliases_zh=(),
        scientific="Branchiostegus argentatus",
        base_colors=_C((210, 130, 140), (160, 80, 95), (230, 200, 80), (40, 30, 32)),
        rare_colors=_C((120, 100, 170), (70, 55, 110), (240, 190, 70), (28, 26, 40)),
        hd_swim=True,
    ),
    "tongue_sole": SpeciesDef(
        key="tongue_sole",
        market_zh="撻沙魚",
        market_en="Three-lined tongue sole",
        aliases_zh=("龍脷",),
        scientific="Cynoglossus abbreviatus",
        base_colors=_C((140, 120, 90), (90, 75, 55), (180, 160, 120), (36, 30, 24)),
        rare_colors=_C((100, 110, 140), (55, 65, 90), (200, 180, 140), (28, 28, 36)),
        hd_swim=True,
    ),
    "fourfinger_threadfin": SpeciesDef(
        key="fourfinger_threadfin",
        market_zh="馬友魚",
        market_en="Fourfinger threadfin",
        aliases_zh=("馬友",),
        scientific="Eleutheronema tetradactylum",
        base_colors=_C((180, 180, 175), (120, 120, 115), (200, 200, 190), (40, 40, 38)),
        rare_colors=_C((160, 130, 90), (100, 75, 50), (220, 190, 140), (36, 28, 24)),
        hd_swim=True,
    ),
    "snubnose_pompano": SpeciesDef(
        key="snubnose_pompano",
        market_zh="黃立倉",
        market_en="Snubnose pompano",
        aliases_zh=("倉魚",),
        scientific="Trachinotus blochii",
        base_colors=_C((200, 185, 120), (150, 130, 70), (230, 160, 60), (40, 36, 28)),
        rare_colors=_C((120, 150, 180), (70, 90, 120), (240, 180, 70), (28, 30, 40)),
        hd_swim=True,
    ),
    "grey_mullet": SpeciesDef(
        key="grey_mullet",
        market_zh="烏頭",
        market_en="Flathead grey mullet",
        aliases_zh=("鯔魚",),
        scientific="Mugil cephalus",
        base_colors=_C((90, 95, 100), (55, 60, 65), (170, 175, 180), (30, 32, 34)),
        rare_colors=_C((70, 90, 120), (40, 55, 80), (200, 190, 160), (28, 30, 40)),
        hd_swim=True,
    ),
    "black_porgy": SpeciesDef(
        key="black_porgy",
        market_zh="黑鯛",
        market_en="Black porgy",
        aliases_zh=("黑立",),
        scientific="Acanthopagrus schlegelii",
        base_colors=_C((70, 75, 80), (40, 44, 48), (180, 185, 190), (24, 26, 28)),
        rare_colors=_C((90, 70, 50), (50, 40, 30), (220, 190, 140), (28, 24, 20)),
        hd_swim=True,
    ),
    "japanese_scad": SpeciesDef(
        key="japanese_scad",
        market_zh="池魚",
        market_en="Japanese scad",
        aliases_zh=("巴浪",),
        scientific="Decapterus maruadsi",
        base_colors=_C((120, 150, 170), (70, 95, 120), (220, 190, 70), (36, 40, 44)),
        rare_colors=_C((160, 100, 80), (100, 55, 45), (240, 200, 80), (36, 28, 24)),
        hd_swim=True,
    ),
    "chinese_pomfret": SpeciesDef(
        key="chinese_pomfret",
        market_zh="鷹鯧",
        market_en="Chinese pomfret",
        aliases_zh=("鯧魚",),
        scientific="Pampus chinensis",
        base_colors=_C((180, 180, 175), (120, 120, 115), (200, 200, 195), (40, 40, 38)),
        rare_colors=_C((140, 110, 80), (90, 70, 50), (220, 190, 150), (36, 28, 24)),
        hd_swim=True,
    ),
    "slender_lizardfish": SpeciesDef(
        key="slender_lizardfish",
        market_zh="九棍魚",
        market_en="Slender lizardfish",
        aliases_zh=("蛇鯔",),
        scientific="Saurida elongata",
        base_colors=_C((140, 120, 95), (90, 75, 55), (180, 160, 130), (36, 30, 24)),
        rare_colors=_C((100, 120, 90), (55, 70, 50), (200, 190, 140), (28, 32, 24)),
        hd_swim=True,
    ),
    # --- Legacy RTS-only (no user HD sheet in this batch) ---
    "lionfish": SpeciesDef(
        key="lionfish",
        market_zh="獅子魚",
        market_en="Lionfish",
        aliases_zh=(),
        scientific="Pterois volitans",
        base_colors=_C((200, 90, 50), (240, 220, 200), (40, 30, 28), (180, 60, 40)),
        rare_colors=_C((60, 90, 160), (220, 230, 245), (20, 24, 40), (90, 70, 180)),
        hd_swim=False,
    ),
    "spotted_scat": SpeciesDef(
        key="spotted_scat",
        market_zh="金鼓",
        market_en="Spotted scat",
        aliases_zh=(),
        scientific="Scatophagus argus",
        base_colors=_C((210, 180, 70), (40, 36, 30), (160, 140, 50), (230, 210, 140)),
        rare_colors=_C((180, 80, 90), (30, 28, 32), (140, 50, 60), (220, 160, 150)),
        hd_swim=False,
    ),
    "catfish": SpeciesDef(
        key="catfish",
        market_zh="塘虱",
        market_en="Walking catfish",
        aliases_zh=("鯰", "本地淡水鯰類"),
        scientific="Clarias spp.",
        base_colors=_C((70, 64, 58), (110, 100, 88), (30, 28, 26), (150, 140, 120)),
        rare_colors=_C((90, 70, 50), (160, 120, 70), (40, 30, 20), (200, 170, 110)),
        hd_swim=False,
    ),
    "waterweed": SpeciesDef(
        key="waterweed",
        market_zh="水蘊草",
        market_en="Waterweed",
        aliases_zh=(),
        scientific="Egeria densa",
        base_colors=_C((48, 120, 62), (30, 80, 42), (90, 160, 90), (20, 50, 30)),
        rare_colors=_C((48, 120, 62), (30, 80, 42), (90, 160, 90), (20, 50, 30)),
        is_plant=True,
        hd_swim=False,
    ),
}

FISH_KEYS: List[str] = [k for k, s in SPECIES.items() if not s.is_plant]
HD_FISH_KEYS: List[str] = [k for k, s in SPECIES.items() if s.hd_swim]
PLANT_KEY = "waterweed"


def species_list_fish() -> List[SpeciesDef]:
    return [SPECIES[k] for k in FISH_KEYS]
