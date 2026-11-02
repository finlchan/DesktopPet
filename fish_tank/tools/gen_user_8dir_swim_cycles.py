#!/usr/bin/env python3
"""Batch-build HD 8-dir × 4-frame swim sheets from user JPGs.

Motion per facing (not tail-only):
  (a) tail sway
  (b) dorsal fin flap
  (c) lower / pectoral fins (魚翼)

Also writes side 圖鑑 cards from E facing frame 0.

Run: QT_QPA_PLATFORM=offscreen python -m fish_tank.tools.gen_user_8dir_swim_cycles
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

from .sheet_cutout import DIRS, extract_base_cells, label_pixel_count

ROOT = Path(__file__).resolve().parents[1]
SWIM_OUT = ROOT / "assets" / "swim"
SIDE_OUT = ROOT / "assets" / "side"
SOURCE_DIRS = [
    Path("/cursor/stores/bc-29e56597-c251-41e3-85ea-3d3b81f1b86a/media/fish-tank-phase1-oblique/user-8dir-sheets"),
    Path("/cursor/stores/self/media/fish-tank-phase1-oblique/user-8dir-sheets"),
]

CELL_W, CELL_H = 120, 100
FRAME_COUNT = 4
SIDE_W, SIDE_H = 96, 56


@dataclass(frozen=True)
class SheetSpec:
    key: str
    file: str  # filename in user-8dir-sheets
    note: str = ""


# Unique processable 8-dir swim sheets (duplicates / non-sheets excluded).
SHEETS: Sequence[SheetSpec] = (
    SheetSpec("grouper", "f028acaf-e27a-4a63-bdda-0aff781d154e.jpg", "青衣"),
    SheetSpec("mudskipper", "a95434bf-a4ea-4d01-b985-82feaac451bc.jpg", "泥鯭"),
    SheetSpec("golden_threadfin", "3bb4247a-1436-482a-a466-98580d95cfa2.jpg", "紅衫魚"),
    SheetSpec("red_bigeye", "8c04fdff-548a-4998-aabc-b22c05911d07.jpg", "大眼雞"),
    SheetSpec("red_seabream", "e9188087-af11-4717-8d82-5f31f7ce6609.jpg", "紅鯛"),
    SheetSpec("goldstriped_seabream", "2c4a2dd4-45e0-48d4-8bfd-97a88ef36759.jpg", "黃腳鯛"),
    SheetSpec("yellow_croaker", "f6523da9-aa9e-4a7a-8dac-dd58c438b079.jpg", "黃魚"),
    SheetSpec("japanese_threadfin", "0126726d-1fff-4a75-8fce-9c73d30f5053.jpg", "金線魚"),
    SheetSpec("leopard_coral_grouper", "3a973a64-f5f0-4259-b198-76d072ef3db1.jpg", "東星斑"),
    SheetSpec("silver_tilefish", "69a9a93e-1f95-4fe0-aadb-10c12f21d47e.jpg", "馬頭魚"),
    SheetSpec("tongue_sole", "aed91b0a-b085-4016-8c88-2029207050a6.jpg", "撻沙魚"),
    SheetSpec("fourfinger_threadfin", "bbbe3699-e4d5-4ae8-a715-cb6e4a49b8ed.jpg", "馬友魚"),
    SheetSpec("snubnose_pompano", "c6dbcdf8-936c-4a2d-8c09-2de235f03247.jpg", "黃立倉"),
    SheetSpec("grey_mullet", "04f95042-d9e3-432b-9769-0a254ff202bc.jpg", "烏頭"),
    SheetSpec("black_porgy", "31d885fb-9105-4ac0-88e4-6ffa630018a2.jpg", "黑鯛"),
    SheetSpec("japanese_scad", "9ea2512a-1665-4d1f-a7fc-8553fd688954.jpg", "池魚"),
    SheetSpec("chinese_pomfret", "ca96ed77-c32c-43d1-886a-f4ca6dc16129.jpg", "鷹鯧"),
    SheetSpec("slender_lizardfish", "cba405fd-202e-4143-8a2b-5fe7fe2d101b.jpg", "九棍魚"),
)

SKIPPED = {
    "fd59d507-6475-4b4b-a7af-ab6918d96e33.jpg": "exact duplicate of 青衣 sheet f028acaf…",
    "4f5dcb48-b9e5-4b1b-989b-e43fc3597c82.jpg": "not a fish sheet (GitHub Releases UI screenshot)",
    "9ff26d6c-14b1-4cd7-8108-9f780a554595.jpg": "quality-ref plate / style still (not 8-dir grid)",
}


def _find_source_dir() -> Path:
    for d in SOURCE_DIRS:
        if d.is_dir():
            return d
    raise FileNotFoundError("user-8dir-sheets directory not found")


def _forward_right(facing: int) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    ang = facing * (math.pi / 4.0)
    fx, fy = math.sin(ang), -math.cos(ang)
    rx, ry = math.cos(ang), math.sin(ang)
    return (fx, fy), (rx, ry)


def _centroid(cell: np.ndarray) -> Tuple[float, float]:
    ys, xs = np.where(cell[:, :, 3] > 40)
    if len(xs) == 0:
        return CELL_W / 2, CELL_H / 2
    return float(xs.mean()), float(ys.mean())


def _warp_frame(base: np.ndarray, facing: int, frame: int) -> np.ndarray:
    """Tail + dorsal + pectoral/lower-fin motion (vectorized)."""
    phase = (frame / FRAME_COUNT) * 2.0 * math.pi
    sway = math.sin(phase)
    dorsal = math.sin(phase + 0.9) * 0.85
    pec = math.sin(phase + math.pi / 2) * 0.9
    (fx, fy), (rx, ry) = _forward_right(facing)
    cx, cy = _centroid(base)
    ux, uy = 0.0, -1.0

    ys, xs = np.mgrid[0:CELL_H, 0:CELL_W]
    dx = xs.astype(np.float32) - cx
    dy = ys.astype(np.float32) - cy
    along = dx * fx + dy * fy
    across = dx * rx + dy * ry
    upness = dx * ux + dy * uy

    t = np.clip((-along) / 38.0, 0.0, 1.0)
    body_t = np.clip((-along + 8) / 45.0, 0.0, 1.0)

    dorsal_w = np.zeros_like(along)
    d_mask = (along > -6) & (along < 28) & (upness > 2)
    dorsal_w[d_mask] = np.minimum(1.0, (upness[d_mask] - 2) / 16.0) * (
        1.0 - np.minimum(1.0, np.abs(across[d_mask]) / 14.0)
    )

    pec_w = np.zeros_like(along)
    p_mask = (along > -10) & (along < 20) & (np.abs(across) > 7)
    pec_w[p_mask] = np.minimum(1.0, (np.abs(across[p_mask]) - 7) / 15.0)
    pec_w = np.where(upness < 0, pec_w * 1.15, pec_w)

    amp_tail, amp_body, amp_dorsal, amp_pec = 4.4, 1.5, 2.8, 2.6
    shift_across = sway * (amp_tail * t * t + amp_body * body_t * 0.45)
    shift_across = shift_across + pec * amp_pec * pec_w * np.where(across >= 0, 1.0, -1.0) * 0.4
    shift_across = shift_across + dorsal * amp_dorsal * dorsal_w * 0.55
    shift_along = -abs(sway) * 0.75 * t
    shift_along = shift_along + dorsal * 1.2 * dorsal_w
    shift_along = shift_along - abs(pec) * 0.6 * pec_w

    sx = xs - (rx * shift_across + fx * shift_along) - ux * dorsal * 1.1 * dorsal_w
    sy = ys - (ry * shift_across + fy * shift_along) - uy * dorsal * 1.1 * dorsal_w
    ix = np.rint(sx).astype(np.int32)
    iy = np.rint(sy).astype(np.int32)
    valid = (ix >= 0) & (ix < CELL_W) & (iy >= 0) & (iy < CELL_H)
    out = np.zeros((CELL_H, CELL_W, 4), dtype=np.uint8)
    # Sample
    src_a = np.zeros((CELL_H, CELL_W), dtype=np.uint8)
    src_a[valid] = base[iy[valid], ix[valid], 3]
    take = valid & (src_a > 0)
    out[take] = base[iy[take], ix[take]]

    # Thin outline
    op = out[:, :, 3] > 40
    edge = binary_dilation(op) & ~op
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


def process_sheet(spec: SheetSpec, src_dir: Path) -> Dict[str, object]:
    path = src_dir / spec.file
    if not path.is_file():
        raise FileNotFoundError(path)
    print(f"\n=== {spec.key} ({spec.note}) ← {spec.file}")
    bases = extract_base_cells(path, CELL_W, CELL_H)
    for i, b in enumerate(bases):
        op = int((b[:, :, 3] > 40).sum())
        lab = label_pixel_count(b)
        print(f"  base {DIRS[i]}: opaque={op} label_px={lab}")
        if lab > 0:
            raise RuntimeError(f"{spec.key} {DIRS[i]} still has label pixels")
        if op < 80:
            raise RuntimeError(f"{spec.key} {DIRS[i]} cutout too empty ({op})")

    sheet = np.zeros((CELL_H * FRAME_COUNT, CELL_W * 8, 4), dtype=np.uint8)
    for d in range(8):
        for f in range(FRAME_COUNT):
            fr = _warp_frame(bases[d], d, f)
            sheet[f * CELL_H : (f + 1) * CELL_H, d * CELL_W : (d + 1) * CELL_W] = fr
            print(f"  {DIRS[d]} f{f}: opaque={int((fr[:,:,3]>40).sum())}")

    SWIM_OUT.mkdir(parents=True, exist_ok=True)
    SIDE_OUT.mkdir(parents=True, exist_ok=True)
    swim_path = SWIM_OUT / f"{spec.key}.png"
    Image.fromarray(sheet, "RGBA").save(swim_path)
    side = _side_from_east(bases[2])  # E
    side_path = SIDE_OUT / f"{spec.key}.png"
    Image.fromarray(side, "RGBA").save(side_path)
    print(f"  wrote {swim_path.name} + side")
    return {"key": spec.key, "swim": str(swim_path), "side": str(side_path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    only = set(argv[1:] if argv is not None else sys.argv[1:])
    src_dir = _find_source_dir()
    print("source dir:", src_dir)
    print("skipped:")
    for k, v in SKIPPED.items():
        print(f"  - {k}: {v}")
    results = []
    errors = []
    for spec in SHEETS:
        if only and spec.key not in only and spec.file not in only:
            continue
        try:
            results.append(process_sheet(spec, src_dir))
        except Exception as e:
            errors.append((spec.key, str(e)))
            print(f"  ERROR {spec.key}: {e}", file=sys.stderr)
    print(f"\nDone OK={len(results)} ERR={len(errors)}")
    for k, msg in errors:
        print(f"  FAIL {k}: {msg}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
