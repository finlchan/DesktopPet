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
SPRITES_DIR = ASSETS_DIR / "sprites"
OCEAN_BACKGROUND = ASSETS_DIR / "ocean-background.png"

# Terrain whose user/bundled PNG is a 2.5D prop (building placement), not a
# diamond fill. Ground for these keys stays the bundled top below.
# Forest, oilfield, and crater stay flat tops. 村／町／都市 are buildings.
ELEVATED_SPRITE_TERRAINS = frozenset({"mountain", "onsen_mountain"})
ELEVATED_SPRITE_FILES: Dict[str, str] = {
    "mountain": "mountain.png",
    "onsen_mountain": "onsen_mountain.png",
}
# Buildings that ship a bundled sprite. User drop still wins.
BUNDLED_BUILDING_SPRITES: Dict[str, str] = {
    "onsen_village": "onsen_village.png",
}

# Primary terrain → active top PNG (flat diamond on black; black keyed out).
# 淺灘 = original sea art as-is; 海 = same art recolored deeper blue.
TERRAIN_TILE_FILES: Dict[str, str] = {
    "sea": "sea-01.png",
    "shallow": "shallow-01.png",
    "oilfield": "oilfield-01.png",  # 海面＋油膜（扁平菱形頂）
    "dirt": "dirt-01.png",
    "grass": "grass-01.png",
    "forest": "grass-01.png",
    "mountain": "dirt-01.png",  # ground tile; height is sprites/mountain.png
    "onsen_mountain": "dirt-01.png",  # ground tile; height is sprites/onsen_mountain.png
    "crater": "crater-01.png",  # 荒地＋圓坑（飛彈落空留下）
}

# Optional colour wash after texture (forest / mountain / oilfield stay readable).
# Forest uses grass top + deeper green wash (flat top only; no skirts).
# Shallow keeps un-tinted shallow-01.png; deep sea is baked into sea-01.png.
# 油田／彈坑 use their own tops (no wash — the slick and pit are in the art).
# 村／町／都市 are buildings (USER_BUILDING_FILES) — no terrain tint.
TERRAIN_TINT: Dict[str, tuple] = {
    "forest": (12, 58, 24, 120),
    "mountain": (90, 85, 75, 110),
    "onsen_mountain": (96, 88, 72, 110),
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

    Lookup order per flat terrain: user PNG (if dropped) → bundled ``tiles/`` →
    None (view falls back to solid TERRAIN color). Ocean: user → bundled → wash.
    Mountain is not a flat fill: ``elevated_sprite`` loads that PNG (user drop,
    else ``assets/sprites/``) and the ground tile stays the bundled top.
    """

    def __init__(self) -> None:
        self._pixmaps: Dict[str, QPixmap] = {}
        self._user_terrain: Dict[str, Optional[QPixmap]] = {}
        self._elevated: Dict[str, Optional[QPixmap]] = {}
        self._bundled_buildings: Dict[str, Optional[QPixmap]] = {}
        self._bg: Optional[QPixmap] = None
        self._bg_tried = False
        self._user_bg_tried = False
        self._user_bg: Optional[QPixmap] = None

    def invalidate_user_cache(self) -> None:
        """Clear user-override caches after :func:`configure_user_art`."""
        self._user_terrain.clear()
        self._elevated.clear()
        self._bundled_buildings.clear()
        self._user_bg = None
        self._user_bg_tried = False
        self._bg = None
        self._bg_tried = False
        clear_content_bounds_cache()

    def pixmap_for(self, terrain: str) -> Optional[QPixmap]:
        # 1) Optional user diamond fill. Elevated sprites (mountain／溫泉山) do not
        # replace this top — their PNG is drawn unclipped by elevated_sprite.
        if terrain not in ELEVATED_SPRITE_TERRAINS:
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

    def elevated_sprite(self, terrain: str) -> Optional[QPixmap]:
        """2.5D prop for a terrain cell. None → ground tile only.

        User PNG wins, else the bundled sprite. No black-key
        (dark rock must stay opaque). Placement is the building AABB path.
        """
        if terrain not in ELEVATED_SPRITE_TERRAINS:
            return None
        if terrain in self._elevated:
            cached = self._elevated[terrain]
            return cached if cached is not None and not cached.isNull() else None
        user_pix = USER_ART.terrain_pixmap(terrain)
        if user_pix is not None and not user_pix.isNull():
            self._elevated[terrain] = user_pix
            return user_pix
        fname = ELEVATED_SPRITE_FILES.get(terrain)
        path = SPRITES_DIR / fname if fname else None
        pix = QPixmap(str(path)) if path is not None and path.is_file() else QPixmap()
        self._elevated[terrain] = None if pix.isNull() else pix
        stored = self._elevated[terrain]
        return stored if stored is not None and not stored.isNull() else None

    def building_pixmap(self, kind: str) -> Optional[QPixmap]:
        """User building art, else a shipped sprite, else None (color diamond).

        ``onsen_village`` ships at ``assets/sprites/``. A drop of the same
        name in the user-art folders still replaces it.
        """
        user_pix = USER_ART.building_pixmap(kind)
        if user_pix is not None and not user_pix.isNull():
            return user_pix
        if kind not in BUNDLED_BUILDING_SPRITES:
            return None
        if kind in self._bundled_buildings:
            cached = self._bundled_buildings[kind]
            return cached if cached is not None and not cached.isNull() else None
        fname = BUNDLED_BUILDING_SPRITES[kind]
        path = SPRITES_DIR / fname if fname else None
        pix = QPixmap(str(path)) if path is not None and path.is_file() else QPixmap()
        self._bundled_buildings[kind] = None if pix.isNull() else pix
        stored = self._bundled_buildings[kind]
        return stored if stored is not None and not stored.isNull() else None

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
