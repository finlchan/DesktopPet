"""Timeline Draw — child rows under a 建築樹 category (HUD teal/cyan/orange).

Qt take on CSS “Timeline Draw” (~2.4s ease-in-out):

- Left thin rail: ``scaleY`` 0→1 with origin at the top
- Each node (dot + title + detail) slides in from ``x: -10`` and fades in
  as the growing line tip reaches it

Triggered when a category expands; collapse resets instantly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

# HUD chrome (match list_row_fill / hud_icons).
TIMELINE_LINE = QColor(90, 200, 190, 220)          # cyan rail
TIMELINE_DOT = QColor(90, 200, 190, 255)
TIMELINE_DOT_ON = QColor(220, 140, 60, 255)        # orange when selected
TIMELINE_TEXT = QColor(230, 248, 245)
TIMELINE_TEXT_DIM = QColor(168, 208, 200)
TIMELINE_TEXT_LOCKED = QColor(140, 170, 168, 170)
TIMELINE_SELECT_BG = QColor(176, 96, 36, 230)      # orange select
TIMELINE_ANIM_MS = 2400
TIMELINE_NODE_H = 26
TIMELINE_LINE_X = 10.0
TIMELINE_DOT_R = 3.5
TIMELINE_TEXT_X = 22.0
TIMELINE_SLIDE_PX = 10.0
TIMELINE_REVEAL_BAND = 18.0  # px of line travel to finish a node fade/slide


@dataclass
class TimelineNodeData:
    key: str
    title: str
    detail: str = ""
    locked: bool = False
    selected: bool = False


class TimelineDrawPanel(QWidget):
    """Vertical timeline of child building／tool nodes with draw-on expand."""

    nodeClicked = Signal(str)
    nodeActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: List[TimelineNodeData] = []
        self._progress = 0.0  # 0 = line undrawn / nodes hidden; 1 = complete
        self._anim = QPropertyAnimation(self, b"drawProgress", self)
        self._anim.setDuration(TIMELINE_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._hover_key: Optional[str] = None

    # --- data -------------------------------------------------------------
    def set_nodes(self, nodes: List[TimelineNodeData]) -> None:
        self._nodes = list(nodes)
        self._progress = 0.0
        self._recompute_height()
        self.update()

    def nodes(self) -> List[TimelineNodeData]:
        return self._nodes

    def node_keys(self) -> List[str]:
        return [n.key for n in self._nodes]

    def find_node(self, key: str) -> Optional[TimelineNodeData]:
        for n in self._nodes:
            if n.key == key:
                return n
        return None

    def set_node_locked(self, key: str, locked: bool, title: str) -> None:
        n = self.find_node(key)
        if n is None:
            return
        n.locked = bool(locked)
        n.title = title
        self.update()

    def set_selected_key(self, key: Optional[str]) -> None:
        for n in self._nodes:
            n.selected = n.key == key
        self.update()

    # --- animation --------------------------------------------------------
    def _get_draw_progress(self) -> float:
        return self._progress

    def _set_draw_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    drawProgress = Property(float, _get_draw_progress, _set_draw_progress)

    def play_expand(self) -> None:
        """Run Timeline Draw 0→1 (~2.4s ease-in-out)."""
        self._anim.stop()
        self._progress = 0.0
        self.update()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def reset_collapsed(self) -> None:
        self._anim.stop()
        self._progress = 0.0
        self.update()

    def snap_complete(self) -> None:
        """Finish instantly (tests / reduced-motion)."""
        self._anim.stop()
        self._progress = 1.0
        self.update()

    # --- layout / hit -----------------------------------------------------
    def _recompute_height(self) -> None:
        h = max(1, len(self._nodes)) * TIMELINE_NODE_H + 4
        self.setFixedHeight(h)
        self.setMinimumHeight(h)

    def _node_rect(self, index: int) -> QRectF:
        y = 2.0 + index * TIMELINE_NODE_H
        return QRectF(0.0, y, float(max(self.width(), 1)), float(TIMELINE_NODE_H))

    def _node_at_pos(self, pos) -> Optional[TimelineNodeData]:
        y = pos.y()
        for i, n in enumerate(self._nodes):
            r = self._node_rect(i)
            if r.top() <= y <= r.bottom():
                return n
        return None

    def _node_reveal(self, index: int) -> float:
        """0..1 how far this node has faded/slid in given line progress."""
        if not self._nodes:
            return 0.0
        r = self._node_rect(index)
        # Line tip Y along the rail (origin top).
        full_h = max(1.0, float(self.height()) - 4.0)
        tip_y = 2.0 + full_h * self._progress
        # Node reveals as tip reaches its vertical center.
        center_y = r.center().y()
        return max(0.0, min(1.0, (tip_y - (center_y - TIMELINE_REVEAL_BAND * 0.5))
                            / TIMELINE_REVEAL_BAND))

    # --- events -----------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        n = self._node_at_pos(event.position())
        key = n.key if n else None
        if key != self._hover_key:
            self._hover_key = key
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_key is not None:
            self._hover_key = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            n = self._node_at_pos(event.position())
            if n is not None and self._node_reveal(self._nodes.index(n)) > 0.4:
                self.nodeClicked.emit(n.key)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            n = self._node_at_pos(event.position())
            if n is not None and self._node_reveal(self._nodes.index(n)) > 0.4:
                self.nodeActivated.emit(n.key)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # --- paint ------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        w = float(max(self.width(), 1))
        h = float(max(self.height(), 1))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Left thin line — scaleY from top (drawn as clipped height).
        line_top = 2.0
        line_full = max(0.0, h - 4.0)
        line_h = line_full * self._progress
        if line_h > 0.5:
            painter.setPen(QPen(TIMELINE_LINE, 2.0))
            x = TIMELINE_LINE_X
            painter.drawLine(QPointF(x, line_top), QPointF(x, line_top + line_h))

        title_font = QFont(self.font())
        title_font.setPointSize(9)
        detail_font = QFont(self.font())
        detail_font.setPointSize(8)

        for i, n in enumerate(self._nodes):
            reveal = self._node_reveal(i)
            if reveal <= 0.001:
                continue
            r = self._node_rect(i)
            slide = TIMELINE_SLIDE_PX * (1.0 - reveal)
            alpha = int(255 * reveal)

            # Selected / hover wash (also faded by reveal).
            if n.selected or n.key == self._hover_key:
                bg = QColor(TIMELINE_SELECT_BG if n.selected else QColor(28, 52, 56, 180))
                bg.setAlpha(int(bg.alpha() * reveal))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRect(r)

            # Dot on the rail
            dot = QColor(TIMELINE_DOT_ON if n.selected else TIMELINE_DOT)
            dot.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            cy = r.center().y()
            painter.drawEllipse(
                QPointF(TIMELINE_LINE_X, cy), TIMELINE_DOT_R, TIMELINE_DOT_R
            )

            # Title + detail, slid from the left
            tx = TIMELINE_TEXT_X + slide
            if n.selected:
                title_c = QColor(255, 248, 240, alpha)
                detail_c = QColor(255, 248, 240, int(alpha * 0.75))
            elif n.locked:
                title_c = QColor(TIMELINE_TEXT_LOCKED)
                title_c.setAlpha(min(title_c.alpha(), alpha))
                detail_c = QColor(title_c)
            else:
                title_c = QColor(TIMELINE_TEXT)
                title_c.setAlpha(alpha)
                detail_c = QColor(TIMELINE_TEXT_DIM)
                detail_c.setAlpha(int(alpha * 0.85))

            painter.setFont(title_font)
            fm = QFontMetrics(title_font)
            baseline = cy + (fm.ascent() - fm.descent()) * 0.35
            title = n.title
            painter.setPen(title_c)
            # Reserve room for detail on the right when present.
            detail_w = 0.0
            if n.detail:
                dfm = QFontMetrics(detail_font)
                detail_w = float(dfm.horizontalAdvance(n.detail)) + 8.0
            title_max = max(20.0, w - tx - 8.0 - detail_w)
            elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, int(title_max))
            painter.drawText(QPointF(tx, baseline), elided)

            if n.detail:
                painter.setFont(detail_font)
                painter.setPen(detail_c)
                dx = w - 8.0 - detail_w + 8.0
                painter.drawText(QPointF(dx, baseline), n.detail)

        painter.end()
