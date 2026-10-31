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
    ATTRACT_POP_BONUS,
    BANK_TRANSFER_LOT,
    BREAKWATER_TSUNAMI_FACTOR,
    ATTRACT_AIRPORT_EXTRA,
    CASINO_TOURISM_BASE,
    CASINO_TOURISM_PER_100_POP,
    COST_AFFOREST,
    COST_AIRPORT,
    COST_ATTRACT,
    COST_BANK,
    COST_BREAKWATER,
    COST_CASINO,
    COST_DEFENSE,
    COST_EXCAVATE,
    COST_FACTORY,
    COST_FARM,
    COST_HARBOR,
    COST_HARVEST,
    COST_HOTEL,
    COST_LANDFILL,
    COST_LEVEL,
    COST_MISSILE,
    COST_MISSILE_BASE,
    COST_MISSILE_CHEAP,
    COST_MONUMENT,
    COST_PARK,
    COST_QUARRY,
    COST_RAISE,
    COST_RESEARCH_LAB,
    COST_ROCKET_BASE,
    COST_ROCKET_LAUNCH,
    COST_SHIPYARD,
    COST_SHRINE,
    COST_SUPERMARKET,
    COST_UNIVERSITY,
    HOTEL_TOURISM_BASE,
    HOTEL_TOURISM_PER_100_POP,
    DEFENSE_RADIUS,
    DEFENSE_SPAWN_FACTOR,
    DEFENSE_STOMP_SAVE_CHANCE,
    FIRE_BASE_CHANCE,
    FOOD_BUY_LOT,
    FOOD_EXPORT_LOT,
    FOOD_PER_FARM,
    FOREST_FIRE_FACTOR,
    FUNDS_PER_FACTORY,
    FUNDS_PER_FOOD_BUY,
    FUNDS_PER_FOOD_LOT,
    FUNDS_PER_OILFIELD,
    FUNDS_PER_QUARRY,
    FUNDS_PER_TIMBER_LOT,
    FUNDS_SOFT_CAP,
    HAPPINESS_POP_PER_MONUMENT,
    HAPPINESS_POP_PER_PARK,
    HAPPINESS_POP_PER_SHRINE,
    LABOR_PER_FACTORY,
    LABOR_PER_FARM,
    LABOR_PER_QUARRY,
    MAX_GUEST_NAME,
    MAX_GUEST_TEXT,
    MONSTER_MIN_POP,
    MONSTER_MIN_TURN,
    MONSTER_REWARD,
    OIL_DEPLETION_CHANCE,
    OIL_DISCOVER_CHANCE,
    PARK_SETTLEMENT_SPAWN_BONUS,
    RESEARCH_LAB_DISASTER_FACTOR,
    SAVE_VERSION,
    SATELLITE_DISASTER_FACTOR,
    SCORE_PER_AIRPORT,
    SCORE_PER_BANK,
    SCORE_PER_BREAKWATER,
    SCORE_PER_CASINO,
    SCORE_PER_HOTEL,
    SCORE_PER_MONUMENT,
    SCORE_PER_OILFIELD,
    SCORE_PER_PARK,
    SCORE_PER_QUARRY,
    SCORE_PER_RESEARCH_LAB,
    SCORE_PER_ROCKET_BASE,
    SCORE_PER_SATELLITE,
    SCORE_PER_SHRINE,
    SCORE_PER_SUPERMARKET,
    SCORE_PER_UNIVERSITY,
    UNIVERSITY_TECH_DISCOUNT,
    TIMBER_LOT,
    TOURISM_FUNDS_BASE,
    TOURISM_FUNDS_PER_100_POP,
    TOWN_TO_CITY_POP,
    TREE_GROWTH_PER_TURN,
    TREE_MAX,
    TREE_MIN,
    TSUNAMI_BASE_CHANCE,
    TSUNAMI_PER_SEA_NEIGHBOR,
    VILLAGE_TO_TOWN_POP,
    VISITOR_TIP_FUNDS,
    Cell,
    IslandState,
    assign_labor,
    compute_island_score,
    food_buy_cost,
    food_export_funds,
    scaled_yield,
    timber_funds,
    tourism_funds,
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

    Correct: screen diamond H/W == OBLIQUE_Y_SCALE == 0.65 (oblique affine).
    Wrong regression: H/W == 1.0 (top-down squares rotated 45° only).
    """
    import math

    params = oblique_projection_params()
    assert params["kind"] == "oblique_affine"
    assert params["forbidden"] == "orthographic_rotate_only"
    assert OBLIQUE_Y_SCALE == 0.65
    assert abs(float(params["y_scale"]) - 0.65) < 1e-12
    assert abs(params["elevation_deg"] - OBLIQUE_ELEVATION_DEG) < 1e-12
    assert abs(OBLIQUE_ELEVATION_DEG - math.degrees(math.asin(0.65))) < 1e-12
    # Hard floor: must not be orthographic (y_scale == 1) or classic 2:1-only.
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
    assert COST_QUARRY == 300
    assert COST_RAISE == 100
    assert COST_EXCAVATE == 200
    assert COST_BREAKWATER == 200
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
    assert COST_HARBOR == 800
    assert COST_SHIPYARD == 500
    assert COST_MONUMENT == 9999
    assert COST_BANK == 500
    assert COST_SUPERMARKET == 300
    assert COST_SHRINE == 800
    assert COST_PARK == 250
    assert COST_ATTRACT == 1000
    assert COST_AIRPORT == 1500
    assert COST_ROCKET_BASE == 2000
    assert COST_ROCKET_LAUNCH == 800
    assert COST_HOTEL == 600
    assert COST_CASINO == 1100
    assert COST_UNIVERSITY == 700
    assert COST_RESEARCH_LAB == 950
    assert SCORE_PER_MONUMENT == 2000
    assert SCORE_PER_QUARRY == 70
    assert SCORE_PER_BREAKWATER == 50
    assert SCORE_PER_OILFIELD == 120
    assert SCORE_PER_BANK == 90
    assert SCORE_PER_SUPERMARKET == 40
    assert SCORE_PER_SHRINE == 800
    assert SCORE_PER_PARK == 150
    assert SCORE_PER_AIRPORT == 500
    assert SCORE_PER_ROCKET_BASE == 400
    assert SCORE_PER_SATELLITE == 300
    assert SCORE_PER_HOTEL == 200
    assert SCORE_PER_CASINO == 320
    assert SCORE_PER_UNIVERSITY == 280
    assert SCORE_PER_RESEARCH_LAB == 380
    assert UNIVERSITY_TECH_DISCOUNT == 200
    assert 0 < RESEARCH_LAB_DISASTER_FACTOR < 1
    assert HAPPINESS_POP_PER_MONUMENT == 5
    assert HAPPINESS_POP_PER_SHRINE == 8
    assert HAPPINESS_POP_PER_PARK == 6
    assert ATTRACT_POP_BONUS == 40
    assert ATTRACT_AIRPORT_EXTRA == 20
    assert TOURISM_FUNDS_BASE == 12
    assert TOURISM_FUNDS_PER_100_POP == 3
    assert HOTEL_TOURISM_BASE == 8
    assert HOTEL_TOURISM_PER_100_POP == 2
    assert CASINO_TOURISM_BASE == 18
    assert CASINO_TOURISM_PER_100_POP == 5
    assert VISITOR_TIP_FUNDS == 20
    assert tourism_funds(0, 500) == 0
    assert tourism_funds(1, 0) == TOURISM_FUNDS_BASE
    assert tourism_funds(1, 180) == TOURISM_FUNDS_BASE + TOURISM_FUNDS_PER_100_POP
    assert tourism_funds(2, 250) == 2 * (TOURISM_FUNDS_BASE + 2 * TOURISM_FUNDS_PER_100_POP)
    assert tourism_funds(0, 180, hotels=1) == HOTEL_TOURISM_BASE + HOTEL_TOURISM_PER_100_POP
    assert tourism_funds(0, 250, casinos=1) == (
        CASINO_TOURISM_BASE + 2 * CASINO_TOURISM_PER_100_POP
    )
    assert tourism_funds(1, 180, hotels=1, casinos=1) == (
        (TOURISM_FUNDS_BASE + TOURISM_FUNDS_PER_100_POP)
        + (HOTEL_TOURISM_BASE + HOTEL_TOURISM_PER_100_POP)
        + (CASINO_TOURISM_BASE + CASINO_TOURISM_PER_100_POP)
    )
    assert 0 < PARK_SETTLEMENT_SPAWN_BONUS < 1
    assert 0 < SATELLITE_DISASTER_FACTOR < 1
    assert FUNDS_SOFT_CAP == 9999
    assert BANK_TRANSFER_LOT == 100
    assert FOOD_EXPORT_LOT == 100
    assert FUNDS_PER_FOOD_LOT == 5
    assert FOOD_BUY_LOT == 100
    assert FUNDS_PER_FOOD_BUY == 8
    assert FUNDS_PER_QUARRY == 8
    assert FUNDS_PER_OILFIELD == 50
    assert SAVE_VERSION == 15
    assert 0 < OIL_DISCOVER_CHANCE <= 1
    assert 0 < OIL_DEPLETION_CHANCE < 1
    assert TSUNAMI_BASE_CHANCE > 0
    assert 0 < BREAKWATER_TSUNAMI_FACTOR < 1
    assert LABOR_PER_FARM == 100
    assert LABOR_PER_FACTORY == 1000
    assert LABOR_PER_QUARRY == 500
    assert food_export_funds(1) == 5
    assert food_export_funds(3) == 15
    assert food_buy_cost(1) == 8
    assert food_buy_cost(2) == 16
    assert DEFENSE_RADIUS == 2
    assert 0 < DEFENSE_SPAWN_FACTOR < 1
    assert 0 < DEFENSE_STOMP_SAVE_CHANCE < 1
    assert SAVE_VERSION >= 9
    # Labor: farms first.
    fl, facl, ql, fs, facs, qs = assign_labor(100, farms=1, factories=1, quarries=1)
    assert (fl, facl, ql) == (100, 0, 0)
    assert (fs, facs, qs) == (100, 1000, 500)
    fl, facl, ql, *_ = assign_labor(1600, farms=1, factories=1, quarries=1)
    assert (fl, facl, ql) == (100, 1000, 500)
    assert scaled_yield(10, 500, 1000) == 5
    assert scaled_yield(10, 0, 1000) == 0


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
    assert any(n.startswith("勞動：") for n in notes)
    # Food rose by farm yield then fell by need; net should reflect production.
    assert farms == 1
    # pop=100 fills 1 farm (100 slots) → full food yield.
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


def test_harbor_shipyard_trade():
    """港灣／造船所須臨海；有其一可貿易輸出糧食→資金。"""
    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    assert land

    # Ensure at least one coastal grass cell.
    coastal = None
    inlandish = None
    for i, j in land:
        c = state.cell(i, j)
        if c.terrain == "dirt":
            assert state.level_land(i, j) == "ok"
        if state._adjacent_to_sea(i, j):
            if coastal is None and state.cell(i, j).building is None:
                coastal = (i, j)
        else:
            if inlandish is None and state.cell(i, j).building is None:
                inlandish = (i, j)
    # Opening map: all 7 land cells border sea on a small island — coastal must exist.
    assert coastal is not None
    ci, cj = coastal

    # Export locked without harbor/shipyard.
    assert state.can_trade_export() is False
    assert state.export_food(1) != "ok"
    ok, reason = tool_enabled(state, "export", None)
    assert ok is False
    assert "港灣" in reason or "造船" in reason

    # Inland (if any) cannot host harbor.
    if inlandish is not None:
        ii, ij = inlandish
        assert state.can_place_building(ii, ij, "harbor") is False
        assert state.place_building(ii, ij, "harbor") != "ok"

    # Harbor on coastal grass.
    state.funds = max(state.funds, COST_HARBOR + COST_SHIPYARD + 50)
    before = state.funds
    assert state.can_place_building(ci, cj, "harbor")
    assert state.place_building(ci, cj, "harbor") == "ok"
    assert state.cell(ci, cj).building == "harbor"
    assert state.funds == before - COST_HARBOR
    assert state.has_harbor()
    assert state.can_trade_export()

    ok, _ = tool_enabled(state, "export", None)
    # Need enough food for one lot.
    state.food = max(state.food, FOOD_EXPORT_LOT)
    ok, _ = tool_enabled(state, "export", None)
    assert ok is True

    food_before = state.food
    funds_before = state.funds
    turn_before = state.turn
    assert state.export_food(1) == "ok"
    assert state.food == food_before - FOOD_EXPORT_LOT
    assert state.funds == funds_before + FUNDS_PER_FOOD_LOT
    assert state.turn == turn_before  # does not advance turn

    # Too many lots → fail.
    state.food = FOOD_EXPORT_LOT - 1
    assert state.export_food(1) != "ok"

    # Shipyard alone also unlocks export (clear harbor, place shipyard elsewhere).
    state.cell(ci, cj).building = None
    assert state.has_harbor() is False
    other = next(
        (
            (i, j)
            for i, j in land
            if (i, j) != (ci, cj)
            and state.cell(i, j).terrain == "grass"
            and state.cell(i, j).building is None
            and state._adjacent_to_sea(i, j)
        ),
        None,
    )
    if other is None:
        # Reuse coastal after clearing.
        other = coastal
        state.cell(*other).building = None
        state.cell(*other).terrain = "grass"
    oi, oj = other
    state.funds = max(state.funds, COST_SHIPYARD)
    assert state.place_building(oi, oj, "shipyard") == "ok"
    assert state.has_shipyard()
    assert state.can_trade_export()
    state.food = FOOD_EXPORT_LOT * 2
    funds_before = state.funds
    assert state.export_food(2) == "ok"
    assert state.funds == funds_before + food_export_funds(2)

    # Toolbar keys present.
    keys = {k for k, *_ in TOOL_SPECS}
    assert "harbor" in keys and "shipyard" in keys and "export" in keys

    # Round-trip save.
    blob = state.to_dict()
    loaded = IslandState.from_dict(blob)
    assert loaded.building_count("shipyard") == 1
    assert loaded.can_trade_export()


def test_monument_and_island_score():
    """紀念碑色塊：國威分數、安穩加成、抗踩踏、鄰格抑火災。"""
    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    assert land
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert grass
    mi, mj = grass[0]

    base_score = state.island_score()
    assert base_score == compute_island_score(
        population=state.population,
        funds=state.funds,
        food=state.food,
        land=state.land_count(),
        monuments=0,
        farms=0,
        factories=0,
        quarries=0,
        mountains=0,
        harbors=0,
        shipyards=0,
        breakwaters=0,
        oilfields=0,
        defenses=0,
        missile_bases=0,
        villages=0,
        towns=0,
        cities=0,
    )
    assert state.happiness_bonus() == 0

    # Too poor → cannot place.
    state.funds = COST_MONUMENT - 1
    assert state.place_building(mi, mj, "monument") != "ok"
    state.funds = COST_MONUMENT + 50
    before = state.funds
    assert state.can_place_building(mi, mj, "monument")
    assert state.place_building(mi, mj, "monument") == "ok"
    assert state.cell(mi, mj).building == "monument"
    assert state.funds == before - COST_MONUMENT
    assert state.monument_count() == 1
    assert state.happiness_bonus() == HAPPINESS_POP_PER_MONUMENT
    scored = state.island_score()
    assert scored >= base_score + SCORE_PER_MONUMENT - 50  # funds spent lowers soft score
    assert scored > base_score

    # Toolbar key present.
    keys = {k for k, *_ in TOOL_SPECS}
    assert "monument" in keys
    ok, _ = tool_enabled(state, "monument", (mi, mj))
    assert ok is False  # occupied

    # Monster stomp cannot destroy monument.
    m = state.spawn_monster(mi, mj)
    assert m is not None
    notes = state._stomp_cell(mi, mj, m)
    assert state.cell(mi, mj).building == "monument"
    assert any("紀念碑" in n and "屹立" in n for n in notes)

    # Neighbor monument mitigates fire like 森; typhoon stays 森-only.
    from hakoniwa.grid import neighbors as hex_neighbors

    neigh = [
        (ni, nj)
        for ni, nj in hex_neighbors(mi, mj, state.size)
        if state.is_land(ni, nj) and state.cell(ni, nj).building is None
    ]
    assert neigh, "need a land neighbor for fire-mitigation check"
    fi, fj = neigh[0]
    state.cell(fi, fj).terrain = "grass"
    state.cell(fi, fj).building = "factory"
    # Ensure no forest neighbors so only the monument counts for fire.
    for ni, nj in hex_neighbors(fi, fj, state.size):
        if state.cell(ni, nj).terrain == "forest":
            state.cell(ni, nj).terrain = "grass"
            state.cell(ni, nj).trees = 0
    assert state._has_forest_neighbor(fi, fj) is True
    assert state._has_forest_for_typhoon(fi, fj) is False

    # Turn log includes 島分數（靜音災害／怪獸，避免噴火偶然清掉紀念碑）.
    import hakoniwa.model as model_mod

    state.food = max(state.food, 500)
    old_fire = model_mod.FIRE_BASE_CHANCE
    old_ty = model_mod.TYPHOON_BASE_CHANCE
    old_qk = model_mod.QUAKE_BASE_CHANCE
    old_vo = model_mod.VOLCANO_BASE_CHANCE
    old_ts = model_mod.TSUNAMI_BASE_CHANCE
    old_mon = model_mod.MONSTER_BASE_CHANCE
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        notes = state.next_turn()
    finally:
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_ty
        model_mod.QUAKE_BASE_CHANCE = old_qk
        model_mod.VOLCANO_BASE_CHANCE = old_vo
        model_mod.TSUNAMI_BASE_CHANCE = old_ts
        model_mod.MONSTER_BASE_CHANCE = old_mon
    assert any("島分數" in n for n in notes)
    assert any("島分數" in line for line in state.log)
    assert state.monument_count() == 1

    # Round-trip.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    loaded = IslandState.from_dict(blob)
    assert loaded.monument_count() == 1
    assert loaded.island_score() == state.island_score()


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
    assert coral.terrain_count("mountain") >= 1
    assert coral.building_count("quarry") == 1
    assert coral.building_count("breakwater") == 1
    assert coral.terrain_count("oilfield") >= 1
    assert coral.building_count("bank") == 1
    assert coral.building_count("supermarket") == 1
    assert coral.building_count("shrine") == 1
    assert coral.airport_count() >= 1
    assert coral.hotel_count() >= 1
    assert coral.casino_count() >= 1
    assert coral.university_count() >= 1
    assert coral.research_lab_count() >= 1
    assert coral.bank_deposit == 150
    row = island_summary(coral)
    assert row["id"] == "demo-coral"
    assert row["land"] == coral.land_count()
    # Round-trip keeps id.
    assert IslandState.from_dict(coral.to_dict()).island_id == "demo-coral"


def test_mountain_quarry_labor():
    """造山→採掘場；勞動優先農場；採掘場產資依就業比例。"""
    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    dirt = next(
        ((i, j) for i, j in land if state.cell(i, j).terrain == "dirt"),
        None,
    )
    grass = next(
        (
            (i, j)
            for i, j in land
            if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
        ),
        None,
    )
    assert dirt is not None and grass is not None
    di, dj = dirt
    gi, gj = grass

    # Quarry cannot sit on 平地.
    assert state.can_place_building(gi, gj, "quarry") is False
    assert state.place_building(gi, gj, "quarry") != "ok"
    ok, reason = tool_enabled(state, "quarry", (gi, gj))
    assert ok is False
    assert "山" in reason

    # Raise mountain on dirt.
    funds_before = state.funds
    assert state.can_raise_mountain(di, dj)
    assert state.raise_mountain(di, dj) == "ok"
    assert state.cell(di, dj).terrain == "mountain"
    assert state.funds == funds_before - COST_RAISE
    ok, _ = tool_enabled(state, "raise", (di, dj))
    assert ok is False  # already mountain

    # Place quarry on mountain.
    state.funds = max(state.funds, COST_QUARRY + COST_FARM + 50)
    before = state.funds
    assert state.can_place_building(di, dj, "quarry")
    assert state.place_building(di, dj, "quarry") == "ok"
    assert state.cell(di, dj).building == "quarry"
    assert state.funds == before - COST_QUARRY
    assert state.island_score() >= SCORE_PER_QUARRY

    keys = {k for k, *_ in TOOL_SPECS}
    assert "raise" in keys and "quarry" in keys

    # Silence disasters / growth noise for labor asserts.
    old = (
        model_mod.FIRE_BASE_CHANCE,
        model_mod.TYPHOON_BASE_CHANCE,
        model_mod.QUAKE_BASE_CHANCE,
        model_mod.VOLCANO_BASE_CHANCE,
        model_mod.TSUNAMI_BASE_CHANCE,
        model_mod.SETTLEMENT_SPAWN_CHANCE,
        model_mod.MONSTER_BASE_CHANCE,
    )
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.SETTLEMENT_SPAWN_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        # Farm takes all pop=100 → quarry idle this turn.
        assert state.place_building(gi, gj, "farm") == "ok"
        state.population = 100
        food_before = state.food
        funds_before = state.funds
        notes = state.next_turn()
        assert any("勞動：" in n and "採掘場 0/" in n for n in notes)
        assert state.food == food_before + FOOD_PER_FARM - 20  # pop < 500 → min need
        assert state.funds == funds_before  # quarry/factory unstaffed

        # With spare labor after farm, quarry produces full funds.
        state.population = LABOR_PER_FARM + LABOR_PER_QUARRY  # 600
        funds_before = state.funds
        notes = state.next_turn()
        assert any("採掘場 500/500" in n for n in notes)
        assert state.funds == funds_before + FUNDS_PER_QUARRY
    finally:
        (
            model_mod.FIRE_BASE_CHANCE,
            model_mod.TYPHOON_BASE_CHANCE,
            model_mod.QUAKE_BASE_CHANCE,
            model_mod.VOLCANO_BASE_CHANCE,
            model_mod.TSUNAMI_BASE_CHANCE,
            model_mod.SETTLEMENT_SPAWN_CHANCE,
            model_mod.MONSTER_BASE_CHANCE,
        ) = old

    # 整地 mountain → dirt (掘削-lite).
    assert state.level_land(di, dj) == "ok"
    assert state.cell(di, dj).terrain == "dirt"
    assert state.cell(di, dj).building is None

    # Save round-trip keeps mountain terrain.
    state2 = IslandState.new_game()
    empty = next(
        (
            (i, j)
            for i in range(20)
            for j in range(20)
            if state2.can_raise_mountain(i, j)
        ),
        None,
    )
    assert empty is not None
    assert state2.raise_mountain(*empty) == "ok"
    loaded = IslandState.from_dict(state2.to_dict())
    assert loaded.cell(*empty).terrain == "mountain"
    assert loaded.to_dict()["version"] == SAVE_VERSION


def test_breakwater_oilfield_tsunami():
    """防波堤臨海；掘削探油→油田產資；海嘯傷臨海設施、防波堤減災。"""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"

    # Coastal grass for breakwater.
    coastal = next(
        (
            (i, j)
            for i, j in land
            if state.cell(i, j).terrain == "grass"
            and state.cell(i, j).building is None
            and state._adjacent_to_sea(i, j)
        ),
        None,
    )
    assert coastal is not None
    bi, bj = coastal
    assert state.can_place_building(bi, bj, "breakwater")
    ok, _ = tool_enabled(state, "breakwater", (bi, bj))
    assert ok is True
    funds_before = state.funds
    assert state.place_building(bi, bj, "breakwater") == "ok"
    assert state.cell(bi, bj).building == "breakwater"
    assert state.funds == funds_before - COST_BREAKWATER
    assert state.island_score() >= SCORE_PER_BREAKWATER

    # Inland grass cannot place breakwater.
    inland = next(
        (
            (i, j)
            for i, j in land
            if state.cell(i, j).terrain == "grass"
            and state.cell(i, j).building is None
            and not state._adjacent_to_sea(i, j)
        ),
        None,
    )
    if inland is not None:
        assert state.can_place_building(*inland, "breakwater") is False
        ok, reason = tool_enabled(state, "breakwater", inland)
        assert ok is False
        assert "臨海" in reason

    keys = {k for k, *_ in TOOL_SPECS}
    assert "excavate" in keys and "breakwater" in keys

    # Excavate sea → oilfield (force discover).
    sea = next(
        (
            (i, j)
            for i in range(20)
            for j in range(20)
            if state.can_excavate(i, j) and state.cell(i, j).terrain == "sea"
        ),
        None,
    )
    assert sea is not None
    si, sj = sea
    ok, _ = tool_enabled(state, "excavate", (si, sj))
    assert ok is True
    funds_before = state.funds
    old_discover = model_mod.OIL_DISCOVER_CHANCE
    model_mod.OIL_DISCOVER_CHANCE = 1.0
    try:
        assert state.excavate(si, sj) == "ok"
    finally:
        model_mod.OIL_DISCOVER_CHANCE = old_discover
    assert state.cell(si, sj).terrain == "oilfield"
    assert state.funds == funds_before - COST_EXCAVATE
    assert state.terrain_count("oilfield") >= 1
    assert state.island_score() >= SCORE_PER_OILFIELD

    # Oilfield passive income; silence disasters / depletion / monsters.
    old = (
        model_mod.FIRE_BASE_CHANCE,
        model_mod.TYPHOON_BASE_CHANCE,
        model_mod.QUAKE_BASE_CHANCE,
        model_mod.VOLCANO_BASE_CHANCE,
        model_mod.TSUNAMI_BASE_CHANCE,
        model_mod.OIL_DEPLETION_CHANCE,
        model_mod.SETTLEMENT_SPAWN_CHANCE,
        model_mod.MONSTER_BASE_CHANCE,
    )
    (
        model_mod.FIRE_BASE_CHANCE,
        model_mod.TYPHOON_BASE_CHANCE,
        model_mod.QUAKE_BASE_CHANCE,
        model_mod.VOLCANO_BASE_CHANCE,
        model_mod.TSUNAMI_BASE_CHANCE,
        model_mod.OIL_DEPLETION_CHANCE,
        model_mod.SETTLEMENT_SPAWN_CHANCE,
        model_mod.MONSTER_BASE_CHANCE,
    ) = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    try:
        oils = state.terrain_count("oilfield")
        funds_before = state.funds
        notes = state.next_turn()
        assert any(f"海底油田×{oils}" in n for n in notes)
        assert state.funds == funds_before + oils * FUNDS_PER_OILFIELD
    finally:
        (
            model_mod.FIRE_BASE_CHANCE,
            model_mod.TYPHOON_BASE_CHANCE,
            model_mod.QUAKE_BASE_CHANCE,
            model_mod.VOLCANO_BASE_CHANCE,
            model_mod.TSUNAMI_BASE_CHANCE,
            model_mod.OIL_DEPLETION_CHANCE,
            model_mod.SETTLEMENT_SPAWN_CHANCE,
            model_mod.MONSTER_BASE_CHANCE,
        ) = old

    # Forced depletion → sea.
    model_mod.OIL_DEPLETION_CHANCE = 1.0
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.SETTLEMENT_SPAWN_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        notes = state.next_turn()
        assert any("油田枯竭" in n for n in notes)
        assert state.cell(si, sj).terrain == "sea"
        assert state.terrain_count("oilfield") == 0
    finally:
        model_mod.OIL_DEPLETION_CHANCE = old[5]
        (
            model_mod.FIRE_BASE_CHANCE,
            model_mod.TYPHOON_BASE_CHANCE,
            model_mod.QUAKE_BASE_CHANCE,
            model_mod.VOLCANO_BASE_CHANCE,
            model_mod.TSUNAMI_BASE_CHANCE,
            model_mod.SETTLEMENT_SPAWN_CHANCE,
            model_mod.MONSTER_BASE_CHANCE,
        ) = (old[0], old[1], old[2], old[3], old[4], old[6], old[7])

    # Tsunami: unprotected coastal farm → dirt; breakwater neighbor mitigates.
    # Place a farm on another coastal grass cell without breakwater neighbor if possible.
    farm_spot = next(
        (
            (i, j)
            for i, j in land
            if state.cell(i, j).terrain == "grass"
            and state.cell(i, j).building is None
            and state._sea_neighbor_count(i, j) > 0
            and not state._has_breakwater_neighbor(i, j)
        ),
        None,
    )
    if farm_spot is None:
        # Fall back: any coastal empty grass.
        farm_spot = next(
            (
                (i, j)
                for i, j in land
                if state.cell(i, j).terrain == "grass"
                and state.cell(i, j).building is None
                and state._sea_neighbor_count(i, j) > 0
            ),
            None,
        )
    assert farm_spot is not None
    fi, fj = farm_spot
    assert state.place_building(fi, fj, "farm") == "ok"

    # Force tsunami hit without breakwater mitigation for this cell.
    # Temporarily clear nearby breakwaters' mitigation by testing a cell
    # that we know has sea neighbors; bump chance high.
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.SETTLEMENT_SPAWN_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    model_mod.OIL_DEPLETION_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 1.0
    model_mod.TSUNAMI_PER_SEA_NEIGHBOR = 0.0
    # If farm is protected by our breakwater, remove breakwater first for the hit assert.
    if state._has_breakwater_neighbor(fi, fj):
        state.cell(bi, bj).building = None
    random.seed(0)
    try:
        notes = state._apply_disasters()
        assert any("海嘯" in n for n in notes)
        assert state.cell(fi, fj).building is None
        assert state.cell(fi, fj).terrain == "dirt"
    finally:
        model_mod.TSUNAMI_BASE_CHANCE = TSUNAMI_BASE_CHANCE
        model_mod.TSUNAMI_PER_SEA_NEIGHBOR = TSUNAMI_PER_SEA_NEIGHBOR
        model_mod.OIL_DEPLETION_CHANCE = OIL_DEPLETION_CHANCE

    # Breakwater itself survives tsunami.
    state.cell(bi, bj).building = "breakwater"
    state.cell(bi, bj).terrain = "grass"
    model_mod.TSUNAMI_BASE_CHANCE = 1.0
    model_mod.TSUNAMI_PER_SEA_NEIGHBOR = 1.0
    try:
        state._apply_disasters()
        assert state.cell(bi, bj).building == "breakwater"
    finally:
        model_mod.TSUNAMI_BASE_CHANCE = TSUNAMI_BASE_CHANCE
        model_mod.TSUNAMI_PER_SEA_NEIGHBOR = TSUNAMI_PER_SEA_NEIGHBOR
        model_mod.FIRE_BASE_CHANCE = FIRE_BASE_CHANCE
        model_mod.TYPHOON_BASE_CHANCE = 0.06
        model_mod.QUAKE_BASE_CHANCE = 0.05
        model_mod.VOLCANO_BASE_CHANCE = 0.04
        model_mod.SETTLEMENT_SPAWN_CHANCE = 0.20
        model_mod.MONSTER_BASE_CHANCE = 0.12
        model_mod.OIL_DEPLETION_CHANCE = OIL_DEPLETION_CHANCE

    # Dig land → shallow, then shallow → sea.
    dig = next(
        (
            (i, j)
            for i, j in land
            if state.cell(i, j).terrain == "grass"
            and state.cell(i, j).building is None
        ),
        None,
    )
    assert dig is not None
    assert state.excavate(*dig) == "ok"
    assert state.cell(*dig).terrain == "shallow"
    assert state.excavate(*dig) == "ok"
    assert state.cell(*dig).terrain == "sea"

    # Save round-trip keeps oilfield + breakwater.
    state3 = IslandState.new_game()
    for i, j in [(x, y) for x in range(20) for y in range(20) if state3.is_land(x, y)]:
        if state3.cell(i, j).terrain == "dirt":
            state3.level_land(i, j)
    coast3 = next(
        (
            (i, j)
            for i in range(20)
            for j in range(20)
            if state3.is_land(i, j)
            and state3.cell(i, j).terrain == "grass"
            and state3._adjacent_to_sea(i, j)
        ),
        None,
    )
    assert coast3 is not None
    state3.funds = 5000
    assert state3.place_building(*coast3, "breakwater") == "ok"
    sea3 = next(
        (
            (i, j)
            for i in range(20)
            for j in range(20)
            if state3.cell(i, j).terrain == "sea"
        ),
        None,
    )
    assert sea3 is not None
    state3.cells[sea3[0]][sea3[1]] = Cell("oilfield")
    loaded3 = IslandState.from_dict(state3.to_dict())
    assert loaded3.cell(*coast3).building == "breakwater"
    assert loaded3.cell(*sea3).terrain == "oilfield"
    assert loaded3.to_dict()["version"] == SAVE_VERSION


def test_bank_supermarket_shrine():
    """銀行緩衝／超市買糧／神社分數色塊（變體民生設施）."""
    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 3
    bi, bj = grass[0]
    si, sj = grass[1]
    hi, hj = grass[2]

    # Soft cap without bank: excess discarded.
    state.funds = FUNDS_SOFT_CAP + 250
    notes = state._apply_funds_cap()
    assert state.funds == FUNDS_SOFT_CAP
    assert state.bank_deposit == 0
    assert any("捨棄" in n for n in notes)

    # Place bank / supermarket / shrine.
    state.funds = COST_BANK + COST_SUPERMARKET + COST_SHRINE + 500
    before = state.funds
    assert state.place_building(bi, bj, "bank") == "ok"
    assert state.cell(bi, bj).building == "bank"
    assert state.place_building(si, sj, "supermarket") == "ok"
    assert state.cell(si, sj).building == "supermarket"
    assert state.place_building(hi, hj, "shrine") == "ok"
    assert state.cell(hi, hj).building == "shrine"
    assert state.funds == before - COST_BANK - COST_SUPERMARKET - COST_SHRINE
    assert state.has_bank() and state.has_supermarket()
    assert state.shrine_count() == 1
    assert state.happiness_bonus() == HAPPINESS_POP_PER_SHRINE
    assert state.island_score() >= SCORE_PER_BANK + SCORE_PER_SUPERMARKET + SCORE_PER_SHRINE

    # Soft cap with bank: excess → deposit.
    state.funds = FUNDS_SOFT_CAP + 180
    state.bank_deposit = 0
    notes = state._apply_funds_cap()
    assert state.funds == FUNDS_SOFT_CAP
    assert state.bank_deposit == 180
    assert any("銀行緩衝" in n for n in notes)

    # Manual deposit / withdraw.
    state.funds = BANK_TRANSFER_LOT + 40
    dep_before = state.bank_deposit
    assert state.deposit_funds() == "ok"
    assert state.funds == 40
    assert state.bank_deposit == dep_before + BANK_TRANSFER_LOT
    assert state.withdraw_funds() == "ok"
    assert state.funds == 40 + BANK_TRANSFER_LOT
    assert state.bank_deposit == dep_before

    # Supermarket buy food.
    state.food = 50
    state.funds = max(state.funds, FUNDS_PER_FOOD_BUY + 20)
    funds_before = state.funds
    food_before = state.food
    assert state.can_buy_food()
    assert state.buy_food(1) == "ok"
    assert state.food == food_before + FOOD_BUY_LOT
    assert state.funds == funds_before - FUNDS_PER_FOOD_BUY
    # Without supermarket → locked.
    state.cell(si, sj).building = None
    assert state.can_buy_food() is False
    assert state.buy_food(1) != "ok"
    state.cell(si, sj).building = "supermarket"

    # Toolbar keys.
    keys = {k for k, *_ in TOOL_SPECS}
    assert "bank" in keys and "supermarket" in keys and "shrine" in keys
    assert "deposit" in keys and "withdraw" in keys and "buy_food" in keys
    ok, _ = tool_enabled(state, "deposit", None)
    assert ok is True  # has bank + enough liquid after withdraw above
    # Ensure enough liquid for deposit tool.
    state.funds = max(state.funds, BANK_TRANSFER_LOT)
    ok, _ = tool_enabled(state, "deposit", None)
    assert ok is True
    state.bank_deposit = max(state.bank_deposit, BANK_TRANSFER_LOT)
    ok, _ = tool_enabled(state, "withdraw", None)
    assert ok is True
    state.funds = max(state.funds, FUNDS_PER_FOOD_BUY)
    ok, _ = tool_enabled(state, "buy_food", None)
    assert ok is True
    ok, _ = tool_enabled(state, "bank", (bi, bj))
    assert ok is False  # occupied

    # next_turn applies soft cap via bank after oil/income.
    state.funds = FUNDS_SOFT_CAP + 50
    state.bank_deposit = 10
    state.food = max(state.food, 500)
    notes = state.next_turn()
    assert state.funds <= FUNDS_SOFT_CAP
    assert state.bank_deposit >= 10
    assert any("島分數" in n for n in notes)
    assert any("神社" in n for n in notes) or state.shrine_count() == 1

    # Save round-trip.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    assert "bank_deposit" in blob
    loaded = IslandState.from_dict(blob)
    assert loaded.building_count("bank") == 1
    assert loaded.building_count("supermarket") == 1
    assert loaded.shrine_count() == 1
    assert loaded.bank_deposit == state.bank_deposit
    assert loaded.island_score() == state.island_score()


def test_park_and_attract():
    """公園色塊（安穩／生村）＋誘致活動（定本 1000；下回合人口加成）."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 2
    pi, pj = grass[0]

    # Place park.
    state.funds = max(state.funds, COST_PARK + COST_ATTRACT + 50)
    before = state.funds
    assert state.place_building(pi, pj, "park") == "ok"
    assert state.cell(pi, pj).building == "park"
    assert state.funds == before - COST_PARK
    assert state.park_count() == 1
    assert state.happiness_bonus() == HAPPINESS_POP_PER_PARK
    assert state.island_score() >= SCORE_PER_PARK

    # Park neighbors count as settlement magnets.
    neigh = [
        (ni, nj)
        for ni, nj in neighbors(pi, pj, state.size)
        if state.cell(ni, nj).terrain == "grass" and state.cell(ni, nj).building is None
    ]
    assert neigh
    si, sj = neigh[0]
    assert state._near_farm_or_settlement(si, sj)
    assert state._near_park(si, sj)

    # Forced spawn near park (chance 1.0).
    old_chance = model_mod.SETTLEMENT_SPAWN_CHANCE
    model_mod.SETTLEMENT_SPAWN_CHANCE = 1.0
    try:
        notes = state._evolve_settlements()
    finally:
        model_mod.SETTLEMENT_SPAWN_CHANCE = old_chance
    assert state.cell(si, sj).terrain == "village" or any("村落" in n for n in notes)

    # Attract: too poor / then success / double-book blocked.
    state.funds = COST_ATTRACT - 1
    assert state.attract_population() != "ok"
    state.funds = COST_ATTRACT + 20
    funds_before = state.funds
    pop_before = state.population
    assert state.attract_population() == "ok"
    assert state.funds == funds_before - COST_ATTRACT
    assert state.attract_pending is True
    assert state.attract_population() != "ok"  # already pending

    keys = {k for k, *_ in TOOL_SPECS}
    assert "park" in keys and "attract" in keys
    ok, _ = tool_enabled(state, "attract", None)
    assert ok is False  # pending
    ok, _ = tool_enabled(state, "park", (pi, pj))
    assert ok is False  # occupied

    # next_turn consumes attract and grows population when fed.
    state.food = max(state.food, 500)
    random.seed(0)
    notes = state.next_turn()
    assert state.attract_pending is False
    assert any("誘致" in n for n in notes)
    assert state.population >= pop_before + ATTRACT_POP_BONUS
    assert any("公園" in n for n in notes) or state.park_count() == 1

    # Save round-trip (attract_pending false after turn).
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    assert "attract_pending" in blob
    loaded = IslandState.from_dict(blob)
    assert loaded.park_count() == 1
    assert loaded.attract_pending is False
    assert loaded.happiness_bonus() == HAPPINESS_POP_PER_PARK

    # Pending flag survives save before turn.
    state2 = IslandState.new_game()
    state2.funds = COST_ATTRACT + 10
    assert state2.attract_population() == "ok"
    loaded2 = IslandState.from_dict(state2.to_dict())
    assert loaded2.attract_pending is True

    # Demo coral seeds a park.
    coral = make_demo_coral()
    assert coral.park_count() >= 1


