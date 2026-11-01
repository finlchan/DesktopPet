#!/usr/bin/env python3
"""Build 青衣 8-dir × 4-frame swim-cycle sheet from user stills.

Source: qingyi-user-8dir-source.jpg (2×4: N NE E SE / S SW W NW).
Per facing: 4 frames — tail/body sway + pectoral flap (no realtime 3D).

Output: fish_tank/assets/swim/grouper.png
  layout: columns = dirs (0..7), rows = frames (0..3)
  cell = 120×100

Run: python -m fish_tank.tools.gen_grouper_swim_cycle
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QTransform

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "swim" / "grouper.png"
# Prefer store path (agent), fall back to repo-local copy if present.
SOURCE_CANDIDATES = [
    Path("/cursor/stores/bc-29e56597-c251-41e3-85ea-3d3b81f1b86a/media/fish-tank-phase1-oblique/qingyi-user-8dir-source.jpg"),
    Path("/cursor/stores/self/media/fish-tank-phase1-oblique/qingyi-user-8dir-source.jpg"),
    ROOT / "assets" / "sources" / "qingyi-user-8dir-source.jpg",
]

CELL_W, CELL_H = 120, 100
DIR_COUNT = 8
FRAME_COUNT = 4
DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _find_source() -> Path:
    for p in SOURCE_CANDIDATES:
        if p.is_file():
            return p
    raise FileNotFoundError("qingyi-user-8dir-source.jpg not found")


def _key_black(img: QImage, thr: float = 28.0) -> QImage:
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            bright = (c.red() + c.green() + c.blue()) / 3.0
            chroma = max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue())
            if bright < thr and chroma < 18:
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return out


def _extract_bases(src: QImage) -> List[QImage]:
    W, H = src.width(), src.height()
    cw, ch = W // 4, H // 2
    bases: List[QImage] = []
    for i in range(DIR_COUNT):
        r, c = (0, i) if i < 4 else (1, i - 4)
        cell = src.copy(c * cw, r * ch, cw, ch)
        # Content bbox (bright / chromatic)
        minx, miny, maxx, maxy = cw, ch, 0, 0
        for y in range(ch):
            for x in range(cw):
                col = cell.pixelColor(x, y)
                bright = (col.red() + col.green() + col.blue()) / 3.0
                chroma = max(col.red(), col.green(), col.blue()) - min(
                    col.red(), col.green(), col.blue()
                )
                if bright > 35 or chroma > 25:
                    minx = min(minx, x)
                    miny = min(miny, y)
                    maxx = max(maxx, x)
                    maxy = max(maxy, y)
        pad = 24
        minx = max(0, minx - pad)
        miny = max(0, miny - pad)
        maxx = min(cw - 1, maxx + pad)
        maxy = min(ch - 1, maxy + pad)
        trimmed = cell.copy(minx, miny, maxx - minx + 1, maxy - miny + 1)
        tw, th = trimmed.width(), trimmed.height()
        scale = min(CELL_W / tw, CELL_H / th) * 0.92
        nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
        scaled = trimmed.scaled(
            nw,
            nh,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled = _key_black(scaled)
        canvas = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage((CELL_W - nw) // 2, (CELL_H - nh) // 2, scaled)
        p.end()
        bases.append(canvas)
    return bases


def _forward_right(facing: int) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Unit forward (nose) and right vectors in image space (+y down)."""
    ang = facing * (math.pi / 4.0)  # 0=N
    # forward: N=(0,-1), E=(1,0)
    fx, fy = math.sin(ang), -math.cos(ang)
    rx, ry = math.cos(ang), math.sin(ang)  # right of fish
    return (fx, fy), (rx, ry)


def _centroid(img: QImage) -> Tuple[float, float]:
    sx = sy = n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 40:
                sx += x
                sy += y
                n += 1
    if n == 0:
        return img.width() / 2, img.height() / 2
    return sx / n, sy / n


