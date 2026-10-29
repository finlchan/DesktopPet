"""Optional user-provided PNG art loader for 箱庭島.

Until the player drops files, buildings／monsters stay color blocks and terrain
uses the bundled sea／dirt／grass tops. Drop PNGs into a user folder to replace
those placeholders — this module never ships new artwork.

Search order (first existing file wins per key):

1. ``{config_dir}/Data/hakoniwa/user/`` — next to the local save (``Data/`` is
   gitignored; preferred runtime drop folder)
2. ``hakoniwa/assets/user/`` — package-local drop folder (PNG ignored by git)

Call :func:`configure_user_art` once the config directory is known (dialog
startup). Smoke／headless paths keep package roots only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from PySide6.QtGui import QImage, QPixmap

from .model import BUILDINGS, MONSTERS, TERRAIN

# Package-local drop folder (no committed PNGs; see README naming table).
ASSETS_USER_DIR = Path(__file__).resolve().parent / "assets" / "user"

# Relative to config parent: beside ``Data/hakoniwa_island.json``.
DATA_USER_REL = Path("Data") / "hakoniwa" / "user"

# ---------------------------------------------------------------------------
# Expected filenames (document in hakoniwa/README.md — do not invent art here)
# ---------------------------------------------------------------------------

# Terrain keys → optional override PNG (else bundled tiles / color wash).
USER_TERRAIN_FILES: Dict[str, str] = {
    "sea": "sea.png",
    "shallow": "shallow.png",
    "oilfield": "oilfield.png",
    "dirt": "dirt.png",
    "grass": "grass.png",
    "forest": "forest.png",
    "mountain": "mountain.png",
    "village": "village.png",
    "town": "town.png",
    "city": "city.png",
}

# Optional sea backdrop override (else bundled ocean-background.png / wash).
USER_OCEAN_BACKGROUND = "ocean-background.png"

# Building keys → optional art (else solid color diamond).
USER_BUILDING_FILES: Dict[str, str] = {
    key: f"{key}.png" for key in BUILDINGS if key is not None
}

# Monster kinds → optional art (else solid color square).
USER_MONSTER_FILES: Dict[str, str] = {
    key: f"{key}.png" for key in MONSTERS
}


def expected_filenames() -> Dict[str, List[str]]:
    """Return the documented naming convention grouped by category."""
    return {
        "terrain": sorted(USER_TERRAIN_FILES.values()),
        "ocean": [USER_OCEAN_BACKGROUND],
        "building": sorted(USER_BUILDING_FILES.values()),
        "monster": sorted(USER_MONSTER_FILES.values()),
    }


def default_user_art_roots(config_dir: Optional[Path] = None) -> List[Path]:
    """Ordered roots: Data/hakoniwa/user then package assets/user."""
    roots: List[Path] = []
    if config_dir is not None:
        roots.append(Path(config_dir).resolve() / DATA_USER_REL)
    roots.append(ASSETS_USER_DIR)
    return roots


class UserArtLoader:
    """Lazy PNG lookup with per-key cache; missing files → None (caller falls back)."""

    def __init__(self, roots: Optional[Sequence[Path]] = None) -> None:
        self._roots: List[Path] = list(roots) if roots else default_user_art_roots()
        self._cache: Dict[str, Optional[QPixmap]] = {}

    def set_roots(self, roots: Sequence[Path]) -> None:
        """Replace search roots and drop the pixmap cache."""
        self._roots = [Path(r) for r in roots]
        self._cache.clear()

    @property
    def roots(self) -> List[Path]:
        return list(self._roots)

    def resolve_path(self, filename: str) -> Optional[Path]:
        """Return the first existing path for ``filename`` across roots."""
        if not filename:
            return None
        for root in self._roots:
            candidate = root / filename
            if candidate.is_file():
                return candidate
        return None

    def path_for_terrain(self, terrain: str) -> Optional[Path]:
        fname = USER_TERRAIN_FILES.get(terrain)
        return self.resolve_path(fname) if fname else None

    def path_for_building(self, kind: str) -> Optional[Path]:
        fname = USER_BUILDING_FILES.get(kind)
        return self.resolve_path(fname) if fname else None

    def path_for_monster(self, kind: str) -> Optional[Path]:
        fname = USER_MONSTER_FILES.get(kind)
        return self.resolve_path(fname) if fname else None

    def path_for_ocean(self) -> Optional[Path]:
        return self.resolve_path(USER_OCEAN_BACKGROUND)

    def _load_pixmap(self, path: Path, *, cache_key: str) -> Optional[QPixmap]:
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached if cached is not None and not cached.isNull() else None
        img = QImage(str(path))
        if img.isNull():
            self._cache[cache_key] = None
            return None
        pix = QPixmap.fromImage(img)
        if pix.isNull():
            self._cache[cache_key] = None
            return None
        self._cache[cache_key] = pix
        return pix

    def terrain_pixmap(self, terrain: str) -> Optional[QPixmap]:
        path = self.path_for_terrain(terrain)
        if path is None:
            return None
        return self._load_pixmap(path, cache_key=f"terrain:{terrain}:{path}")

    def building_pixmap(self, kind: str) -> Optional[QPixmap]:
        path = self.path_for_building(kind)
        if path is None:
            return None
        return self._load_pixmap(path, cache_key=f"building:{kind}:{path}")

    def monster_pixmap(self, kind: str) -> Optional[QPixmap]:
        path = self.path_for_monster(kind)
        if path is None:
            return None
        return self._load_pixmap(path, cache_key=f"monster:{kind}:{path}")

    def ocean_pixmap(self) -> Optional[QPixmap]:
        path = self.path_for_ocean()
        if path is None:
            return None
        return self._load_pixmap(path, cache_key=f"ocean:{path}")

    def present_keys(self) -> Dict[str, List[str]]:
        """Keys that currently resolve to a file (for diagnostics / settings)."""
        found: Dict[str, List[str]] = {
            "terrain": [],
            "building": [],
            "monster": [],
            "ocean": [],
        }
        for key in USER_TERRAIN_FILES:
            if self.path_for_terrain(key) is not None:
                found["terrain"].append(key)
        for key in USER_BUILDING_FILES:
            if self.path_for_building(key) is not None:
                found["building"].append(key)
        for key in USER_MONSTER_FILES:
            if self.path_for_monster(key) is not None:
                found["monster"].append(key)
        if self.path_for_ocean() is not None:
            found["ocean"].append("ocean-background")
        return found


# Module singleton used by TileAtlas / map widget.
LOADER = UserArtLoader()


def configure_user_art(config_dir: Optional[Path] = None) -> UserArtLoader:
    """Point the singleton at Data/hakoniwa/user + package assets/user."""
    LOADER.set_roots(default_user_art_roots(config_dir))
    return LOADER


def assert_naming_covers_catalog() -> None:
    """Dev／smoke helper: every paint-able catalog key has a filename slot."""
    for key in TERRAIN:
        assert key in USER_TERRAIN_FILES, f"missing user terrain filename for {key}"
    for key in BUILDINGS:
        if key is None:
            continue
        assert key in USER_BUILDING_FILES, f"missing user building filename for {key}"
    for key in MONSTERS:
        assert key in USER_MONSTER_FILES, f"missing user monster filename for {key}"


def iter_documented_paths(roots: Optional[Iterable[Path]] = None) -> List[Path]:
    """All documented filenames under the given roots (may not exist yet)."""
    use_roots = list(roots) if roots is not None else LOADER.roots
    names = (
        list(USER_TERRAIN_FILES.values())
        + [USER_OCEAN_BACKGROUND]
        + list(USER_BUILDING_FILES.values())
        + list(USER_MONSTER_FILES.values())
    )
    out: List[Path] = []
    for root in use_roots:
        for name in names:
            out.append(Path(root) / name)
    return out
