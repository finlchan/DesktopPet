#!/usr/bin/env python3
"""Build 青衣 8-dir × 4-frame swim-cycle sheet from user stills.

Source: qingyi-user-8dir-source.jpg (header + 2×4: N NE E SE / S SW W NW).
Per facing: 4 frames — tail/body sway + pectoral flap (no realtime 3D).

Cutout rules (user feedback 2026-11-01 HK):
  - Remove navy plate / backdrop
  - Remove sheet frame text, direction labels, grid borders
  - Remove soft ground shadow under fish
  - Keep only the fish (transparent PNG); preserve black spot + outline

Output: fish_tank/assets/swim/grouper.png
  layout: columns = dirs (0..7), rows = frames (0..3)
  cell = 120×100

Requires: PySide6, numpy, scipy, Pillow (offline tool only).

Run: python -m fish_tank.tools.gen_grouper_swim_cycle
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from scipy import ndimage
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "swim" / "grouper.png"
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


def _rgba_to_qimage(rgba: np.ndarray) -> QImage:
    h, w = rgba.shape[:2]
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    for y in range(h):
        for x in range(w):
            r, g, b, a = map(int, rgba[y, x])
            if a:
                img.setPixelColor(x, y, QColor(r, g, b, a))
    return img


def _qimage_from_pil(im: Image.Image) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, QImage.Format.Format_RGBA8888)
    return qimg.copy().convertToFormat(QImage.Format.Format_ARGB32)


def _is_fish_core_arr(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    br = (r + g + b) / 3.0
    ch = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    teal = (g > 65) & (b > 55) & ((g + b) > r * 1.35) & (ch > 28)
    yellow = (r > 120) & (g > 100) & (b < 145) & ((r + g) > b * 2.0) & (ch > 30)
    pale = (r > 100) & (g > 110) & (b > 90) & (ch > 25) & (g >= r * 0.85)
    mid_teal = (g > 90) & (b > 80) & ((g + b) > r * 1.5) & (br > 70) & (ch > 22)
    return teal | yellow | pale | mid_teal


def _is_plate_arr(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    br = (r + g + b) / 3.0
    ch = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    core = _is_fish_core_arr(rgb)
    return (br < 62) & (ch < 48) & (b >= r - 5) & (~core)


def _is_label_arr(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    br = (r + g + b) / 3.0
    ch = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    return (br > 145) & (ch < 60)


def _find_fish_bboxes(rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
    core = _is_fish_core_arr(rgb)
    labeled, n = ndimage.label(core)
    if n == 0:
        raise RuntimeError("no fish cores found")
    sizes = ndimage.sum(core, labeled, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    fish_ids = []
    for i in order:
        if sizes[i] < 5000:
            break
        fish_ids.append(int(i) + 1)
        if len(fish_ids) >= 8:
            break
    if len(fish_ids) < 8:
        raise RuntimeError(f"expected 8 fish blobs, found {len(fish_ids)}")
    bboxes = []
    for fid in fish_ids:
        ys, xs = np.where(labeled == fid)
        bboxes.append(
            (
                int(xs.min()),
                int(ys.min()),
                int(xs.max()),
                int(ys.max()),
                float(xs.mean()),
                float(ys.mean()),
            )
        )
    med_y = float(np.median([b[5] for b in bboxes]))
    top = sorted([b for b in bboxes if b[5] < med_y], key=lambda b: b[4])
    bot = sorted([b for b in bboxes if b[5] >= med_y], key=lambda b: b[4])
    ordered = top + bot
    if len(ordered) != 8:
        raise RuntimeError("failed to order 2×4 fish grid")
    return [(b[0], b[1], b[2], b[3]) for b in ordered]


def _clean_cutout(rgb: np.ndarray, bbox: Tuple[int, int, int, int], pad: int = 48) -> np.ndarray:
    """Return RGBA uint8 cutout — fish only, transparent elsewhere."""
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = bbox
    x0p, y0p = max(0, x0 - pad), max(0, y0 - pad)
    x1p, y1p = min(W - 1, x1 + pad), min(H - 1, y1 + pad)
    crop = rgb[y0p : y1p + 1, x0p : x1p + 1].copy()
    r = crop[:, :, 0].astype(np.float32)
    g = crop[:, :, 1].astype(np.float32)
    b = crop[:, :, 2].astype(np.float32)
    br = (r + g + b) / 3.0
    ch = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)

    core = _is_fish_core_arr(crop)
    core_d = binary_dilation(core, iterations=5)
    dark = core_d & (br < 70) & (ch <= 55)
    shade = core_d & (ch > 18) & (br > 35) & (g > 45) & (b > 40) & ((g + b) > r * 1.15)
    keep = core | dark | shade
    keep = binary_dilation(binary_erosion(keep, iterations=1), iterations=2)
    keep = binary_fill_holes(keep)

    plate = _is_plate_arr(crop)
    text = _is_label_arr(crop)
    soft_shadow = (~binary_dilation(core, iterations=2)) & (br < 45) & (ch < 35)
    floodable = plate | text | soft_shadow | ((~core_d) & (br < 90))

    # Flood from border through floodable → background
    exterior = np.zeros(keep.shape, dtype=bool)
    exterior[0, :] = floodable[0, :]
    exterior[-1, :] = floodable[-1, :]
    exterior[:, 0] = floodable[:, 0]
    exterior[:, -1] = floodable[:, -1]
    # iterative grow (cheap enough at cell size)
    changed = True
    while changed:
        dil = binary_dilation(exterior) & floodable
        new = dil & ~exterior
        changed = bool(new.any())
        exterior |= new

    alpha = np.zeros(keep.shape, dtype=np.uint8)
    alpha[keep & ~exterior] = 255
    alpha[text] = 0
    alpha[(~core_d) & plate] = 0
    alpha[soft_shadow] = 0

    # Largest component + fill holes (preserve black spot)
    op = alpha > 0
    op = binary_fill_holes(op)
    labeled, n = ndimage.label(op)
    if n > 0:
        sizes = ndimage.sum(op, labeled, range(1, n + 1))
        best = int(np.argmax(sizes)) + 1
        op = labeled == best
    alpha = np.where(op, 255, 0).astype(np.uint8)

    rgba = np.dstack([crop, alpha])
    # Hole-filled pixels that were transparent → dark opaque (black spot)
    filled_only = op & (rgba[:, :, 3] == 0)
    # Actually alpha already set from op; ensure RGB for former holes
    was_clear = (crop.sum(axis=2) == 0)  # won't happen from jpg
    # For pixels that were plate-dark inside silhouette, keep their RGB;
    # if somehow zeroed, paint near-black
    hole_rgb = op & plate & (br < 40)
    rgba[hole_rgb, 0:3] = (12, 14, 18)
    rgba[:, :, 3] = alpha
    _ = was_clear
    _ = filled_only
    return rgba


def _fit_cell(rgba: np.ndarray) -> QImage:
    ys, xs = np.where(rgba[:, :, 3] > 40)
    if len(xs) == 0:
        canvas = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        return canvas
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    trimmed = rgba[y0 : y1 + 1, x0 : x1 + 1]
    # Force binary alpha; drop residual plate/label crumbs
    rgb = trimmed[:, :, :3]
    a = trimmed[:, :, 3] > 40
    a &= ~_is_label_arr(rgb)
    # Drop plate-like only when not dark-on-fish (black spot/outline stay)
    plate = _is_plate_arr(rgb)
    br = rgb.astype(np.float32).mean(axis=2)
    # plate crumbs at cell edge: remove; keep dark interior plate-ish as outline
    edge = np.zeros(a.shape, dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge = binary_dilation(edge, iterations=2)
    a &= ~(plate & edge)
    a &= ~(plate & (br > 32) & (br < 55))  # mid navy panel crumbs
    cleaned = np.dstack([rgb, np.where(a, 255, 0).astype(np.uint8)])
    im = Image.fromarray(cleaned, "RGBA")
    tw, th = im.size
    scale = min(CELL_W / tw, CELL_H / th) * 0.92
    nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
    scaled = im.resize((nw, nh), Image.Resampling.NEAREST)
    # After scale, kill any leftover plate/label
    arr = np.array(scaled)
    kill = _is_label_arr(arr[:, :, :3]) | (
        _is_plate_arr(arr[:, :, :3]) & (arr[:, :, :3].mean(axis=2) > 28)
    )
    arr[kill, 3] = 0
    arr[arr[:, :, 3] < 40, 3] = 0
    arr[arr[:, :, 3] >= 40, 3] = 255
    canvas = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    canvas.paste(Image.fromarray(arr), ((CELL_W - nw) // 2, (CELL_H - nh) // 2), Image.fromarray(arr))
    return _qimage_from_pil(canvas)


def _extract_bases(rgb: np.ndarray) -> List[QImage]:
    bboxes = _find_fish_bboxes(rgb)
    bases: List[QImage] = []
    for i, bbox in enumerate(bboxes):
        cut = _clean_cutout(rgb, bbox)
        cell = _fit_cell(cut)
        opaque = label_px = plate_px = 0
        for y in range(CELL_H):
            for x in range(CELL_W):
                c = cell.pixelColor(x, y)
                if c.alpha() <= 40:
                    continue
                opaque += 1
                r, g, b = c.red(), c.green(), c.blue()
                br = (r + g + b) / 3.0
                ch = max(r, g, b) - min(r, g, b)
                if br > 145 and ch < 60:
                    label_px += 1
                if br < 62 and ch < 48 and b >= r - 5 and not (
                    (g > 65 and b > 55 and (g + b) > r * 1.35 and ch > 28)
                    or (r > 120 and g > 100 and b < 145 and ch > 30)
                ):
                    # allow dark outline / black spot (br very low)
                    if br > 28:
                        plate_px += 1
        print(f"  base {DIRS[i]}: opaque={opaque} label_px={label_px} plate_px={plate_px}")
        if label_px > 0:
            raise RuntimeError(f"{DIRS[i]} still has label pixels ({label_px})")
        if plate_px > 80:
            raise RuntimeError(f"{DIRS[i]} still has plate pixels ({plate_px})")
        bases.append(cell)
    return bases


def _forward_right(facing: int) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    ang = facing * (math.pi / 4.0)
    fx, fy = math.sin(ang), -math.cos(ang)
    rx, ry = math.cos(ang), math.sin(ang)
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
    phase = (frame / FRAME_COUNT) * 2.0 * math.pi
    sway = math.sin(phase)
    pec = math.sin(phase + math.pi / 2) * 0.7
    (fx, fy), (rx, ry) = _forward_right(facing)
    cx, cy = _centroid(base)

    out = QImage(CELL_W, CELL_H, QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.transparent)
    amp_tail, amp_body, amp_pec = 4.2, 1.6, 2.2
    for y in range(CELL_H):
        for x in range(CELL_W):
            dx, dy = x - cx, y - cy
            along = dx * fx + dy * fy
            across = dx * rx + dy * ry
            t = max(0.0, min(1.0, (-along) / 38.0))
            body_t = max(0.0, min(1.0, (-along + 8) / 45.0))
            pec_w = 0.0
            if -8 < along < 18 and abs(across) > 8:
                pec_w = min(1.0, (abs(across) - 8) / 16.0)
            shift_across = sway * (amp_tail * t * t + amp_body * body_t * 0.5)
            shift_across += pec * amp_pec * pec_w * (1.0 if across >= 0 else -1.0) * 0.35
            shift_along = -abs(sway) * 0.8 * t
            sx = x - (rx * shift_across + fx * shift_along)
            sy = y - (ry * shift_across + fy * shift_along)
            ix, iy = int(round(sx)), int(round(sy))
            if 0 <= ix < CELL_W and 0 <= iy < CELL_H:
                col = base.pixelColor(ix, iy)
                if col.alpha() > 0:
                    out.setPixelColor(x, y, col)

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
    rgb = np.array(Image.open(src_path).convert("RGB"))
    bases = _extract_bases(rgb)
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
