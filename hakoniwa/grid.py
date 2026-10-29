"""箱庭斜視 grid: 1:1 square diamonds + v9 diagonal-strip stagger.

Lattice (see docs/hakoniwa-oblique-view.md, internal v13 notes):
  pos(i, j) = i·u + j·v + (i odd ? ½v : 0)
  u = (W/2,  H/2)   # down-right
  v = (W/2, −H/2)   # up-right (blue-arrow axis)
Odd strips shift +½ along v so vertices meet mid-edges (brick stagger).

Logical adjacency is 6-neighbor (hex), matching Hakoniwa Islands topology.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

GRID_SIZE = 20

# Screen diamond size (pixels). W:H = 1:1.
DEFAULT_CELL = 30

Coord = Tuple[int, int]


def cell_center(i: int, j: int, cell: float = DEFAULT_CELL) -> Tuple[float, float]:
    """Return screen-space center of cell (i, j) before map origin offset."""
    w = h = float(cell)
    ux, uy = w / 2.0, h / 2.0
    vx, vy = w / 2.0, -h / 2.0
    x = i * ux + j * vx
    y = i * uy + j * vy
    if i % 2 == 1:
        x += vx / 2.0
        y += vy / 2.0
    return x, y


def diamond_vertices(
    cx: float, cy: float, cell: float = DEFAULT_CELL
) -> List[Tuple[float, float]]:
    """1:1 rhombus (square rotated ~45°): N, E, S, W."""
    w = h = float(cell)
    hw, hh = w / 2.0, h / 2.0
    return [
        (cx, cy - hh),  # N
        (cx + hw, cy),  # E
        (cx, cy + hh),  # S
        (cx - hw, cy),  # W
    ]


def in_bounds(i: int, j: int, size: int = GRID_SIZE) -> bool:
    return 0 <= i < size and 0 <= j < size


def neighbors(i: int, j: int, size: int = GRID_SIZE) -> List[Coord]:
    """Six hex neighbors for odd-i half-cell stagger along v."""
    if i % 2 == 0:
        deltas = (
            (0, -1),
            (0, 1),
            (-1, 0),
            (-1, -1),
            (1, 0),
            (1, -1),
        )
    else:
        deltas = (
            (0, -1),
            (0, 1),
            (-1, 0),
            (-1, 1),
            (1, 0),
            (1, 1),
        )
    out: List[Coord] = []
    for di, dj in deltas:
        ni, nj = i + di, j + dj
        if in_bounds(ni, nj, size):
            out.append((ni, nj))
    return out


def center_cluster(size: int = GRID_SIZE) -> List[Coord]:
    """Central cell plus its six neighbors (7 land cells for new islands)."""
    ci = size // 2 - 1
    cj = size // 2 - 1
    cells = [(ci, cj)] + neighbors(ci, cj, size)
    # Deduplicate while preserving order.
    seen = set()
    unique: List[Coord] = []
    for c in cells:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def map_bounds(
    size: int = GRID_SIZE, cell: float = DEFAULT_CELL, pad: float = 8.0
) -> Tuple[float, float, float, float]:
    """Axis-aligned bounds of all diamond extents (min_x, min_y, max_x, max_y)."""
    w = h = float(cell)
    hw, hh = w / 2.0, h / 2.0
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for i in range(size):
        for j in range(size):
            cx, cy = cell_center(i, j, cell)
            min_x = min(min_x, cx - hw)
            max_x = max(max_x, cx + hw)
            min_y = min(min_y, cy - hh)
            max_y = max(max_y, cy + hh)
    return min_x - pad, min_y - pad, max_x + pad, max_y + pad


def paint_order(size: int = GRID_SIZE, cell: float = DEFAULT_CELL) -> List[Coord]:
    """Far-to-near draw order (ascending screen y, then x)."""
    cells: List[Tuple[float, float, int, int]] = []
    for i in range(size):
        for j in range(size):
            cx, cy = cell_center(i, j, cell)
            cells.append((cy, cx, i, j))
    cells.sort()
    return [(i, j) for _, _, i, j in cells]


def point_in_diamond(
    px: float,
    py: float,
    cx: float,
    cy: float,
    cell: float = DEFAULT_CELL,
) -> bool:
    """Hit-test a 1:1 diamond (Manhattan in rotated axes)."""
    w = h = float(cell)
    # Transform: diamond is |dx|/(w/2) + |dy|/(h/2) <= 1
    dx = abs(px - cx) / (w / 2.0)
    dy = abs(py - cy) / (h / 2.0)
    return dx + dy <= 1.0 + 1e-9


def hit_test(
    px: float,
    py: float,
    size: int = GRID_SIZE,
    cell: float = DEFAULT_CELL,
    origin: Sequence[float] = (0.0, 0.0),
) -> Coord | None:
    """Front-to-back pick; returns (i, j) or None."""
    ox, oy = origin
    for i, j in reversed(paint_order(size, cell)):
        cx, cy = cell_center(i, j, cell)
        if point_in_diamond(px, py, cx + ox, cy + oy, cell):
            return i, j
    return None


def iter_cells(size: int = GRID_SIZE) -> Iterable[Coord]:
    for i in range(size):
        for j in range(size):
            yield i, j
