"""建築抽屜樹 — catalog categories, unlock prerequisites, detail copy.

Formal categories follow `docs/hakoniwa-content-catalog.md` groupings used in
the content browse/build drawer (prefs: 建築抽屜樹). Tree rows are text-only
(no building thumbnails). Unmet island unlock prerequisites hard-lock the
row (not activatable); placement terrain rules are shown in the detail pane
and enforced by ``tool_enabled`` / ``can_place_building``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .model import (
    BUILDING_UNLOCK_PREREQS,
    BUILDINGS,
    COASTAL_BUILDINGS,
    COST_MISSILE,
    MOUNTAIN_ONLY_BUILDINGS,
    PLACEABLE_BUILDINGS,
    SEA_ONLY_BUILDINGS,
    SHALLOW_ONLY_BUILDINGS,
    IslandState,
)

# Optional: PR #83 moves village/town/city into BUILDINGS as non-placeable.
try:
    from .model import SETTLEMENT_BUILDINGS  # type: ignore
except ImportError:  # pragma: no cover — older tip keeps settlements as terrain
    SETTLEMENT_BUILDINGS = frozenset()  # type: ignore
try:
    from .model import HARD_LOCKED_BUILDINGS  # type: ignore
except ImportError:  # pragma: no cover
    HARD_LOCKED_BUILDINGS = frozenset()  # type: ignore

# Action keys hard-locked until a facility exists (already in game rules).
ACTION_UNLOCK_PREREQS: Dict[str, Tuple[str, str]] = {
    "export": ("harbor|shipyard", "需要港灣或造船所"),
    "deposit": ("bank", "需要銀行"),
    "withdraw": ("bank", "需要銀行"),
    "buy_food": ("supermarket", "需要超市"),
    "rocket_launch": ("rocket_base", "需要ロケット基地"),
}

# Placement condition blurbs (terrain / adjacency — not island unlocks).
PLACEMENT_BLURBS: Dict[str, str] = {
    "quarry": "山上（僅山）",
    "aquafarm": "淺灘",
    "undersea_base": "深海（非淺灘／油田）",
    "harbor": "臨海平地",
    "shipyard": "臨海平地",
    "breakwater": "臨海平地",
    "farm": "平地",
    "factory": "平地",
    "defense": "平地",
    "missile_base": "平地",
    "decoy": "平地",
    "monument": "平地",
    "bank": "平地",
    "supermarket": "平地",
    "shrine": "平地",
    "park": "平地",
    "airport": "平地",
    "rocket_base": "平地",
    "hotel": "平地",
    "casino": "平地",
    "university": "平地",
    "research_lab": "平地",
    "amusement_park": "平地",
    "power_plant": "平地",
    "onsen_village": "溫泉山旁的空平地（自然出現）",
}

# One-line effect blurbs for the detail pane.
EFFECT_BLURBS: Dict[str, Tuple[str, ...]] = {
    "farm": ("產糧食（勞動就業）",),
    "factory": ("產資金（勞動就業）",),
    "quarry": ("山上產資金（勞動就業）",),
    "aquafarm": ("淺灘被動產糧",),
    "power_plant": ("被動產資；有電時工場加產",),
    "harbor": ("解鎖貿易輸出；臨海樞紐",),
    "shipyard": ("解鎖貿易輸出（需港灣）",),
    "breakwater": ("鄰格減海嘯",),
    "export": ("糧食→資金（不推進回合）",),
    "bank": ("超上限資金進存款緩衝", "可手動存提"),
    "supermarket": ("資金買糧食",),
    "park": ("安穩／島分數；鄰格提高生村",),
    "shrine": ("大幅加島分數；安穩人口加成",),
    "hotel": ("住宿觀光收入；留言小費",),
    "casino": ("娛樂觀光收入（依人口加碼）",),
    "airport": ("觀光收入；誘致 inbound；留言小費",),
    "amusement_park": ("大型觀光收入；安穩",),
    "monument": ("國威／島分數；抗怪獸；鄰格抑火災",),
    "defense": ("周圍 2 格減怪出現／踩踏；再建設＝自爆",),
    "missile_base": ("飛彈費用優惠；觀光偽裝成森",),
    "undersea_base": ("深海飛彈基地；觀光偽裝成海",),
    "decoy": ("外觀像防衛、無實防；觀光顯示為防衛",),
    "missile": ("攻擊怪獸／拆紙糊",),
    "wait": ("本回合不攻擊；怪獸仍會行動",),
    "university": ("島分數；觀測衛星發射折扣",),
    "research_lab": ("島分數；輕量減震／海嘯／噴火",),
    "rocket_base": ("解鎖觀測衛星發射",),
    "rocket_launch": ("發射觀測衛星（減災；不推進回合）",),
    "landfill": ("海→淺灘／淺灘→荒地（須鄰陸）",),
    "level": ("荒地→平地；可清建築；山→荒地",),
    "raise": ("荒地／平地→山（可再建採掘場）",),
    "excavate": ("陸→淺灘／淺灘→海／海→探油",),
    "afforest": ("平地→森",),
    "harvest": ("森→平地；木材瞬售資金",),
    "remove": ("清除格上建築（不退費）",),
    "attract": ("下回合餵飽時額外人口",),
    "deposit": ("流動資金→銀行存款",),
    "withdraw": ("銀行存款→流動資金",),
    "buy_food": ("資金→糧食",),
    "village": ("住居建築；人口自然演進（非點選建造）",),
    "town": ("住居建築；人口自然演進（非點選建造）",),
    "city": ("住居建築；人口自然演進（非點選建造）",),
    "onsen_village": ("溫泉山旁的平地自然出現（與村同族，不可直接建設）",),
}


# Formal catalog categories → tool / building keys (browse order).
# 住居 only listed when settlements are buildings (PR #83+).
_BASE_CATEGORIES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "開發",
        (
            "landfill",
            "level",
            "raise",
            "excavate",
            "afforest",
            "harvest",
            "remove",
            "attract",
        ),
    ),
    (
        "生産",
        ("farm", "factory", "quarry", "aquafarm", "power_plant"),
    ),
    (
        "港湾",
        ("harbor", "shipyard", "breakwater", "export"),
    ),
    (
        "民生",
        ("bank", "supermarket", "park", "deposit", "withdraw", "buy_food"),
    ),
    (
        "観光",
        (
            "shrine",
            "hotel",
            "casino",
            "airport",
            "amusement_park",
            "monument",
        ),
    ),
    (
        "軍事",
        (
            "defense",
            "missile_base",
            "undersea_base",
            "decoy",
            "missile",
            "wait",
        ),
    ),
    (
        "教育",
        ("university", "research_lab", "rocket_base", "rocket_launch"),
    ),
)


def settlement_keys_for_tree() -> Tuple[str, ...]:
    """Village/town/city when they are non-placeable buildings; else empty.

    Safe on older tips where settlements remain terrain keys.
    """
    keys: List[str] = []
    for k in ("village", "town", "city"):
        if k in SETTLEMENT_BUILDINGS and k in BUILDINGS:
            keys.append(k)
        elif k in BUILDINGS and k not in PLACEABLE_BUILDINGS:
            # Present as building meta but not placeable.
            keys.append(k)
    return tuple(keys)


def build_tree_categories() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """Categories for the drawer tree (includes 住居 when applicable)."""
    cats: List[Tuple[str, Tuple[str, ...]]] = list(_BASE_CATEGORIES)
    settlements = settlement_keys_for_tree()
    extra: List[str] = []
    # 溫泉村 is a hard-locked village-family building, not a population upgrade.
    if "onsen_village" in BUILDINGS and "onsen_village" not in settlements:
        extra.append("onsen_village")
    residence = settlements + tuple(extra)
    if residence:
        # Insert after 開發 (catalog §2.2 住居).
        cats.insert(1, ("住居", residence))
    return tuple(cats)


def _has_building(state: IslandState, key: str) -> bool:
    if "|" in key:
        return any(state.building_count(part) > 0 for part in key.split("|"))
    return state.building_count(key) > 0


def unlock_prereq(kind: str) -> Optional[Tuple[str, str]]:
    """Return (required_key_expr, reason) for island unlock, or None."""
    if kind in BUILDING_UNLOCK_PREREQS:
        return BUILDING_UNLOCK_PREREQS[kind]
    if kind in ACTION_UNLOCK_PREREQS:
        return ACTION_UNLOCK_PREREQS[kind]
    return None


def unlock_met(state: IslandState, kind: str) -> Tuple[bool, str]:
    """Whether island unlock prerequisites for ``kind`` are satisfied.

    Returns (met, reason). Reason empty when met; otherwise the lock tip.
    Placement terrain is *not* an unlock — handled separately.
    """
    # Hard-locked catalog rows (溫泉村): visible, never activatable.
    if kind in HARD_LOCKED_BUILDINGS:
        return False, "只能在溫泉山旁的平地自然出現"
    # Non-placeable settlements: always "browse only", never activatable.
    if kind in settlement_keys_for_tree():
        return False, "住居由人口演進生成（不可點選建造）"
    prereq = unlock_prereq(kind)
    if prereq is None:
        return True, ""
    req, reason = prereq
    if _has_building(state, req):
        return True, ""
    return False, reason


def placement_blurb(kind: str) -> str:
    if kind in PLACEMENT_BLURBS:
        return PLACEMENT_BLURBS[kind]
    if kind in MOUNTAIN_ONLY_BUILDINGS:
        return "山上（僅山）"
    if kind in SHALLOW_ONLY_BUILDINGS:
        return "淺灘"
    if kind in SEA_ONLY_BUILDINGS:
        return "深海"
    if kind in COASTAL_BUILDINGS:
        return "臨海平地"
    if kind in PLACEABLE_BUILDINGS:
        return "平地"
    if kind in settlement_keys_for_tree():
        return "平地（演進生成）"
    return "—"


_ACTION_LABELS: Dict[str, str] = {
    "export": "貿易輸出",
    "deposit": "銀行存款",
    "withdraw": "銀行提款",
    "buy_food": "超市買糧",
    "rocket_launch": "發射火箭",
    "missile": "發射飛彈",
    "wait": "觀望怪獸",
    "landfill": "填海造陸",
    "level": "整地",
    "raise": "造山",
    "excavate": "掘削／探油",
    "afforest": "植林",
    "harvest": "伐採",
    "remove": "移除建築",
    "attract": "誘致活動",
}


def display_label(kind: str, tool_name: Optional[str] = None) -> str:
    """Short tree / detail title (strip leading 建設…)."""
    if kind in BUILDINGS and BUILDINGS[kind].get("label"):
        return str(BUILDINGS[kind]["label"])
    if kind in _ACTION_LABELS:
        return _ACTION_LABELS[kind]
    if tool_name:
        if tool_name.startswith("建設"):
            return tool_name[len("建設") :]
        return tool_name
    return kind


def effect_lines(kind: str) -> Sequence[str]:
    return EFFECT_BLURBS.get(kind, ())


def cost_for_kind(state: IslandState, kind: str, tool_cost: Optional[int]) -> Optional[int]:
    if kind == "missile":
        return state.missile_cost() if hasattr(state, "missile_cost") else COST_MISSILE
    if kind in BUILDINGS:
        return int(BUILDINGS[kind].get("cost", 0))
    return tool_cost


def prereq_table_rows() -> List[Tuple[str, str, str]]:
    """Rows for PR / docs: (item, prerequisite, notes)."""
    rows: List[Tuple[str, str, str]] = []
    for kind, (req, reason) in BUILDING_UNLOCK_PREREQS.items():
        label = display_label(kind)
        req_label = " 或 ".join(
            display_label(p) for p in req.split("|")
        )
        rows.append((label, req_label, f"島上解鎖硬鎖：{reason}"))
    for kind, (req, reason) in ACTION_UNLOCK_PREREQS.items():
        label = display_label(kind, kind)
        req_label = " 或 ".join(display_label(p) for p in req.split("|"))
        rows.append((label, req_label, f"指令解鎖硬鎖：{reason}"))
    rows.append(("採掘場", "山上", "配置條件（非島解鎖）"))
    rows.append(("養殖場", "淺灘", "配置條件（非島解鎖）"))
    rows.append(("海底基地", "深海", "配置條件（非島解鎖）"))
    rows.append(("港灣／造船所／防波堤", "臨海平地", "配置條件（非島解鎖）"))
    if settlement_keys_for_tree():
        rows.append(("村／町／都市", "人口演進", "非點選建造（瀏覽用）"))
    return rows
