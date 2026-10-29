"""箱庭島 — Desktop Pet mini-program (箱庭斜視 + simplified v1 loop).

Public entry: HakoniwaIslandDialog (lazy-imported from .dialog).
Optional NAS client: hakoniwa.remote.HakoniwaRemote.
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
