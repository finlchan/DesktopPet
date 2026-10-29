"""箱庭島 — Desktop Pet mini-program (scaffold).

Public entry: HakoniwaIslandDialog (lazy-imported from .dialog).
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
