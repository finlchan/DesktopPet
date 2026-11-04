"""Terrain top textures for 箱庭斜視 map cells (flat tops only; no skirts).

Bundled under ``hakoniwa/assets/tiles/`` (from project store
``media/tiles/active/``). Logical 1:1 diamond art is drawn into foreshortened
screen diamonds (H = W · OBLIQUE_Y_SCALE, 0.65) via clip — never under-tile thickness.

Optional user overrides (``Data/hakoniwa/user/`` or ``assets/user/``) are
checked first via :mod:`hakoniwa.user_art`; missing files keep bundled tops.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPixmap

from .user_art import LOADER as USER_ART

# Tight AABB of non-transparent pixels, keyed by QPixmap.cacheKey().
_CONTENT_BOUNDS: Dict[int, QRect] = {}
_ALPHA_MIN = 8  # treat near-transparent as empty

# Package-local assets (also bundled into frozen EXE via build.bat --add-data).
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TILES_DIR = ASSETS_DIR / "tiles"
OCEAN_BACKGROUND = ASSETS_DIR / "ocean-background.png"

# Primary terrain → active top PNG (flat diamond on black; black keyed out).
# 淺灘 = original sea art as-is; 海 = same art recolored deeper blue.
TERRAIN_TILE_FILES: Dict[str, str] = {
    "sea": "sea-01.png",
    "shallow": "shallow-01.png",
    "oilfield": "sea-01.png",  # reuse deep-sea top + dark wash（色塊；用戶後補平台圖）
    "dirt": "dirt-01.png",
    "grass": "grass-01.png",
    "forest": "grass-01.png",
    "mountain": "dirt-01.png",  # reuse dirt top + wash（色塊；用戶後補山圖）
    "village": "dirt-01.png",
    "town": "dirt-01.png",
    "city": "dirt-01.png",
}

# Optional colour wash after texture (settlements / forest stay readable).
# Forest uses grass top + deeper green wash (flat top only; no skirts).
# Shallow keeps un-tinted shallow-01.png; deep sea is baked into sea-01.png.
TERRAIN_TINT: Dict[str, tuple] = {
    "oilfield": (30, 28, 24, 150),  # 海底油田／石油平台色塊洗
    "forest": (12, 58, 24, 120),
    "mountain": (90, 85, 75, 110),
    "village": (200, 170, 100, 55),
    "town": (180, 120, 70, 70),
    "city": (140, 100, 120, 80),
}

_BLACK_KEY_LUMA = 28  # near-black outside diamond → transparent


def clear_content_bounds_cache() -> None:
    """Drop alpha-content AABB cache (call with atlas user-cache invalidate)."""
    _CONTENT_BOUNDS.clear()


def alpha_content_rect(pix: QPixmap, alpha_min: int = _ALPHA_MIN) -> QRect:
    """Return the tight AABB of pixels with alpha > ``alpha_min``.

    Used so building／user sprites align by **visible content**, not PNG canvas
    padding. Empty／fully-transparent images fall back to the full pixmap rect.
    """
    if pix is None or pix.isNull():
        return QRect()
    key = int(pix.cacheKey())
    cached = _CONTENT_BOUNDS.get(key)
    if cached is not None:
        return QRect(cached)
    img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if (img.pixel(x, y) >> 24) & 0xFF > alpha_min:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x < 0:
        rect = QRect(0, 0, w, h)
    else:
        rect = QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    _CONTENT_BOUNDS[key] = QRect(rect)
    return rect


def _key_black_to_alpha(img: QImage) -> QImage:
    """Make near-black backdrop transparent so diamond tops composite cleanly."""
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            c = QColor(out.pixel(x, y))
            if c.red() + c.green() + c.blue() < _BLACK_KEY_LUMA:
                c.setAlpha(0)
                out.setPixelColor(x, y, c)
    return out


class TileAtlas:
    """Lazy-loaded terrain tops + optional ocean backdrop.

    Lookup order per terrain: user PNG (if dropped) → bundled ``tiles/`` → None
    (view falls back to solid TERRAIN color). Ocean: user → bundled → wash.
    """

    def __init__(self) -> None:
        self._pixmaps: Dict[str, QPixmap] = {}
        self._user_terrain: Dict[str, Optional[QPixmap]] = {}
        self._bg: Optional[QPixmap] = None
        self._bg_tried = False
        self._user_bg_tried = False
        self._user_bg: Optional[QPixmap] = None

    def invalidate_user_cache(self) -> None:
        """Clear user-override caches after :func:`configure_user_art`."""
        self._user_terrain.clear()
        self._user_bg = None
        self._user_bg_tried = False
        self._bg = None
        self._bg_tried = False
        clear_content_bounds_cache()

    def pixmap_for(self, terrain: str) -> Optional[QPixmap]:
        # 1) Optional user override (no new art shipped — only if file exists).
        if terrain in self._user_terrain:
            user_cached = self._user_terrain[terrain]
            if user_cached is not None and not user_cached.isNull():
                return user_cached
        else:
            user_pix = USER_ART.terrain_pixmap(terrain)
            if user_pix is not None and not user_pix.isNull():
                # Apply same black-key as bundled diamond tops when needed.
                img = user_pix.toImage()
                keyed = QPixmap.fromImage(_key_black_to_alpha(img))
                self._user_terrain[terrain] = keyed if not keyed.isNull() else user_pix
                return self._user_terrain[terrain]
            self._user_terrain[terrain] = None

        # 2) Bundled active tops (sea／dirt／grass and aliases).
        fname = TERRAIN_TILE_FILES.get(terrain)
        if not fname:
            return None
        if fname in self._pixmaps:
            pix = self._pixmaps[fname]
            return pix if not pix.isNull() else None
        path = TILES_DIR / fname
        if not path.is_file():
            self._pixmaps[fname] = QPixmap()
            return None
        img = QImage(str(path))
        if img.isNull():
            self._pixmaps[fname] = QPixmap()
            return None
        pix = QPixmap.fromImage(_key_black_to_alpha(img))
        self._pixmaps[fname] = pix
        return pix if not pix.isNull() else None

    def tint_for(self, terrain: str) -> Optional[QColor]:
        rgba = TERRAIN_TINT.get(terrain)
        if not rgba:
            return None
        return QColor(*rgba)

    def ocean_background(self) -> Optional[QPixmap]:
        if not self._user_bg_tried:
            self._user_bg_tried = True
            user_bg = USER_ART.ocean_pixmap()
            if user_bg is not None and not user_bg.isNull():
                self._user_bg = user_bg
        if self._user_bg is not None and not self._user_bg.isNull():
            return self._user_bg

        if self._bg_tried:
            return self._bg if self._bg and not self._bg.isNull() else None
        self._bg_tried = True
        if not OCEAN_BACKGROUND.is_file():
            self._bg = QPixmap()
            return None
        self._bg = QPixmap(str(OCEAN_BACKGROUND))
        return self._bg if not self._bg.isNull() else None

    def building_pixmap(self, kind: str) -> Optional[QPixmap]:
        """Optional user building art; None → view paints color diamond."""
        return USER_ART.building_pixmap(kind)

    def monster_pixmap(self, kind: str) -> Optional[QPixmap]:
        """Optional user monster art; None → view paints color square."""
        return USER_ART.monster_pixmap(kind)

    def has_primary_tops(self) -> bool:
        """True when dirt／grass／sea／shallow active tops are all loadable."""
        for key in ("dirt", "grass", "sea", "shallow"):
            pix = self.pixmap_for(key)
            if pix is None or pix.isNull():
                return False
        return True


# Module singleton used by the map widget.
ATLAS = TileAtlas()
