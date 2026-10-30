"""Seed / local-fallback demo islands for 觀光 (multi-island tourism).

Server seeds these when the islands catalog is empty; the client also builds
the same shapes for offline tourism (no NAS).
"""

from __future__ import annotations

from typing import List, Tuple

from .grid import GRID_SIZE, center_cluster, neighbors
from .model import TREE_MIN, Cell, GuestbookEntry, IslandState, _utc_now_iso


def _paint_blob(
    cells: List[List[Cell]],
    seeds: List[Tuple[int, int]],
    terrain: str,
) -> None:
    for i, j in seeds:
        if 0 <= i < GRID_SIZE and 0 <= j < GRID_SIZE:
            cells[i][j] = Cell(terrain)


def _expand(seeds: List[Tuple[int, int]], rings: int) -> List[Tuple[int, int]]:
    seen = set(seeds)
    frontier = list(seeds)
    for _ in range(rings):
        nxt: List[Tuple[int, int]] = []
        for i, j in frontier:
            for ni, nj in neighbors(i, j, GRID_SIZE):
                if (ni, nj) not in seen:
                    seen.add((ni, nj))
                    nxt.append((ni, nj))
        frontier = nxt
    return list(seen)


def make_demo_coral() -> IslandState:
    """Compact coral-ish island: larger land, farm + factory, a guestbook seed."""
    cells = [[Cell("sea") for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    core = center_cluster(GRID_SIZE)
    land = _expand(core, 1)
    for idx, (i, j) in enumerate(land):
        if idx == 0:
            cells[i][j] = Cell("mountain")
        elif idx < 3:
            cells[i][j] = Cell("dirt")
        elif idx < 8:
            cells[i][j] = Cell("grass")
        else:
            if idx % 3 == 0:
                cells[i][j] = Cell("forest", trees=TREE_MIN + 200)
            else:
                cells[i][j] = Cell("grass")
    # Place a farm and factory on grass; quarry on the mountain.
    farms = [(i, j) for i, j in land if cells[i][j].terrain == "grass"]
    if farms:
        cells[farms[0][0]][farms[0][1]].building = "farm"
    if len(farms) > 2:
        cells[farms[2][0]][farms[2][1]].building = "factory"
    mountains = [(i, j) for i, j in land if cells[i][j].terrain == "mountain"]
    if mountains:
        cells[mountains[0][0]][mountains[0][1]].building = "quarry"
    # One shallow ring touch + one coastal breakwater + one oilfield offshore.
    shallow_hit = None
    for i, j in land:
        for ni, nj in neighbors(i, j, GRID_SIZE):
            if cells[ni][nj].terrain == "sea":
                cells[ni][nj] = Cell("shallow")
                shallow_hit = (ni, nj)
                break
        else:
            continue
        break
    # Place breakwater on a coastal grass cell.
    for i, j in land:
        if cells[i][j].terrain != "grass" or cells[i][j].building is not None:
            continue
        if any(
            cells[ni][nj].terrain in ("sea", "shallow")
            for ni, nj in neighbors(i, j, GRID_SIZE)
        ):
            cells[i][j].building = "breakwater"
            break
    # Oilfield near the shallow touch (or any sea neighbor of land).
    oil_placed = False
    if shallow_hit is not None:
        for ni, nj in neighbors(*shallow_hit, GRID_SIZE):
            if cells[ni][nj].terrain == "sea":
                cells[ni][nj] = Cell("oilfield")
                oil_placed = True
                break
    if not oil_placed:
        for i, j in land:
            for ni, nj in neighbors(i, j, GRID_SIZE):
                if cells[ni][nj].terrain == "sea":
                    cells[ni][nj] = Cell("oilfield")
                    oil_placed = True
                    break
            if oil_placed:
                break
    # Civic color blocks after coastal breakwater so 防波堤 still gets a shore cell.
    free_grass = [
        (i, j)
        for i, j in land
        if cells[i][j].terrain == "grass" and cells[i][j].building is None
    ]
    for idx, kind in enumerate(("bank", "supermarket", "shrine", "park", "airport")):
        if idx >= len(free_grass):
            break
        gi, gj = free_grass[idx]
        cells[gi][gj].building = kind

    state = IslandState(
        size=GRID_SIZE,
        turn=4,
        funds=820,
        food=640,
        population=180,
        bank_deposit=150,
        name="珊瑚灘島",
        cells=cells,
        log=["示範島：珊瑚灘（觀光唯讀；防波堤／油田／銀行超市神社／公園／空港）"],
        comments=[
            GuestbookEntry(
                id="demo-coral-1",
                name="導覽員",
                text="歡迎觀光珊瑚灘島！",
                at=_utc_now_iso(),
            )
        ],
        island_id="demo-coral",
    )
    return state


def make_demo_pine() -> IslandState:
    """Sparse pine-ish island: more forest, no factory yet."""
    cells = [[Cell("sea") for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    # Offset cluster toward upper-left of center.
    ci = GRID_SIZE // 2 - 2
    cj = GRID_SIZE // 2 - 1
    seeds = [(ci, cj), (ci + 1, cj), (ci, cj + 1), (ci - 1, cj), (ci + 1, cj - 1)]
    land = _expand(seeds, 1)
    for idx, (i, j) in enumerate(sorted(land)):
        if idx % 2 == 0:
            cells[i][j] = Cell("forest", trees=TREE_MIN + idx * 50)
        elif idx % 3 == 0:
            cells[i][j] = Cell("dirt")
        else:
            cells[i][j] = Cell("grass")
    grass = [(i, j) for i, j in land if cells[i][j].terrain == "grass"]
    if grass:
        cells[grass[0][0]][grass[0][1]].building = "farm"

    state = IslandState(
        size=GRID_SIZE,
        turn=2,
        funds=1100,
        food=420,
        population=90,
        name="松風島",
        cells=cells,
        log=["示範島：松風（觀光唯讀）"],
        comments=[],
        island_id="demo-pine",
    )
    return state


def local_demo_islands() -> List[IslandState]:
    """Offline tourism catalog (same ids/shapes as server seeds)."""
    return [make_demo_coral(), make_demo_pine()]


def island_summary(state: IslandState) -> dict:
    """List-row payload for 觀光 picker (server + client)."""
    return {
        "id": state.island_id or "unknown",
        "name": state.name,
        "turn": state.turn,
        "funds": state.funds,
        "food": state.food,
        "population": state.population,
        "land": state.land_count(),
        "comments": len(state.list_comments()),
    }
