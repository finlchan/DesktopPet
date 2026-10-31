"""Procedural ~16% soft pixel placeholders (HIGH OBLIQUE swim + side capture).

Camera lock (plan item 4 / 7):
- Swim sprites = **high slightly oblique** (bird's-eye tilted). Top of body
  + both pectorals left/right; slight near-flank shade for tilt. NEVER
  eye-level / side-profile for swimming fish.
- Capture／圖鑑 card = full side profile (OK).

Style: soft light grit (~16%). Rare = palette / marking only (same silhouette).
Sprites are generated at fixed pixel sizes; the tank view never scales them.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from .species import SPECIES, SpeciesDef

# Fixed on-screen sprite sizes (zoom changes visible range only).
# Swim canvas is wider than tall so the top-down oval reads clearly.
SWIM_W, SWIM_H = 56, 40
SIDE_W, SIDE_H = 96, 56
PLANT_W, PLANT_H = 32, 40


def _soft_pixel(img: QImage, x: int, y: int, color: QColor, grit: float = 0.16) -> None:
    """Plot a soft ~16% grit pixel (slight neighbour bleed)."""
    if x < 0 or y < 0 or x >= img.width() or y >= img.height():
        return
    base = QColor(color)
    img.setPixelColor(x, y, base)
    dim_a = max(40, int(base.alpha() * grit * 4))
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < img.width() and 0 <= ny < img.height():
            existing = img.pixelColor(nx, ny)
            if existing.alpha() == 0:
                c = QColor(base.red(), base.green(), base.blue(), int(55 + 80 * grit))
                c.setAlpha(min(dim_a + 20, 120))
                img.setPixelColor(nx, ny, c)


def _palette(species: SpeciesDef, rare: bool) -> Tuple[QColor, QColor, QColor, QColor]:
    cols = species.rare_colors if rare else species.base_colors
    return tuple(QColor(*c) for c in cols)  # type: ignore[return-value]


def _draw_oblique_fish(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    """High, slightly oblique bird's-eye swim silhouette (view 1).

    Reads as looking down from above at a slight tilt — NOT a side-profile
    aquarium silhouette. Signals: dorsal ridge centerline, body oval, BOTH
    pectorals left+right, foreshortened near-flank band, tail aft.
    """
    c0, c1, c2, c3 = colors
    cx, cy = 30, 18  # body center; heading +X (right)

    # Soft ground shadow (oblique offset — suggests height above sand).
    shadow = QColor(20, 30, 40, 70)
    for x, y in (
        (cx - 6, cy + 10),
        (cx - 2, cy + 11),
        (cx + 2, cy + 11),
        (cx + 6, cy + 10),
        (cx + 10, cy + 9),
        (cx - 10, cy + 9),
    ):
        _soft_pixel(img, x, y, shadow)

    # Top-down body oval (longer along heading, moderately wide).
    rx, ry = 14.0, 7.5
    for y in range(cy - 9, cy + 10):
        for x in range(cx - 16, cx + 17):
            nx = (x - cx) / rx
            ny = (y - cy) / ry
            if nx * nx + ny * ny <= 1.0:
                # Near-flank band (bottom of oval) = darker = slight oblique tilt.
                if y >= cy + 3:
                    col = c3
                elif y <= cy - 3:
                    col = c2  # far/dorsal highlight
                else:
                    col = c0 if ((x + y) % 4) else c1
                _soft_pixel(img, x, y, col)

    # Dorsal ridge centerline (high camera sees the back ridge).
    for x in range(cx - 10, cx + 12):
        _soft_pixel(img, x, cy - 1, c2)
        if abs(x - cx) < 6:
            _soft_pixel(img, x, cy - 2, c2)

    # Head / snout (front) — both eye dots slightly offset = oblique, not flat top.
    for x, y in ((cx + 13, cy), (cx + 14, cy), (cx + 15, cy - 1), (cx + 15, cy)):
        _soft_pixel(img, x, y, c1)
    _soft_pixel(img, cx + 14, cy - 2, c3)  # far-side eye hint
    _soft_pixel(img, cx + 14, cy + 1, QColor(240, 240, 220, 200))  # near eye

    # Tail aft — V shape opening left (behind).
    for dy in range(-5, 6):
        span = 4 - abs(dy) // 2
        for dx in range(span):
            _soft_pixel(img, cx - 15 - dx, cy + dy, c1 if abs(dy) < 3 else c3)

    # BOTH pectoral fins left + right of body (definitive top-down cue).
    # Far (upper) pectoral — slightly smaller / lighter.
    for i, (dx, dy) in enumerate(
        ((0, -1), (1, -2), (2, -3), (3, -4), (4, -4), (5, -3), (3, -2), (2, -1))
    ):
        _soft_pixel(img, cx - 1 + dx, cy - 6 + dy + 4, c2 if i % 2 == 0 else c1)
    # Near (lower) pectoral — larger, darker (closer to camera).
    for i, (dx, dy) in enumerate(
        ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 4), (4, 3), (2, 2), (1, 1))
    ):
        _soft_pixel(img, cx - 1 + dx, cy + 2 + dy, c3 if i % 2 else c1)

    # Soft side rays (shared silhouette; rare/common differ by palette only).
    for dx in range(0, 5):
        _soft_pixel(img, cx - 4 + dx, cy - 8 - dx // 2, c2)
        _soft_pixel(img, cx - 4 + dx, cy + 8 + dx // 2, c3)


def _draw_side_fish(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    """Full side-profile capture / 圖鑑 silhouette (view 2) — OK per plan item 7."""
    c0, c1, c2, c3 = colors
    for y in range(18, 38):
        for x in range(22, 68):
            nx = (x - 45) / 24.0
            ny = (y - 28) / 10.0
            if nx * nx + ny * ny <= 1.0:
                _soft_pixel(img, x, y, c0 if (x + y) % 3 else c1)
    for x in range(28, 62):
        _soft_pixel(img, x, 34, c2)
    for i, h in enumerate((4, 7, 9, 8, 6, 4)):
        for dy in range(h):
            _soft_pixel(img, 40 + i * 2, 17 - dy, c2 if dy < 2 else c0)
    for dy in range(-8, 9):
        span = 6 - abs(dy) // 2
        for dx in range(span):
            _soft_pixel(img, 18 - dx, 28 + dy, c1)
    _soft_pixel(img, 62, 24, c3)
    _soft_pixel(img, 63, 24, QColor(240, 240, 240))
    _soft_pixel(img, 63, 25, c3)
    _soft_pixel(img, 67, 29, c3)
    for x, y in ((48, 36), (49, 37), (50, 38), (51, 37), (52, 36)):
        _soft_pixel(img, x, y, c2)


def _draw_oblique_plant(img: QImage, colors: Tuple[QColor, QColor, QColor, QColor]) -> None:
    """Waterweed from high oblique — bushy crown, foreshortened stems (not flat side)."""
    c0, c1, c2, c3 = colors
    for x in range(10, 22):
        _soft_pixel(img, x, 36, c3)
        _soft_pixel(img, x, 37, c3)
    for y in range(14, 36):
        _soft_pixel(img, 15, y, c1)
        _soft_pixel(img, 16, y, c0)
        if y % 3 == 0:
            _soft_pixel(img, 14, y, c0)
            _soft_pixel(img, 17, y, c1)
    for angle_i, (dx, dy) in enumerate(
        (
            (0, -6),
            (4, -5),
            (6, -2),
            (5, 2),
            (2, 4),
            (-2, 4),
            (-5, 2),
            (-6, -2),
            (-4, -5),
            (1, -3),
            (-1, -3),
            (3, 0),
            (-3, 0),
        )
    ):
        for t in range(0, 6):
            px = 16 + dx * t // 5
            py = 16 + dy * t // 5
            _soft_pixel(img, px, py, c2 if angle_i % 2 == 0 else c0)


def _make_image(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


@lru_cache(maxsize=64)
def swim_pixmap(species_key: str, rare: bool = False, facing_right: bool = True) -> QPixmap:
    species = SPECIES[species_key]
    colors = _palette(species, rare)
    if species.is_plant:
        img = _make_image(PLANT_W, PLANT_H)
        _draw_oblique_plant(img, colors)
        return QPixmap.fromImage(img)
    img = _make_image(SWIM_W, SWIM_H)
    _draw_oblique_fish(img, colors)
    if not facing_right:
        img = img.mirrored(True, False)
    return QPixmap.fromImage(img)


@lru_cache(maxsize=64)
def side_pixmap(species_key: str, rare: bool = False) -> QPixmap:
    """Capture / 圖鑑 side profile (view 2). Plants reuse oblique plant art centered."""
    species = SPECIES[species_key]
    colors = _palette(species, rare)
    if species.is_plant:
        img = _make_image(SIDE_W, SIDE_H)
        plant = _make_image(PLANT_W, PLANT_H)
        _draw_oblique_plant(plant, colors)
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


def oblique_swim_metrics(species_key: str = "grouper") -> Dict[str, float]:
    """Geometry checks that swim art is top-down oblique, not side-profile.

    Oblique top-down has opaque mass both above and below the horizontal
    midline (bilateral pectorals) and a clear Y span across the canvas.
    """
    pix = swim_pixmap(species_key, False, True)
    img = pix.toImage()
    w, h = img.width(), img.height()
    ys = []
    upper_band = 0
    lower_band = 0
    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() > 40:
                ys.append(y)
                if y < h // 2 - 4:
                    upper_band += 1
                if y > h // 2 + 4:
                    lower_band += 1
    if not ys:
        return {"opaque": 0, "y_span": 0, "upper_band": 0, "lower_band": 0}
    return {
        "opaque": float(len(ys)),
        "y_span": float(max(ys) - min(ys)),
        "upper_band": float(upper_band),
        "lower_band": float(lower_band),
    }
