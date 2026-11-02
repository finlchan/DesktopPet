#!/usr/bin/env python3
"""Shared clean-cutout helpers for user HD 8-dir swim sheets.

Strip navy plate, drop shadows, header text, N/NE/… labels, and grid —
return fish-only RGBA cutouts ordered N→NW.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes

DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _chroma(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=2) - rgb.min(axis=2)


def _bright(rgb: np.ndarray) -> np.ndarray:
    return rgb.astype(np.float32).mean(axis=2)


def _is_label(rgb: np.ndarray) -> np.ndarray:
    br = _bright(rgb)
    ch = _chroma(rgb.astype(np.float32))
    return (br > 145) & (ch < 60)


def _bg_sample(rgb: np.ndarray) -> np.ndarray:
    """Estimate plate colour from border strips."""
    h, w = rgb.shape[:2]
    border = np.concatenate(
        [
            rgb[: max(8, h // 40), :].reshape(-1, 3),
            rgb[-max(8, h // 40) :, :].reshape(-1, 3),
            rgb[:, : max(8, w // 40)].reshape(-1, 3),
            rgb[:, -max(8, w // 40) :].reshape(-1, 3),
        ],
        axis=0,
    )
    # Ignore bright label pixels in border estimate
    br = border.astype(np.float32).mean(axis=1)
    ch = border.max(axis=1) - border.min(axis=1)
    keep = ~((br > 140) & (ch < 60))
    sample = border[keep] if keep.any() else border
    return np.median(sample.astype(np.float32), axis=0)


def _fish_mask(rgb: np.ndarray) -> np.ndarray:
    """Foreground mask: not plate, not labels — works for dark and bright fish."""
    bg = _bg_sample(rgb)
    br = _bright(rgb)
    ch = _chroma(rgb.astype(np.float32))
    dist = np.linalg.norm(rgb.astype(np.float32) - bg[None, None, :], axis=2)
    label = _is_label(rgb)
    # Plate-like: near bg colour
    plate = (dist < 22) & (ch < 45) & (br < 70)
    # Soft shadow under fish: darker than bg, low chroma, near plate
    soft = (br < bg.mean() - 4) & (ch < 35) & (dist < 40) & ~label
    # Fish: differs from plate OR chromatic / structured body
    fishy_chroma = (ch > 28) & (br > 35) & ~label
    fishy_diff = (dist > 28) & ~label & ~plate
    # Mid-dark bodies (black porgy etc.): differ modestly, not pure plate
    fishy_dark = (dist > 14) & (br < 120) & ~label & ~plate & (ch >= 8)
    mask = (fishy_chroma | fishy_diff | fishy_dark) & ~soft
    mask = binary_dilation(binary_erosion(mask, iterations=1), iterations=2)
    mask = binary_fill_holes(mask)
    return mask


def _header_end_y(rgb: np.ndarray) -> int:
    """First content row below white header text band."""
    br = _bright(rgb)
    ch = _chroma(rgb.astype(np.float32))
    row_white = ((br > 150) & (ch < 55)).mean(axis=1)
    end = 0
    for y in range(min(220, rgb.shape[0])):
        if row_white[y] > 0.008:
            end = y
    # Also skip a few rows of plate after last text
    return min(rgb.shape[0] // 3, end + 12)


def _grid_bboxes(rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Geometric 2×4 cells under the header (fallback for dark fish)."""
    H, W = rgb.shape[:2]
    y0 = _header_end_y(rgb)
    # Some sheets have a thin margin; inset slightly
    x0, x1 = int(W * 0.02), int(W * 0.98)
    y1 = int(H * 0.98)
    gw, gh = (x1 - x0) // 4, (y1 - y0) // 2
    boxes: List[Tuple[int, int, int, int]] = []
    for r in range(2):
        for c in range(4):
            bx0 = x0 + c * gw
            by0 = y0 + r * gh
            boxes.append((bx0 + 8, by0 + 8, bx0 + gw - 9, by0 + gh - 9))
    return boxes


