"""Classic dual height-buffer water ripple (low-res sim → UV-offset sample → upscale).

Algorithm per cell:
    next = (avg(left, right, up, down) * 2 - prev) * damping

Display keeps the bundled sea photo at full source resolution and cover-fits it
into the viewport (KeepAspectRatioByExpanding + center). The physics buffer stays
low-res for speed; refraction samples the cover-fitted viewport sea with UV
offsets from the height field, then soft-fades the four outer edges.
"""
from __future__ import annotations

import sys
from array import array
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient

# Steel-blue pool palette (underlay + fallback if sea-surface.jpg is missing)
WATER_DEEP = QColor(22, 34, 48)
WATER_MID = QColor(36, 58, 82)
WATER_EDGE = QColor(14, 22, 32)  # vignette target (soft outer fade)

DEFAULT_DAMPING = 0.965
# Cap sim resolution so Python loops stay interactive on modest hardware.
MAX_SIM_W = 220
MAX_SIM_H = 160
MIN_SCALE = 3
# Intermediate warp buffer (sharper than raw sim, cheaper than full viewport).
MAX_WARP_W = 640
MAX_WARP_H = 480

# Soft fade band as a fraction of the shorter viewport side (all four edges).
EDGE_FADE_FRAC = 0.18

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
    Does not downsample or crop the file on disk — callers cover-fit at draw time.
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


def cover_fit_rect(
    src_w: int, src_h: int, dst_w: int, dst_h: int
) -> Tuple[float, float, float, float]:
    """Return (scale, offset_x, offset_y, _) for cover-fit of src into dst.

    Cover-fit = KeepAspectRatioByExpanding + center: the source fills the
    destination; overflow is centered (visual crop of sides or top/bottom only
    when aspect ratios differ — the asset itself is never permanently cropped).
    """
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return 1.0, 0.0, 0.0, 0.0
    scale = max(dst_w / src_w, dst_h / src_h)
    scaled_w = src_w * scale
    scaled_h = src_h * scale
    ox = (scaled_w - dst_w) * 0.5
    oy = (scaled_h - dst_h) * 0.5
    return scale, ox, oy, 0.0


def paint_cover_sea(target: QImage, sea: Optional[QImage] = None) -> None:
    """Fill ``target`` with steel-blue underlay + cover-fitted sea at 60% opacity."""
    if target is None or target.isNull():
        return
    tw, th = target.width(), target.height()
    p = QPainter(target)
    grad = QLinearGradient(0, 0, 0, th)
    grad.setColorAt(0.0, WATER_MID)
    grad.setColorAt(0.45, WATER_DEEP)
    grad.setColorAt(1.0, QColor(18, 28, 40))
    p.fillRect(0, 0, tw, th, grad)
    if sea is None:
        sea = load_sea_surface()
    if sea is not None and not sea.isNull():
        # Cover-fit: preserve aspect; center any overflow (no IgnoreAspectRatio stretch).
        scaled = sea.scaled(
            tw,
            th,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - tw) // 2
        y = (scaled.height() - th) // 2
        cropped = scaled.copy(x, y, tw, th)
        p.setOpacity(SEA_SURFACE_OPACITY)
        p.drawImage(0, 0, cropped)
        p.setOpacity(1.0)
    p.end()


