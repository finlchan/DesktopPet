"""Tank viewport: translucent water, fixed-size sprites, zoom = visible range."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
    QMouseEvent,
)
from PySide6.QtWidgets import QWidget

from .model import TankState
from .sprites import PLANT_H, PLANT_W, SWIM_H, SWIM_W, side_pixmap, swim_pixmap


class TankView(QWidget):
    """Paints the aquarium glass. Mouse events ignored (click-through glass).

    Zoom/pan change the world rectangle mapped into this widget; sprite blit
    size stays fixed (SWIM_* / PLANT_*).
    """

    fish_clicked = Signal(str)  # fish id (only when interact mode enabled)

    def __init__(self, state: TankState, parent=None):
        super().__init__(parent)
        self.state = state
        self.interact_mode = False  # when True, glass accepts clicks (catch aim)
        self._pan_last: Optional[QPointF] = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        # Default: glass click-through within Qt stacking (desktop pass-through
        # is handled at dialog level on Windows).
        self._apply_glass_mouse()

    def set_state(self, state: TankState) -> None:
        self.state = state
        self.update()

    def set_interact_mode(self, enabled: bool) -> None:
        self.interact_mode = enabled
        self._apply_glass_mouse()

    def _apply_glass_mouse(self) -> None:
        # When not interacting, ignore mouse so grips/toolbar receive / pass.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, not self.interact_mode
        )

    # --- camera helpers -------------------------------------------------

    def visible_size(self) -> tuple[float, float]:
        return self.state.visible_size()

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        vw, vh = self.visible_size()
        sx = (wx - self.state.cam_x) / vw * self.width()
        sy = (wy - self.state.cam_y) / vh * self.height()
        return QPointF(sx, sy)

    def screen_to_world(self, sx: float, sy: float) -> QPointF:
        vw, vh = self.visible_size()
        wx = self.state.cam_x + (sx / max(1, self.width())) * vw
        wy = self.state.cam_y + (sy / max(1, self.height())) * vh
        return QPointF(wx, wy)

    def pan_by_screen(self, dx: float, dy: float) -> None:
        vw, vh = self.visible_size()
        self.state.cam_x -= dx / max(1, self.width()) * vw
        self.state.cam_y -= dy / max(1, self.height()) * vh
        self._clamp_cam()
        self.update()

    def zoom_at(self, factor: float, anchor_sx: float, anchor_sy: float) -> None:
        before = self.screen_to_world(anchor_sx, anchor_sy)
        self.state.zoom = max(0.35, min(2.5, self.state.zoom * factor))
        after = self.screen_to_world(anchor_sx, anchor_sy)
        self.state.cam_x += before.x() - after.x()
        self.state.cam_y += before.y() - after.y()
        self._clamp_cam()
        self.update()

    def _clamp_cam(self) -> None:
        from .model import WORLD_H, WORLD_W

        vw, vh = self.visible_size()
        self.state.cam_x = max(0.0, min(WORLD_W - vw, self.state.cam_x))
        self.state.cam_y = max(0.0, min(WORLD_H - vh, self.state.cam_y))

    # --- paint ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        w, h = self.width(), self.height()

        # Soft water wash (translucent).
        p.fillRect(0, 0, w, h, QColor(40, 110, 150, 55))
        # Light god-ray bands.
        p.setPen(Qt.PenStyle.NoPen)
        for i, alpha in enumerate((18, 12, 8)):
            p.setBrush(QColor(200, 230, 255, alpha))
            x0 = int(w * (0.15 + i * 0.22))
            p.drawRect(x0, 0, max(8, w // 18), h)
        # Sandy floor hint at bottom of view.
        p.setBrush(QColor(180, 160, 110, 40))
        p.drawRect(0, int(h * 0.82), w, int(h * 0.18))

        # Decor (plants) — fixed sprite size.
        for d in self.state.decor:
            sp = self.world_to_screen(d.x, d.y)
            pix = swim_pixmap(d.species_key, False, True)
            p.drawPixmap(
                int(sp.x() - PLANT_W / 2),
                int(sp.y() - PLANT_H / 2),
                pix,
            )

        # Food pellets.
        p.setBrush(QColor(200, 140, 60, 200))
        for food in self.state.food_pellets:
            sp = self.world_to_screen(food["x"], food["y"])
            p.drawEllipse(sp, 2.5, 2.5)

        # Fish — fixed SWIM size regardless of zoom.
        for f in self.state.active_fish():
            sp = self.world_to_screen(f.x, f.y)
            pix = swim_pixmap(f.species_key, f.rare, f.facing_right)
            p.drawPixmap(
                int(sp.x() - SWIM_W / 2),
                int(sp.y() - SWIM_H / 2),
                pix,
            )
            if f.owned and f.custom_name:
                p.setPen(QColor(255, 255, 230, 200))
                p.drawText(
                    int(sp.x() - 40),
                    int(sp.y() - SWIM_H / 2 - 4),
                    80,
                    14,
                    Qt.AlignmentFlag.AlignHCenter,
                    f.custom_name,
                )

        # Subtle glass edge vignette (visual only).
        p.setPen(QPen(QColor(220, 235, 245, 50), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(1, 1, w - 2, h - 2)
        p.end()

    # --- interact / pan / zoom (when interact_mode or parent forwards) --

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.1 if delta > 0 else 1 / 1.1
        pos = event.position()
        self.zoom_at(factor, pos.x(), pos.y())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.interact_mode:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._pan_last = event.position()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_fish(event.position())
            if hit:
                self.fish_clicked.emit(hit)
                event.accept()
                return
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pan_last is not None:
            pos = event.position()
            self.pan_by_screen(
                pos.x() - self._pan_last.x(),
                pos.y() - self._pan_last.y(),
            )
            self._pan_last = pos
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._pan_last = None
        event.accept()

    def _hit_fish(self, pos: QPointF) -> Optional[str]:
        # Topmost fish whose fixed sprite rect contains the point.
        for f in reversed(self.state.active_fish()):
            sp = self.world_to_screen(f.x, f.y)
            if abs(pos.x() - sp.x()) <= SWIM_W / 2 and abs(pos.y() - sp.y()) <= SWIM_H / 2:
                return f.id
        return None


def capture_card_pixmap(species_key: str, rare: bool = False):
    """Expose side (view 2) art for 圖鑑 / capture UI."""
    return side_pixmap(species_key, rare)
