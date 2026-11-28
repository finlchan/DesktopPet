"""Classic dual height-buffer water ripple (low-res sim → UV-offset sample → upscale).

Algorithm per cell:
    next = (avg(left, right, up, down) * 2 - prev) * damping

Rendering samples a bundled sea-surface photo/texture with offsets from the
height gradient, then the caller upscales to the view. Bubbles are drawn by
the scene above this layer (not stamped into the refracted backdrop).
"""

from __future__ import annotations

import sys
from array import array
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtGui import QColor, QImage, QPainter, QLinearGradient
from PySide6.QtCore import Qt

# Steel-blue pool palette (underlay + fallback if sea-surface.jpg is missing)
WATER_DEEP = QColor(22, 34, 48)
WATER_MID = QColor(36, 58, 82)

DEFAULT_DAMPING = 0.965
# Cap sim resolution so Python loops stay interactive on modest hardware.
MAX_SIM_W = 220
MAX_SIM_H = 160
MIN_SCALE = 3

# User-provided ocean photo (bundled). Drawn at SEA_SURFACE_OPACITY over the pool underlay.
SEA_SURFACE_NAME = "sea-surface.jpg"
SEA_SURFACE_OPACITY = 0.60


def _assets_root() -> Path:
    """Locate map_bubbles/assets beside the package (dev) or in PyInstaller extract."""
    here = Path(__file__).resolve().parent / "assets"
    candidates = [here, Path.cwd() / "map_bubbles" / "assets"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "map_bubbles" / "assets")
    for c in candidates:
        if c.is_dir():
            return c
    return here


@lru_cache(maxsize=1)
def load_sea_surface() -> Optional[QImage]:
    """Load the bundled ocean photo (RGB32). Cached once per process.

    Prefers ``sea-surface.jpg``; falls back to legacy ``sea-surface.png``.
    """
    root = _assets_root()
    for name in (SEA_SURFACE_NAME, "sea-surface.png"):
        path = root / name
        if not path.is_file():
            continue
        img = QImage(str(path))
        if not img.isNull():
            return img.convertToFormat(QImage.Format.Format_RGB32)
    return None