def apply_edge_fade(img: QImage, fade_frac: float = EDGE_FADE_FRAC) -> None:
    """Soft vignette: fade all four outer edges toward WATER_EDGE (in-place)."""
    if img is None or img.isNull():
        return
    w, h = img.width(), img.height()
    if w < 4 or h < 4:
        return
    band = max(12, int(round(min(w, h) * max(0.04, min(fade_frac, 0.40)))))
    # Soft darken via SourceOver gradients (淡化 on all four outer edges).
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    edge = QColor(WATER_EDGE)
    edge.setAlpha(235)
    mid_edge = QColor(WATER_EDGE)
    mid_edge.setAlpha(110)
    clear = QColor(WATER_EDGE)
    clear.setAlpha(0)
    # Left
    g = QLinearGradient(0, 0, band, 0)
    g.setColorAt(0.0, edge)
    g.setColorAt(0.45, mid_edge)
    g.setColorAt(1.0, clear)
    p.fillRect(0, 0, band, h, g)
    # Right
    g = QLinearGradient(w, 0, w - band, 0)
    g.setColorAt(0.0, edge)
    g.setColorAt(0.45, mid_edge)
    g.setColorAt(1.0, clear)
    p.fillRect(w - band, 0, band, h, g)
    # Top
    g = QLinearGradient(0, 0, 0, band)
    g.setColorAt(0.0, edge)
    g.setColorAt(0.45, mid_edge)
    g.setColorAt(1.0, clear)
    p.fillRect(0, 0, w, band, g)
    # Bottom
    g = QLinearGradient(0, h, 0, h - band)
    g.setColorAt(0.0, edge)
    g.setColorAt(0.45, mid_edge)
    g.setColorAt(1.0, clear)
    p.fillRect(0, h - band, w, band, g)
    # Soften corners further with a gentle radial.
    cx, cy = w * 0.5, h * 0.5
    radius = max(w, h) * 0.78
    rg = QRadialGradient(cx, cy, radius)
    mid = QColor(WATER_EDGE)
    mid.setAlpha(0)
    outer = QColor(WATER_EDGE)
    outer.setAlpha(120)
    rg.setColorAt(0.50, mid)
    rg.setColorAt(1.0, outer)
    p.fillRect(0, 0, w, h, rg)
    p.end()


