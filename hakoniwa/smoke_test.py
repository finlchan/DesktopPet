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
    OBLIQUE_ELEVATION_DEG,
    OBLIQUE_Y_SCALE,
    cell_center,
    cell_screen_size,
    center_cluster,
    diamond_vertices,
    neighbors,
    oblique_projection_params,
    point_in_diamond,
)
from hakoniwa.model import (
    COST_AFFOREST,
    COST_DEFENSE,
    COST_FACTORY,
    COST_FARM,
    COST_HARVEST,
    COST_LANDFILL,
    COST_LEVEL,
    COST_MISSILE,
    COST_MISSILE_BASE,
    COST_MISSILE_CHEAP,
    DEFENSE_RADIUS,
    DEFENSE_SPAWN_FACTOR,
    DEFENSE_STOMP_SAVE_CHANCE,
    FIRE_BASE_CHANCE,
    FOOD_PER_FARM,
    FOREST_FIRE_FACTOR,
    FUNDS_PER_FACTORY,
    FUNDS_PER_TIMBER_LOT,
    MAX_GUEST_NAME,
    MAX_GUEST_TEXT,
    MONSTER_MIN_POP,
    MONSTER_MIN_TURN,
    MONSTER_REWARD,
    SAVE_VERSION,
    TIMBER_LOT,
    TOWN_TO_CITY_POP,
    TREE_GROWTH_PER_TURN,
    TREE_MAX,
    TREE_MIN,
    VILLAGE_TO_TOWN_POP,
    IslandState,
    timber_funds,
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

    # T-junction: W of (1,0) equals mid of E–S on (0,0) for logical 1:1 + oblique.
    cell = 64.0
    w, h = cell_screen_size(cell)
    c00 = cell_center(0, 0, cell)
    c10 = cell_center(1, 0, cell)
    e = (c00[0] + w / 2, c00[1])
    s = (c00[0], c00[1] + h / 2)
    mid_es = ((e[0] + s[0]) / 2, (e[1] + s[1]) / 2)
    w10 = (c10[0] - w / 2, c10[1])
    assert abs(mid_es[0] - w10[0]) < 1e-6 and abs(mid_es[1] - w10[1]) < 1e-6

    verts = diamond_vertices(0, 0, cell)
    assert len(verts) == 4
    assert point_in_diamond(0, 0, 0, 0, cell)
    assert not point_in_diamond(cell, 0, 0, 0, cell)


def test_oblique_foreshortening_invariant():
    """箱庭斜視 must foreshorten depth — reject flat rotate(45°) orthographic.

    Correct: screen diamond H/W == sin(45°) ≈ 0.707 (oblique affine).
    Wrong regression: H/W == 1.0 (top-down squares rotated 45° only).
    """
    import math

    params = oblique_projection_params()
    assert params["kind"] == "oblique_affine"
    assert params["elevation_deg"] == OBLIQUE_ELEVATION_DEG == 45.0
    assert params["forbidden"] == "orthographic_rotate_only"
    assert abs(float(params["y_scale"]) - math.sin(math.radians(45.0))) < 1e-12
    assert abs(OBLIQUE_Y_SCALE - math.sin(math.radians(45.0))) < 1e-12
    # Hard floor: must not be orthographic (y_scale == 1).
    assert OBLIQUE_Y_SCALE < 0.95, OBLIQUE_Y_SCALE
    assert OBLIQUE_Y_SCALE > 0.5, OBLIQUE_Y_SCALE

    cell = 64.0
    w, h = cell_screen_size(cell)
    assert abs(w - cell) < 1e-9
    assert abs(h / w - OBLIQUE_Y_SCALE) < 1e-9

    n, e, s, west = diamond_vertices(0.0, 0.0, cell)
    width = e[0] - west[0]
    height = s[1] - n[1]
    ratio = height / width
    assert abs(ratio - OBLIQUE_Y_SCALE) < 1e-6, (ratio, OBLIQUE_Y_SCALE)
    # Regression guard vs wrong-flat-rotated-grid (equal diagonals).
    assert abs(ratio - 1.0) > 0.1, ratio

    # Lattice Y basis must also be foreshortened (not only the polygon).
    # Even→even along j: step is v = (W/2, −H/2).
    c00 = cell_center(0, 0, cell)
    c01 = cell_center(0, 1, cell)
    assert abs((c01[0] - c00[0]) - w / 2.0) < 1e-6
    assert abs((c01[1] - c00[1]) - (-h / 2.0)) < 1e-6
    # Map height span must be shorter than width span (foreshortened island disc).
    from hakoniwa.grid import map_bounds

    min_x, min_y, max_x, max_y = map_bounds(GRID_SIZE, cell)
    assert (max_y - min_y) < (max_x - min_x) * 0.95


def test_catalog_costs():
    assert COST_FARM == 20
    assert COST_FACTORY == 100
    assert COST_LANDFILL == 150
    assert COST_LEVEL == 5
    assert COST_AFFOREST == 50
    assert COST_HARVEST == 0
    assert TREE_MIN == 100
    assert TREE_MAX == 20000
    assert TREE_GROWTH_PER_TURN == 100
    assert TIMBER_LOT == 100
    assert FUNDS_PER_TIMBER_LOT == 5
    assert timber_funds(100) == 5
    assert timber_funds(250) == 10
    assert timber_funds(99) == 0
    assert COST_MISSILE == 20
    assert COST_MISSILE_CHEAP == 10
    assert COST_MISSILE_BASE == 300
    assert COST_DEFENSE == 1000
    assert DEFENSE_RADIUS == 2
    assert 0 < DEFENSE_SPAWN_FACTOR < 1
    assert 0 < DEFENSE_STOMP_SAVE_CHANCE < 1
    assert SAVE_VERSION >= 6


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
    assert state.cell(gi, gj).trees == TREE_MIN
    assert state.funds == funds_before - COST_AFFOREST

    # 整地 forest → grass (no timber payout).
    assert state.level_land(gi, gj) == "ok"
    assert state.cell(gi, gj).terrain == "grass"
    assert state.cell(gi, gj).trees == 0

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


def test_forest_plant_grow_harvest():
    """植林 → 回合生長 → 伐採瞬售資金（定本 100本≈5億）。"""
    state = IslandState.new_game()
    grass = next(
        (
            (x, y)
            for x in range(20)
            for y in range(20)
            if state.can_afforest(x, y)
        ),
        None,
    )
    assert grass is not None
    gi, gj = grass
    assert state.afforest(gi, gj) == "ok"
    cell = state.cell(gi, gj)
    assert cell.terrain == "forest" and cell.trees == TREE_MIN

    ok, _ = tool_enabled(state, "harvest", (gi, gj))
    assert ok is True
    ok, reason = tool_enabled(state, "afforest", (gi, gj))
    assert ok is False and "平地" in reason

    # Grow one turn (silence disasters/monsters for a clean assert).
    import random as _rnd

    _rnd.seed(0)
    notes = state.next_turn()
    assert any("林木生長" in n for n in notes)
    assert state.cell(gi, gj).trees == TREE_MIN + TREE_GROWTH_PER_TURN

    # Cap: pre-fill near max then grow.
    state.cell(gi, gj).trees = TREE_MAX - 50
    state.next_turn()
    assert state.cell(gi, gj).trees == TREE_MAX

    funds_before = state.funds
    trees = state.cell(gi, gj).trees
    expected = timber_funds(trees)
    assert state.harvest(gi, gj) == "ok"
    assert state.cell(gi, gj).terrain == "grass"
    assert state.cell(gi, gj).trees == 0
    assert state.funds == funds_before + expected
    assert expected == (TREE_MAX // TIMBER_LOT) * FUNDS_PER_TIMBER_LOT

    # Free action; cannot harvest grass.
    assert state.can_harvest(gi, gj) is False
    assert state.harvest(gi, gj) != "ok"

    # Persist trees across save round-trip.
    state.afforest(gi, gj)
    state.cell(gi, gj).trees = 450
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    assert blob["cells"][gi][gj]["trees"] == 450
    loaded = IslandState.from_dict(blob)
    assert loaded.cell(gi, gj).terrain == "forest"
    assert loaded.cell(gi, gj).trees == 450
    # Legacy forest without trees key → TREE_MIN.
    legacy = IslandState.from_dict(
        {
            "version": 5,
            "size": 20,
            "cells": [
                [
                    {"terrain": "forest"}
                    if (r, c) == (gi, gj)
                    else {"terrain": "sea"}
                    for c in range(20)
                ]
                for r in range(20)
            ],
        }
    )
    assert legacy.cell(gi, gj).trees == TREE_MIN

    keys = {k for k, *_ in TOOL_SPECS}
    assert "harvest" in keys and "afforest" in keys


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
        assert raw["version"] == SAVE_VERSION
        assert len(raw["comments"]) == 1
        assert "monsters" in raw
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


def test_settlements_and_disasters():
    """Village/town/city evolution + fire/typhoon/quake stubs (local-first)."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    # Ensure grass cells: farm + empty neighbor for village spawn.
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 3
    fi, fj = grass[0]
    assert state.place_building(fi, fj, "farm") == "ok"
    spawn = next(
        (
            (ni, nj)
            for ni, nj in neighbors(fi, fj)
            if state.cell(ni, nj).terrain == "grass"
            and state.cell(ni, nj).building is None
        ),
        None,
    )
    assert spawn is not None
    si, sj = spawn
    assert state._near_farm_or_settlement(si, sj)

    orig_random = random.random
    old_fire = model_mod.FIRE_BASE_CHANCE
    old_typhoon = model_mod.TYPHOON_BASE_CHANCE
    old_quake = model_mod.QUAKE_BASE_CHANCE
    try:
        # Force spawn (random < 0.20).
        random.random = lambda: 0.0  # type: ignore[assignment]
        notes = state._evolve_settlements()
        assert state.cell(si, sj).terrain == "village"
        assert any("村落" in n for n in notes)

        state.population = VILLAGE_TO_TOWN_POP
        notes = state._evolve_settlements()
        assert state.cell(si, sj).terrain == "town"
        assert any("村→町" in n for n in notes)

        state.population = TOWN_TO_CITY_POP
        notes = state._evolve_settlements()
        assert state.cell(si, sj).terrain == "city"
        assert any("町→都市" in n for n in notes)

        assert state.can_level(si, sj)
        assert state.level_land(si, sj) == "ok"
        assert state.cell(si, sj).terrain == "grass"

        # Fire on town (no forest neighbor); silence typhoon/quake for a clean assert.
        model_mod.TYPHOON_BASE_CHANCE = 0.0
        model_mod.QUAKE_BASE_CHANCE = 0.0
        state.cell(si, sj).terrain = "town"
        assert not state._has_forest_neighbor(si, sj)
        notes = state._apply_disasters()
        assert state.cell(si, sj).terrain == "dirt"
        assert any("火災" in n for n in notes)

        # Forest neighbor mitigates fire: mid-roll between reduced and base → no burn.
        state.cell(si, sj).terrain = "town"
        forest_spot = next(
            (
                (ni, nj)
                for ni, nj in neighbors(si, sj)
                if (ni, nj) != (fi, fj) and state.is_land(ni, nj)
            ),
            None,
        )
        assert forest_spot is not None
        fxi, fxj = forest_spot
        state.cell(fxi, fxj).building = None
        state.cell(fxi, fxj).terrain = "forest"
        assert state._has_forest_neighbor(si, sj)
        reduced = FIRE_BASE_CHANCE * FOREST_FIRE_FACTOR
        mid = (reduced + FIRE_BASE_CHANCE) / 2.0
        assert reduced < mid < FIRE_BASE_CHANCE
        random.random = lambda: mid  # type: ignore[assignment]
        notes = state._apply_disasters()
        assert state.cell(si, sj).terrain == "town"
        assert not any("火災" in n and f"({si},{sj})" in n for n in notes)

        # Typhoon: farm → plain (silence fire/quake).
        model_mod.FIRE_BASE_CHANCE = 0.0
        model_mod.TYPHOON_BASE_CHANCE = old_typhoon
        model_mod.QUAKE_BASE_CHANCE = 0.0
        random.random = lambda: 0.0  # type: ignore[assignment]
        assert state.cell(fi, fj).building == "farm"
        notes = state._apply_disasters()
        assert state.cell(fi, fj).building is None
        assert any("颱風" in n for n in notes)

        # Quake: factory → wasteland (silence fire/typhoon).
        model_mod.FIRE_BASE_CHANCE = 0.0
        model_mod.TYPHOON_BASE_CHANCE = 0.0
        model_mod.QUAKE_BASE_CHANCE = old_quake
        gi, gj = grass[1] if grass[1] != (fi, fj) else grass[2]
        state.cell(gi, gj).terrain = "grass"
        state.cell(gi, gj).building = "factory"
        notes = state._apply_disasters()
        assert state.cell(gi, gj).building is None
        assert state.cell(gi, gj).terrain == "dirt"
        assert any("地震" in n for n in notes)

        state.cell(si, sj).terrain = "village"
        data = state.to_dict()
        assert data["version"] == SAVE_VERSION
        loaded = IslandState.from_dict(data)
        assert loaded.cell(si, sj).terrain == "village"
    finally:
        random.random = orig_random  # type: ignore[assignment]
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_typhoon
        model_mod.QUAKE_BASE_CHANCE = old_quake


def test_monster_events():
    """Color-block monster spawn / missile / wait (local-first)."""
    state = IslandState.new_game()
    assert state.monsters == []
    assert state.has_monster() is False

    # Forced spawn on land.
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    i, j = land[0]
    m = state.spawn_monster(i, j)
    assert m is not None
    assert state.has_monster()
    assert state.monster_at(i, j) is m
    assert any("怪獸出現" in line for line in state.log)

    # Cannot build / level under monster.
    assert state.place_building(i, j, "farm") != "ok"
    ok, reason = tool_enabled(state, "farm", (i, j))
    assert ok is False and "怪獸" in reason
    ok, reason = tool_enabled(state, "missile", (i, j))
    assert ok is True
    ok, reason = tool_enabled(state, "wait", None)
    assert ok is True

    # Wait logs without removing monster.
    funds_before = state.funds
    assert state.wait_monster() == "ok"
    assert state.has_monster()
    assert state.funds == funds_before
    assert any("觀望" in line for line in state.log)

    # Missile kills color-block monster and pays reward stub.
    funds_before = state.funds
    assert state.fire_missile(i, j) == "ok"
    assert not state.has_monster()
    assert state.funds == funds_before - COST_MISSILE + MONSTER_REWARD
    assert any("擊破" in line for line in state.log)

    # Thresholds: no spawn chance below pop/turn gates.
    state.population = MONSTER_MIN_POP - 1
    state.turn = MONSTER_MIN_TURN
    assert state._monster_spawn_chance() == 0.0
    state.population = MONSTER_MIN_POP
    state.turn = MONSTER_MIN_TURN - 1
    assert state._monster_spawn_chance() == 0.0
    state.turn = MONSTER_MIN_TURN
    assert state._monster_spawn_chance() > 0.0

    # Round-trip monsters in save JSON.
    m2 = state.spawn_monster()
    assert m2 is not None
    data = state.to_dict()
    assert data["version"] == SAVE_VERSION
    assert len(data["monsters"]) == 1
    loaded = IslandState.from_dict(data)
    assert loaded.has_monster()
    assert loaded.monsters[0].kind == m2.kind
    assert (loaded.monsters[0].i, loaded.monsters[0].j) == (m2.i, m2.j)


def test_defense_and_missile_base():
    """防衛設施／飛彈基地 place + spawn/stomp/missile stubs."""
    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    # Ensure two grass cells for base + defense.
    grass = [
        (i, j) for i, j in land if state.cell(i, j).terrain == "grass"
    ]
    while len(grass) < 3:
        for i, j in land:
            if state.cell(i, j).terrain == "dirt" and state.cell(i, j).building is None:
                assert state.level_land(i, j) == "ok"
                grass.append((i, j))
                if len(grass) >= 3:
                    break
        else:
            break
    assert len(grass) >= 3
    bi, bj = grass[0]
    di, dj = grass[1]
    fi, fj = grass[2]

    # Missile base → cheaper missiles.
    state.funds = max(state.funds, COST_MISSILE_BASE + COST_DEFENSE + 50)
    assert state.missile_cost() == COST_MISSILE
    assert state.place_building(bi, bj, "missile_base") == "ok"
    assert state.cell(bi, bj).building == "missile_base"
    assert state.has_missile_base()
    assert state.missile_cost() == COST_MISSILE_CHEAP
    ok, _ = tool_enabled(state, "missile_base", (fi, fj))
    assert ok is True

    # Defense facility covers neighbors within radius.
    assert state.place_building(di, dj, "defense") == "ok"
    assert state.cell(di, dj).building == "defense"
    assert state.protected_by_defense(di, dj)
    covered = state.cells_within(di, dj, DEFENSE_RADIUS)
    assert (di, dj) in covered
    assert len(covered) > 1

    # Spawn chance reduced when defense exists.
    state.population = MONSTER_MIN_POP
    state.turn = MONSTER_MIN_TURN
    # Temporarily clear defense to measure baseline, then restore.
    state.cell(di, dj).building = None
    base_chance = state._monster_spawn_chance()
    state.cell(di, dj).building = "defense"
    reduced = state._monster_spawn_chance()
    assert base_chance > 0
    assert abs(reduced - base_chance * DEFENSE_SPAWN_FACTOR) < 1e-9

    # Spawn candidates prefer cells outside defense cover.
    cands = state._spawn_candidate_cells()
    assert cands
    assert all(not state.protected_by_defense(x, y) for x, y in cands) or all(
        state.protected_by_defense(x, y) for x, y in cands
    )

    # Cheaper missile kill with base.
    open_cell = next(
        ((x, y) for x, y in land if not state.protected_by_defense(x, y)),
        land[-1],
    )
    m = state.spawn_monster(*open_cell)
    assert m is not None
    funds_before = state.funds
    assert state.fire_missile(m.i, m.j) == "ok"
    assert not state.has_monster()
    assert state.funds == funds_before - COST_MISSILE_CHEAP + MONSTER_REWARD
    assert any("飛彈基地" in line for line in state.log)

    # Miss near defense logs nullified collateral.
    near = next(iter(state.cells_within(di, dj, 1)))
    funds_before = state.funds
    assert state.monster_at(*near) is None
    assert state.fire_missile(*near) == "ok"
    assert state.funds == funds_before - COST_MISSILE_CHEAP
    assert any("無效化" in line for line in state.log)

    # Stomp on defense → self-destruct clears monster.
    state.funds = max(state.funds, COST_DEFENSE)
    # Re-place defense if wiped (shouldn't be).
    if state.cell(di, dj).building != "defense":
        if state.cell(di, dj).terrain != "grass":
            state.cell(di, dj).terrain = "grass"
        state.cell(di, dj).building = None
        assert state.place_building(di, dj, "defense") == "ok"
    m2 = state.spawn_monster(di, dj)
    assert m2 is not None
    notes = state._stomp_cell(di, dj, m2)
    assert any("自爆" in n for n in notes)
    assert not state.has_monster()
    assert state.cell(di, dj).building is None

    # Near-defense stomp mitigation (force save).
    from hakoniwa.model import Monster
    import hakoniwa.model as model_mod

    state.cell(di, dj).terrain = "grass"
    state.cell(di, dj).building = "defense"
    nbr = next(
        (
            (x, y)
            for x, y in state.cells_within(di, dj, DEFENSE_RADIUS)
            if (x, y) != (di, dj)
            and state.is_land(x, y)
            # Do not overwrite the missile base — needed for round-trip asserts.
            and state.cell(x, y).building != "missile_base"
        ),
        None,
    )
    assert nbr is not None
    ni, nj = nbr
    state.cell(ni, nj).terrain = "grass"
    state.cell(ni, nj).building = "farm"
    m3 = Monster(kind="inora", i=ni, j=nj, hp=1)
    state.monsters = [m3]
    old_save = model_mod.DEFENSE_STOMP_SAVE_CHANCE
    model_mod.DEFENSE_STOMP_SAVE_CHANCE = 1.0
    try:
        notes = state._stomp_cell(ni, nj, m3)
        assert any("減免" in n for n in notes)
        assert state.cell(ni, nj).building == "farm"
        assert state.cell(ni, nj).terrain == "grass"
    finally:
        model_mod.DEFENSE_STOMP_SAVE_CHANCE = old_save

    # Round-trip new buildings in save.
    data = state.to_dict()
    assert data["version"] == SAVE_VERSION
    loaded = IslandState.from_dict(data)
    assert loaded.building_count("missile_base") == 1
    assert loaded.building_count("defense") == 1
    assert loaded.missile_cost() == COST_MISSILE_CHEAP

    # Toolbar rules for defense / missile_base.
    empty = next(
        (
            (x, y)
            for x in range(20)
            for y in range(20)
            if loaded.cell(x, y).terrain == "grass"
            and loaded.cell(x, y).building is None
            and loaded.monster_at(x, y) is None
        ),
        None,
    )
    if empty is None:
        # Level a dirt cell.
        dirt = next(
            (
                (x, y)
                for x in range(20)
                for y in range(20)
                if loaded.cell(x, y).terrain == "dirt"
                and loaded.cell(x, y).building is None
            ),
            None,
        )
        assert dirt is not None
        loaded.funds = max(loaded.funds, COST_LEVEL + COST_DEFENSE)
        assert loaded.level_land(*dirt) == "ok"
        empty = dirt
    loaded.funds = max(loaded.funds, COST_DEFENSE)
    ok, _ = tool_enabled(loaded, "defense", empty)
    assert ok is True
    ok, reason = tool_enabled(loaded, "defense", (bi, bj))
    assert ok is False and "建築" in reason


def test_tool_enabled_rules():
    state = IslandState.new_game()
    # No selection → cell tools disabled; wait needs a monster.
    for key, *_ in TOOL_SPECS:
        ok, reason = tool_enabled(state, key, None)
        assert ok is False
        if key == "wait":
            assert "怪獸" in reason
        else:
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
    # HUD overlays live inside the map viewport (not outside columns).
    from hakoniwa.dialog import HakoniwaMapHud

    assert isinstance(dlg.hud, HakoniwaMapHud)
    assert dlg.stats.parent() is dlg.hud
    assert dlg.sel_label.parent() is dlg.hud
    assert dlg.log_view.parent() is dlg.hud
    assert dlg.guestbook_view.parent() is dlg.hud.guestbook_frame
    assert dlg.map.parent() is dlg.hud
    assert dlg.server_url.parent() is dlg.hud.settings_body
    assert dlg.conn_status.parent() is dlg.hud.settings_body
    assert not dlg.hud.tools_drawer.isVisible()
    # No selection → tools disabled.
    dlg._refresh_toolbar()
    assert all(not b.isEnabled() for b in dlg.tool_buttons.values())
    # Status overlay: locked order 狀態→資金→糧食→人口→回合→格數; no connection mode.
    st = dlg.stats.text()
    assert "資金" in st and "糧食" in st and "人口" in st
    assert "回合" in st and "格數" in st
    assert "狀態" in st
    assert "[本機]" not in st and "[連線]" not in st
    # Exact field order (indices increase left→right).
    i_status, i_funds = st.index("狀態"), st.index("資金")
    i_food, i_pop = st.index("糧食"), st.index("人口")
    i_turn, i_cells = st.index("回合"), st.index("格數")
    assert i_status < i_funds < i_food < i_pop < i_turn < i_cells, st
    # Status HUD is a single horizontal line (no wrap / multi-line).
    assert dlg.stats.wordWrap() is False
    assert "\n" not in st
    dlg.show()
    dlg.resize(960, 780)
    dlg._refresh_ui()
    app.processEvents()
    status_h = dlg.stats.height()
    line_h = dlg.stats.fontMetrics().height()
    assert status_h <= line_h + 16, (status_h, line_h, dlg.stats.text())
    # Opening tools drawer exposes build toolbar + server settings.
    # Use isHidden() — isVisible() is false while the dialog itself is not shown.
    dlg.hud.tools_btn.setChecked(True)
    assert not dlg.hud.tools_drawer.isHidden()
    dlg.hud.tools_btn.setChecked(False)
    assert dlg.hud.tools_drawer.isHidden()

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
    assert dlg.tool_buttons["defense"].isEnabled()
    assert dlg.tool_buttons["missile_base"].isEnabled()
    assert not dlg.tool_buttons["remove"].isEnabled()
    assert "農場" in dlg.tool_buttons["farm"].text()
    assert str(COST_FARM) in dlg.tool_buttons["farm"].text()
    assert "防衛" in dlg.tool_buttons["defense"].text()
    assert "飛彈基地" in dlg.tool_buttons["missile_base"].text()

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

    # Offscreen proof: overlays sit on the map viewport.
    _write_ui_overlay_proof(dlg)

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
    assert tour.guestbook_view.parent() is tour.hud.guestbook_frame
    assert not tour.hud.tools_btn.isVisible()
    tour.state.add_comment("Tourist", "nice pines")
    tour._show_guestbook(tour.state.list_comments())
    assert "Tourist" in tour.guestbook_view.toPlainText()
    tour.close()

    dlg.close()
    del app


def _write_ui_overlay_proof(dlg) -> None:
    """Grab map HUD proving status/tile/log/guestbook/tools live on the map."""
    from PySide6.QtWidgets import QApplication

    out_dir = Path(__file__).resolve().parents[1] / "hakoniwa" / "testdata"
    out_dir.mkdir(parents=True, exist_ok=True)

    dlg.resize(960, 780)
    dlg.show()
    dlg.hud.tools_btn.setChecked(False)
    dlg._refresh_ui()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    closed = dlg.hud.grab()
    closed_path = out_dir / "ui_overlay_map_hud.png"
    assert closed.save(str(closed_path), "PNG"), closed_path
    print(f"ui overlay proof: wrote {closed_path}")

    dlg.hud.tools_btn.setChecked(True)
    if app is not None:
        app.processEvents()
    open_pix = dlg.hud.grab()
    open_path = out_dir / "ui_overlay_tools_open.png"
    assert open_pix.save(str(open_path), "PNG"), open_path
    print(f"ui overlay proof: wrote {open_path}")
    dlg.hud.tools_btn.setChecked(False)


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
        assert island["version"] == SAVE_VERSION
        assert island.get("monsters") == []

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

        # Monster missile / wait endpoints (seed via PUT).
        snap = client.get("/api/v1/island").json()
        land_ij = next(
            (
                (ri, rj)
                for ri, row in enumerate(snap["cells"])
                for rj, c in enumerate(row)
                if c["terrain"] in ("dirt", "grass", "forest")
            ),
            None,
        )
        assert land_ij is not None
        mi, mj = land_ij
        snap["monsters"] = [{"kind": "inora", "i": mi, "j": mj, "hp": 1}]
        put = client.put("/api/v1/island", json=snap)
        assert put.status_code == 200
        assert len(put.json().get("monsters") or []) == 1
        waited = client.post("/api/v1/island/wait").json()
        assert waited["ok"] is True
        assert len(waited["island"]["monsters"]) == 1
        shot = client.post(
            "/api/v1/island/missile", json={"i": mi, "j": mj}
        ).json()
        assert shot["ok"] is True
        assert shot["island"]["monsters"] == []

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


def test_terrain_top_assets():
    """Bundled dirt／grass／sea flat tops must exist (no skirt assets required)."""
    from hakoniwa.tiles import (
        OCEAN_BACKGROUND,
        TERRAIN_TILE_FILES,
        TILES_DIR,
        ATLAS,
    )

    for key in ("dirt", "grass", "sea"):
        fname = TERRAIN_TILE_FILES[key]
        path = TILES_DIR / fname
        assert path.is_file(), f"missing terrain top {path}"
        assert path.stat().st_size > 1000, path
    # Ocean backdrop is preferred but optional (dark teal fallback).
    if OCEAN_BACKGROUND.is_file():
        assert OCEAN_BACKGROUND.stat().st_size > 1000

    # Qt load path (offscreen) — primary tops must decode.
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover
        print(f"terrain assets: skip Qt load ({exc})")
        return
    _app = QApplication.instance() or QApplication([])
    assert ATLAS.has_primary_tops(), "dirt/grass/sea tops failed to load"
    for key in ("dirt", "grass", "sea"):
        pix = ATLAS.pixmap_for(key)
        assert pix is not None and not pix.isNull()
        assert pix.width() >= 64 and pix.height() >= 64
    print("terrain tops: dirt/grass/sea OK")


def test_oblique_preview_png_if_possible():
    """Write a small foreshortening proof PNG when Qt offscreen is available."""
    import json
    import os

    out_dir = Path(__file__).resolve().parents[1] / "hakoniwa" / "testdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    params_path = out_dir / "oblique_projection.json"
    params_path.write_text(
        json.dumps(oblique_projection_params(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Always emit a pure-Python comparison strip (no Qt required).
    _write_foreshorten_proof_png(out_dir / "oblique_foreshorten_proof.png")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from hakoniwa.view import HakoniwaMapWidget
    except Exception as exc:  # pragma: no cover - optional GUI
        print(f"oblique preview: skip map grab ({exc})")
        return

    app = QApplication.instance() or QApplication([])
    state = IslandState.new_game()
    widget = HakoniwaMapWidget(state)
    widget.resize(640, 480)
    widget.show()
    app.processEvents()
    pix = widget.grab()
    map_path = out_dir / "oblique_map_offscreen.png"
    assert pix.save(str(map_path), "PNG"), map_path
    # Textured grab should not be a flat single-color field.
    img = pix.toImage()
    samples = {
        img.pixel(x, y)
        for x in (80, 160, 320, 480, 560)
        for y in (120, 240, 360)
    }
    assert len(samples) >= 8, f"map grab looks untextured ({len(samples)} colors)"
    print(f"oblique preview: wrote {map_path}")


def _write_foreshorten_proof_png(path: Path) -> None:
    """PNG proving foreshortened diamond ≠ pure rotate (equal W/H).

    Left: wrong orthographic rotate (H/W=1). Right: 箱庭斜視 (H/W=sin45).
    Minimal uncompressed RGB PNG, no third-party deps.
    """
    import struct
    import zlib

    width, height = 320, 160
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            # Split canvas: left = wrong, right = correct.
            if x < width // 2:
                cx, cy = 80.0, 80.0
                hw, hh = 48.0, 48.0  # flat rotate (bad)
                bg = (40, 48, 56)
                fill = (70, 130, 200)
            else:
                cx, cy = 240.0, 80.0
                hw, hh = 48.0, 48.0 * OBLIQUE_Y_SCALE  # foreshortened (good)
                bg = (28, 48, 72)
                fill = (64, 160, 210)
            # Point-in-diamond via Manhattan in scaled axes.
            dx = abs(x - cx) / hw
            dy = abs(y - cy) / hh
            if dx + dy <= 1.0:
                row.extend(fill)
            else:
                row.extend(bg)
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(
        b"IEND", b""
    )
    path.write_bytes(png)
    print(f"oblique proof: wrote {path} (params y_scale={OBLIQUE_Y_SCALE:.6f})")


def main():
    test_grid_geometry()
    test_oblique_foreshortening_invariant()
    test_terrain_top_assets()
    test_catalog_costs()
    test_new_island_and_loop()
    test_guestbook_local()
    test_settlements_and_disasters()
    test_monster_events()
    test_defense_and_missile_base()
    test_local_demos()
    test_save_load_roundtrip()
    test_remote_url_normalize()
    test_tool_enabled_rules()
    test_dialog_import_offscreen()
    test_oblique_preview_png_if_possible()
    test_server_api_if_available()
    print("hakoniwa smoke_test: OK")


if __name__ == "__main__":
    main()
