"""Bottom HUD icon bar — five checkable buttons with Qt hover micro-animations.

Pure Qt (QPainter + QPropertyAnimation); no WebEngine. Icons:

  notify   — bell pivots from top, wiggles L/R then settles
  build    — hammer taps a square box
  info     — paper flips its bottom-right corner
  guestbook — speech cloud reveals 「...」 one by one
  settings — gear rotates 90° with a slight bounce
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

# Theme: dark translucent + cyan/teal border; orange when active (matches HUD).
_ICON_BG = QColor(18, 36, 40, 210)
_ICON_BG_HOVER = QColor(28, 52, 56, 230)
_ICON_BG_ON = QColor(176, 96, 36, 230)
_ICON_BORDER = QColor(90, 200, 190, 210)
_ICON_BORDER_ON = QColor(220, 140, 60, 230)
_ICON_FG = QColor(230, 248, 245, 240)
_ICON_FG_ON = QColor(255, 248, 240, 255)

ICON_SIZE = 36
ICON_GAP = 6
ICON_ANIM_MS = 720
ICON_KEYS = ("notify", "build", "info", "guestbook", "settings")
ICON_TIPS = {
    "notify": "通知：格資訊／日誌／警報走馬燈",
    "build": "建築／工具",
    "info": "格子資訊",
    "guestbook": "訪客留言板",
    "settings": "設定",
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, float(t)))


class HakoniwaIconButton(QWidget):
    """One square HUD icon with a one-shot hover micro-animation."""

    toggled = Signal(bool)
    clicked = Signal()

    def __init__(self, kind: str, tip: str = "", parent=None):
        super().__init__(parent)
        self.kind = kind
        self._checked = False
        self._hover = False
        self._anim_t = 0.0
        self.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip or ICON_TIPS.get(kind, kind))
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._anim = QPropertyAnimation(self, b"animProgress", self)
        self._anim.setDuration(ICON_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # --- Qt property for QPropertyAnimation ---
    def _get_anim_progress(self) -> float:
        return self._anim_t

    def _set_anim_progress(self, value: float) -> None:
        self._anim_t = _clamp01(value)
        self.update()

    animProgress = Property(float, _get_anim_progress, _set_anim_progress)

    def isChecked(self) -> bool:  # noqa: N802 — Qt naming
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def _play_hover(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _reset_hover(self) -> None:
        self._anim.stop()
        # Snap back quickly so leave feels snappy.
        self._anim.setDuration(180)
        self._anim.setStartValue(self._anim_t)
        self._anim.setEndValue(0.0)
        self._anim.start()
        self._anim.setDuration(ICON_ANIM_MS)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._play_hover()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._reset_hover()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.toggle()
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        bg = _ICON_BG_ON if self._checked else (
            _ICON_BG_HOVER if self._hover else _ICON_BG
        )
        border = _ICON_BORDER_ON if self._checked else _ICON_BORDER
        fg = _ICON_FG_ON if self._checked else _ICON_FG

        p.setPen(QPen(border, 1.4))
        p.setBrush(bg)
        p.drawRoundedRect(r, 5.0, 5.0)

        cx, cy = r.center().x(), r.center().y()
        drawer = _DRAWERS.get(self.kind)
        if drawer is not None:
            drawer(p, QPointF(cx, cy), min(r.width(), r.height()) * 0.36, fg, self._anim_t)
        p.end()


# ---------------------------------------------------------------------------
# Icon drawers (painter helpers)
# ---------------------------------------------------------------------------


def _draw_bell(
    p: QPainter, c: QPointF, s: float, color: QColor, t: float
) -> None:
    """Bell pivots from its top; decaying L/R wiggle then settle."""
    # Decaying sine: ~2.5 oscillations, amplitude → 0 by t=1.
    amp = 18.0 * (1.0 - t) * math.sin(t * math.pi * 5.0) if t > 0 else 0.0
    # Soften early kick so it reads as a hang-from-top swing.
    amp *= math.sin(min(1.0, t * 2.2) * math.pi * 0.5) if t > 0 else 0.0

    pivot = QPointF(c.x(), c.y() - s * 0.85)
    p.save()
    p.translate(pivot)
    p.rotate(amp)
    p.translate(-pivot)

    pen = QPen(color, max(1.4, s * 0.14))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Dome
    path = QPainterPath()
    top = QPointF(c.x(), c.y() - s * 0.75)
    path.moveTo(c.x() - s * 0.65, c.y() + s * 0.35)
    path.cubicTo(
        c.x() - s * 0.65,
        c.y() - s * 0.35,
        c.x() - s * 0.35,
        top.y(),
        top.x(),
        top.y(),
    )
    path.cubicTo(
        c.x() + s * 0.35,
        top.y(),
        c.x() + s * 0.65,
        c.y() - s * 0.35,
        c.x() + s * 0.65,
        c.y() + s * 0.35,
    )
    p.drawPath(path)
    # Clapper bar
    p.drawLine(
        QPointF(c.x() - s * 0.72, c.y() + s * 0.35),
        QPointF(c.x() + s * 0.72, c.y() + s * 0.35),
    )
    # Clapper bead
    p.setBrush(color)
    p.drawEllipse(QPointF(c.x(), c.y() + s * 0.62), s * 0.16, s * 0.16)
    # Cap nub
    p.drawEllipse(QPointF(c.x(), c.y() - s * 0.88), s * 0.12, s * 0.12)
    p.restore()


def _draw_build(
    p: QPainter, c: QPointF, s: float, color: QColor, t: float
) -> None:
    """Hammer taps a square box (rotate down → impact → rebound)."""
    # 0–0.45 swing down, 0.45–0.7 hold/impact, 0.7–1 rebound.
    if t <= 0.0:
        angle = -35.0
    elif t < 0.45:
        u = t / 0.45
        angle = _lerp(-35.0, 18.0, QEasingCurve(QEasingCurve.Type.InCubic).valueForProgress(u))
    elif t < 0.7:
        angle = 18.0
    else:
        u = (t - 0.7) / 0.3
        angle = _lerp(18.0, -12.0, QEasingCurve(QEasingCurve.Type.OutBack).valueForProgress(u))

    pen = QPen(color, max(1.3, s * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Box (target) — bottom-right of icon
    box = QRectF(c.x() + s * 0.05, c.y() + s * 0.15, s * 0.75, s * 0.75)
    p.drawRoundedRect(box, 1.5, 1.5)

    # Hammer pivots near handle end
    pivot = QPointF(c.x() - s * 0.15, c.y() + s * 0.55)
    p.save()
    p.translate(pivot)
    p.rotate(angle)
    p.translate(-pivot)

    # Handle
    p.drawLine(
        QPointF(c.x() - s * 0.55, c.y() + s * 0.75),
        QPointF(c.x() + s * 0.15, c.y() - s * 0.35),
    )
    # Head
    head = QRectF(c.x() - s * 0.05, c.y() - s * 0.70, s * 0.70, s * 0.38)
    p.setBrush(color)
    p.drawRoundedRect(head, 1.5, 1.5)
    p.restore()


def _draw_info(
    p: QPainter, c: QPointF, s: float, color: QColor, t: float
) -> None:
    """Paper with bottom-right corner flip."""
    pen = QPen(color, max(1.2, s * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    paper = QRectF(c.x() - s * 0.70, c.y() - s * 0.85, s * 1.40, s * 1.70)
    # Fold amount 0 → peek → settle slightly open
    fold = 0.0
    if t > 0:
        if t < 0.55:
            fold = QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(t / 0.55)
        else:
            fold = _lerp(1.0, 0.55, (t - 0.55) / 0.45)

    flap = s * 0.55 * fold
    path = QPainterPath()
    path.moveTo(paper.left(), paper.top())
    path.lineTo(paper.right(), paper.top())
    path.lineTo(paper.right(), paper.bottom() - flap)
    path.lineTo(paper.right() - flap, paper.bottom())
    path.lineTo(paper.left(), paper.bottom())
    path.closeSubpath()
    p.drawPath(path)

    if fold > 0.05:
        # Folded triangle
        fold_path = QPainterPath()
        fold_path.moveTo(paper.right(), paper.bottom() - flap)
        fold_path.lineTo(paper.right() - flap, paper.bottom() - flap)
        fold_path.lineTo(paper.right() - flap, paper.bottom())
        fold_path.closeSubpath()
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
        p.drawPath(fold_path)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # Text lines
    y0 = paper.top() + s * 0.35
    for i in range(3):
        y = y0 + i * s * 0.32
        x1 = paper.left() + s * 0.22
        x2 = paper.right() - s * 0.22 - (flap * 0.35 if i == 2 else 0)
        p.drawLine(QPointF(x1, y), QPointF(x2, y))


def _draw_guestbook(
    p: QPainter, c: QPointF, s: float, color: QColor, t: float
) -> None:
    """Speech cloud; 「...」 appear one by one."""
    pen = QPen(color, max(1.3, s * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    bubble = QRectF(c.x() - s * 0.85, c.y() - s * 0.75, s * 1.70, s * 1.15)
    p.drawRoundedRect(bubble, s * 0.35, s * 0.35)
    # Tail
    tail = QPainterPath()
    tail.moveTo(c.x() - s * 0.25, bubble.bottom() - 1)
    tail.lineTo(c.x() - s * 0.55, bubble.bottom() + s * 0.45)
    tail.lineTo(c.x() + s * 0.10, bubble.bottom() - 1)
    p.drawPath(tail)

    # Dots reveal at 0.2 / 0.45 / 0.7
    thresholds = (0.18, 0.42, 0.66)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    positions = (-0.40, 0.0, 0.40)
    for i, (th, dx) in enumerate(zip(thresholds, positions)):
        if t >= th:
            # Pop scale briefly after reveal
            pop = 1.0
            age = t - th
            if age < 0.15:
                pop = 0.6 + 0.4 * (age / 0.15)
            r = s * 0.13 * pop
            p.drawEllipse(QPointF(c.x() + dx * s, c.y() - s * 0.15), r, r)


def _draw_settings(
    p: QPainter, c: QPointF, s: float, color: QColor, t: float
) -> None:
    """Gear rotates 90° with slight overshoot bounce."""
    # Ease to 90° then overshoot to ~105° and settle at 90°.
    if t <= 0.0:
        angle = 0.0
    elif t < 0.7:
        u = t / 0.7
        angle = 90.0 * QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(u)
    else:
        u = (t - 0.7) / 0.3
        # Bounce: 90 → 105 → 90
        bounce = math.sin(u * math.pi) * 15.0 * (1.0 - u)
        angle = 90.0 + bounce

    p.save()
    p.translate(c)
    p.rotate(angle)
    p.translate(-c)

    pen = QPen(color, max(1.3, s * 0.14))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    teeth = 6
    outer = s * 0.95
    inner = s * 0.62
    hole = s * 0.28
    path = QPainterPath()
    for i in range(teeth * 2):
        ang = (i / (teeth * 2)) * math.pi * 2.0 - math.pi / 2.0
        rad = outer if i % 2 == 0 else inner
        # Flat tooth: sample two edge points for outer
        if i % 2 == 0:
            a0 = ang - math.pi / (teeth * 2) * 0.55
            a1 = ang + math.pi / (teeth * 2) * 0.55
            for a in (a0, a1):
                pt = QPointF(c.x() + math.cos(a) * rad, c.y() + math.sin(a) * rad)
                if path.elementCount() == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
        else:
            pt = QPointF(c.x() + math.cos(ang) * rad, c.y() + math.sin(ang) * rad)
            path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(c, hole, hole)
    p.restore()


_DRAWERS: Dict[str, Callable[[QPainter, QPointF, float, QColor, float], None]] = {
    "notify": _draw_bell,
    "build": _draw_build,
    "info": _draw_info,
    "guestbook": _draw_guestbook,
    "settings": _draw_settings,
}


class HakoniwaIconBar(QWidget):
    """Horizontal row of the five HUD icon buttons."""

    iconToggled = Signal(str, bool)  # kind, checked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ICON_GAP)

        self.buttons: Dict[str, HakoniwaIconButton] = {}
        for key in ICON_KEYS:
            btn = HakoniwaIconButton(key, ICON_TIPS[key], self)
            btn.toggled.connect(lambda checked, k=key: self._on_toggled(k, checked))
            lay.addWidget(btn)
            self.buttons[key] = btn

        self._relayout_size()

    def _relayout_size(self) -> None:
        """Fit width to currently visible icons (tourism hides 建築)."""
        visible = [b for b in self.buttons.values() if not b.isHidden()]
        n = max(len(visible), 1)
        self.setFixedSize(
            ICON_SIZE * n + ICON_GAP * max(n - 1, 0),
            ICON_SIZE,
        )

    def _on_toggled(self, kind: str, checked: bool) -> None:
        self.iconToggled.emit(kind, checked)

    def button(self, kind: str) -> Optional[HakoniwaIconButton]:
        return self.buttons.get(kind)

    def set_checked(self, kind: str, checked: bool) -> None:
        btn = self.buttons.get(kind)
        if btn is not None:
            btn.setChecked(checked)

    def set_icon_visible(self, kind: str, visible: bool) -> None:
        btn = self.buttons.get(kind)
        if btn is None:
            return
        btn.setVisible(visible)
        self._relayout_size()

    def exclusive_open(self, kind: Optional[str]) -> None:
        """Check only ``kind`` among mutually exclusive bottom drawers.

        ``notify`` (status chrome) and ``info`` (tile panel) stay independent.
        """
        exclusive = ("build", "guestbook", "settings")
        for key in exclusive:
            self.set_checked(key, key == kind)
