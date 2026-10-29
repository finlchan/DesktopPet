"""箱庭斜視 map widget — solid-color diamond placeholders (no art assets yet)."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from .grid import (
    DEFAULT_CELL,
    cell_center,
    diamond_vertices,
    hit_test,
    map_bounds,
    paint_order,
)
from .model import BUILDINGS, TERRAIN, IslandState

Coord = Tuple[int, int]


class HakoniwaMapWidget(QWidget):
    """Paints the 20×20 staggered diamond island and emits cell clicks."""

    cell_clicked = Signal(int, int)

    def __init__(self, state: IslandState, parent=None):
        super().__init__(parent)
        self.state = state
        self.cell = DEFAULT_CELL
        self.selected: Optional[Coord] = None
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin = (0.0, 0.0)
        self._recompute_origin()

    def set_state(self, state: IslandState) -> None:
        self.state = state
        self.selected = None
        self._recompute_origin()
        self.update()

    def select(self, i: int, j: int) -> None:
        self.selected = (i, j)
        self.update()

    def clear_selection(self) -> None:
        self.selected = None
        self.update()

    def _recompute_origin(self) -> None:
        min_x, min_y, max_x, max_y = map_bounds(self.state.size, self.cell)
        # Center the lattice in the widget when possible.
        self._lattice_w = max_x - min_x
        self._lattice_h = max_y - min_y
        self._min_x = min_x
        self._min_y = min_y

    def _origin_offset(self) -> Tuple[float, float]:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        ox = (w - self._lattice_w) / 2.0 - self._min_x
        oy = (h - self._lattice_h) / 2.0 - self._min_y
        return ox, oy

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Soft sky → sea wash (atmosphere; tiles remain solid diamonds).
        bg = QColor(28, 48, 72)
        painter.fillRect(self.rect(), bg)

        ox, oy = self._origin_offset()
        size = self.state.size

        for i, j in paint_order(size, self.cell):
            cell = self.state.cell(i, j)
            cx, cy = cell_center(i, j, self.cell)
            cx += ox
            cy += oy
            verts = diamond_vertices(cx, cy, self.cell)
            poly = QPolygonF([QPointF(x, y) for x, y in verts])

            terrain = TERRAIN.get(cell.terrain, TERRAIN["sea"])
            fill = QColor(*terrain["color"])
            painter.setBrush(QBrush(fill))
            edge = QColor(20, 24, 32, 180)
            painter.setPen(QPen(edge, 1.0))
            painter.drawPolygon(poly)

            # Building: smaller inset diamond (solid placeholder block).
            if cell.building and cell.building in BUILDINGS:
                bcol = BUILDINGS[cell.building]["color"]
                if bcol:
                    inset = self.cell * 0.55
                    bverts = diamond_vertices(cx, cy - self.cell * 0.08, inset)
                    bpoly = QPolygonF([QPointF(x, y) for x, y in bverts])
                    painter.setBrush(QBrush(QColor(*bcol)))
                    painter.setPen(QPen(QColor(30, 30, 30, 200), 1.0))
                    painter.drawPolygon(bpoly)

            if self.selected == (i, j):
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 240, 160), 2.2))
                painter.drawPolygon(poly)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        ox, oy = self._origin_offset()
        pos = event.position()
        hit = hit_test(
            pos.x(),
            pos.y(),
            self.state.size,
            self.cell,
            origin=(ox, oy),
        )
        if hit is not None:
            self.selected = hit
            self.cell_clicked.emit(hit[0], hit[1])
            self.update()
        super().mousePressEvent(event)
