#!/usr/bin/env python3
"""Offline generator: RTS-like isometric pre-rendered pixel swim sheets.

Produces chunky RA2-adjacent silhouettes (theme colors only — not C&C assets).
Run from repo root:
  python -m fish_tank.tools.gen_rts_sheets

Writes PNG strips under fish_tank/assets/swim/ and plant/.
No realtime 3D in-app — sheets are static blits.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Prefer Qt for ARGB PNG; fall back to pure struct PNG if needed.
try:
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtCore import Qt
    HAS_QT = True
except Exception:
    HAS_QT = False

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SWIM_DIR = ASSETS / "swim"
PLANT_DIR = ASSETS / "plant"
SIDE_DIR = ASSETS / "side"

# Frame size — fixed blit size in-game.
CELL_W, CELL_H = 48, 40
DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# Species shape + base palette (R,G,B). Rare remapped at load time.
SPECIES_SHAPES: Dict[str, dict] = {
    "mudskipper": {
        "len": 1.15, "wid": 0.55, "h": 0.42, "spines": 0,
        "colors": [(92, 118, 86), (58, 74, 52), (180, 168, 120), (40, 48, 36)],
    },
    "lionfish": {
        "len": 1.0, "wid": 0.7, "h": 0.45, "spines": 7,
        "colors": [(200, 90, 50), (240, 220, 200), (40, 30, 28), (180, 60, 40)],
    },
    "spotted_scat": {
        "len": 0.85, "wid": 0.75, "h": 0.5, "spines": 0, "spots": True,
        "colors": [(210, 180, 70), (40, 36, 30), (160, 140, 50), (230, 210, 140)],
    },
    "catfish": {
        "len": 1.25, "wid": 0.5, "h": 0.4, "spines": 0, "whiskers": True,
        "colors": [(70, 64, 58), (110, 100, 88), (30, 28, 26), (150, 140, 120)],
    },
    "grouper": {
        "len": 1.05, "wid": 0.65, "h": 0.55, "spines": 0,
        "colors": [(70, 120, 90), (40, 80, 60), (200, 140, 50), (30, 50, 40)],
    },
}


def _yaw_rad(dir_index: int) -> float:
    # 0=N … clockwise in screen space (N up). Nose points along local +forward.
    # Forward in world: N=(0,-1), E=(1,0), …
    return dir_index * (math.pi / 4.0)


def _project(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """High slightly-oblique / isometric-like projection (no realtime 3D engine).

    Camera looks down from above with slight tilt — RA2 unit vibe.
    """
    # Oblique: foreshorten ground Y, lift Z into screen-up.
    sx = x * 1.0 + y * 0.15
    sy = y * 0.58 - z * 0.85
    depth = y * 0.4 + z * 0.2  # painter's algorithm key
    return sx, sy, depth


def _sample_body(shape: dict, yaw: float) -> List[Tuple[float, float, float, int]]:
    """Return list of (sx, sy, depth, band) pre-projected voxels. band: 0 mid 1 hi 2 sh 3 accent."""
    pts: List[Tuple[float, float, float, int]] = []
    length = 18.0 * shape["len"]
    width = 11.0 * shape["wid"]
    height = 8.0 * shape["h"]
    # Dense capsule grid in local space: +X = nose.
    for i in range(-16, 17):
        t = i / 16.0  # -1..1 along body
        # Taper nose / tail
        taper = 1.0 - abs(t) ** 1.3 * 0.5
        if t > 0.72:
            taper *= 1.0 - (t - 0.72) / 0.28 * 0.55  # nose point
        if t < -0.65:
            taper *= 1.0 - (-0.65 - t) / 0.35 * 0.4
        lx = t * length * 0.5
        for j in range(-9, 10):
            for k in range(0, 10):
                ly = (j / 9.0) * width * 0.5 * taper
                lz = (k / 9.0) * height * taper
                # Ellipsoid mask
                ny = (j / 9.0) / max(0.15, taper)
                nz = (k / 9.0)
                nx = t
                if (ny * ny + nz * nz) > 1.02:
                    continue
                # Rotate yaw around Z (up)
                cy, sy_ = math.cos(yaw), math.sin(yaw)
                # Local +X nose → world: rotate so yaw 0 points North (0,-1)
                # yaw 0: nose = (0, -1) on ground plane
                wx = lx * math.sin(yaw) + ly * math.cos(yaw)
                wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
                wz = lz
                sx, sy, depth = _project(wx, wy, wz)
                # Band: dorsal highlight, flank mid, belly shadow
                if nz > 0.65:
                    band = 1
                elif nz < 0.25:
                    band = 2
                elif abs(ny) > 0.7:
                    band = 3
                else:
                    band = 0
                pts.append((sx, sy, depth, band))

    # Tail fan
    for i in range(5):
        for j in range(-4, 5):
            lx = -length * 0.55 - i * 0.9
            ly = j * 0.7 * (1.0 - i * 0.12)
            lz = 1.5 + abs(j) * 0.15
            wx = lx * math.sin(yaw) + ly * math.cos(yaw)
            wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
            sx, sy, depth = _project(wx, wy, lz)
            pts.append((sx, sy, depth, 3 if abs(j) > 2 else 0))

    # Pectorals (both sides) — chunky
    for side in (-1, 1):
        for i in range(5):
            lx = -1.0 + i * 0.4
            ly = side * (width * 0.55 + i * 0.55)
            lz = 2.0
            wx = lx * math.sin(yaw) + ly * math.cos(yaw)
            wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
            sx, sy, depth = _project(wx, wy, lz)
            pts.append((sx, sy, depth, 3))

    # Lionfish spines
    for s in range(int(shape.get("spines", 0))):
        ang = -0.6 + s * 0.2
        for i in range(6):
            lx = -2 + i * 0.3
            ly = math.sin(ang) * (3 + i * 1.1)
            lz = 4 + i * 0.8
            wx = lx * math.sin(yaw) + ly * math.cos(yaw)
            wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
            sx, sy, depth = _project(wx, wy, lz)
            pts.append((sx, sy, depth, 1 if i % 2 == 0 else 3))

    # Catfish whiskers
    if shape.get("whiskers"):
        for side in (-1, 1):
            for i in range(5):
                lx = length * 0.35 + i * 0.5
                ly = side * (1.5 + i * 0.8)
                lz = 1.0
                wx = lx * math.sin(yaw) + ly * math.cos(yaw)
                wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
                sx, sy, depth = _project(wx, wy, lz)
                pts.append((sx, sy, depth, 2))

    return pts


def _render_frame(shape: dict, dir_index: int) -> "QImage":
    colors = shape["colors"]
    c_mid = QColor(*colors[0])
    c_hi = QColor(*colors[2])
    c_sh = QColor(*colors[1])
    c_acc = QColor(*colors[3])
    outline = QColor(20, 24, 28, 255)
    shadow = QColor(15, 20, 28, 90)

    img = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    depth_buf = [[-1e9] * CELL_W for _ in range(CELL_H)]
    band_buf = [[-1] * CELL_W for _ in range(CELL_H)]

    yaw = _yaw_rad(dir_index)
    pts = _sample_body(shape, yaw)
    # Center
    if not pts:
        return img
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    ox, oy = CELL_W * 0.5 - cx, CELL_H * 0.52 - cy

    # Ground shadow (chunky blob)
    for p in pts:
        sx = int(round(p[0] + ox))
        sy = int(round(p[1] + oy + 3))
        if 0 <= sx < CELL_W and 0 <= sy < CELL_H:
            img.setPixelColor(sx, sy, shadow)

    # Depth paint — 2×2 chunky stamp (RTS pre-rendered pixel weight)
    for sx0, sy0, depth, band in pts:
        x0 = int(round(sx0 + ox))
        y0 = int(round(sy0 + oy))
        for dx in (0, 1):
            for dy in (0, 1):
                x, y = x0 + dx, y0 + dy
                if not (0 <= x < CELL_W and 0 <= y < CELL_H):
                    continue
                if depth >= depth_buf[y][x]:
                    depth_buf[y][x] = depth
                    band_buf[y][x] = band

    palette = {0: c_mid, 1: c_hi, 2: c_sh, 3: c_acc}
    opaque = []
    for y in range(CELL_H):
        for x in range(CELL_W):
            b = band_buf[y][x]
            if b >= 0:
                col = QColor(palette[b])
                # Chunky dither on mid band (pre-rendered pixel grit)
                if b == 0 and ((x + y) & 3) == 0:
                    col = QColor(c_sh)
                img.setPixelColor(x, y, col)
                opaque.append((x, y))

    # Spots for scat
    if shape.get("spots"):
        for x, y in opaque:
            if ((x * 5 + y * 3) % 11) == 0 and band_buf[y][x] in (0, 1):
                img.setPixelColor(x, y, c_acc)

    # Hard outline (RTS unit edge)
    for x, y in opaque:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < CELL_W and 0 <= ny < CELL_H) or band_buf[ny][nx] < 0:
                # Only outline empty neighbour inside frame
                if 0 <= nx < CELL_W and 0 <= ny < CELL_H and band_buf[ny][nx] < 0:
                    img.setPixelColor(nx, ny, outline)
    return img


def _render_plant() -> "QImage":
    """Oblique chunky waterweed — single frame (no 8-dir)."""
    img = QImage(32, 40, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    cols = [QColor(48, 120, 62), QColor(30, 80, 42), QColor(90, 160, 90), QColor(20, 50, 30)]
    # Stem voxels
    for y in range(12, 38):
        for x in (14, 15, 16):
            img.setPixelColor(x, y, cols[0] if (x + y) % 2 == 0 else cols[1])
    # Leaf crowns
    for ang_i, (dx, dy) in enumerate(
        ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
    ):
        for t in range(1, 7):
            x = 15 + dx * t
            y = 14 + dy * (t // 2)
            if 0 <= x < 32 and 0 <= y < 40:
                img.setPixelColor(x, y, cols[2] if ang_i % 2 == 0 else cols[0])
    # Base
    for x in range(11, 20):
        img.setPixelColor(x, 37, cols[3])
        img.setPixelColor(x, 38, cols[3])
    # Outline
    for y in range(40):
        for x in range(32):
            if img.pixelColor(x, y).alpha() == 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < 32 and 0 <= ny < 40 and img.pixelColor(nx, ny).alpha() == 0:
                    img.setPixelColor(nx, ny, QColor(20, 30, 22))
    return img


def _render_side(shape: dict) -> "QImage":
    """Side-profile 圖鑑 card art (chunky pixel, not 8-dir)."""
    w, h = 96, 56
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    colors = [QColor(*c) for c in shape["colors"]]
    # Ellipse body
    for y in range(h):
        for x in range(w):
            nx = (x - 50) / 28.0
            ny = (y - 30) / 12.0
            if nx * nx + ny * ny <= 1.0:
                band = 1 if ny < -0.35 else (2 if ny > 0.35 else 0)
                col = colors[2] if band == 1 else (colors[1] if band == 2 else colors[0])
                if ((x + y) & 3) == 0:
                    col = colors[1]
                img.setPixelColor(x, y, col)
    # Tail
    for dy in range(-10, 11):
        span = 7 - abs(dy) // 2
        for dx in range(span):
            img.setPixelColor(18 - dx, 30 + dy, colors[1])
    # Dorsal
    for i, hh in enumerate((5, 8, 10, 9, 6, 4)):
        for dy in range(hh):
            img.setPixelColor(42 + i * 2, 18 - dy, colors[2])
    # Eye
    img.setPixelColor(68, 26, colors[3])
    img.setPixelColor(69, 26, QColor(240, 240, 240))
    # Outline
    opaque = [(x, y) for y in range(h) for x in range(w) if img.pixelColor(x, y).alpha() > 0]
    for x, y in opaque:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and img.pixelColor(nx, ny).alpha() == 0:
                img.setPixelColor(nx, ny, QColor(20, 24, 28))
    return img


def write_swim_sheet(key: str, shape: dict) -> Path:
    sheet = QImage(CELL_W * 8, CELL_H, QImage.Format.Format_ARGB32)
    sheet.fill(Qt.GlobalColor.transparent)
    painter = QPainter(sheet)
    for i in range(8):
        frame = _render_frame(shape, i)
        painter.drawImage(i * CELL_W, 0, frame)
    painter.end()
    SWIM_DIR.mkdir(parents=True, exist_ok=True)
    path = SWIM_DIR / f"{key}.png"
    sheet.save(str(path), "PNG")
    return path


def main() -> int:
    if not HAS_QT:
        print("PySide6 required to generate sheets", file=sys.stderr)
        return 1
    # Ensure QGuiApplication for some platforms
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    written = []
    for key, shape in SPECIES_SHAPES.items():
        path = write_swim_sheet(key, shape)
        written.append(path)
        side = _render_side(shape)
        SIDE_DIR.mkdir(parents=True, exist_ok=True)
        sp = SIDE_DIR / f"{key}.png"
        side.save(str(sp), "PNG")
        written.append(sp)
        print("wrote", path.name, "frames=8", "side", sp.name)
    plant = _render_plant()
    PLANT_DIR.mkdir(parents=True, exist_ok=True)
    pp = PLANT_DIR / "waterweed.png"
    plant.save(str(pp), "PNG")
    written.append(pp)
    print("wrote", pp)
    _ = app
    print(f"gen_rts_sheets: {len(written)} files → {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
