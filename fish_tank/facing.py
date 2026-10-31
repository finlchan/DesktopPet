"""8-direction swim facing (plan item 24).

Order on sheets / indices:
  0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW

No realtime 3D — only discrete blit from pre-rendered pixel sheets.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

DIRS: Sequence[str] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
DIR_COUNT = 8
# Default idle facing (eastbound).
DEFAULT_FACING = 2  # E


def facing_from_velocity(vx: float, vy: float, *, prev: int = DEFAULT_FACING) -> int:
    """Bucket velocity into one of 8 compass facings (screen +y down).

    Uses atan2(vx, -vy) so 0° = North (up on screen). Returns ``prev`` when
    nearly stationary so sprites don't jitter.
    """
    if abs(vx) < 0.8 and abs(vy) < 0.8:
        return int(prev) % DIR_COUNT
    deg = math.degrees(math.atan2(vx, -vy)) % 360.0
    return int((deg + 22.5) // 45.0) % DIR_COUNT


def facing_name(index: int) -> str:
    return DIRS[int(index) % DIR_COUNT]


def coerce_facing(value, *, fallback: int = DEFAULT_FACING) -> int:
    """Accept int facing, legacy bool facing_right, or name string."""
    if isinstance(value, bool):
        return 2 if value else 6  # E / W
    if isinstance(value, str):
        key = value.strip().upper()
        if key in DIRS:
            return DIRS.index(key)
        return fallback
    try:
        return int(value) % DIR_COUNT
    except (TypeError, ValueError):
        return fallback
