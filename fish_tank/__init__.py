"""Transparent Fish Tank — Desktop Pet mini-program (Phase 1 local).

Public entry: FishTankDialog (lazy-imported from .dialog).

Phase 1: local translucent tank, free swim, feed/decorate/name/catch stubs.
Phase 2 hooks: fish_tank.remote_stubs (settlement / immediate catch-trade) — no public server.
"""

from .model import TankState
from .species import SPECIES

__all__ = [
    "TankState",
    "SPECIES",
    "FishTankDialog",
]


def __getattr__(name):
    if name == "FishTankDialog":
        from .dialog import FishTankDialog

        return FishTankDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
