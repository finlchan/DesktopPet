"""List Row Fill — category rows for the 建築抽屜樹 (HUD teal/cyan/orange).

Qt take on CSS “List Row Fill” (same motion as ``desktop_pet.ListRowFillItem``):

- Row: index number · name · right arrow; thin separators **above and below**
- Hover (~0.5s): solid fill scaleX 0→1 from left origin; name shifts right;
  arrow slides in from the left onto the right edge; text color inverts
- Leave: fill scaleX 1→0 with origin on the right (exits to the right / 左進右出)

Palette follows ``hud_icons`` (deep teal glass · cyan · orange) — no new scheme.
"""

from __future__ import annotations

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
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

# Match hakoniwa.hud_icons / dialog drawer chrome.
LIST_ROW_IDLE_BG = QColor(18, 36, 40, 230)        # deep teal glass
LIST_ROW_FILL = QColor(200, 236, 230, 245)        # light cyan wipe (invert face)
LIST_ROW_TEXT_IDLE = QColor(230, 248, 245)        # #e6f8f5
LIST_ROW_TEXT_ON = QColor(18, 40, 44)             # dark teal on light fill
LIST_ROW_DIVIDER = QColor(90, 200, 190, 180)      # cyan hairline (above + below)
LIST_ROW_NUM_ACCENT = QColor(220, 140, 60, 255)   # orange index — always visible
LIST_ROW_ANIM_MS = 500
LIST_ROW_NAME_SHIFT = 10.0
LIST_ROW_ARROW_SLIDE = 18.0
LIST_ROW_HEIGHT = 30


class HakoniwaListRowFillItem(QWidget):
    """One main-category row with List Row Fill hover (建築樹 categories only)."""

    clicked = Signal()

    def __init__(self, index: int, name: str, parent=None):
        super().__init__(parent)
        self._index = int(index)
        self._name = name or ""
        self._hover_t = 0.0
        self._origin_left = True  # enter: left; leave: right
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setMinimumWidth(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(LIST_ROW_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    @property
    def category_name(self) -> str:
        return self._name

    @property
    def index(self) -> int:
        return self._index

    def _get_hover_progress(self) -> float:
        return self._hover_t

    def _set_hover_progress(self, value: float) -> None:
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _animate_to(self, target: float, *, origin_left: bool) -> None:
        self._origin_left = bool(origin_left)
        self._anim.stop()
        self._anim.setStartValue(self._hover_t)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate_to(1.0, origin_left=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate_to(0.0, origin_left=False)
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
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        t = self._hover_t
        w = float(max(self.width(), 1))
        h = float(max(self.height(), 1))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Idle face (always opaque enough that number/name read clearly).
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(LIST_ROW_IDLE_BG)
        painter.drawRect(QRectF(0, 0, w, h))

        # Absolute fill layer: enter scaleX from left; leave toward right.
        fill_rect = QRectF()
        if t > 0.001:
            fill_w = w * t
            if self._origin_left:
                fill_rect = QRectF(0.0, 0.0, fill_w, h)
            else:
                fill_rect = QRectF(w - fill_w, 0.0, fill_w, h)
            painter.setBrush(LIST_ROW_FILL)
            painter.drawRect(fill_rect)

        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        pad_l = 8.0
        pad_r = 10.0
        num_w = float(fm.horizontalAdvance("00"))
        arrow = "→"
        arrow_w = float(fm.horizontalAdvance(arrow))
        baseline = (h + fm.ascent() - fm.descent()) * 0.5

        # 1) Number always visible on every category row.
        num_text = f"{self._index:02d}"
        # 2) Name shifts right on hover.
        name_x = pad_l + num_w + 10.0 + LIST_ROW_NAME_SHIFT * t
        name_right = w - pad_r - arrow_w - 8.0
        name_max = max(20.0, name_right - name_x)
        elided = fm.elidedText(self._name, Qt.TextElideMode.ElideRight, int(name_max))
        # 3) Arrow on the RIGHT — slides in from the left as t→1 (idle: gone).
        arrow_rest_x = w - pad_r - arrow_w
        arrow_x = arrow_rest_x - LIST_ROW_ARROW_SLIDE * (1.0 - t)
        arrow_alpha = int(255 * t)  # fully hidden at rest; full on hover

        def _draw_row_text(color: QColor, *, num_color: QColor | None = None) -> None:
            painter.setPen(num_color or color)
            painter.drawText(QPointF(pad_l, baseline), num_text)
            painter.setPen(color)
            painter.drawText(QPointF(name_x, baseline), elided)
            if arrow_alpha > 0:
                ac = QColor(color)
                ac.setAlpha(min(255, arrow_alpha))
                painter.setPen(ac)
                painter.drawText(QPointF(arrow_x, baseline), arrow)

        if fill_rect.width() > 0.5:
            uncovered = QPainterPath()
            uncovered.addRect(QRectF(0.0, 0.0, w, h))
            filled = QPainterPath()
            filled.addRect(fill_rect)
            uncovered = uncovered.subtracted(filled)
            painter.setClipPath(uncovered)
            _draw_row_text(LIST_ROW_TEXT_IDLE, num_color=LIST_ROW_NUM_ACCENT)
            painter.setClipPath(filled)
            _draw_row_text(LIST_ROW_TEXT_ON, num_color=LIST_ROW_TEXT_ON)
            painter.setClipping(False)
        else:
            _draw_row_text(LIST_ROW_TEXT_IDLE, num_color=LIST_ROW_NUM_ACCENT)

        # Thin separators ABOVE and BELOW each category row.
        painter.setPen(QPen(LIST_ROW_DIVIDER, 1.0))
        painter.drawLine(QPointF(0.0, 0.5), QPointF(w, 0.5))
        painter.drawLine(QPointF(0.0, h - 0.5), QPointF(w, h - 0.5))
        painter.end()
