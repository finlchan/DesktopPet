"""v1 species catalogue for Transparent Fish Tank (Phase 1).

Market / 圖鑑 naming locked in transparent-fish-tank-plan.md:
- Display (tank HUD): market names; aliases as ``主名 (別名)``.
- Scientific name: capture / 圖鑑 card (view 2) only.
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

    def display_market_zh(self) -> str:
        if self.aliases_zh:
            alias = "／".join(self.aliases_zh)
            return f"{self.market_zh} ({alias})"
        return self.market_zh

    def display_market_bilingual(self) -> str:
        return f"{self.display_market_zh()} / {self.market_en}"


# Five fish + one plant (v1).
SPECIES: Dict[str, SpeciesDef] = {
    "mudskipper": SpeciesDef(
        key="mudskipper",
        market_zh="泥鯭",
        market_en="Spottybelly greenling",
        aliases_zh=(),
        scientific="Hexagrammos agrammus",
        base_colors=((92, 118, 86), (58, 74, 52), (180, 168, 120), (40, 48, 36)),
        rare_colors=((70, 96, 120), (40, 58, 78), (210, 190, 140), (28, 36, 48)),
    ),
    "lionfish": SpeciesDef(
        key="lionfish",
        market_zh="獅子魚",
        market_en="Lionfish",
        aliases_zh=(),
        scientific="Pterois volitans",
        base_colors=((200, 90, 50), (240, 220, 200), (40, 30, 28), (180, 60, 40)),
        rare_colors=((60, 90, 160), (220, 230, 245), (20, 24, 40), (90, 70, 180)),
    ),
    "spotted_scat": SpeciesDef(
        key="spotted_scat",
        market_zh="金鼓",
        market_en="Spotted scat",
        aliases_zh=(),
        scientific="Scatophagus argus",
        base_colors=((210, 180, 70), (40, 36, 30), (160, 140, 50), (230, 210, 140)),
        rare_colors=((180, 80, 90), (30, 28, 32), (140, 50, 60), (220, 160, 150)),
    ),
    "catfish": SpeciesDef(
        key="catfish",
        market_zh="塘虱",
        market_en="Walking catfish",
        aliases_zh=("鯰", "本地淡水鯰類"),
        scientific="Clarias spp.",
        base_colors=((70, 64, 58), (110, 100, 88), (30, 28, 26), (150, 140, 120)),
        rare_colors=((90, 70, 50), (160, 120, 70), (40, 30, 20), (200, 170, 110)),
    ),
    "grouper": SpeciesDef(
        key="grouper",
        market_zh="青衣",
        market_en="Orange-spotted grouper",
        aliases_zh=(),
        scientific="Epinephelus coioides",
        base_colors=((70, 120, 90), (40, 80, 60), (200, 140, 50), (30, 50, 40)),
        rare_colors=((50, 90, 130), (30, 55, 90), (220, 160, 40), (20, 36, 55)),
    ),
    "waterweed": SpeciesDef(
        key="waterweed",
        market_zh="水蘊草",
        market_en="Waterweed",
        aliases_zh=(),
        scientific="Egeria densa",
        base_colors=((48, 120, 62), (30, 80, 42), (90, 160, 90), (20, 50, 30)),
        rare_colors=((48, 120, 62), (30, 80, 42), (90, 160, 90), (20, 50, 30)),
        is_plant=True,
    ),
}

FISH_KEYS: List[str] = [k for k, s in SPECIES.items() if not s.is_plant]
PLANT_KEY = "waterweed"


def species_list_fish() -> List[SpeciesDef]:
    return [SPECIES[k] for k in FISH_KEYS]
