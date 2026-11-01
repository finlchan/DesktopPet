#!/usr/bin/env python3
"""Swim-cycle from user **already-debacked** 8-dir RGBA sheets.

Do NOT re-key / re-deback — alpha is authoritative.

Motion (visible amplitude):
  - Tail: left–right swing
  - Dorsal: open / close (flare toward tip ↔ fold toward spine)
  - Lower fins (魚翼): stretch + swing

Trial source:
  media/.../user-debacked/red-bigeye-trial.png → assets/swim/red_bigeye.png

Run: python -m fish_tank.tools.gen_debacked_swim_cycle
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.ndimage import binary_dilation, map_coordinates

ROOT = Path(__file__).resolve().parents[1]
SWIM_OUT = ROOT / "assets" / "swim"
SIDE_OUT = ROOT / "assets" / "side"

SOURCE_CANDIDATES = [
    Path("/cursor/stores/bc-29e56597-c251-41e3-85ea-3d3b81f1b86a/media/fish-tank-phase1-oblique/user-debacked/red-bigeye-trial.png"),
    Path("/cursor/stores/self/media/fish-tank-phase1-oblique/user-debacked/red-bigeye-trial.png"),
]

CELL_W, CELL_H = 120, 100
FRAME_COUNT = 4
DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SPECIES_KEY = "red_bigeye"
SIDE_W, SIDE_H = 96, 56


def _find_source() -> Path:
    for p in SOURCE_CANDIDATES:
        if p.is_file():
            return p
    raise FileNotFoundError("red-bigeye-trial.png not found")


def _extract_bases(rgba: np.ndarray) -> List[np.ndarray]:
    """Split 8 fish using alpha only; fit into CELL_W×CELL_H (nearest)."""
    op = rgba[:, :, 3] > 40
    labeled, n = ndimage.label(op)
    if n == 0:
        raise RuntimeError("no opaque fish in debacked sheet")
    sizes = ndimage.sum(op, labeled, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    fish_ids = [int(i) + 1 for i in order if sizes[i] >= 2000][:8]
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
        raise RuntimeError("failed to order 2×4 grid")

    cells: List[np.ndarray] = []
    for b in ordered:
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        # slight pad but stay within image; keep existing alpha (no re-key)
        pad = 6
        H, W = rgba.shape[:2]
        x0p, y0p = max(0, x0 - pad), max(0, y0 - pad)
        x1p, y1p = min(W - 1, x1 + pad), min(H - 1, y1 + pad)
        cut = rgba[y0p : y1p + 1, x0p : x1p + 1].copy()
        # keep only this fish's alpha component
        local = cut[:, :, 3] > 40
        lab, nloc = ndimage.label(local)
        if nloc > 0:
            sz = ndimage.sum(local, lab, range(1, nloc + 1))
            best = int(np.argmax(sz)) + 1
            cut[lab != best, 3] = 0
        # trim to opaque bbox
        ys, xs = np.where(cut[:, :, 3] > 40)
        cut = cut[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
        im = Image.fromarray(cut, "RGBA")
        tw, th = im.size
        scale = min(CELL_W / tw, CELL_H / th) * 0.94
        nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
        # NEAREST keeps pixel look; do not regenerate alpha via thresholding
        scaled = im.resize((nw, nh), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
        canvas.paste(scaled, ((CELL_W - nw) // 2, (CELL_H - nh) // 2), scaled)
        cells.append(np.array(canvas))
    return cells


def _forward_right(facing: int) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    ang = facing * (math.pi / 4.0)
    fx, fy = math.sin(ang), -math.cos(ang)
    rx, ry = math.cos(ang), math.sin(ang)
    return (fx, fy), (rx, ry)


def _centroid(cell: np.ndarray) -> Tuple[float, float]:
    ys, xs = np.where(cell[:, :, 3] > 40)
    if len(xs) == 0:
        return CELL_W / 2.0, CELL_H / 2.0
    return float(xs.mean()), float(ys.mean())


def _warp_frame(base: np.ndarray, facing: int, frame: int) -> np.ndarray:
    """Inverse-map warp with strong visible fin/tail motion; preserve sampled RGBA."""
    phase = (frame / FRAME_COUNT) * 2.0 * math.pi
    # Explicit phases
    tail = math.sin(phase)  # L/R
    dorsal_open = 0.55 + 0.45 * math.sin(phase + 0.7)  # 0.1..1.0 open amount
    lower = math.sin(phase + math.pi / 2)  # stretch/swing

    (fx, fy), (rx, ry) = _forward_right(facing)
    cx, cy = _centroid(base)
    ux, uy = 0.0, -1.0  # image up ≈ dorsal bias

    ys, xs = np.mgrid[0:CELL_H, 0:CELL_W].astype(np.float32)
    dx = xs - cx
    dy = ys - cy
    along = dx * fx + dy * fy
    across = dx * rx + dy * ry
    upness = dx * ux + dy * uy

    # --- region weights ---
    # Tail: behind nose
    t = np.clip((-along) / 34.0, 0.0, 1.0)
    t = t * t  # tip-weighted

    # Dorsal: upper side, mid-body, near spine band then out to tip
    dorsal_w = np.zeros_like(along)
    d_mask = (along > -8) & (along < 32) & (upness > 1.5)
    dorsal_w[d_mask] = np.clip((upness[d_mask] - 1.5) / 14.0, 0.0, 1.0) * (
        1.0 - np.clip(np.abs(across[d_mask]) / 22.0, 0.0, 1.0) * 0.35
    )

    # Lower fins / 魚翼: belly-ish + outward mid-body
    lower_w = np.zeros_like(along)
    l_mask = (along > -12) & (along < 22) & (np.abs(across) > 5)
    lower_w[l_mask] = np.clip((np.abs(across[l_mask]) - 5) / 14.0, 0.0, 1.0)
    # Prefer belly (negative upness)
    lower_w = np.where(upness < 2.0, lower_w * (1.0 + 0.35 * np.clip(-upness / 12.0, 0, 1)), lower_w * 0.55)

    # Amplitudes (visible)
    amp_tail = 7.5
    amp_dorsal_close = 5.5  # how far tips fold toward spine when closed
    amp_lower_stretch = 4.5
    amp_lower_swing = 5.0

    # Tail L/R (across)
    shift_across = tail * amp_tail * t
    # slight along foreshorten on tail tip
    shift_along = -abs(tail) * 1.4 * t

    # Dorsal open/close: when closed, pull tips toward spine (reduce |across| in source)
    # Inverse map: sample from farther-out across when closed so dest looks folded in
    close = 1.0 - dorsal_open  # 0 open … ~0.9 closed
    # For dorsal pixels, sample from across * (1 + close*k)  → dest appears pulled in
    dorsal_pull = close * amp_dorsal_close * dorsal_w
    # sign: pull toward zero across
    shift_across = shift_across + np.sign(across + 1e-3) * dorsal_pull
    # open lifts tip slightly toward image-up
    shift_along = shift_along + (dorsal_open - 0.55) * 2.2 * dorsal_w
    sx_up = ux * (dorsal_open - 0.55) * 2.8 * dorsal_w
    sy_up = uy * (dorsal_open - 0.55) * 2.8 * dorsal_w

    # Lower fins: stretch (push |across|) + swing
    stretch = (0.5 + 0.5 * lower)  # 0..1
    lower_out = stretch * amp_lower_stretch * lower_w
    # inverse: sample from closer-to-spine when dest is stretched out
    shift_across = shift_across - np.sign(across + 1e-3) * lower_out
    shift_across = shift_across + lower * amp_lower_swing * lower_w * 0.85
    shift_along = shift_along - abs(lower) * 1.2 * lower_w

    sx = xs - (rx * shift_across + fx * shift_along) - sx_up
    sy = ys - (ry * shift_across + fy * shift_along) - sy_up

    out = np.zeros((CELL_H, CELL_W, 4), dtype=np.uint8)
    # Sample each channel with nearest (keep pixel look / alpha)
    for c in range(4):
        sampled = map_coordinates(
            base[:, :, c].astype(np.float32),
            [sy, sx],
            order=0,
            mode="constant",
            cval=0.0,
        )
        out[:, :, c] = np.clip(sampled, 0, 255).astype(np.uint8)

    # Thin outline on new alpha edge (does not re-key body)
    op = out[:, :, 3] > 40
    edge = binary_dilation(op) & ~op
    # only write outline where fully empty
    out[edge] = (18, 22, 26, 255)
    return out


def _side_from_east(cell: np.ndarray) -> np.ndarray:
    ys, xs = np.where(cell[:, :, 3] > 40)
    if len(xs) == 0:
        return np.zeros((SIDE_H, SIDE_W, 4), dtype=np.uint8)
    trimmed = cell[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    im = Image.fromarray(trimmed, "RGBA")
    tw, th = im.size
    scale = min(SIDE_W / tw, SIDE_H / th) * 0.92
    nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
    scaled = im.resize((nw, nh), Image.Resampling.NEAREST)
    out = Image.new("RGBA", (SIDE_W, SIDE_H), (0, 0, 0, 0))
    out.paste(scaled, ((SIDE_W - nw) // 2, (SIDE_H - nh) // 2), scaled)
    return np.array(out)


def main(argv: Sequence[str] | None = None) -> int:
    src = _find_source()
    print("source (debacked, alpha authoritative):", src)
    rgba = np.array(Image.open(src).convert("RGBA"))
    bases = _extract_bases(rgba)
    for i, b in enumerate(bases):
        op = int((b[:, :, 3] > 40).sum())
        print(f"  base {DIRS[i]}: opaque={op}")
        if op < 80:
            print(f"WARNING: {DIRS[i]} sparse", file=sys.stderr)

    sheet = np.zeros((CELL_H * FRAME_COUNT, CELL_W * 8, 4), dtype=np.uint8)
    for d in range(8):
        for f in range(FRAME_COUNT):
            fr = _warp_frame(bases[d], d, f)
            sheet[f * CELL_H : (f + 1) * CELL_H, d * CELL_W : (d + 1) * CELL_W] = fr
            print(f"  {DIRS[d]} f{f}: opaque={int((fr[:,:,3]>40).sum())}")

    SWIM_OUT.mkdir(parents=True, exist_ok=True)
    SIDE_OUT.mkdir(parents=True, exist_ok=True)
    swim_path = SWIM_OUT / f"{SPECIES_KEY}.png"
    Image.fromarray(sheet, "RGBA").save(swim_path)
    side = _side_from_east(bases[2])
    side_path = SIDE_OUT / f"{SPECIES_KEY}.png"
    Image.fromarray(side, "RGBA").save(side_path)
    print(f"wrote {swim_path} + {side_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
