#!/usr/bin/env python3
"""Headless smoke checks for 箱庭島 gameplay deepen (no GUI required for model/grid)."""

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
from hakoniwa.model import (
    COST_AFFOREST,
    COST_FACTORY,
    COST_FARM,
    COST_LANDFILL,
    COST_LEVEL,
    FOOD_PER_FARM,
    FUNDS_PER_FACTORY,
    IslandState,
)
from hakoniwa.remote import HakoniwaRemoteError, normalize_base_url
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


def test_catalog_costs():
    assert COST_FARM == 20
    assert COST_FACTORY == 100
    assert COST_LANDFILL == 150
    assert COST_LEVEL == 5
    assert COST_AFFOREST == 50


def test_new_island_and_loop():
    state = IslandState.new_game()
    assert state.land_count() == 7
    assert state.funds == 1000
    sea = sum(1 for row in state.cells for c in row if c.terrain == "sea")
    assert sea == 20 * 20 - 7

    # Need 平地 for buildings — level a dirt cell first if needed.
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    build_ij = None
    for i, j in land:
        if state.cell(i, j).terrain == "grass":
            build_ij = (i, j)
            break
    if build_ij is None:
        i, j = land[0]
        assert state.cell(i, j).terrain == "dirt"
        assert state.level_land(i, j) == "ok"
        assert state.funds == 1000 - COST_LEVEL
        assert state.cell(i, j).terrain == "grass"
        build_ij = (i, j)
        funds_after_level = state.funds
    else:
        funds_after_level = state.funds

    i, j = build_ij
    assert state.place_building(i, j, "farm") == "ok"
    assert state.funds == funds_after_level - COST_FARM
    assert state.cell(i, j).building == "farm"

    # Cannot build on dirt without leveling.
    dirt = next(
        ((x, y) for x in range(20) for y in range(20) if state.cell(x, y).terrain == "dirt"),
        None,
    )
    if dirt:
        assert state.place_building(dirt[0], dirt[1], "factory") != "ok"

    # Landfill: sea → shallow (adjacent), then shallow → dirt.
    filled = False
    for si in range(20):
        for sj in range(20):
            if state.can_landfill(si, sj) and state.cell(si, sj).terrain == "sea":
                funds_before = state.funds
                assert state.landfill(si, sj) == "ok"
                assert state.cell(si, sj).terrain == "shallow"
                assert state.funds == funds_before - COST_LANDFILL
                assert state.landfill(si, sj) == "ok"
                assert state.cell(si, sj).terrain == "dirt"
                filled = True
                break
        if filled:
            break
    assert filled
    assert state.land_count() == 8

    # 植林 on empty grass.
    grass_empty = next(
        (
            (x, y)
            for x in range(20)
            for y in range(20)
            if state.can_afforest(x, y)
        ),
        None,
    )
    assert grass_empty is not None
    gi, gj = grass_empty
    funds_before = state.funds
    assert state.afforest(gi, gj) == "ok"
    assert state.cell(gi, gj).terrain == "forest"
    assert state.funds == funds_before - COST_AFFOREST

    # 整地 forest → grass.
    assert state.level_land(gi, gj) == "ok"
    assert state.cell(gi, gj).terrain == "grass"

    food_before = state.food
    funds_before = state.funds
    farms = state.building_count("farm")
    factories = state.building_count("factory")
    notes = state.next_turn()
    assert state.turn == 2
    assert notes
    assert any("產糧" in n for n in notes)
    assert any("勞動 stub" in n for n in notes)
    # Food rose by farm yield then fell by need; net should reflect production.
    assert farms == 1
    assert state.food == food_before + farms * FOOD_PER_FARM - 20  # pop < 500 → min need
    assert state.funds == funds_before + factories * FUNDS_PER_FACTORY
    assert state.food > 0


def test_save_load_roundtrip():
    state = IslandState.new_game()
    # Level + factory on plains.
    for i in range(20):
        for j in range(20):
            if state.cell(i, j).terrain == "dirt":
                state.level_land(i, j)
            if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None:
                state.place_building(i, j, "factory")
                break
        else:
            continue
        break
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "island.json"
        save_island(state, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["version"] == 2
        loaded = load_island(path)
        assert loaded is not None
        assert loaded.funds == state.funds
        assert loaded.building_count("factory") == 1
        assert loaded.land_count() == 7


def test_remote_url_normalize():
    assert normalize_base_url("http://192.168.1.10:8787/") == "http://192.168.1.10:8787"
    assert normalize_base_url("192.168.1.10:8787") == "http://192.168.1.10:8787"
    try:
        normalize_base_url("not a url")
        assert False, "expected HakoniwaRemoteError"
    except HakoniwaRemoteError:
        pass


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
    assert dlg._online is False
    assert "本機" in dlg.conn_status.text()
    dlg.close()
    del app


def test_server_api_if_available():
    """Exercise FastAPI endpoints when hakoniwa_server deps are installed."""
    import os
    import tempfile

    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("hakoniwa_server deps missing — skip API smoke")
        return

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HAKONIWA_DATA_DIR"] = tmp
        os.environ.pop("HAKONIWA_API_KEY", None)
        # Reload store/app against temp dir.
        import importlib

        import hakoniwa_server.store as store_mod
        import hakoniwa_server.app as app_mod

        importlib.reload(store_mod)
        importlib.reload(app_mod)
        client = TestClient(app_mod.app)

        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["ok"] is True

        island = client.get("/api/v1/island").json()
        assert island["size"] == 20
        assert island["version"] == 2

        # Find a grass cell (or level dirt) then place farm.
        cells = island["cells"]
        target = None
        for i, row in enumerate(cells):
            for j, c in enumerate(row):
                if c["terrain"] == "grass" and not c.get("building"):
                    target = (i, j)
                    break
            if target:
                break
        if target is None:
            for i, row in enumerate(cells):
                for j, c in enumerate(row):
                    if c["terrain"] == "dirt":
                        r = client.post("/api/v1/island/level", json={"i": i, "j": j})
                        assert r.status_code == 200 and r.json()["ok"]
                        target = (i, j)
                        break
                if target:
                    break
        assert target is not None
        i, j = target
        placed = client.post(
            "/api/v1/island/place", json={"i": i, "j": j, "kind": "farm"}
        ).json()
        assert placed["ok"] is True
        assert placed["island"]["cells"][i][j]["building"] == "farm"

        turned = client.post("/api/v1/island/turn").json()
        assert turned["ok"] is True
        assert turned["island"]["turn"] == 2
        assert turned["notes"]

        removed = client.post(
            "/api/v1/island/remove", json={"i": i, "j": j}
        ).json()
        assert removed["ok"] is True
        assert removed["island"]["cells"][i][j]["building"] is None


def main():
    test_grid_geometry()
    test_catalog_costs()
    test_new_island_and_loop()
    test_save_load_roundtrip()
    test_remote_url_normalize()
    test_dialog_import_offscreen()
    test_server_api_if_available()
    print("hakoniwa smoke_test: OK")


if __name__ == "__main__":
    main()