def _refine_bbox_in_cell(rgb: np.ndarray, cell: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """Within a grid cell, tighten bbox around non-plate content."""
    x0, y0, x1, y1 = cell
    crop = rgb[y0 : y1 + 1, x0 : x1 + 1]
    bg = _bg_sample(crop)
    dist = np.linalg.norm(crop.astype(np.float32) - bg[None, None, :], axis=2)
    br = _bright(crop)
    ch = _chroma(crop.astype(np.float32))
    label = _is_label(crop)
    # Aggressive for dark fish: anything not plate/label
    plate = (dist < 18) & (ch < 40)
    soft = (br < bg.mean() - 6) & (ch < 30) & (dist < 35)
    fg = (~plate) & (~label) & (~soft) & ((dist > 10) | (ch > 18))
    fg = binary_dilation(binary_erosion(fg, iterations=1), iterations=2)
    if not fg.any():
        # Loosen
        fg = (dist > 8) & (~label)
        fg = binary_fill_holes(binary_dilation(fg, iterations=1))
    if not fg.any():
        return cell
    labeled, n = ndimage.label(fg)
    if n == 0:
        return cell
    sizes = ndimage.sum(fg, labeled, range(1, n + 1))
    best = int(np.argmax(sizes)) + 1
    ys, xs = np.where(labeled == best)
    return (
        x0 + int(xs.min()),
        y0 + int(ys.min()),
        x0 + int(xs.max()),
        y0 + int(ys.max()),
    )


def find_fish_bboxes(rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
    mask = _fish_mask(rgb)
    labeled, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, labeled, range(1, n + 1)) if n else np.array([])
    order = np.argsort(sizes)[::-1] if n else []
    min_size = max(2500, int(rgb.shape[0] * rgb.shape[1] * 0.0012))
    fish_ids: List[int] = []
    for i in order:
        if sizes[i] < min_size:
            break
        fish_ids.append(int(i) + 1)
        if len(fish_ids) >= 8:
            break
    if len(fish_ids) < 8:
        fish_ids = [int(i) + 1 for i in order[:8] if sizes[i] >= 800]

    if len(fish_ids) >= 8:
        bboxes = []
        for fid in fish_ids[:8]:
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
        if len(ordered) == 8:
            return [(b[0], b[1], b[2], b[3]) for b in ordered]

    # Fallback: geometric 2×4 under header (dark fish / fused blobs)
    grid = _grid_bboxes(rgb)
    return [_refine_bbox_in_cell(rgb, g) for g in grid]


def clean_cutout(
    rgb: np.ndarray, bbox: Tuple[int, int, int, int], pad: int = 40
) -> np.ndarray:
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = bbox
    x0p, y0p = max(0, x0 - pad), max(0, y0 - pad)
    x1p, y1p = min(W - 1, x1 + pad), min(H - 1, y1 + pad)
    crop = rgb[y0p : y1p + 1, x0p : x1p + 1].copy()
    bg = _bg_sample(crop)
    dist = np.linalg.norm(crop.astype(np.float32) - bg[None, None, :], axis=2)
    br = _bright(crop)
    ch = _chroma(crop.astype(np.float32))
    label = _is_label(crop)
    # Plate / panel fill near sampled bg
    plate = (dist < 24) & (ch < 48)
    soft = (br < float(bg.mean()) - 4) & (ch < 34) & (dist < 40) & (~label)

    # Strong fish core: chromatic OR clearly different from plate
    chroma_core = (ch > 32) & (br > 40) & (~label)
    diff_core = (dist > 26) & (~label) & (~plate)
    dark_core = (dist > 16) & (ch >= 10) & (~label) & (~plate) & (br < 130)
    core = chroma_core | diff_core | dark_core
    core = binary_fill_holes(binary_dilation(binary_erosion(core, iterations=1), iterations=2))
    if not core.any():
        core = (dist > 14) & (~label) & (~plate)
        core = binary_fill_holes(binary_dilation(core, iterations=1))

    labeled, n = ndimage.label(core)
    if n == 0:
        return np.dstack([crop, np.zeros(core.shape, dtype=np.uint8)])
    sizes = ndimage.sum(core, labeled, range(1, n + 1))
    best = int(np.argmax(sizes)) + 1
    keep = binary_fill_holes(labeled == best)
    keep_d = binary_dilation(keep, iterations=3)

    # Allow dark outline / black spots only inside dilated core
    outline = keep_d & (br < 75) & (ch <= 55) & (~label)
    shade = keep_d & (ch > 16) & (br > 35) & (~plate) & (~label)
    fish = keep | outline | shade
    fish = binary_fill_holes(fish)

    # Flood plate/text/shadow from border → must not eat fish core
    floodable = (plate | soft | label | ((~keep_d) & (dist < 30))) & (~keep)
    exterior = np.zeros(fish.shape, dtype=bool)
    exterior[0, :] |= floodable[0, :]
    exterior[-1, :] |= floodable[-1, :]
    exterior[:, 0] |= floodable[:, 0]
    exterior[:, -1] |= floodable[:, -1]
    changed = True
    while changed:
        grow = binary_dilation(exterior) & floodable & ~exterior
        changed = bool(grow.any())
        exterior |= grow

    alpha = np.zeros(fish.shape, dtype=np.uint8)
    alpha[fish & ~exterior & ~label] = 255
    alpha[soft & ~keep] = 0
    alpha[plate & ~keep] = 0
    op = binary_fill_holes(alpha > 0)
    labeled, n = ndimage.label(op)
    if n > 0:
        sizes = ndimage.sum(op, labeled, range(1, n + 1))
        best = int(np.argmax(sizes)) + 1
        op = labeled == best
    return np.dstack([crop, np.where(op, 255, 0).astype(np.uint8)])


def fit_cell(rgba: np.ndarray, cell_w: int, cell_h: int) -> np.ndarray:
    ys, xs = np.where(rgba[:, :, 3] > 40)
    out = np.zeros((cell_h, cell_w, 4), dtype=np.uint8)
    if len(xs) == 0:
        return out
    trimmed = rgba[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    # Drop residual labels
    trimmed = trimmed.copy()
    trimmed[_is_label(trimmed[:, :, :3]), 3] = 0
    im = Image.fromarray(trimmed, "RGBA")
    tw, th = im.size
    scale = min(cell_w / tw, cell_h / th) * 0.92
    nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
    scaled = im.resize((nw, nh), Image.Resampling.NEAREST)
    arr = np.array(scaled)
    br = _bright(arr[:, :, :3])
    ch = _chroma(arr[:, :, :3].astype(np.float32))
    r = arr[:, :, 0].astype(np.float32)
    g = arr[:, :, 1].astype(np.float32)
    b = arr[:, :, 2].astype(np.float32)
    # Navy plate crumbs: bluish, low-mid brightness, low chroma, not yellow/teal punch
    navy = (br > 22) & (br < 58) & (ch < 42) & (b >= r - 2) & (b >= g - 8)
    # Keep true black outline / black spot (very dark)
    navy &= br > 26
    # High-chroma body protects against kill
    punch = (ch > 40) & ((g + b > r * 1.2) | ((r > 140) & (g > 100)))
    kill = _is_label(arr[:, :, :3]) | (navy & ~punch)
    arr[kill, 3] = 0
    arr[arr[:, :, 3] < 40, 3] = 0
    arr[arr[:, :, 3] >= 40, 3] = 255
    # Drop components touching the cell border that look like plate scraps
    op = arr[:, :, 3] > 0
    if op.any():
        labeled, n = ndimage.label(op)
        border = np.zeros_like(op)
        border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
        for i in range(1, n + 1):
            comp = labeled == i
            if (comp & border).any() and int(comp.sum()) < max(40, int(op.sum() * 0.04)):
                arr[comp, 3] = 0
    ox, oy = (cell_w - nw) // 2, (cell_h - nh) // 2
    out[oy : oy + nh, ox : ox + nw] = arr
    return out


def extract_base_cells(
    path: Path, cell_w: int = 120, cell_h: int = 100
) -> List[np.ndarray]:
    rgb = np.array(Image.open(path).convert("RGB"))
    bboxes = find_fish_bboxes(rgb)
    cells: List[np.ndarray] = []
    for bbox in bboxes:
        cut = clean_cutout(rgb, bbox)
        cells.append(fit_cell(cut, cell_w, cell_h))
    return cells


def label_pixel_count(cell: np.ndarray) -> int:
    op = cell[:, :, 3] > 40
    return int((_is_label(cell[:, :, :3]) & op).sum())
