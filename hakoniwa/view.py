"""箱庭斜視 map widget — textured diamond tops (dirt／grass／sea) + overlays.

Lattice is logical 1:1 diamonds with v9 stagger, then H/W≈0.65 oblique
foreshortening (Y *= OBLIQUE_Y_SCALE) from ``hakoniwa.grid`` — NOT a flat
top-down grid merely rotated 45°. Terrain uses flat top textures only; no
under-tile thickness/skirts. Buildings／monsters default to solid color
placeholders; optional user PNGs from ``Data/hakoniwa/user/`` or ``assets/user/``
replace them when present.

After any map/view change, run smoke (oblique invariant) and reject equal-
diagonal flat rotate (wrong-flat-rotated-grid.png). Prior
correct-hakoniwa-oblique-45.png was the old 0.707 reference; formal scale is 0.65.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPointF, QPoint, QRectF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QPolygonF,
    QWheelEvent,
    QMouseEvent,
    QKeyEvent,
)
from PySide6.QtWidgets import QWidget

from .grid import (
    DEFAULT_CELL,
    cell_center,
    cell_screen_size,
    diamond_vertices,
    hit_test,
    map_bounds,
    paint_order,
)
from .model import BUILDINGS, TERRAIN, IslandState
from .tiles import ATLAS

Coord = Tuple[int, int]

MIN_CELL = 12.0
MAX_CELL = 96.0
ZOOM_STEP = 1.12
# Fallback wash when ocean-background.png is missing.
BG_FALLBACK = QColor(28, 48, 72)


class HakoniwaMapWidget(QWidget):
    """Paints the 20×20 staggered diamond island and emits cell clicks."""

    cell_clicked = Signal(int, int)

    def __init__(self, state: IslandState, parent=None):
        super().__init__(parent)
        self.state = state
        self.cell = float(DEFAULT_CELL)
        self.selected: Optional[Coord] = None
        self._pan = QPointF(0.0, 0.0)
        self._panning = False
        self._pan_last: Optional[QPoint] = None
        self._atlas = ATLAS
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("滾輪縮放 · 中鍵／右鍵拖曳平移 · 左鍵選格")
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

    def reset_view(self) -> None:
        """Fit map to widget (default cell size, centered, no pan)."""
        self.cell = float(DEFAULT_CELL)
        self._pan = QPointF(0.0, 0.0)
        self._recompute_origin()
        self.update()

    def zoom_by(self, factor: float, anchor: Optional[QPointF] = None) -> None:
        """Multiply cell size by factor; keep ``anchor`` (widget coords) stable."""
        old = self.cell
        new = max(MIN_CELL, min(MAX_CELL, old * factor))
        if abs(new - old) < 1e-6:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        ratio = new / old
        c_old_x, c_old_y = self._origin_offset_raw()
        pan_old = self._pan
        self.cell = new
        self._recompute_origin()
        c_new_x, c_new_y = self._origin_offset_raw()
        # Lattice coords scale with cell; keep the point under anchor fixed.
        # pan_new = (1-r)*anchor + r*C(old) - C(new) + r*pan_old
        self._pan = QPointF(
            (1.0 - ratio) * anchor.x()
            + ratio * c_old_x
            - c_new_x
            + ratio * pan_old.x(),
            (1.0 - ratio) * anchor.y()
            + ratio * c_old_y
            - c_new_y
            + ratio * pan_old.y(),
        )
        self.update()

    def pan_by(self, dx: float, dy: float) -> None:
        self._pan = QPointF(self._pan.x() + dx, self._pan.y() + dy)
        self.update()

    def _recompute_origin(self) -> None:
        min_x, min_y, max_x, max_y = map_bounds(self.state.size, self.cell)
        self._lattice_w = max_x - min_x
        self._lattice_h = max_y - min_y
        self._min_x = min_x
        self._min_y = min_y

    def _origin_offset_raw(self) -> Tuple[float, float]:
        """Centered lattice origin without user pan."""
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        ox = (w - self._lattice_w) / 2.0 - self._min_x
        oy = (h - self._lattice_h) / 2.0 - self._min_y
        return ox, oy

    def _origin_offset(self) -> Tuple[float, float]:
        ox, oy = self._origin_offset_raw()
        return ox + self._pan.x(), oy + self._pan.y()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def _paint_background(self, painter: QPainter) -> None:
        """Sea backdrop (ocean texture) or dark-teal wash; sea cells still tiled."""
        bg = self._atlas.ocean_background()
        if bg is not None and not bg.isNull():
            painter.drawPixmap(self.rect(), bg)
            # Slight darken so HUD text stays readable over bright water.
            painter.fillRect(self.rect(), QColor(8, 24, 36, 70))
        else:
            painter.fillRect(self.rect(), BG_FALLBACK)

    def _paint_terrain_top(
        self,
        painter: QPainter,
        terrain_key: str,
        cx: float,
        cy: float,
        poly: QPolygonF,
    ) -> None:
        """Draw flat top texture clipped to the foreshortened diamond (no skirts)."""
        w, h = cell_screen_size(self.cell)
        hw, hh = w / 2.0, h / 2.0
        dest = QRectF(cx - hw, cy - hh, w, h)
        pix = self._atlas.pixmap_for(terrain_key)
        if pix is not None and not pix.isNull():
            path = QPainterPath()
            path.addPolygon(poly)
            painter.save()
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPixmap(dest, pix, QRectF(0, 0, pix.width(), pix.height()))
            tint = self._atlas.tint_for(terrain_key)
            if tint is not None:
                painter.fillPath(path, tint)
            painter.restore()
        else:
            # Color placeholder if a top PNG is missing.
            meta = TERRAIN.get(terrain_key, TERRAIN["sea"])
            painter.setBrush(QBrush(QColor(*meta["color"])))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly)

        edge = QColor(20, 24, 32, 160)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(edge, 1.0))
        painter.drawPolygon(poly)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        self._paint_background(painter)

        ox, oy = self._origin_offset()
        size = self.state.size

        for i, j in paint_order(size, self.cell):
            cell = self.state.cell(i, j)
            cx, cy = cell_center(i, j, self.cell)
            cx += ox
            cy += oy
            verts = diamond_vertices(cx, cy, self.cell)
            poly = QPolygonF([QPointF(x, y) for x, y in verts])

            self._paint_terrain_top(painter, cell.terrain, cx, cy, poly)

            # Building: user PNG when dropped, else solid color diamond.
            # tall=True → sprite keeps aspect, anchored at the footprint's south
            # tip, drawn unclipped so peaks may rise above the cell's N tip
            # (ground footprint still spans the inset diamond).
            if cell.building and cell.building in BUILDINGS:
                meta = BUILDINGS[cell.building]
                inset = self.cell * 0.55
                bcy = cy - self.cell * 0.08
                bverts = diamond_vertices(cx, bcy, inset)
                bpoly = QPolygonF([QPointF(x, y) for x, y in bverts])
                bpix = self._atlas.building_pixmap(cell.building)
                if bpix is not None and not bpix.isNull():
                    bw, bh = cell_screen_size(inset)
                    if meta.get("tall"):
                        sprite_h = bw * bpix.height() / max(1.0, float(bpix.width()))
                        dest = QRectF(cx - bw / 2.0, bcy + bh / 2.0 - sprite_h, bw, sprite_h)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawPixmap(
                            dest, bpix, QRectF(0, 0, bpix.width(), bpix.height())
                        )
                    else:
                        dest = QRectF(cx - bw / 2.0, bcy - bh / 2.0, bw, bh)
                        path = QPainterPath()
                        path.addPolygon(bpoly)
                        painter.save()
                        painter.setClipPath(path)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawPixmap(
                            dest, bpix, QRectF(0, 0, bpix.width(), bpix.height())
                        )
                        painter.restore()
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.setPen(QPen(QColor(30, 30, 30, 200), 1.0))
                        painter.drawPolygon(bpoly)
                else:
                    bcol = BUILDINGS[cell.building]["color"]
                    if bcol:
                        painter.setBrush(QBrush(QColor(*bcol)))
                        painter.setPen(QPen(QColor(30, 30, 30, 200), 1.0))
                        painter.drawPolygon(bpoly)

            # Monster: user PNG when dropped, else axis-aligned color square.
            monster = self.state.monster_at(i, j)
            if monster is not None:
                side = self.cell * 0.42
                rect = QRectF(
                    cx - side / 2.0,
                    cy - side / 2.0 - self.cell * 0.06,
                    side,
                    side,
                )
                mpix = self._atlas.monster_pixmap(monster.kind)
                if mpix is not None and not mpix.isNull():
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPixmap(
                        rect, mpix, QRectF(0, 0, mpix.width(), mpix.height())
                    )
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor(20, 20, 20, 220), 1.4))
                    painter.drawRect(rect)
                else:
                    painter.setBrush(QBrush(QColor(*monster.color())))
                    painter.setPen(QPen(QColor(20, 20, 20, 220), 1.4))
                    painter.drawRect(rect)

            if self.selected == (i, j):
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 240, 160), 2.2))
                painter.drawPolygon(poly)

        painter.end()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP
        self.zoom_by(factor, event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        ):
            self._panning = True
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

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

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning and self._pan_last is not None:
            cur = event.position().toPoint()
            dx = cur.x() - self._pan_last.x()
            dy = cur.y() - self._pan_last.y()
            self._pan_last = cur
            self.pan_by(float(dx), float(dy))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        ):
            self._panning = False
            self._pan_last = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # Optional map-local shortcuts (dialog also handles global ones).
        key = event.key()
        step = 40.0
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by(ZOOM_STEP)
            event.accept()
            return
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom_by(1.0 / ZOOM_STEP)
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            self.pan_by(step, 0.0)
            event.accept()
            return
        if key == Qt.Key.Key_Right:
            self.pan_by(-step, 0.0)
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            self.pan_by(0.0, step)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            self.pan_by(0.0, -step)
            event.accept()
            return
        if key == Qt.Key.Key_0 and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.reset_view()
            event.accept()
            return
        super().keyPressEvent(event)
