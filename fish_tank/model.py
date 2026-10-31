"""Local tank state: fish entities, plants, ownership stub, care actions."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from . import remote_stubs
from .species import FISH_KEYS, PLANT_KEY, SPECIES


# World extents (world units). Viewport shows a window into this; zoom changes
# visible range only — sprite pixel size stays fixed in the view.
WORLD_W = 1600.0
WORLD_H = 900.0

# Default camera shows this much of the world at zoom=1.
VIEW_W = 640.0
VIEW_H = 360.0


@dataclass
class FishEntity:
    """One free-swimming (or owned) fish in / around the local tank."""

    id: str
    species_key: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    facing_right: bool = True
    rare: bool = False
    # Status (shown on capture / 圖鑑 view-2 card).
    health: float = 1.0  # 0..1
    fullness: float = 0.6  # 0..1
    age_days: float = 0.0
    custom_name: str = ""
    # Ownership: uncaught = unowned; catch → local ownership stub.
    owned: bool = False
    owner_display_name: str = ""
    # Away stub: left local view → despawned (Phase 2: public sea visit).
    away: bool = False
    away_until: float = 0.0  # monotonic time; 0 = not scheduled

    def market_label(self) -> str:
        return SPECIES[self.species_key].display_market_zh()

    def scientific(self) -> str:
        return SPECIES[self.species_key].scientific

    def rarity_label(self) -> str:
        return "稀有／Rare" if self.rare else "普通／Common"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FishEntity":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class DecorItem:
    """Local decoration (v1: waterweed plant placements)."""

    id: str
    species_key: str
    x: float
    y: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecorItem":
        return cls(
            id=str(data["id"]),
            species_key=str(data["species_key"]),
            x=float(data["x"]),
            y=float(data["y"]),
        )


@dataclass
class TankState:
    """Local-only aquarium simulation state."""

    fish: List[FishEntity] = field(default_factory=list)
    decor: List[DecorItem] = field(default_factory=list)
    food_pellets: List[Dict[str, float]] = field(default_factory=list)
    # Care deltas awaiting Phase 2 settlement flush.
    pending_care_deltas: List[Dict[str, Any]] = field(default_factory=list)
    display_name: str = "Player"
    # Camera (world units of visible range; sprite size independent).
    cam_x: float = (WORLD_W - VIEW_W) * 0.5
    cam_y: float = (WORLD_H - VIEW_H) * 0.5
    # zoom: 1 = default visible range; <1 zooms out (larger range); >1 zooms in.
    zoom: float = 1.0

    def visible_size(self) -> tuple[float, float]:
        z = max(0.35, min(2.5, self.zoom))
        return VIEW_W / z, VIEW_H / z

    def active_fish(self) -> List[FishEntity]:
        return [f for f in self.fish if not f.away]

    def owned_fish(self) -> List[FishEntity]:
        return [f for f in self.fish if f.owned and not f.away]

    # --- Player actions (local) -----------------------------------------

    def feed(self, at_x: Optional[float] = None, at_y: Optional[float] = None) -> None:
        """Scatter food in view; raise fullness of nearby active fish."""
        vw, vh = self.visible_size()
        cx = self.cam_x + (at_x if at_x is not None else vw * 0.5)
        cy = self.cam_y + (at_y if at_y is not None else vh * 0.25)
        for _ in range(6):
            self.food_pellets.append(
                {
                    "x": cx + random.uniform(-40, 40),
                    "y": cy + random.uniform(-10, 10),
                    "vy": random.uniform(12, 28),
                    "life": 8.0,
                }
            )
        for f in self.active_fish():
            if abs(f.x - cx) < 120 and abs(f.y - cy) < 100:
                f.fullness = min(1.0, f.fullness + 0.18)
                f.health = min(1.0, f.health + 0.04)
        self.pending_care_deltas.append(
            {"op": "feed", "t": time.time(), "x": cx, "y": cy}
        )

    def decorate(self, x: Optional[float] = None, y: Optional[float] = None) -> DecorItem:
        """Place a waterweed in the local tank (local only)."""
        vw, vh = self.visible_size()
        px = self.cam_x + (x if x is not None else vw * random.uniform(0.2, 0.8))
        py = self.cam_y + (y if y is not None else vh * random.uniform(0.55, 0.9))
        item = DecorItem(
            id=str(uuid.uuid4())[:8],
            species_key=PLANT_KEY,
            x=px,
            y=py,
        )
        self.decor.append(item)
        self.pending_care_deltas.append(
            {"op": "decorate", "t": time.time(), "id": item.id, "x": px, "y": py}
        )
        return item

    def name_fish(self, fish_id: str, new_name: str) -> bool:
        for f in self.fish:
            if f.id == fish_id and f.owned:
                f.custom_name = (new_name or "").strip()[:24]
                self.pending_care_deltas.append(
                    {
                        "op": "name",
                        "t": time.time(),
                        "id": fish_id,
                        "name": f.custom_name,
                    }
                )
                return True
        return False

    def catch_fish(self, fish_id: str) -> Optional[FishEntity]:
        """Local ownership stub + Phase 2 immediate-upload hook (no-op online)."""
        for f in self.fish:
            if f.id == fish_id and not f.away and not f.owned:
                f.owned = True
                f.owner_display_name = self.display_name
                # Phase 2: immediate server upload (stub echoes locally).
                remote_stubs.upload_catch_immediate(f.to_dict())
                self.pending_care_deltas.append(
                    {"op": "catch", "t": time.time(), "id": fish_id}
                )
                return f
        return None

    def flush_settlement_stub(self) -> None:
        """Phase 1: hand pending care deltas to settlement no-op, then clear."""
        if self.pending_care_deltas:
            remote_stubs.flush_care_deltas_for_settlement(
                {"deltas": list(self.pending_care_deltas)}
            )
            self.pending_care_deltas.clear()
        remote_stubs.on_settlement_tick_stub()

    # --- Serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fish": [f.to_dict() for f in self.fish],
            "decor": [d.to_dict() for d in self.decor],
            "food_pellets": list(self.food_pellets),
            "pending_care_deltas": list(self.pending_care_deltas),
            "display_name": self.display_name,
            "cam_x": self.cam_x,
            "cam_y": self.cam_y,
            "zoom": self.zoom,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TankState":
        st = cls(
            fish=[FishEntity.from_dict(f) for f in data.get("fish", [])],
            decor=[DecorItem.from_dict(d) for d in data.get("decor", [])],
            food_pellets=list(data.get("food_pellets", [])),
            pending_care_deltas=list(data.get("pending_care_deltas", [])),
            display_name=str(data.get("display_name", "Player")),
            cam_x=float(data.get("cam_x", (WORLD_W - VIEW_W) * 0.5)),
            cam_y=float(data.get("cam_y", (WORLD_H - VIEW_H) * 0.5)),
            zoom=float(data.get("zoom", 1.0)),
        )
        return st

    @classmethod
    def new_tank(cls, display_name: str = "Player") -> "TankState":
        st = cls(display_name=display_name)
        # Seed a few unowned free-swimmers + one plant.
        for key in FISH_KEYS:
            rare = random.random() < 0.12
            st.fish.append(
                FishEntity(
                    id=str(uuid.uuid4())[:8],
                    species_key=key,
                    x=random.uniform(200, WORLD_W - 200),
                    y=random.uniform(120, WORLD_H - 120),
                    vx=random.uniform(-35, 35),
                    vy=random.uniform(-18, 18),
                    facing_right=True,
                    rare=rare,
                    health=random.uniform(0.7, 1.0),
                    fullness=random.uniform(0.4, 0.8),
                    age_days=random.uniform(1, 40),
                )
            )
        st.decorate(VIEW_W * 0.3, VIEW_H * 0.75)
        st.pending_care_deltas.clear()
        return st