def _warp_frame(base: QImage, facing: int, frame: int) -> QImage:
    """Tail sway + light pectoral flap for one cycle frame."""
    phase = (frame / FRAME_COUNT) * 2.0 * math.pi
    sway = math.sin(phase)  # -1..1
    pec = math.sin(phase + math.pi / 2) * 0.7
    (fx, fy), (rx, ry) = _forward_right(facing)
    cx, cy = _centroid(base)

    out = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.transparent)

    # Inverse map: for each dest pixel, sample source with reverse warp
    amp_tail = 4.2  # px
    amp_body = 1.6
    amp_pec = 2.2
    for y in range(CELL_H):
        for x in range(CELL_W):
            # Position relative to centroid in fish axes
            dx, dy = x - cx, y - cy
            along = dx * fx + dy * fy  # nose positive
            across = dx * rx + dy * ry

            # Tail is negative-along (behind nose). Normalize by ~half-length.
            t = max(0.0, min(1.0, (-along) / 38.0))  # 0 at center → 1 at tail tip
            # Body undulation weaker midship
            body_t = max(0.0, min(1.0, (-along + 8) / 45.0))

            # Pectoral band: near mid-body, outward across
            pec_w = 0.0
            if -8 < along < 18 and abs(across) > 8:
                pec_w = min(1.0, (abs(across) - 8) / 16.0)

            # Source offset (inverse of forward warp)
            # forward warp moved pixels by +across_dir * sway * t
            # so sample from -that
            shift_across = sway * (amp_tail * t * t + amp_body * body_t * 0.5)
            shift_across += pec * amp_pec * pec_w * (1.0 if across >= 0 else -1.0) * 0.35
            # slight foreshortening on tail
            shift_along = -abs(sway) * 0.8 * t

            sx = x - (rx * shift_across + fx * shift_along)
            sy = y - (ry * shift_across + fy * shift_along)
            ix, iy = int(round(sx)), int(round(sy))
            if 0 <= ix < CELL_W and 0 <= iy < CELL_H:
                col = base.pixelColor(ix, iy)
                if col.alpha() > 0:
                    out.setPixelColor(x, y, col)

    # Re-apply a thin outline where alpha edge appears (keeps HD punch)
    opaque = [
        (x, y)
        for y in range(CELL_H)
        for x in range(CELL_W)
        if out.pixelColor(x, y).alpha() > 40
    ]
    outline = QColor(18, 22, 26)
    for x, y in opaque:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < CELL_W and 0 <= ny < CELL_H and out.pixelColor(nx, ny).alpha() == 0:
                out.setPixelColor(nx, ny, outline)
    return out


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    src_path = _find_source()
    print("source:", src_path)
    src = QImage(str(src_path))
    if src.isNull():
        print("failed to load source", file=sys.stderr)
        return 1
    bases = _extract_bases(src)
    sheet = QImage(CELL_W * DIR_COUNT, CELL_H * FRAME_COUNT, QImage.Format.Format_ARGB32)
    sheet.fill(Qt.GlobalColor.transparent)
    painter = QPainter(sheet)
    for d in range(DIR_COUNT):
        for f in range(FRAME_COUNT):
            frame = _warp_frame(bases[d], d, f)
            opaque = sum(
                1
                for y in range(CELL_H)
                for x in range(CELL_W)
                if frame.pixelColor(x, y).alpha() > 40
            )
            print(f"  {DIRS[d]} frame{f}: opaque={opaque}")
            painter.drawImage(d * CELL_W, f * CELL_H, frame)
    painter.end()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ok = sheet.save(str(OUT), "PNG")
    print(f"wrote {OUT} {sheet.width()}x{sheet.height()} ok={ok}")
    # Also write base-only row as preview strip
    prev = ROOT / "assets" / "swim" / "grouper_bases_preview.png"
    bp = QImage(CELL_W * DIR_COUNT, CELL_H, QImage.Format.Format_ARGB32)
    bp.fill(QColor(16, 24, 32))
    p2 = QPainter(bp)
    for d, b in enumerate(bases):
        p2.drawImage(d * CELL_W, 0, b)
    p2.end()
    bp.save(str(prev))
    _ = app
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