class WaterRippleSim:
    """Low-resolution dual-buffer ripple field + refracted frame builder."""

    def __init__(self, damping: float = DEFAULT_DAMPING):
        self.damping = float(damping)
        self.w = 0
        self.h = 0
        self._curr: array = array("f")
        self._prev: array = array("f")
        self._backdrop: Optional[QImage] = None
        self._frame: Optional[QImage] = None
        self._active = False  # True while energy remains (skip work when quiet)

    def ensure_size(self, view_w: int, view_h: int) -> Tuple[int, int]:
        """Size the sim from the viewport; returns (sim_w, sim_h)."""
        vw = max(1, int(view_w))
        vh = max(1, int(view_h))
        scale = max(MIN_SCALE, max(vw // MAX_SIM_W, vh // MAX_SIM_H, 1))
        bw = max(8, vw // scale)
        bh = max(8, vh // scale)
        bw = min(bw, MAX_SIM_W)
        bh = min(bh, MAX_SIM_H)
        if bw == self.w and bh == self.h and self._curr:
            return self.w, self.h
        self.w, self.h = bw, bh
        n = bw * bh
        self._curr = array("f", [0.0] * n)
        self._prev = array("f", [0.0] * n)
        self._backdrop = QImage(bw, bh, QImage.Format.Format_RGB32)
        self._frame = QImage(bw, bh, QImage.Format.Format_RGB32)
        self._active = False
        self.paint_base_water()
        return self.w, self.h

    def paint_base_water(self) -> None:
        """Fill the backdrop with the ocean photo at 60% opacity (steel-blue underlay)."""
        img = self._backdrop
        if img is None or img.isNull():
            return
        sea = load_sea_surface()
        p = QPainter(img)
        # Always paint the pool underlay so the 60%-opaque photo has something to blend onto.
        grad = QLinearGradient(0, 0, 0, self.h)
        grad.setColorAt(0.0, WATER_MID)
        grad.setColorAt(0.45, WATER_DEEP)
        grad.setColorAt(1.0, QColor(18, 28, 40))
        p.fillRect(0, 0, self.w, self.h, grad)
        if sea is not None and not sea.isNull():
            # Cover the low-res sim buffer; refraction will distort this image.
            scaled = sea.scaled(
                self.w,
                self.h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.setOpacity(SEA_SURFACE_OPACITY)
            p.drawImage(0, 0, scaled)
            p.setOpacity(1.0)
        p.end()

    def disturb(
        self,
        x: float,
        y: float,
        radius: float = 2.5,
        strength: float = 220.0,
    ) -> None:
        """Add a circular splash in sim coordinates."""
        if self.w < 3 or self.h < 3:
            return
        cx = int(round(x))
        cy = int(round(y))
        r = max(1, int(round(radius)))
        r2 = r * r
        curr = self._curr
        w, h = self.w, self.h
        for dy in range(-r, r + 1):
            yy = cy + dy
            if yy <= 0 or yy >= h - 1:
                continue
            row = yy * w
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r2:
                    continue
                xx = cx + dx
                if xx <= 0 or xx >= w - 1:
                    continue
                curr[row + xx] += strength
        self._active = True

    def view_to_sim(self, vx: float, vy: float, view_w: int, view_h: int) -> Tuple[float, float]:
        if view_w <= 0 or view_h <= 0 or self.w <= 0 or self.h <= 0:
            return 0.0, 0.0
        return vx * self.w / view_w, vy * self.h / view_h

    def step(self) -> bool:
        """Advance one wave step. Returns True if the field still has energy."""
        w, h = self.w, self.h
        if w < 3 or h < 3:
            return False
        curr = self._curr
        prev = self._prev
        damp = self.damping
        energy = 0.0
        # Interior cells only (borders stay 0 → reflecting edge).
        for y in range(1, h - 1):
            row = y * w
            row_u = row - w
            row_d = row + w
            for x in range(1, w - 1):
                i = row + x
                avg = (
                    curr[i - 1]
                    + curr[i + 1]
                    + curr[row_u + x]
                    + curr[row_d + x]
                ) * 0.5
                v = (avg - prev[i]) * damp
                # Soft clamp to keep refraction offsets sane.
                if v > 1024.0:
                    v = 1024.0
                elif v < -1024.0:
                    v = -1024.0
                prev[i] = v
                energy += abs(v)
        # Swap roles: prev becomes the new current height field.
        self._curr, self._prev = prev, curr
        # Quiet threshold — stop ticking hard work when nearly flat.
        self._active = energy > 0.8
        return self._active

    @property
    def active(self) -> bool:
        return self._active

    def backdrop(self) -> QImage:
        assert self._backdrop is not None
        return self._backdrop

    def refract(self) -> QImage:
        """Sample backdrop with height-gradient UV offset → low-res frame."""
        src = self._backdrop
        dst = self._frame
        assert src is not None and dst is not None
        w, h = self.w, self.h
        curr = self._curr
        # Raw BGRA/RGB32 scanlines (much faster than setPixel/pixel).
        src_bpl = src.bytesPerLine()
        dst_bpl = dst.bytesPerLine()
        src_buf = memoryview(src.constBits()).cast("B")
        dst_buf = memoryview(dst.bits()).cast("B")
        # Copy top / bottom rows verbatim.
        dst_buf[:src_bpl] = src_buf[:src_bpl]
        bottom = (h - 1) * src_bpl
        dst_buf[bottom : bottom + src_bpl] = src_buf[bottom : bottom + src_bpl]

        for y in range(1, h - 1):
            row = y * w
            row_u = row - w
            row_d = row + w
            src_row = y * src_bpl
            dst_row = y * dst_bpl
            # Left / right border pixels.
            dst_buf[dst_row : dst_row + 4] = src_buf[src_row : src_row + 4]
            dst_buf[dst_row + (w - 1) * 4 : dst_row + w * 4] = src_buf[
                src_row + (w - 1) * 4 : src_row + w * 4
            ]
            for x in range(1, w - 1):
                i = row + x
                # Gradient → refraction offset (scale down for subtle look).
                dx = int((curr[i + 1] - curr[i - 1]) * 0.08)
                dy = int((curr[row_d + x] - curr[row_u + x]) * 0.08)
                sx = x + dx
                sy = y + dy
                if sx < 0:
                    sx = 0
                elif sx >= w:
                    sx = w - 1
                if sy < 0:
                    sy = 0
                elif sy >= h:
                    sy = h - 1
                s_off = sy * src_bpl + sx * 4
                d_off = dst_row + x * 4
                dst_buf[d_off : d_off + 4] = src_buf[s_off : s_off + 4]
        return dst

    def render_upscaled(self, view_w: int, view_h: int) -> QImage:
        """Refract then Smooth upscale to the viewport size."""
        low = self.refract()
        return low.scaled(
            max(1, view_w),
            max(1, view_h),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
