"""Procedural ~16% soft pixel placeholders (oblique swim + side capture).

Style target: soft, light grit (plan ~16%). Rare = palette swap only.
Sprites are generated at fixed pixel sizes; the tank view never scales them.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from .species import SPECIES, SpeciesDef

# Fixed on-screen sprite sizes (zoom changes visible range only).
SWIM_W, SWIM_H = 48, 36
SIDE_W, SIDE_H = 96, 56
PLANT_W, PLANT_H = 28, 40


def _soft_pixel(img: QImage, x: int, y: int, color: QColor, grit: float = 0.16) -> None:
    """Plot a soft ~16% grit pixel (slight neighbour bleed)."""
    if x < 0 or y < 0 or x >= img.width() or y >= img.height():
        return
    base = QColor(color)
    img.setPixelColor(x, y, base)
    # Light grit: bleed a dimmer neighbour for soft look.
    dim = QColor(base)
    dim.setAlpha(max(40, int(base.alpha() * grit * 4)))
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < img.width() and 0 <= ny < img.height():
            existing = img.pixelColor(nx, ny)
            if existing.alpha() == 0:
                c = QColor(base.red(), base.green(), base.blue(), int(55 + 80 * grit))
                img.setPixelColor(nx, ny, c)


def _palette(species: SpeciesDef, rare: bool) -> Tuple[QColor, QColor, QColor, QColor]:
    cols = species.rare_colors if rare else species.base_colors
    return tuple(QColor(*c) for c in cols)  # type: ignore[return-value]


def _draw_oblique_fish(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    """High, slightly oblique top-down swim silhouette (view 1)."""
    c0, c1, c2, c3 = colors
    # Body oval (oblique diamond-ish blob).
    body = [
        (18, 14), (19, 14), (20, 14), (21, 14), (22, 14), (23, 14),
        (16, 15), (17, 15), (18, 15), (19, 15), (20, 15), (21, 15), (22, 15), (23, 15), (24, 15), (25, 15),
        (15, 16), (16, 16), (17, 16), (18, 16), (19, 16), (20, 16), (21, 16), (22, 16), (23, 16), (24, 16), (25, 16), (26, 16),
        (14, 17), (15, 17), (16, 17), (17, 17), (18, 17), (19, 17), (20, 17), (21, 17), (22, 17), (23, 17), (24, 17), (25, 17), (26, 17), (27, 17),
        (14, 18), (15, 18), (16, 18), (17, 18), (18, 18), (19, 18), (20, 18), (21, 18), (22, 18), (23, 18), (24, 18), (25, 18), (26, 18), (27, 18),
        (15, 19), (16, 19), (17, 19), (18, 19), (19, 19), (20, 19), (21, 19), (22, 19), (23, 19), (24, 19), (25, 19), (26, 19),
        (17, 20), (18, 20), (19, 20), (20, 20), (21, 20), (22, 20), (23, 20), (24, 20),
    ]
    for x, y in body:
        _soft_pixel(img, x, y, c0)
    # Dorsal ridge (oblique highlight).
    for x, y in ((19, 13), (20, 13), (21, 12), (22, 13), (23, 13)):
        _soft_pixel(img, x, y, c2)
    # Head / eye.
    for x, y in ((26, 16), (27, 16), (26, 17), (27, 17)):
        _soft_pixel(img, x, y, c1)
    _soft_pixel(img, 27, 16, c3)
    # Tail.
    for x, y in ((12, 16), (11, 15), (11, 17), (10, 14), (10, 18), (9, 16)):
        _soft_pixel(img, x, y, c1)
    # Pectoral fin shadow (oblique).
    for x, y in ((20, 21), (21, 22), (22, 21), (19, 22)):
        _soft_pixel(img, x, y, c3)


def _draw_side_fish(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    """Full side-profile capture / 圖鑑 silhouette (view 2)."""
    c0, c1, c2, c3 = colors
    # Main body.
    for y in range(18, 38):
        for x in range(22, 68):
            # Elliptical mask.
            nx = (x - 45) / 24.0
            ny = (y - 28) / 10.0
            if nx * nx + ny * ny <= 1.0:
                _soft_pixel(img, x, y, c0 if (x + y) % 3 else c1)
    # Belly stripe.
    for x in range(28, 62):
        _soft_pixel(img, x, 34, c2)
    # Dorsal fin.
    for i, h in enumerate((4, 7, 9, 8, 6, 4)):
        for dy in range(h):
            _soft_pixel(img, 40 + i * 2, 17 - dy, c2 if dy < 2 else c0)
    # Tail.
    for dy in range(-8, 9):
        span = 6 - abs(dy) // 2
        for dx in range(span):
            _soft_pixel(img, 18 - dx, 28 + dy, c1)
    # Eye.
    _soft_pixel(img, 62, 24, c3)
    _soft_pixel(img, 63, 24, QColor(240, 240, 240))
    _soft_pixel(img, 63, 25, c3)
    # Mouth.
    _soft_pixel(img, 67, 29, c3)
    # Pectoral.
    for x, y in ((48, 36), (49, 37), (50, 38), (51, 37), (52, 36)):
        _soft_pixel(img, x, y, c2)


def _draw_plant(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    c0, c1, c2, c3 = colors
    # Stems.
    for y in range(8, 38):
        _soft_pixel(img, 13, y, c1)
        _soft_pixel(img, 14, y, c0)
    # Leaves (alternating).
    for y in (12, 18, 24, 30):
        for dx in range(1, 8):
            _soft_pixel(img, 14 + dx, y - dx // 3, c2 if dx % 2 == 0 else c0)
            _soft_pixel(img, 13 - dx, y + 3 - dx // 3, c0 if dx % 2 == 0 else c1)
    # Base.
    for x in range(10, 18):
        _soft_pixel(img, x, 38, c3)
        _soft_pixel(img, x, 39, c3)


def _make_image(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


@lru_cache(maxsize=64)
def swim_pixmap(species_key: str, rare: bool = False, facing_right: bool = True) -> QPixmap:
    species = SPECIES[species_key]
    colors = _palette(species, rare)
    img = _make_image(SWIM_W, SWIM_H)
    if species.is_plant:
        _draw_plant(img, colors)
    else:
        _draw_oblique_fish(img, colors)
    if not facing_right and not species.is_plant:
        img = img.mirrored(True, False)
    return QPixmap.fromImage(img)


@lru_cache(maxsize=64)
def side_pixmap(species_key: str, rare: bool = False) -> QPixmap:
    """Capture / 圖鑑 side profile (view 2). Plants reuse swim art scaled."""
    species = SPECIES[species_key]
    colors = _palette(species, rare)
    if species.is_plant:
        img = _make_image(SIDE_W, SIDE_H)
        # Center plant in card.
        plant = _make_image(PLANT_W, PLANT_H)
        _draw_plant(plant, colors)
        p = QPainter(img)
        p.drawImage((SIDE_W - PLANT_W) // 2, (SIDE_H - PLANT_H) // 2, plant)
        p.end()
        return QPixmap.fromImage(img)
    img = _make_image(SIDE_W, SIDE_H)
    _draw_side_fish(img, colors)
    return QPixmap.fromImage(img)


def warm_cache() -> None:
    """Pre-generate all v1 sprites (both views, common + rare)."""
    for key, sp in SPECIES.items():
        for rare in (False, True):
            swim_pixmap(key, rare, True)
            swim_pixmap(key, rare, False)
            side_pixmap(key, rare)


def sprite_cache_stats() -> Dict[str, int]:
    return {
        "swim": swim_pixmap.cache_info().currsize,
        "side": side_pixmap.cache_info().currsize,
    }