class WaterRippleSim:
    """Low-resolution dual-buffer ripple field + high-res cover-fit frame builder."""

    def __init__(self, damping: float = DEFAULT_DAMPING):
        self.damping = float(damping)
        self.w = 0
        self.h = 0
        self._curr: array = array("f")
        self._prev: array = array("f")
        self._backdrop: Optional[QImage] = None  # low-res stamp for quiet energy checks
        self._frame: Optional[QImage] = None
        self._active = False  # True while energy remains (skip work when quiet)
        self._view_base: Optional[QImage] = None
        self._view_base_size: Tuple[int, int] = (0, 0)

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
        self._view_base = None
        self._view_base_size = (0, 0)
        self.paint_base_water()
        return self.w, self.h

    def paint_base_water(self) -> None:
        """Stamp cover-fitted sea into the low-res sim buffer (physics / legacy)."""
        img = self._backdrop
        if img is None or img.isNull():
            return
        paint_cover_sea(img)
        # Viewport base is rebuilt lazily in render_upscaled.
        self._view_base = None
        self._view_base_size = (0, 0)

    def _ensure_view_base(self, view_w: int, view_h: int) -> QImage:
        """Full-viewport cover-fit of the original sea (not permanently downsampled)."""
        vw, vh = max(1, int(view_w)), max(1, int(view_h))
        if (
            self._view_base is not None
            and not self._view_base.isNull()
            and self._view_base_size == (vw, vh)
        ):
            return self._view_base
        base = QImage(vw, vh, QImage.Format.Format_RGB32)
        paint_cover_sea(base)
        self._view_base = base
        self._view_base_size = (vw, vh)
        return base

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
        """Sample low-res backdrop with height-gradient UV offset (legacy helper)."""
        src = self._backdrop
        dst = self._frame
        assert src is not None and dst is not None
        w, h = self.w, self.h
        curr = self._curr
        src_bpl = src.bytesPerLine()
        dst_bpl = dst.bytesPerLine()
        src_buf = memoryview(src.constBits()).cast("B")
        dst_buf = memoryview(dst.bits()).cast("B")
        dst_buf[:src_bpl] = src_buf[:src_bpl]
        bottom = (h - 1) * src_bpl
        dst_buf[bottom : bottom + src_bpl] = src_buf[bottom : bottom + src_bpl]

        for y in range(1, h - 1):
            row = y * w
            row_u = row - w
            row_d = row + w
            src_row = y * src_bpl
            dst_row = y * dst_bpl
            dst_buf[dst_row : dst_row + 4] = src_buf[src_row : src_row + 4]
            dst_buf[dst_row + (w - 1) * 4 : dst_row + w * 4] = src_buf[
                src_row + (w - 1) * 4 : src_row + w * 4
            ]
            for x in range(1, w - 1):
                i = row + x
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

    def _warp_from_view_base(self, view_w: int, view_h: int) -> QImage:
        """Refract by sampling the cover-fitted viewport sea (keeps source detail)."""
        base = self._ensure_view_base(view_w, view_h)
        vw, vh = base.width(), base.height()
        # Intermediate warp size: sharper than sim, capped for Python loop cost.
        scale = max(1, max(vw // MAX_WARP_W, vh // MAX_WARP_H, 1))
        ww = max(self.w, vw // scale)
        wh = max(self.h, vh // scale)
        ww = min(ww, MAX_WARP_W, vw)
        wh = min(wh, MAX_WARP_H, vh)
        warped = QImage(ww, wh, QImage.Format.Format_RGB32)
        curr = self._curr
        sw, sh = self.w, self.h
        src_bpl = base.bytesPerLine()
        dst_bpl = warped.bytesPerLine()
        src_buf = memoryview(base.constBits()).cast("B")
        dst_buf = memoryview(warped.bits()).cast("B")
        # Map warp pixel → sim cell for height gradient; sample base at offset UV.
        for y in range(wh):
            # Sim Y (float) then nearest interior.
            sy = y * (sh - 1) / max(1, wh - 1)
            syi = int(sy)
            if syi < 1:
                syi = 1
            elif syi > sh - 2:
                syi = sh - 2
            row = syi * sw
            row_u = row - sw
            row_d = row + sw
            dst_row = y * dst_bpl
            # Corresponding Y on the high-res base before refraction.
            by0 = y * (vh - 1) / max(1, wh - 1)
            for x in range(ww):
                sx = x * (sw - 1) / max(1, ww - 1)
                sxi = int(sx)
                if sxi < 1:
                    sxi = 1
                elif sxi > sw - 2:
                    sxi = sw - 2
                i = row + sxi
                # Gradient → refraction offset in sim cells; scale to base pixels.
                dx_sim = (curr[i + 1] - curr[i - 1]) * 0.08
                dy_sim = (curr[row_d + sxi] - curr[row_u + sxi]) * 0.08
                dx = dx_sim * (vw / max(1, sw))
                dy = dy_sim * (vh / max(1, sh))
                bx0 = x * (vw - 1) / max(1, ww - 1)
                sx_pix = int(bx0 + dx)
                sy_pix = int(by0 + dy)
                if sx_pix < 0:
                    sx_pix = 0
                elif sx_pix >= vw:
                    sx_pix = vw - 1
                if sy_pix < 0:
                    sy_pix = 0
                elif sy_pix >= vh:
                    sy_pix = vh - 1
                s_off = sy_pix * src_bpl + sx_pix * 4
                d_off = dst_row + x * 4
                dst_buf[d_off : d_off + 4] = src_buf[s_off : s_off + 4]
        if ww == vw and wh == vh:
            return warped
        return warped.scaled(
            vw,
            vh,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def render_upscaled(self, view_w: int, view_h: int) -> QImage:
        """Cover-fit original sea at viewport size; warp when ripples are active; edge-fade."""
        vw = max(1, int(view_w))
        vh = max(1, int(view_h))
        if self._active and self.w >= 3 and self.h >= 3:
            out = self._warp_from_view_base(vw, vh)
        else:
            out = self._ensure_view_base(vw, vh).copy()
        apply_edge_fade(out)
        return out
