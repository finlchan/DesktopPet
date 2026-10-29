"""Terrain top textures for 箱庭斜視 map cells (flat tops only; no skirts).

Bundled under ``hakoniwa/assets/tiles/`` (from project store
``media/tiles/active/``). Logical 1:1 diamond art is drawn into foreshortened
screen diamonds (H = W · sin(45°)) via clip — never under-tile thickness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtGui import QColor, QImage, QPixmap

# Package-local assets (also bundled into frozen EXE via build.bat --add-data).
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TILES_DIR = ASSETS_DIR / "tiles"
OCEAN_BACKGROUND = ASSETS_DIR / "ocean-background.png"

# Primary terrain → active top PNG (flat diamond on black; black keyed out).
TERRAIN_TILE_FILES: Dict[str, str] = {
    "sea": "sea-01.png",
    "shallow": "sea-01.png",
    "oilfield": "sea-01.png",  # reuse sea top + dark wash（色塊；用戶後補平台圖）
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
TERRAIN_TINT: Dict[str, tuple] = {
    "shallow": (90, 180, 200, 70),
    "oilfield": (30, 28, 24, 150),  # 海底油田／石油平台色塊洗
    "forest": (12, 58, 24, 120),
    "mountain": (90, 85, 75, 110),
    "village": (200, 170, 100, 55),
    "town": (180, 120, 70, 70),
    "city": (140, 100, 120, 80),
}

_BLACK_KEY_LUMA = 28  # near-black outside diamond → transparent


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
    """Lazy-loaded terrain tops + optional ocean backdrop."""

    def __init__(self) -> None:
        self._pixmaps: Dict[str, QPixmap] = {}
        self._bg: Optional[QPixmap] = None
        self._bg_tried = False

    def pixmap_for(self, terrain: str) -> Optional[QPixmap]:
        fname = TERRAIN_TILE_FILES.get(terrain)
        if not fname:
            return None
        if fname in self._pixmaps:
            return self._pixmaps[fname]
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
        if self._bg_tried:
            return self._bg if self._bg and not self._bg.isNull() else None
        self._bg_tried = True
        if not OCEAN_BACKGROUND.is_file():
            self._bg = QPixmap()
            return None
        self._bg = QPixmap(str(OCEAN_BACKGROUND))
        return self._bg if not self._bg.isNull() else None

    def has_primary_tops(self) -> bool:
        """True when dirt／grass／sea active tops are all loadable."""
        for key in ("dirt", "grass", "sea"):
            pix = self.pixmap_for(key)
            if pix is None or pix.isNull():
                return False
        return True


# Module singleton used by the map widget.
ATLAS = TileAtlas()
