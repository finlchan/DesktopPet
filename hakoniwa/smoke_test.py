#!/usr/bin/env python3
"""Headless smoke checks for 箱庭島 scaffold (no GUI required for model/grid)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Allow running as `python -m hakoniwa.smoke_test` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hakoniwa.grid import (
    GRID_SIZE,
    cell_center,
    center_cluster,
    diamond_vertices,
    neighbors,
    point_in_diamond,
)
from hakoniwa.model import IslandState, LANDFILL_COST
from hakoniwa.save import load_island, save_island


def test_grid_geometry():
    assert GRID_SIZE == 20
    land = center_cluster()
    assert len(land) == 7, land
    ci, cj = land[0]
    assert len(neighbors(ci, cj)) == 6

    # T-junction: W of (1,0) equals mid of E–S on (0,0) for 1:1 cell.
    cell = 64.0
    c00 = cell_center(0, 0, cell)
    c10 = cell_center(1, 0, cell)
    e = (c00[0] + cell / 2, c00[1])
    s = (c00[0], c00[1] + cell / 2)
    mid_es = ((e[0] + s[0]) / 2, (e[1] + s[1]) / 2)
    w10 = (c10[0] - cell / 2, c10[1])
    assert abs(mid_es[0] - w10[0]) < 1e-6 and abs(mid_es[1] - w10[1]) < 1e-6

    verts = diamond_vertices(0, 0, cell)
    assert len(verts) == 4
    assert point_in_diamond(0, 0, 0, 0, cell)
    assert not point_in_diamond(cell, 0, 0, 0, cell)


def test_new_island_and_loop():
    state = IslandState.new_game()
    assert state.land_count() == 7
    assert state.funds == 1000
    sea = sum(1 for row in state.cells for c in row if c.terrain == "sea")
    assert sea == 20 * 20 - 7

    # Place farm on a land cell.
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    i, j = land[0]
    assert state.place_building(i, j, "farm") == "ok"
    assert state.funds == 1000 - 20
    assert state.cell(i, j).building == "farm"

    # Landfill an adjacent sea.
    filled = False
    for i in range(20):
        for j in range(20):
            if state.can_landfill(i, j):
                assert state.landfill(i, j) == "ok"
                filled = True
                break
        if filled:
            break
    assert filled
    assert state.land_count() == 8
    assert state.funds == 1000 - 20 - LANDFILL_COST

    notes = state.next_turn()
    assert state.turn == 2
    assert notes
    assert state.food > 0


def test_save_load_roundtrip():
    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    state.place_building(land[0][0], land[0][1], "factory")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "island.json"
        save_island(state, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        loaded = load_island(path)
        assert loaded is not None
        assert loaded.funds == state.funds
        assert loaded.building_count("factory") == 1
        assert loaded.land_count() == 7


def test_dialog_import_offscreen():
    """Instantiate dialog under offscreen Qt if available."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    # Minimal stub so dialog chrome can resolve.
    import desktop_pet  # noqa: F401
    from hakoniwa import HakoniwaIslandDialog

    dlg = HakoniwaIslandDialog(None, None)
    assert dlg.windowTitle() == "箱庭島"
    assert dlg.state.land_count() == 7
    dlg.close()
    del app


def main():
    test_grid_geometry()
    test_new_island_and_loop()
    test_save_load_roundtrip()
    test_dialog_import_offscreen()
    print("hakoniwa smoke_test: OK")


if __name__ == "__main__":
    main()
