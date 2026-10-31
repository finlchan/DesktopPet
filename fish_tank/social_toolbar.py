"""Social Icon Fill circular toolbar (bottom-left) for Transparent Fish Tank.

Qt approximation of the CSS “Social Icon Fill” pattern:
- Circular outline + centered comic line icon
- Hover (~0.45s): solid fill rises from bottom (translateY 101%→0),
  idle icon slides up out, contrast icon slides up from below,
  button lifts slightly; mouse-leave reverses.
- Clip to circle = overflow:hidden.

Colors stay within the existing fish-tank / Desktop Pet cool teal-slate palette
(see dialog.TANK_STYLE) — no new brand palette.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QFont,
)
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

# Theme colors locked to fish-tank TANK_STYLE / mini-program blues.
OUTLINE = QColor(140, 180, 200, 200)
OUTLINE_HOVER = QColor(180, 210, 230, 230)
ICON_IDLE = QColor(232, 242, 248)       # #e8f2f8
ICON_ON_FILL = QColor(240, 246, 250)    # #f0f6fa on filled button
FILL = QColor(50, 78, 100, 235)         # fishTankBtn face
FILL_HOVER = QColor(70, 110, 140, 240)  # fishTankBtn:hover
FILL_CHECKED = QColor(120, 90, 40, 240) # fishTankBtn:checked (catch)
BG_IDLE = QColor(24, 36, 48, 70)        # soft glass disc

BTN_SIZE = 46
BTN_GAP = 8
ANIM_MS = 450
LIFT_PX = 5.0


# ---------------------------------------------------------------------------
# Comic-simple line icons (vector-ish stroke drawings inside the circle)
# ---------------------------------------------------------------------------

def _pen(color: QColor, width: float = 1.8) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_icon_feed(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Comic meat／肉 — drumstick (bulb + twin bone knobs)."""
    p.setPen(_pen(color, 1.9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Meat bulb (upper-left)
    p.drawEllipse(QRectF(c.x() - r * 0.62, c.y() - r * 0.55, r * 0.9, r * 0.78))
    # Drumstick shaft
    p.drawLine(
        QPointF(c.x() + r * 0.12, c.y() + r * 0.12),
        QPointF(c.x() + r * 0.42, c.y() + r * 0.42),
    )
    # Twin bone knobs
    p.drawEllipse(QRectF(c.x() + r * 0.32, c.y() + r * 0.38, r * 0.26, r * 0.26))
    p.drawEllipse(QRectF(c.x() + r * 0.46, c.y() + r * 0.26, r * 0.24, r * 0.24))


def draw_icon_decorate(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Plant / waterweed sprout (佈景)."""
    p.setPen(_pen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Stem
    p.drawLine(QPointF(c.x(), c.y() + r * 0.55), QPointF(c.x(), c.y() - r * 0.15))
    # Leaves
    path_l = QPainterPath()
    path_l.moveTo(c.x(), c.y() + r * 0.1)
    path_l.quadTo(c.x() - r * 0.55, c.y() - r * 0.05, c.x() - r * 0.15, c.y() - r * 0.45)
    p.drawPath(path_l)
    path_r = QPainterPath()
    path_r.moveTo(c.x(), c.y() - r * 0.05)
    path_r.quadTo(c.x() + r * 0.55, c.y() - r * 0.2, c.x() + r * 0.1, c.y() - r * 0.55)
    p.drawPath(path_r)
    # Pot hint
    p.drawLine(
        QPointF(c.x() - r * 0.35, c.y() + r * 0.55),
        QPointF(c.x() + r * 0.35, c.y() + r * 0.55),
    )


def draw_icon_name(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Name-tag with Aa (命名)."""
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    tag = QRectF(c.x() - r * 0.55, c.y() - r * 0.35, r * 1.1, r * 0.7)
    p.drawRoundedRect(tag, 3, 3)
    # Hole
    p.drawEllipse(QRectF(c.x() - r * 0.45, c.y() - r * 0.08, r * 0.18, r * 0.18))
    # Aa
    p.setFont(QFont("Sans", max(8, int(r * 0.55)), QFont.Weight.Bold))
    p.setPen(color)
    p.drawText(QRectF(c.x() - r * 0.15, c.y() - r * 0.28, r * 0.65, r * 0.55),
               Qt.AlignmentFlag.AlignCenter, "Aa")


def draw_icon_catch(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Fishing net (捕捉)."""
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Handle
    p.drawLine(
        QPointF(c.x() - r * 0.5, c.y() + r * 0.5),
        QPointF(c.x() - r * 0.1, c.y() - r * 0.05),
    )
    # Rim
    p.drawEllipse(QRectF(c.x() - r * 0.15, c.y() - r * 0.55, r * 0.75, r * 0.7))
    # Mesh cross
    p.drawLine(
        QPointF(c.x() + r * 0.05, c.y() - r * 0.4),
        QPointF(c.x() + r * 0.35, c.y() - r * 0.05),
    )
    p.drawLine(
        QPointF(c.x() + r * 0.4, c.y() - r * 0.4),
        QPointF(c.x() + r * 0.1, c.y() - r * 0.05),
    )


def draw_icon_dex(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Open book / 圖鑑 card."""
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Left page
    p.drawRoundedRect(QRectF(c.x() - r * 0.55, c.y() - r * 0.45, r * 0.5, r * 0.9), 2, 2)
    # Right page
    p.drawRoundedRect(QRectF(c.x() + r * 0.05, c.y() - r * 0.45, r * 0.5, r * 0.9), 2, 2)
    # Spine
    p.drawLine(QPointF(c.x(), c.y() - r * 0.45), QPointF(c.x(), c.y() + r * 0.45))
    # Lines
    for i in range(3):
        y = c.y() - r * 0.2 + i * r * 0.22
        p.drawLine(QPointF(c.x() - r * 0.42, y), QPointF(c.x() - r * 0.15, y))
        p.drawLine(QPointF(c.x() + r * 0.15, y), QPointF(c.x() + r * 0.42, y))


def draw_icon_view(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Eye (視圖 / reset view)."""
    p.setPen(_pen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    eye = QPainterPath()
    eye.moveTo(c.x() - r * 0.6, c.y())
    eye.quadTo(c.x(), c.y() - r * 0.45, c.x() + r * 0.6, c.y())
    eye.quadTo(c.x(), c.y() + r * 0.45, c.x() - r * 0.6, c.y())
    p.drawPath(eye)
    p.drawEllipse(QRectF(c.x() - r * 0.18, c.y() - r * 0.18, r * 0.36, r * 0.36))
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(c.x() - r * 0.07, c.y() - r * 0.07, r * 0.14, r * 0.14))


def draw_icon_close(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """X close."""
    p.setPen(_pen(color, 2.0))
    d = r * 0.4
    p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
    p.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))


ICON_DRAWERS = {
    "feed": draw_icon_feed,
    "decorate": draw_icon_decorate,
    "name": draw_icon_name,
    "catch": draw_icon_catch,
    "dex": draw_icon_dex,
    "view": draw_icon_view,
    "close": draw_icon_close,
}


# ---------------------------------------------------------------------------
# Single circular Social Icon Fill button
# ---------------------------------------------------------------------------

class SocialIconFillButton(QWidget):
    """One circular Social Icon Fill control."""

    clicked = Signal()
    toggled = Signal(bool)

    def __init__(
        self,
        icon_key: str,
        tip: str,
        parent=None,
        *,
        checkable: bool = False,
    ):
        super().__init__(parent)
        self.icon_key = icon_key
        self._drawer = ICON_DRAWERS[icon_key]
        self._checkable = checkable
        self._checked = False
        self._hover_t = 0.0
        self.setFixedSize(BTN_SIZE, BTN_SIZE + int(LIFT_PX) + 2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # --- animatable property --------------------------------------------

    def _get_hover_progress(self) -> float:
        return self._hover_t

    def _set_hover_progress(self, value: float) -> None:
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        if self._checked:
            self._animate_to(1.0)
        else:
            # Snap toward idle unless still hovered.
            if not self.underMouse():
                self._animate_to(0.0)
        self.toggled.emit(self._checked)
        self.update()

    def _animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_t)
        self._anim.setEndValue(target)
        self._anim.start()

    # --- events ---------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._checked:
            self._animate_to(0.0)
        else:
            # Stay filled when checked; still full.
            self._animate_to(1.0)
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
            if self._checkable:
                self.setChecked(not self._checked)
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- paint ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        t = self._hover_t
        lift = t * LIFT_PX
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Disc rests on the bottom of the widget; hover lifts it (paint-only).
        size = float(BTN_SIZE)
        rect = QRectF(0.5, float(self.height() - BTN_SIZE) + 0.5, size - 1.0, size - 1.0)
        rect.translate(0.0, -lift)

        # Soft idle disc
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BG_IDLE)
        painter.drawEllipse(rect)

        # Circular clip = overflow:hidden
        clip = QPainterPath()
        clip.addEllipse(rect)
        painter.setClipPath(clip)

        # Fill rising from bottom: translateY(101%) → 0
        fill_color = FILL_CHECKED if self._checked else FILL_HOVER
        if t > 0.001:
            h = rect.height()
            fill_top = rect.top() + h * (1.0 - t)
            fill_rect = QRectF(rect.left() - 1, fill_top, rect.width() + 2, h * t + 3)
            painter.setBrush(fill_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(fill_rect)

        # Icons: idle slides up out; contrast slides up from below.
        center = rect.center()
        icon_r = size * 0.28
        idle_y = center.y() - t * rect.height()
        hover_y = center.y() + (1.0 - t) * rect.height()
        self._drawer(painter, QPointF(center.x(), idle_y), icon_r, ICON_IDLE)
        self._drawer(painter, QPointF(center.x(), hover_y), icon_r, ICON_ON_FILL)

        painter.setClipping(False)

        # Thin outline on top of fill/icons
        pen = QPen(OUTLINE_HOVER if t > 0.2 else OUTLINE)
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        painter.end()


# ---------------------------------------------------------------------------
# Toolbar row
# ---------------------------------------------------------------------------

class SocialIconToolbar(QWidget):
    """Bottom-left row of Social Icon Fill buttons + slim status chip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fishTankSocialToolbar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 8, 4)
        lay.setSpacing(BTN_GAP)

        self.buttons: dict[str, SocialIconFillButton] = {}
        specs: List[Tuple[str, str, bool]] = [
            ("feed", "餵食／Feed — comic meat／肉", False),
            ("decorate", "佈景／Decorate — plant／水蘊草", False),
            ("name", "命名／Name — name tag", False),
            ("catch", "捕捉／Catch — fishing net", True),
            ("dex", "圖鑑／Dex — open book", False),
            ("view", "視圖／View — reset camera", False),
            ("close", "關閉／Close", False),
        ]
        for key, tip, checkable in specs:
            btn = SocialIconFillButton(key, tip, self, checkable=checkable)
            self.buttons[key] = btn
            lay.addWidget(btn)

        # Compact bottom-left chrome — do not stretch across the tank.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.adjustSize()

    def bind(
        self,
        *,
        feed: Callable,
        decorate: Callable,
        name: Callable,
        catch_toggle: Callable,
        dex: Callable,
        view: Callable,
        close: Callable,
    ) -> None:
        self.buttons["feed"].clicked.connect(feed)
        self.buttons["decorate"].clicked.connect(decorate)
        self.buttons["name"].clicked.connect(name)
        self.buttons["catch"].clicked.connect(catch_toggle)
        self.buttons["dex"].clicked.connect(dex)
        self.buttons["view"].clicked.connect(view)
        self.buttons["close"].clicked.connect(close)

    def catch_button(self) -> SocialIconFillButton:
        return self.buttons["catch"]

    def set_status(self, text: str) -> None:
        # Status lives on the slim top chip; keep API for dialog refresh.
        del text
