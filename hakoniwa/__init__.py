"""箱庭島 — Desktop Pet mini-program (箱庭斜視 + simplified v1 loop).

Public entry: HakoniwaIslandDialog (lazy-imported from .dialog).
Optional NAS client: hakoniwa.remote.HakoniwaRemote.

View checklist (mandatory after any map/view change):
  1. Player view must be 箱庭斜視 (H/W ≈ 0.65 foreshortening).
  2. ``hakoniwa.grid.OBLIQUE_Y_SCALE == 0.65`` — not orthographic rotate-only.
  3. Run ``python -m hakoniwa.smoke_test`` (asserts projection invariant).
  4. Reject equal-diagonal flat rotate (wrong-flat-rotated-grid.png);
     prior correct-hakoniwa-oblique-45.png was the old 0.707 reference.
"""

from .model import IslandState, BUILDINGS, TERRAIN

__all__ = [
    "IslandState",
    "BUILDINGS",
    "TERRAIN",
    "HakoniwaIslandDialog",
]


def __getattr__(name):
    if name == "HakoniwaIslandDialog":
        from .dialog import HakoniwaIslandDialog

        return HakoniwaIslandDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
