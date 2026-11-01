#!/usr/bin/env python3
"""Offline HD pixel 8-dir swim sheet for 青衣 (Epinephelus coioides) only.

Quality benchmark: media/.../qingyi-quality-ref-hd-pixel.jpg
(detail density / shading / fin rays — NOT mandarinfish species identity).

Palette: web-typical green/blue body + yellow/orange accents & spots.
Other species sheets are untouched. No realtime 3D.

Run: python -m fish_tank.tools.gen_grouper_hd
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "swim" / "grouper.png"

# HD cell — ~2× legacy RTS sheets (48×40). Fixed blit size for 青衣.
CELL_W, CELL_H = 96, 80
DIRS = 8

# Epinephelus coioides–like palette (green/blue + yellow accents).
C_BODY = QColor(58, 110, 88)       # olive-green mid
C_BODY_DK = QColor(36, 72, 58)     # deep flank
C_BODY_HI = QColor(92, 150, 118)   # dorsal highlight
C_BLUE = QColor(48, 92, 120)       # cool blue cast
C_YELLOW = QColor(220, 170, 55)    # fin / accent yellow
C_ORANGE = QColor(210, 130, 45)    # orange spots (coioides)
C_BELLY = QColor(170, 175, 120)    # pale belly
C_EYE = QColor(30, 28, 24)
C_EYE_RING = QColor(230, 200, 70)
C_OUT = QColor(18, 22, 26)
C_OUT2 = QColor(40, 50, 48)
C_SHADOW = QColor(12, 18, 24, 100)


def _yaw(i: int) -> float:
    return i * (math.pi / 4.0)


def _project(x: float, y: float, z: float) -> Tuple[float, float, float]:
    sx = x * 1.0 + y * 0.12
    sy = y * 0.56 - z * 0.88
    depth = y * 0.45 + z * 0.25
    return sx, sy, depth


def _rot(lx: float, ly: float, yaw: float) -> Tuple[float, float]:
    # yaw 0 = nose North (0,-1)
    wx = lx * math.sin(yaw) + ly * math.cos(yaw)
    wy = -lx * math.cos(yaw) + ly * math.sin(yaw)
    return wx, wy


def _voxels(yaw: float) -> List[Tuple[float, float, float, str]]:
    """Dense HD voxel cloud. tag: body|hi|dk|blue|belly|spot|fin|eye|ring."""
    pts: List[Tuple[float, float, float, str]] = []
    length, width, height = 34.0, 16.0, 12.0

    # Main body ellipsoid (dense)
    for i in range(-28, 29):
        t = i / 28.0
        taper = 1.0 - abs(t) ** 1.25 * 0.48
        if t > 0.7:
            taper *= 1.0 - (t - 0.7) / 0.3 * 0.55
        if t < -0.6:
            taper *= 1.0 - (-0.6 - t) / 0.4 * 0.4
        lx = t * length * 0.5
        for j in range(-14, 15):
            for k in range(0, 14):
                ny = (j / 14.0) / max(0.12, taper)
                nz = k / 13.0
                if ny * ny + nz * nz > 1.0:
                    continue
                ly = (j / 14.0) * width * 0.5 * taper
                lz = nz * height * taper
                wx, wy = _rot(lx, ly, yaw)
                sx, sy, depth = _project(wx, wy, lz)
                # Material bands
                if nz > 0.72:
                    tag = "hi"
                elif nz < 0.22:
                    tag = "belly"
                elif abs(ny) > 0.75:
                    tag = "dk"
                elif nz > 0.45 and abs(ny) < 0.35:
                    tag = "blue" if ((i + j + k) % 5 == 0) else "body"
                else:
                    tag = "body"
                # Orange spots (coioides) — scattered on flanks
                if tag in ("body", "dk", "blue") and ((i * 3 + j * 5 + k * 7) % 17) == 0:
                    tag = "spot"
                pts.append((sx, sy, depth, tag))

    # Tail fan with rays
    for ray in range(-7, 8):
        for i in range(10):
            lx = -length * 0.52 - i * 1.0
            ly = ray * (0.55 + i * 0.22)
            lz = 3.5 + abs(ray) * 0.2
            wx, wy = _rot(lx, ly, yaw)
            sx, sy, depth = _project(wx, wy, lz)
            tag = "fin" if abs(ray) > 3 or i > 5 else ("spot" if i % 4 == 0 else "body")
            pts.append((sx, sy, depth, tag))

    # Pectorals — fan rays (HD detail cue from quality ref)
    for side in (-1.0, 1.0):
        for ray in range(0, 9):
            ang = side * (0.35 + ray * 0.12)
            for i in range(1, 11):
                lx = -2.0 + i * 0.35
                ly = math.sin(ang) * (width * 0.35 + i * 1.15)
                lz = 3.0 + i * 0.15
                wx, wy = _rot(lx, ly, yaw)
                sx, sy, depth = _project(wx, wy, lz)
                tag = "fin" if ray % 2 == 0 else "yellow"
                pts.append((sx, sy, depth, tag))

    # Dorsal ridge / soft spines
    for i in range(-8, 10):
        for k in range(3):
            lx = i * 1.1
            ly = 0.0
            lz = height * 0.85 + k * 1.2 + abs(i) * 0.05
            wx, wy = _rot(lx, ly, yaw)
            sx, sy, depth = _project(wx, wy, lz)
            pts.append((sx, sy, depth, "hi" if k == 0 else "fin"))

    # Eye (near snout)
    for j in range(-2, 3):
        for k in range(2, 6):
            lx = length * 0.32
            ly = 2.2 + j * 0.55
            lz = k * 1.1
            wx, wy = _rot(lx, ly, yaw)
            sx, sy, depth = _project(wx, wy, lz)
            tag = "eye" if abs(j) < 2 and 2 < k < 5 else "ring"
            pts.append((sx, sy, depth + 0.5, tag))

    return pts


_TAG_COLOR = {
    "body": C_BODY,
    "hi": C_BODY_HI,
    "dk": C_BODY_DK,
    "blue": C_BLUE,
    "belly": C_BELLY,
    "spot": C_ORANGE,
    "fin": C_YELLOW,
    "yellow": C_YELLOW,
    "eye": C_EYE,
    "ring": C_EYE_RING,
}


def render_frame(dir_index: int) -> QImage:
    img = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    depth_buf = [[-1e9] * CELL_W for _ in range(CELL_H)]
    tag_buf = [[""] * CELL_W for _ in range(CELL_H)]

    pts = _voxels(_yaw(dir_index))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    ox, oy = CELL_W * 0.5 - cx, CELL_H * 0.55 - cy

    # Soft ground shadow (multi-layer)
    for sx0, sy0, depth, tag in pts:
        if tag in ("fin", "yellow") and depth < 0:
            continue
        for sdx, sdy, a in ((0, 4, 70), (1, 5, 50), (-1, 5, 50), (0, 6, 35)):
            x = int(round(sx0 + ox + sdx))
            y = int(round(sy0 + oy + sdy))
            if 0 <= x < CELL_W and 0 <= y < CELL_H:
                prev = img.pixelColor(x, y)
                if prev.alpha() < a:
                    img.setPixelColor(x, y, QColor(12, 18, 24, a))

    # Depth stamp 2×2 for chunky HD pixels
    for sx0, sy0, depth, tag in pts:
        x0 = int(round(sx0 + ox))
        y0 = int(round(sy0 + oy))
        for dx in (0, 1):
            for dy in (0, 1):
                x, y = x0 + dx, y0 + dy
                if not (0 <= x < CELL_W and 0 <= y < CELL_H):
                    continue
                if depth >= depth_buf[y][x]:
                    depth_buf[y][x] = depth
                    tag_buf[y][x] = tag

    opaque = []
    for y in range(CELL_H):
        for x in range(CELL_W):
            tag = tag_buf[y][x]
            if not tag:
                continue
            col = QColor(_TAG_COLOR[tag])
            # Micro dither for HD volume (quality-ref style)
            if tag == "body" and ((x * 3 + y * 5) % 7) == 0:
                col = QColor(C_BODY_DK)
            if tag == "hi" and ((x + y) % 5) == 0:
                col = QColor(C_BODY)
            if tag == "belly" and ((x + 2 * y) % 6) == 0:
                col = QColor(C_BODY_HI)
            img.setPixelColor(x, y, col)
            opaque.append((x, y))

    # Dual outline (dark + secondary) for HD readability
    for x, y in opaque:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < CELL_W and 0 <= ny < CELL_H and not tag_buf[ny][nx]:
                img.setPixelColor(nx, ny, C_OUT)
                tag_buf[ny][nx] = "out"
    for x, y in list(opaque):
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < CELL_W and 0 <= ny < CELL_H and not tag_buf[ny][nx]:
                # Only soft rim if neighbour empty
                if img.pixelColor(nx, ny).alpha() == 0:
                    img.setPixelColor(nx, ny, QColor(C_OUT2.red(), C_OUT2.green(), C_OUT2.blue(), 160))
                    tag_buf[ny][nx] = "out2"

    # Specular speckles on dorsal (pre-rendered highlight)
    for x, y in opaque:
        if tag_buf[y][x] == "hi" and ((x * 7 + y * 3) % 11) == 0:
            img.setPixelColor(x, y, QColor(210, 230, 200))

    return img


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    sheet = QImage(CELL_W * DIRS, CELL_H, QImage.Format.Format_ARGB32)
    sheet.fill(Qt.GlobalColor.transparent)
    p = QPainter(sheet)
    for i in range(DIRS):
        frame = render_frame(i)
        opaque = sum(
            1
            for y in range(CELL_H)
            for x in range(CELL_W)
            if frame.pixelColor(x, y).alpha() > 40
        )
        print(f"  facing {i}: opaque={opaque}")
        p.drawImage(i * CELL_W, 0, frame)
    p.end()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ok = sheet.save(str(OUT), "PNG")
    print(f"wrote {OUT} ({sheet.width()}x{sheet.height()}) ok={ok}")
    _ = app
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