def test_airport_and_tourism_buffs():
    """空港色塊（分數／觀光收入）＋訪客留言小費＋誘致 inbound 加成."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 1
    ai, aj = grass[0]

    # Too poor → cannot place.
    state.funds = COST_AIRPORT - 1
    assert state.place_building(ai, aj, "airport") != "ok"
    state.funds = COST_AIRPORT + 80
    before = state.funds
    assert state.can_place_building(ai, aj, "airport")
    assert state.place_building(ai, aj, "airport") == "ok"
    assert state.cell(ai, aj).building == "airport"
    assert state.funds == before - COST_AIRPORT
    assert state.airport_count() == 1
    assert state.has_airport()
    assert state.island_score() >= SCORE_PER_AIRPORT

    keys = {k for k, *_ in TOOL_SPECS}
    assert "airport" in keys
    ok, _ = tool_enabled(state, "airport", (ai, aj))
    assert ok is False  # occupied

    # Save round-trip before disaster-prone turns.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    loaded = IslandState.from_dict(blob)
    assert loaded.airport_count() == 1
    assert loaded.cell(ai, aj).building == "airport"
    assert loaded.island_score() == state.island_score()

    # Guestbook tip only with airport.
    funds_pre = state.funds
    assert state.add_comment("Tourist", "飛來觀光") == "ok"
    assert state.funds == funds_pre + VISITOR_TIP_FUNDS
    assert any("小費" in line for line in state.log)

    # No tip without airport.
    bare = IslandState.new_game()
    bare_funds = bare.funds
    assert bare.add_comment("Walk-in", "無空港") == "ok"
    assert bare.funds == bare_funds

    # Mute disasters／monsters so airport survives income／誘致 checks.
    old_fire = model_mod.FIRE_BASE_CHANCE
    old_ty = model_mod.TYPHOON_BASE_CHANCE
    old_qk = model_mod.QUAKE_BASE_CHANCE
    old_vo = model_mod.VOLCANO_BASE_CHANCE
    old_ts = model_mod.TSUNAMI_BASE_CHANCE
    old_mon = model_mod.MONSTER_BASE_CHANCE
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        # Per-turn tourism income (no farms／油田 on this stub → exact tour gain).
        state.food = max(state.food, 500)
        state.population = 180
        expected_tour = tourism_funds(1, 180)
        assert expected_tour == TOURISM_FUNDS_BASE + TOURISM_FUNDS_PER_100_POP
        funds_before_turn = state.funds
        random.seed(1)
        notes = state.next_turn()
        assert any("觀光收入" in n for n in notes)
        assert state.airport_count() == 1
        assert state.funds == funds_before_turn + expected_tour

        # Attract + airport inbound extra.
        state.funds = COST_ATTRACT + 30
        pop_before = state.population
        assert state.attract_population() == "ok"
        state.food = max(state.food, 500)
        random.seed(2)
        notes2 = state.next_turn()
        assert state.attract_pending is False
        assert any("誘致" in n for n in notes2)
        assert state.population >= pop_before + ATTRACT_POP_BONUS + ATTRACT_AIRPORT_EXTRA
        assert state.airport_count() == 1
    finally:
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_ty
        model_mod.QUAKE_BASE_CHANCE = old_qk
        model_mod.VOLCANO_BASE_CHANCE = old_vo
        model_mod.TSUNAMI_BASE_CHANCE = old_ts
        model_mod.MONSTER_BASE_CHANCE = old_mon

    # Demo coral seeds an airport.
    coral = make_demo_coral()
    assert coral.airport_count() >= 1


def test_rocket_base_and_launch():
    """ロケット基地色塊＋觀測衛星發射（減震／海嘯／噴火；SAVE round-trip）."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 1
    ri, rj = grass[0]

    # Launch without base → fail.
    assert state.launch_rocket() != "ok"
    ok, reason = tool_enabled(state, "rocket_launch", None)
    assert ok is False
    assert "ロケット" in reason or "基地" in reason

    # Too poor → cannot place base.
    state.funds = COST_ROCKET_BASE - 1
    assert state.place_building(ri, rj, "rocket_base") != "ok"
    state.funds = COST_ROCKET_BASE + COST_ROCKET_LAUNCH + 50
    before = state.funds
    assert state.can_place_building(ri, rj, "rocket_base")
    assert state.place_building(ri, rj, "rocket_base") == "ok"
    assert state.cell(ri, rj).building == "rocket_base"
    assert state.funds == before - COST_ROCKET_BASE
    assert state.rocket_base_count() == 1
    assert state.has_rocket_base()
    assert state.island_score() >= SCORE_PER_ROCKET_BASE

    keys = {k for k, *_ in TOOL_SPECS}
    assert "rocket_base" in keys and "rocket_launch" in keys
    ok, _ = tool_enabled(state, "rocket_base", (ri, rj))
    assert ok is False  # occupied

    # Launch success → satellite_active.
    funds_pre = state.funds
    ok, _ = tool_enabled(state, "rocket_launch", None)
    assert ok is True
    assert state.launch_rocket() == "ok"
    assert state.funds == funds_pre - COST_ROCKET_LAUNCH
    assert state.has_satellite()
    assert state.satellite_active is True
    assert state.island_score() >= SCORE_PER_ROCKET_BASE + SCORE_PER_SATELLITE
    assert any("衛星" in line for line in state.log)

    # Second launch blocked.
    assert state.launch_rocket() != "ok"
    ok, reason = tool_enabled(state, "rocket_launch", None)
    assert ok is False
    assert "在軌" in reason or "衛星" in reason

    # Save round-trip preserves satellite + base.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    assert blob.get("satellite_active") is True
    loaded = IslandState.from_dict(blob)
    assert loaded.rocket_base_count() == 1
    assert loaded.cell(ri, rj).building == "rocket_base"
    assert loaded.has_satellite()
    assert loaded.island_score() == state.island_score()

    # Satellite disaster factor helper + turn note when disasters run.
    assert state._satellite_disaster_factor() == SATELLITE_DISASTER_FACTOR
    bare = IslandState.new_game()
    assert bare._satellite_disaster_factor() == 1.0

    old_fire = model_mod.FIRE_BASE_CHANCE
    old_ty = model_mod.TYPHOON_BASE_CHANCE
    old_qk = model_mod.QUAKE_BASE_CHANCE
    old_vo = model_mod.VOLCANO_BASE_CHANCE
    old_ts = model_mod.TSUNAMI_BASE_CHANCE
    old_mon = model_mod.MONSTER_BASE_CHANCE
    # Keep quake path live so satellite note is emitted; silence wipe risk.
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        # With all base chances 0, factor still applied but no events —
        # force a non-zero quake chance only to surface the 減災 note.
        model_mod.QUAKE_BASE_CHANCE = 0.01
        state.food = max(state.food, 500)
        random.seed(42)
        notes = state.next_turn()
        assert any("減災" in n for n in notes), notes
        assert state.rocket_base_count() == 1
        assert state.has_satellite()
    finally:
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_ty
        model_mod.QUAKE_BASE_CHANCE = old_qk
        model_mod.VOLCANO_BASE_CHANCE = old_vo
        model_mod.TSUNAMI_BASE_CHANCE = old_ts
        model_mod.MONSTER_BASE_CHANCE = old_mon

    coral = make_demo_coral()
    assert coral.rocket_base_count() >= 1


