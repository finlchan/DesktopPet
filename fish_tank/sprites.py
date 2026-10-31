"""RTS isometric pre-rendered pixel swim sprites (8-dir) + side 圖鑑.

Plan items 5 / 7 / 24:
- Swim art = chunky RA2-adjacent pre-rendered pixel sheets (no soft-16% look).
- 8 facings N/NE/E/SE/S/SW/W/NW from PNG strips under ``fish_tank/assets/swim/``.
- Rare = palette remap of the same sheet (no new silhouette).
- Side capture／圖鑑 from ``assets/side/`` (or procedural fallback).
- No realtime 3D in-app — blit only; sheets are offline-generated.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from .facing import DEFAULT_FACING, DIR_COUNT, DIRS, coerce_facing
from .species import SPECIES, SpeciesDef

# Default blit size for legacy RTS sheets (48×40). HD species (青衣) use larger
# cells detected from the PNG strip width/height (see swim_frame_size).
SWIM_W, SWIM_H = 48, 40
SIDE_W, SIDE_H = 96, 56
PLANT_W, PLANT_H = 32, 40

_ASSETS = Path(__file__).resolve().parent / "assets"


def _assets_root() -> Path:
    """Locate assets beside the package (dev) or in PyInstaller extract."""
    candidates = [
        _ASSETS,
        Path.cwd() / "fish_tank" / "assets",
    ]
    try:
        import sys

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.insert(0, Path(sys._MEIPASS) / "fish_tank" / "assets")
    except Exception:
        pass
    for c in candidates:
        if (c / "swim").is_dir():
            return c
    return _ASSETS


def _palette(species: SpeciesDef, rare: bool) -> Tuple[QColor, QColor, QColor, QColor]:
    cols = species.rare_colors if rare else species.base_colors
    return tuple(QColor(*c) for c in cols)  # type: ignore[return-value]


def _load_sheet(path: Path) -> Optional[QImage]:
    if not path.is_file():
        return None
    img = QImage(str(path))
    if img.isNull():
        return None
    return img.convertToFormat(QImage.Format.Format_ARGB32)


def _nearest_palette_map(
    img: QImage,
    src_colors: Tuple[Tuple[int, int, int], ...],
    dst_colors: Tuple[Tuple[int, int, int], ...],
) -> QImage:
    """Remap opaque pixels toward destination palette (rare variant)."""
    out = QImage(img)
    # Build mapping from each src color → dst
    pairs = list(zip(src_colors, dst_colors))
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            if c.alpha() < 40:
                continue
            # Keep near-black outlines
            if c.red() + c.green() + c.blue() < 90:
                continue
            best = None
            best_d = 1e18
            for (sr, sg, sb), dst in pairs:
                d = (c.red() - sr) ** 2 + (c.green() - sg) ** 2 + (c.blue() - sb) ** 2
                if d < best_d:
                    best_d = d
                    best = dst
            if best is not None and best_d < 220 ** 2:
                out.setPixelColor(x, y, QColor(best[0], best[1], best[2], c.alpha()))
    return out


@lru_cache(maxsize=128)
def _swim_sheet_image(species_key: str, rare: bool) -> Optional[QImage]:
    species = SPECIES[species_key]
    path = _assets_root() / "swim" / f"{species_key}.png"
    img = _load_sheet(path)
    if img is None:
        return None
    if rare:
        img = _nearest_palette_map(img, species.base_colors, species.rare_colors)
    return img


@lru_cache(maxsize=64)
def swim_frame_size(species_key: str) -> Tuple[int, int]:
    """Per-species cell size from sheet (width//8, height). Falls back to SWIM_*."""
    if SPECIES[species_key].is_plant:
        return PLANT_W, PLANT_H
    sheet = _swim_sheet_image(species_key, False)
    if sheet is not None and sheet.width() >= DIR_COUNT:
        fw = sheet.width() // DIR_COUNT
        fh = sheet.height()
        if fw > 0 and fh > 0:
            return fw, fh
    return SWIM_W, SWIM_H


@lru_cache(maxsize=256)
def swim_pixmap(
    species_key: str,
    rare: bool = False,
    facing: object = DEFAULT_FACING,
) -> QPixmap:
    """8-dir swim frame. ``facing`` = int 0..7, name, or legacy bool (right=True→E)."""
    species = SPECIES[species_key]
    if species.is_plant:
        return plant_pixmap()

    idx = coerce_facing(facing)
    sheet = _swim_sheet_image(species_key, rare)
    fw, fh = swim_frame_size(species_key)
    if sheet is not None and sheet.width() >= fw * DIR_COUNT and sheet.height() >= fh:
        frame = sheet.copy(idx * fw, 0, fw, fh)
        return QPixmap.fromImage(frame)

    # Fallback empty transparent (assets missing)
    img = QImage(fw, fh, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return QPixmap.fromImage(img)


@lru_cache(maxsize=32)
def plant_pixmap() -> QPixmap:
    path = _assets_root() / "plant" / "waterweed.png"
    img = _load_sheet(path)
    if img is None:
        img = QImage(PLANT_W, PLANT_H, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
    return QPixmap.fromImage(img)


@lru_cache(maxsize=64)
def side_pixmap(species_key: str, rare: bool = False) -> QPixmap:
    """Capture / 圖鑑 side profile (view 2)."""
    species = SPECIES[species_key]
    if species.is_plant:
        return plant_pixmap()
    path = _assets_root() / "side" / f"{species_key}.png"
    img = _load_sheet(path)
    if img is None:
        img = QImage(SIDE_W, SIDE_H, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        return QPixmap.fromImage(img)
    if rare:
        img = _nearest_palette_map(img, species.base_colors, species.rare_colors)
    return QPixmap.fromImage(img)


def warm_cache() -> None:
    """Pre-load all v1 swim facings + side cards (common + rare)."""
    for key, sp in SPECIES.items():
        for rare in (False, True):
            if sp.is_plant:
                plant_pixmap()
                continue
            for facing in range(DIR_COUNT):
                swim_pixmap(key, rare, facing)
            side_pixmap(key, rare)


def sprite_cache_stats() -> Dict[str, int]:
    return {
        "swim": swim_pixmap.cache_info().currsize,
        "side": side_pixmap.cache_info().currsize,
        "sheets": _swim_sheet_image.cache_info().currsize,
    }


def oblique_swim_metrics(species_key: str = "grouper") -> Dict[str, float]:
    """Sanity: swim frames are opaque + differ across opposite facings."""
    pix_e = swim_pixmap(species_key, False, 2)  # E
    pix_n = swim_pixmap(species_key, False, 0)  # N
    img_e = pix_e.toImage()
    img_n = pix_n.toImage()
    opaque_e = sum(
        1
        for y in range(img_e.height())
        for x in range(img_e.width())
        if img_e.pixelColor(x, y).alpha() > 40
    )
    opaque_n = sum(
        1
        for y in range(img_n.height())
        for x in range(img_n.width())
        if img_n.pixelColor(x, y).alpha() > 40
    )
    # Pixel mismatch between E and N (should be different silhouettes).
    diff = 0
    for y in range(min(img_e.height(), img_n.height())):
        for x in range(min(img_e.width(), img_n.width())):
            if img_e.pixelColor(x, y).rgba() != img_n.pixelColor(x, y).rgba():
                diff += 1
    return {
        "opaque_e": float(opaque_e),
        "opaque_n": float(opaque_n),
        "diff_e_n": float(diff),
        "dirs": float(DIR_COUNT),
    }
