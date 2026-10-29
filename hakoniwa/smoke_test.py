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
    MAX_GUEST_NAME,
    MAX_GUEST_TEXT,
    IslandState,
)
from hakoniwa.demos import island_summary, local_demo_islands, make_demo_coral, make_demo_pine
from hakoniwa.dialog import TOOL_SPECS, tool_enabled
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


def test_guestbook_local():
    state = IslandState.new_game()
    assert state.list_comments() == []
    assert state.add_comment("", "hi") != "ok"
    assert state.add_comment("Ada", "") != "ok"
    assert state.add_comment("x" * (MAX_GUEST_NAME + 1), "hi") != "ok"
    assert state.add_comment("Ada", "y" * (MAX_GUEST_TEXT + 1)) != "ok"
    assert state.add_comment("Ada", "你好箱庭島") == "ok"
    assert state.add_comment("Bob", "second") == "ok"
    comments = state.list_comments()
    assert len(comments) == 2
    assert comments[0].name == "Ada" and comments[0].text == "你好箱庭島"
    assert comments[1].name == "Bob"
    assert any("訪客留言" in line for line in state.log)


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
    assert state.add_comment("Visitor", "nice island") == "ok"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "island.json"
        save_island(state, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["version"] == 2
        assert len(raw["comments"]) == 1
        loaded = load_island(path)
        assert loaded is not None
        assert loaded.funds == state.funds
        assert loaded.building_count("factory") == 1
        assert loaded.land_count() == 7
        assert len(loaded.list_comments()) == 1
        assert loaded.list_comments()[0].text == "nice island"


def test_remote_url_normalize():
    assert normalize_base_url("http://192.168.1.10:8787/") == "http://192.168.1.10:8787"
    assert normalize_base_url("192.168.1.10:8787") == "http://192.168.1.10:8787"
    try:
        normalize_base_url("not a url")
        assert False, "expected HakoniwaRemoteError"
    except HakoniwaRemoteError:
        pass


def test_local_demos():
    demos = local_demo_islands()
    assert len(demos) == 2
    ids = {d.island_id for d in demos}
    assert ids == {"demo-coral", "demo-pine"}
    coral = make_demo_coral()
    pine = make_demo_pine()
    assert coral.land_count() >= 7
    assert pine.land_count() >= 5
    assert coral.name == "珊瑚灘島"
    assert pine.name == "松風島"
    row = island_summary(coral)
    assert row["id"] == "demo-coral"
    assert row["land"] == coral.land_count()
    # Round-trip keeps id.
    assert IslandState.from_dict(coral.to_dict()).island_id == "demo-coral"


def test_tool_enabled_rules():
    state = IslandState.new_game()
    # No selection → all tools disabled.
    for key, *_ in TOOL_SPECS:
        ok, reason = tool_enabled(state, key, None)
        assert ok is False
        assert "選格" in reason

    # Pick a grass cell if any; else level dirt.
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    grass = next(
        ((i, j) for i, j in land if state.cell(i, j).terrain == "grass"),
        None,
    )
    if grass is None:
        i, j = land[0]
        assert state.level_land(i, j) == "ok"
        grass = (i, j)
    gi, gj = grass
    ok, _ = tool_enabled(state, "farm", (gi, gj))
    assert ok is True
    ok, _ = tool_enabled(state, "factory", (gi, gj))
    assert ok is True
    ok, reason = tool_enabled(state, "remove", (gi, gj))
    assert ok is False
    assert "沒有建築" in reason
    ok, reason = tool_enabled(state, "landfill", (gi, gj))
    assert ok is False

    # Broke: funds 0 → farm disabled for cost.
    state.funds = 0
    ok, reason = tool_enabled(state, "farm", (gi, gj))
    assert ok is False
    assert "資金" in reason

    # Sea cell adjacent to land → landfill ok when funded.
    state.funds = 1000
    sea_adj = next(
        (
            (i, j)
            for i in range(20)
            for j in range(20)
            if state.can_landfill(i, j) and state.cell(i, j).terrain == "sea"
        ),
        None,
    )
    assert sea_adj is not None
    ok, _ = tool_enabled(state, "landfill", sea_adj)
    assert ok is True
    ok, reason = tool_enabled(state, "farm", sea_adj)
    assert ok is False
    assert "平地" in reason


def test_dialog_import_offscreen():
    """Instantiate dialog under offscreen Qt if available."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    # Minimal stub so dialog chrome can resolve.
    import desktop_pet  # noqa: F401
    from hakoniwa import HakoniwaIslandDialog
    from hakoniwa.dialog import TourismIslandDialog, TourismListDialog

    dlg = HakoniwaIslandDialog(None, None)
    assert dlg.windowTitle() == "箱庭島"
    assert dlg.state.land_count() == 7
    assert dlg._online is False
    assert "本機" in dlg.conn_status.text()
    assert dlg.guestbook_view is not None
    assert dlg.guest_name is not None
    assert dlg.guest_text is not None
    assert hasattr(dlg, "tool_buttons")
    assert set(dlg.tool_buttons) == {k for k, *_ in TOOL_SPECS}
    # No selection → tools disabled.
    dlg._refresh_toolbar()
    assert all(not b.isEnabled() for b in dlg.tool_buttons.values())
    # Status bar carries the four core fields.
    assert "資金" in dlg.stats.text()
    assert "糧食" in dlg.stats.text()
    assert "回合" in dlg.stats.text()
    assert "陸地" in dlg.stats.text()

    # Select a buildable grass cell → farm/factory enable.
    land = [(i, j) for i in range(20) for j in range(20) if dlg.state.is_land(i, j)]
    grass = next(
        ((i, j) for i, j in land if dlg.state.cell(i, j).terrain == "grass"),
        None,
    )
    if grass is None:
        i, j = land[0]
        dlg.state.level_land(i, j)
        grass = (i, j)
    dlg._on_cell_clicked(*grass)
    assert dlg.tool_buttons["farm"].isEnabled()
    assert dlg.tool_buttons["factory"].isEnabled()
    assert not dlg.tool_buttons["remove"].isEnabled()
    assert "農場" in dlg.tool_buttons["farm"].text()
    assert str(COST_FARM) in dlg.tool_buttons["farm"].text()

    # Map pan/zoom API.
    old_cell = dlg.map.cell
    dlg.map.zoom_by(1.5)
    assert dlg.map.cell > old_cell
    dlg.map.pan_by(12.0, -8.0)
    dlg.map.reset_view()
    assert abs(dlg.map.cell - old_cell) < 1e-6

    dlg.state.add_comment("Smoke", "panel ok")
    dlg._refresh_ui()
    assert "Smoke" in dlg.guestbook_view.toPlainText()

    catalog = dlg._tourism_catalog()
    assert len(catalog) >= 2
    assert any(r.get("id") == "demo-coral" for r in catalog)
    picker = TourismListDialog(catalog, parent=dlg)
    assert picker.list.count() == len(catalog)
    picker.close()

    island = dlg._load_tourism_island("demo-pine")
    assert island is not None
    assert island.island_id == "demo-pine"
    tour = TourismIslandDialog(island, remote=None, parent=dlg)
    assert "觀光" in tour.windowTitle()
    assert tour.guestbook_view is not None
    assert hasattr(tour.map, "zoom_by")
    tour.state.add_comment("Tourist", "nice pines")
    tour._show_guestbook(tour.state.list_comments())
    assert "Tourist" in tour.guestbook_view.toPlainText()
    tour.close()

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

        listed = client.get("/api/v1/island/comments").json()
        assert listed["comments"] == []
        posted = client.post(
            "/api/v1/island/comments",
            json={"name": "NasGuest", "text": "hello from API"},
        ).json()
        assert posted["ok"] is True
        assert len(posted["comments"]) == 1
        assert posted["comments"][0]["name"] == "NasGuest"
        listed2 = client.get("/api/v1/island/comments").json()
        assert len(listed2["comments"]) == 1
        # Island snapshot also carries guestbook.
        snap = client.get("/api/v1/island").json()
        assert len(snap.get("comments") or []) == 1
        assert snap.get("id") == "home"

        # Multi-island tourism catalog (seeded demos).
        catalog = client.get("/api/v1/islands").json()
        assert "islands" in catalog
        ids = {row["id"] for row in catalog["islands"]}
        assert "home" in ids
        assert "demo-coral" in ids
        assert "demo-pine" in ids
        assert h.json().get("islands") == len(catalog["islands"])

        coral = client.get("/api/v1/islands/demo-coral").json()
        assert coral["id"] == "demo-coral"
        assert coral["name"] == "珊瑚灘島"
        assert len(coral["cells"]) == 20

        missing = client.get("/api/v1/islands/no-such-island")
        assert missing.status_code == 404

        pine_comments = client.get("/api/v1/islands/demo-pine/comments").json()
        assert pine_comments["comments"] == []
        posted_tour = client.post(
            "/api/v1/islands/demo-pine/comments",
            json={"name": "Tourist", "text": "松風好美"},
        ).json()
        assert posted_tour["ok"] is True
        assert len(posted_tour["comments"]) == 1
        listed_pine = client.get("/api/v1/islands/demo-pine/comments").json()
        assert listed_pine["comments"][0]["text"] == "松風好美"


def main():
    test_grid_geometry()
    test_catalog_costs()
    test_new_island_and_loop()
    test_guestbook_local()
    test_local_demos()
    test_save_load_roundtrip()
    test_remote_url_normalize()
    test_tool_enabled_rules()
    test_dialog_import_offscreen()
    test_server_api_if_available()
    print("hakoniwa smoke_test: OK")


if __name__ == "__main__":
    main()