def test_hotel_casino_tourism():
    """酒店／賭場色塊：建設費用、島分數、觀光收入、酒店留言小費、SAVE round-trip."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 2
    hi, hj = grass[0]
    ci, cj = grass[1]

    # Too poor → cannot place hotel.
    state.funds = COST_HOTEL - 1
    assert state.place_building(hi, hj, "hotel") != "ok"
    state.funds = COST_HOTEL + COST_CASINO + 80
    before = state.funds
    assert state.can_place_building(hi, hj, "hotel")
    assert state.place_building(hi, hj, "hotel") == "ok"
    assert state.cell(hi, hj).building == "hotel"
    assert state.funds == before - COST_HOTEL
    assert state.hotel_count() == 1
    assert state.has_hotel()
    assert state.island_score() >= SCORE_PER_HOTEL

    before_c = state.funds
    assert state.can_place_building(ci, cj, "casino")
    assert state.place_building(ci, cj, "casino") == "ok"
    assert state.cell(ci, cj).building == "casino"
    assert state.funds == before_c - COST_CASINO
    assert state.casino_count() == 1
    assert state.has_casino()
    assert state.island_score() >= SCORE_PER_HOTEL + SCORE_PER_CASINO

    keys = {k for k, *_ in TOOL_SPECS}
    assert "hotel" in keys and "casino" in keys
    ok, _ = tool_enabled(state, "hotel", (hi, hj))
    assert ok is False  # occupied
    ok, _ = tool_enabled(state, "casino", (ci, cj))
    assert ok is False

    # Save round-trip.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    loaded = IslandState.from_dict(blob)
    assert loaded.hotel_count() == 1
    assert loaded.casino_count() == 1
    assert loaded.cell(hi, hj).building == "hotel"
    assert loaded.cell(ci, cj).building == "casino"
    assert loaded.island_score() == state.island_score()

    # Guestbook tip with hotel (no airport).
    tip_state = IslandState.new_game()
    for i, j in [
        (ii, jj)
        for ii in range(20)
        for jj in range(20)
        if tip_state.is_land(ii, jj)
    ]:
        if tip_state.cell(i, j).terrain == "dirt":
            tip_state.level_land(i, j)
    tip_grass = [
        (i, j)
        for i in range(20)
        for j in range(20)
        if tip_state.cell(i, j).terrain == "grass"
        and tip_state.cell(i, j).building is None
    ]
    tip_state.funds = COST_HOTEL + 20
    assert tip_state.place_building(tip_grass[0][0], tip_grass[0][1], "hotel") == "ok"
    funds_pre = tip_state.funds
    assert tip_state.add_comment("Lodger", "住宿觀光") == "ok"
    assert tip_state.funds == funds_pre + VISITOR_TIP_FUNDS
    assert any("酒店" in line and "小費" in line for line in tip_state.log)

    # Mute disasters／monsters so hotel／casino survive income check.
    old_fire = model_mod.FIRE_BASE_CHANCE
    old_ty = model_mod.TYPHOON_BASE_CHANCE
    old_qk = model_mod.QUAKE_BASE_CHANCE
    old_vo = model_mod.VOLCANO_BASE_CHANCE
    old_ts = model_mod.TSUNAMI_BASE_CHANCE
    old_mon = model_mod.MONSTER_BASE_CHANCE
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.0
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        state.food = max(state.food, 500)
        state.population = 180
        expected_tour = tourism_funds(0, 180, hotels=1, casinos=1)
        assert expected_tour == (
            (HOTEL_TOURISM_BASE + HOTEL_TOURISM_PER_100_POP)
            + (CASINO_TOURISM_BASE + CASINO_TOURISM_PER_100_POP)
        )
        funds_before_turn = state.funds
        random.seed(3)
        notes = state.next_turn()
        assert any("觀光收入" in n for n in notes)
        assert "酒店" in " ".join(notes) or any("酒店" in n for n in notes)
        assert "賭場" in " ".join(notes) or any("賭場" in n for n in notes)
        assert state.hotel_count() == 1
        assert state.casino_count() == 1
        assert state.funds == funds_before_turn + expected_tour
    finally:
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_ty
        model_mod.QUAKE_BASE_CHANCE = old_qk
        model_mod.VOLCANO_BASE_CHANCE = old_vo
        model_mod.TSUNAMI_BASE_CHANCE = old_ts
        model_mod.MONSTER_BASE_CHANCE = old_mon

    coral = make_demo_coral()
    assert coral.hotel_count() >= 1
    assert coral.casino_count() >= 1


def test_university_research_lab():
    """大學／研究所色塊：建設費用、島分數、發射折扣、研究所減災、SAVE round-trip."""
    import random

    import hakoniwa.model as model_mod

    state = IslandState.new_game()
    land = [(i, j) for i in range(20) for j in range(20) if state.is_land(i, j)]
    for i, j in land:
        if state.cell(i, j).terrain == "dirt":
            assert state.level_land(i, j) == "ok"
    grass = [
        (i, j)
        for i, j in land
        if state.cell(i, j).terrain == "grass" and state.cell(i, j).building is None
    ]
    assert len(grass) >= 3
    ui, uj = grass[0]
    li, lj = grass[1]
    ri, rj = grass[2]

    # Too poor → cannot place university.
    state.funds = COST_UNIVERSITY - 1
    assert state.place_building(ui, uj, "university") != "ok"
    state.funds = (
        COST_UNIVERSITY + COST_RESEARCH_LAB + COST_ROCKET_BASE + COST_ROCKET_LAUNCH + 50
    )
    before = state.funds
    assert state.can_place_building(ui, uj, "university")
    assert state.place_building(ui, uj, "university") == "ok"
    assert state.cell(ui, uj).building == "university"
    assert state.funds == before - COST_UNIVERSITY
    assert state.university_count() == 1
    assert state.has_university()
    assert state.island_score() >= SCORE_PER_UNIVERSITY
    assert state.rocket_launch_cost() == COST_ROCKET_LAUNCH - UNIVERSITY_TECH_DISCOUNT

    before_l = state.funds
    assert state.can_place_building(li, lj, "research_lab")
    assert state.place_building(li, lj, "research_lab") == "ok"
    assert state.cell(li, lj).building == "research_lab"
    assert state.funds == before_l - COST_RESEARCH_LAB
    assert state.research_lab_count() == 1
    assert state.has_research_lab()
    assert state.island_score() >= SCORE_PER_UNIVERSITY + SCORE_PER_RESEARCH_LAB
    assert state._disaster_mitigation_factor() == RESEARCH_LAB_DISASTER_FACTOR

    keys = {k for k, *_ in TOOL_SPECS}
    assert "university" in keys and "research_lab" in keys
    ok, _ = tool_enabled(state, "university", (ui, uj))
    assert ok is False  # occupied
    ok, _ = tool_enabled(state, "research_lab", (li, lj))
    assert ok is False

    # Rocket launch with university discount.
    assert state.place_building(ri, rj, "rocket_base") == "ok"
    launch_cost = state.rocket_launch_cost()
    assert launch_cost == COST_ROCKET_LAUNCH - UNIVERSITY_TECH_DISCOUNT
    funds_pre = state.funds
    ok, _ = tool_enabled(state, "rocket_launch", None)
    assert ok is True
    assert state.launch_rocket() == "ok"
    assert state.funds == funds_pre - launch_cost
    assert state.has_satellite()
    assert any("大學" in line and "折扣" in line for line in state.log)
    # Satellite × lab stack.
    assert state._disaster_mitigation_factor() == (
        SATELLITE_DISASTER_FACTOR * RESEARCH_LAB_DISASTER_FACTOR
    )

    # Save round-trip.
    blob = state.to_dict()
    assert blob["version"] == SAVE_VERSION
    loaded = IslandState.from_dict(blob)
    assert loaded.university_count() == 1
    assert loaded.research_lab_count() == 1
    assert loaded.cell(ui, uj).building == "university"
    assert loaded.cell(li, lj).building == "research_lab"
    assert loaded.island_score() == state.island_score()
    assert loaded.rocket_launch_cost() == launch_cost
    assert loaded._disaster_mitigation_factor() == state._disaster_mitigation_factor()

    # Lab-only mitigation note on turn (mute wipe risk).
    lab_only = IslandState.new_game()
    for i, j in [
        (ii, jj)
        for ii in range(20)
        for jj in range(20)
        if lab_only.is_land(ii, jj)
    ]:
        if lab_only.cell(i, j).terrain == "dirt":
            lab_only.level_land(i, j)
    lab_grass = [
        (i, j)
        for i in range(20)
        for j in range(20)
        if lab_only.cell(i, j).terrain == "grass"
        and lab_only.cell(i, j).building is None
    ]
    lab_only.funds = COST_RESEARCH_LAB + 20
    assert lab_only.place_building(lab_grass[0][0], lab_grass[0][1], "research_lab") == "ok"

    old_fire = model_mod.FIRE_BASE_CHANCE
    old_ty = model_mod.TYPHOON_BASE_CHANCE
    old_qk = model_mod.QUAKE_BASE_CHANCE
    old_vo = model_mod.VOLCANO_BASE_CHANCE
    old_ts = model_mod.TSUNAMI_BASE_CHANCE
    old_mon = model_mod.MONSTER_BASE_CHANCE
    model_mod.FIRE_BASE_CHANCE = 0.0
    model_mod.TYPHOON_BASE_CHANCE = 0.0
    model_mod.QUAKE_BASE_CHANCE = 0.01
    model_mod.VOLCANO_BASE_CHANCE = 0.0
    model_mod.TSUNAMI_BASE_CHANCE = 0.0
    model_mod.MONSTER_BASE_CHANCE = 0.0
    try:
        lab_only.food = max(lab_only.food, 500)
        random.seed(7)
        notes = lab_only.next_turn()
        assert any("研究所" in n and "減災" in n for n in notes), notes
        assert lab_only.research_lab_count() == 1
        assert any("大學" in n or "研究所" in n for n in notes)
    finally:
        model_mod.FIRE_BASE_CHANCE = old_fire
        model_mod.TYPHOON_BASE_CHANCE = old_ty
        model_mod.QUAKE_BASE_CHANCE = old_qk
        model_mod.VOLCANO_BASE_CHANCE = old_vo
        model_mod.TSUNAMI_BASE_CHANCE = old_ts
        model_mod.MONSTER_BASE_CHANCE = old_mon

    coral = make_demo_coral()
    assert coral.university_count() >= 1
    assert coral.research_lab_count() >= 1


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
    old_volcano = model_mod.VOLCANO_BASE_CHANCE
    old_tsunami = model_mod.TSUNAMI_BASE_CHANCE
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

        # Fire on town (no forest neighbor); silence typhoon/quake/volcano/tsunami.
        model_mod.TYPHOON_BASE_CHANCE = 0.0
        model_mod.QUAKE_BASE_CHANCE = 0.0
        model_mod.VOLCANO_BASE_CHANCE = 0.0
        model_mod.TSUNAMI_BASE_CHANCE = 0.0
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

        # Typhoon: farm → plain (silence fire/quake/tsunami).
        model_mod.FIRE_BASE_CHANCE = 0.0
        model_mod.TYPHOON_BASE_CHANCE = old_typhoon
        model_mod.QUAKE_BASE_CHANCE = 0.0
        model_mod.TSUNAMI_BASE_CHANCE = 0.0
        random.random = lambda: 0.0  # type: ignore[assignment]
        assert state.cell(fi, fj).building == "farm"
        notes = state._apply_disasters()
        assert state.cell(fi, fj).building is None
        assert any("颱風" in n for n in notes)

        # Quake: factory → wasteland (silence fire/typhoon/tsunami).
        model_mod.FIRE_BASE_CHANCE = 0.0
        model_mod.TYPHOON_BASE_CHANCE = 0.0
        model_mod.QUAKE_BASE_CHANCE = old_quake
        model_mod.TSUNAMI_BASE_CHANCE = 0.0
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
        model_mod.VOLCANO_BASE_CHANCE = old_volcano
        model_mod.TSUNAMI_BASE_CHANCE = old_tsunami


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
    # No selection → cell tools disabled; wait needs a monster; export needs port;
    # bank/supermarket actions need their buildings; 誘致不需選格但要資金.
    for key, *_ in TOOL_SPECS:
        ok, reason = tool_enabled(state, key, None)
        if key == "attract":
            # new_game funds == COST_ATTRACT → enabled without selection.
            assert ok is True
            continue
        assert ok is False
        if key == "wait":
            assert "怪獸" in reason
        elif key == "export":
            assert "港灣" in reason or "造船" in reason
        elif key in ("deposit", "withdraw"):
            assert "銀行" in reason
        elif key == "buy_food":
            assert "超市" in reason
        elif key == "rocket_launch":
            assert "ロケット" in reason or "基地" in reason
        else:
            assert "選格" in reason
    # Poor island → attract locked.
    state.funds = COST_ATTRACT - 1
    ok, reason = tool_enabled(state, "attract", None)
    assert ok is False and "資金" in reason
    state.funds = max(state.funds, COST_ATTRACT)

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
    ok, _ = tool_enabled(state, "raise", (gi, gj))
    assert ok is True
    ok, reason = tool_enabled(state, "quarry", (gi, gj))
    assert ok is False
    assert "山" in reason
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
    # No top instruction banner (「點選格子…」/ shortcut strip) on open.
    from PySide6.QtWidgets import QLabel

    banner_bits = ("點選格子", "快捷鍵：", "滾輪縮放")
    for lab in dlg.findChildren(QLabel):
        t = lab.text() or ""
        assert not any(b in t for b in banner_bits), t
    # Tools button geometry is correct even before the dialog is shown
    # (isHidden()-based layout; was stuck at top-left with isVisible()).
    assert not dlg.hud.tools_btn.isHidden()
    btn_geo = dlg.hud.tools_btn.geometry()
    assert btn_geo.y() >= dlg.hud.height() // 2, (
        btn_geo,
        dlg.hud.size(),
    )
    assert btn_geo.x() <= 16, btn_geo
    # No selection → cell tools disabled；誘致不需選格（資金足夠時可點）；
    # 火箭發射無基地時仍鎖.
    dlg._refresh_toolbar()
    for key, btn in dlg.tool_buttons.items():
        if key == "attract" and dlg.state.funds >= COST_ATTRACT and not dlg.state.attract_pending:
            assert btn.isEnabled()
        else:
            assert not btn.isEnabled(), key
    # Status overlay: locked order 狀態→資金→糧食→人口→回合→格數→分數; no connection mode.
    st = dlg.stats.text()
    assert "資金" in st and "糧食" in st and "人口" in st
    assert "回合" in st and "格數" in st and "分數" in st
    assert "狀態" in st
    assert "[本機]" not in st and "[連線]" not in st
    # Exact field order (indices increase left→right).
    i_status, i_funds = st.index("狀態"), st.index("資金")
    i_food, i_pop = st.index("糧食"), st.index("人口")
    i_turn, i_cells = st.index("回合"), st.index("格數")
    i_score = st.index("分數")
    assert i_status < i_funds < i_food < i_pop < i_turn < i_cells < i_score, st
    # Status HUD is a single horizontal line (no wrap / multi-line).
    assert dlg.stats.wordWrap() is False
    assert "\n" not in st
    dlg.show()
    dlg.resize(960, 780)
    dlg._refresh_ui()
    app.processEvents()
    # After show: tools button still bottom-left without needing a click.
    btn_geo = dlg.hud.tools_btn.geometry()
    assert btn_geo.y() >= dlg.hud.height() - btn_geo.height() - 24, (
        btn_geo,
        dlg.hud.size(),
    )
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


def test_user_art_loader_hook():
    """Naming covers catalog; missing files → None; drop-in PNG loads then falls back."""
    import os
    import struct
    import zlib

    from hakoniwa.user_art import (
        ASSETS_USER_DIR,
        USER_BUILDING_FILES,
        USER_MONSTER_FILES,
        USER_TERRAIN_FILES,
        UserArtLoader,
        assert_naming_covers_catalog,
        configure_user_art,
        default_user_art_roots,
        expected_filenames,
    )

    assert_naming_covers_catalog()
    names = expected_filenames()
    assert "farm.png" in names["building"]
    assert "park.png" in names["building"]
    assert "airport.png" in names["building"]
    assert "rocket_base.png" in names["building"]
    assert "hotel.png" in names["building"]
    assert "casino.png" in names["building"]
    assert "university.png" in names["building"]
    assert "research_lab.png" in names["building"]
    assert "inora.png" in names["monster"]
    assert "sea.png" in names["terrain"]
    assert "ocean-background.png" in names["ocean"]
    # Every BUILDINGS／MONSTERS／TERRAIN key has a documented slot.
    assert set(USER_BUILDING_FILES) >= {
        k for k in USER_BUILDING_FILES
    }
    assert "farm" in USER_BUILDING_FILES and "missile_base" in USER_BUILDING_FILES
    assert "inora" in USER_MONSTER_FILES
    assert set(USER_TERRAIN_FILES) >= {"sea", "dirt", "grass", "forest", "mountain"}

    roots = default_user_art_roots(None)
    assert ASSETS_USER_DIR in roots
    assert roots[-1] == ASSETS_USER_DIR

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp)
        data_user = cfg / "Data" / "hakoniwa" / "user"
        data_user.mkdir(parents=True)
        ordered = default_user_art_roots(cfg)
        assert ordered[0] == data_user.resolve()
        assert ordered[1] == ASSETS_USER_DIR

        loader = UserArtLoader(roots=[data_user])
        # Empty folder → no art (color-block / bundled fallback path).
        assert loader.path_for_building("farm") is None
        assert loader.path_for_monster("inora") is None
        assert loader.path_for_terrain("sea") is None
        assert loader.present_keys()["building"] == []

        def _tiny_png(path: Path, rgb=(200, 40, 40)) -> None:
            """Write a 2×2 RGB PNG without Qt (smoke can run headless)."""
            w = h = 2
            r, g, b = rgb
            raw = b""
            for _y in range(h):
                raw += b"\x00" + bytes([r, g, b]) * w
            compressed = zlib.compress(raw, 9)

            def chunk(tag: bytes, data: bytes) -> bytes:
                return (
                    struct.pack(">I", len(data))
                    + tag
                    + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
                )

            ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", compressed)
                + chunk(b"IEND", b"")
            )

        farm_png = data_user / "farm.png"
        _tiny_png(farm_png)
        assert loader.path_for_building("farm") == farm_png
        assert loader.path_for_building("park") is None  # still color block
        assert "farm" in loader.present_keys()["building"]

        # configure_user_art + atlas: user building loads; terrain still bundled.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from hakoniwa.tiles import ATLAS
        except Exception as exc:  # pragma: no cover
            print(f"user art: skip Qt load ({exc})")
            configure_user_art(None)  # restore package-only roots
            print("user art loader: naming + path resolve OK (no Qt)")
            return

        _app = QApplication.instance() or QApplication([])
        configure_user_art(cfg)
        ATLAS.invalidate_user_cache()
        bpix = ATLAS.building_pixmap("farm")
        assert bpix is not None and not bpix.isNull()
        assert ATLAS.building_pixmap("park") is None
        assert ATLAS.monster_pixmap("inora") is None
        # Bundled tops still work when no user terrain PNG.
        assert ATLAS.has_primary_tops()
        # After dropping sea.png, user override wins for that key.
        _tiny_png(data_user / "sea.png", rgb=(20, 80, 160))
        ATLAS.invalidate_user_cache()
        configure_user_art(cfg)
        sea = ATLAS.pixmap_for("sea")
        assert sea is not None and not sea.isNull()

        # Restore singleton for later smoke steps (no leftover temp roots).
        configure_user_art(None)
        ATLAS.invalidate_user_cache()
        print("user art loader: naming + optional PNG hook OK")


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
    test_user_art_loader_hook()
    test_catalog_costs()
    test_new_island_and_loop()
    test_guestbook_local()
    test_settlements_and_disasters()
    test_monster_events()
    test_defense_and_missile_base()
    test_harbor_shipyard_trade()
    test_monument_and_island_score()
    test_mountain_quarry_labor()
    test_breakwater_oilfield_tsunami()
    test_bank_supermarket_shrine()
    test_park_and_attract()
    test_airport_and_tourism_buffs()
    test_rocket_base_and_launch()
    test_hotel_casino_tourism()
    test_university_research_lab()
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
