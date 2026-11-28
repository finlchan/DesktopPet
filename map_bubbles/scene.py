"""QGraphicsView/Scene bubble graph for MAP (static drag; water-ripple backdrop)."""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .water_ripple import WaterRippleSim

# Steel-blue theme (Desktop Pet / menu palette)
# Interior fill ~60% opaque; labels stay full opacity on the live item.
BUBBLE_FILL_ALPHA = int(round(255 * 0.60))      # ≈153
BUBBLE_FILL = QColor(61, 90, 128, BUBBLE_FILL_ALPHA)          # #3d5a80
BUBBLE_FILL_SEL = QColor(90, 130, 170, BUBBLE_FILL_ALPHA)
BUBBLE_OUTLINE = QColor(135, 206, 250, 220)     # sky
BUBBLE_OUTLINE_SEL = QColor(232, 212, 139, 240)  # soft gilt
BUBBLE_TEXT = QColor(240, 246, 250)
EDGE_COLOR = QColor(176, 224, 255, 200)
EDGE_PREVIEW = QColor(232, 212, 139, 180)
SCENE_BG = QColor(28, 40, 55, 230)

# Ripple tick / interaction
RIPPLE_FPS_MS = 33          # ~30 fps
IDLE_DROP_MIN_MS = 2800
IDLE_DROP_MAX_MS = 5200
MOVE_DRIP_MIN_DIST = 6.0    # view pixels between path drips
MOVE_DRIP_RADIUS = 1.6
MOVE_DRIP_STRENGTH = 90.0
CLICK_RADIUS = 4.0
CLICK_STRENGTH = 320.0
IDLE_RADIUS = 3.2
IDLE_STRENGTH = 240.0


class EdgeItem(QGraphicsLineItem):
    """Undirected link between two bubbles (drawn above the water layer).

    Endpoints sit on each bubble's outer rim (not the centers).
    """

    def __init__(self, a: "BubbleItem", b: "BubbleItem"):
        super().__init__()
        self.bubble_a = a
        self.bubble_b = b
        self.setZValue(-1)
        self.setPen(QPen(EDGE_COLOR, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.refresh()

    def edge_key(self) -> Tuple[str, str]:
        a, b = self.bubble_a.bubble_id, self.bubble_b.bubble_id
        return (a, b) if a < b else (b, a)

    def refresh(self) -> None:
        c1 = self.bubble_a.scenePos()
        c2 = self.bubble_b.scenePos()
        dx = c2.x() - c1.x()
        dy = c2.y() - c1.y()
        dist = math.hypot(dx, dy)
        r1 = float(self.bubble_a.radius)
        r2 = float(self.bubble_b.radius)
        if dist < 1e-6:
            # Coincident centers — hide the segment
            self.setLine(c1.x(), c1.y(), c1.x(), c1.y())
            self.setVisible(False)
            return
        # Overlap / touch: no visible gap between rims
        if dist <= r1 + r2 + 0.5:
            self.setVisible(False)
            self.setLine(c1.x(), c1.y(), c2.x(), c2.y())
            return
        self.setVisible(True)
        ux, uy = dx / dist, dy / dist
        x1 = c1.x() + ux * r1
        y1 = c1.y() + uy * r1
        x2 = c2.x() - ux * r2
        y2 = c2.y() - uy * r2
        self.setLine(x1, y1, x2, y2)


class BubbleItem(QGraphicsEllipseItem):
    """One editable bubble: topic / local path / website."""

    def __init__(
        self,
        bubble_id: str,
        topic: str = "",
        path: str = "",
        url: str = "",
        radius: float = 52.0,
    ):
        diam = radius * 2.0
        super().__init__(-radius, -radius, diam, diam)
        self.bubble_id = bubble_id
        self.topic = topic or ""
        self.path = path or ""
        self.url = url or ""
        self.radius = radius
        self._edges: Set[EdgeItem] = set()

        self.setBrush(QBrush(BUBBLE_FILL))
        self.setPen(QPen(BUBBLE_OUTLINE, 2.0))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._label = QGraphicsSimpleTextItem(self)
        self._label.setBrush(QBrush(BUBBLE_TEXT))
        font = QFont("Sans Serif")
        font.setPointSize(9)
        font.setBold(True)
        self._label.setFont(font)
        self._refresh_label()
        # Labels stay on the live item (above water) so text is never refracted.
        self._label.setOpacity(1.0)

    def attach_edge(self, edge: EdgeItem) -> None:
        self._edges.add(edge)

    def detach_edge(self, edge: EdgeItem) -> None:
        self._edges.discard(edge)

    def edges(self) -> Set[EdgeItem]:
        return set(self._edges)

    def display_text(self) -> str:
        if self.topic.strip():
            return self.topic.strip()
        if self.path.strip():
            # Show basename-ish tail for long paths
            p = self.path.strip().replace("\\", "/")
            return p.rsplit("/", 1)[-1] or p
        if self.url.strip():
            u = self.url.strip()
            if "://" in u:
                u = u.split("://", 1)[1]
            return u[:28]
        return "(empty)"

    def _refresh_label(self) -> None:
        text = self.display_text()
        # Soft wrap by truncating for the circle
        max_chars = max(10, int(self.radius / 3.2))
        if len(text) > max_chars:
            text = text[: max(1, max_chars - 2)] + "…"
        self._label.setText(text)
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2.0, -br.height() / 2.0)

    def set_radius(self, radius: float) -> None:
        """Resize the circle (config field ``r``); refresh attached edges."""
        try:
            r = float(radius)
        except (TypeError, ValueError):
            r = 52.0
        r = max(36.0, min(r, 120.0))
        if abs(r - self.radius) < 1e-6:
            return
        self.radius = r
        diam = r * 2.0
        self.setRect(-r, -r, diam, diam)
        self._refresh_label()
        for edge in list(self._edges):
            edge.refresh()
        self.update()

    def set_fields(
        self,
        topic: str,
        path: str,
        url: str,
        radius: Optional[float] = None,
    ) -> None:
        self.topic = (topic or "").strip()
        self.path = (path or "").strip()
        self.url = (url or "").strip()
        if radius is not None:
            # set_radius early-returns when r is unchanged — still refresh the label.
            self.set_radius(radius)
        # Always refresh on-bubble text so topic/path/URL renames show immediately.
        self._refresh_label()
        self.update()

    def to_dict(self) -> dict:
        pos = self.scenePos()
        return {
            "id": self.bubble_id,
            "x": pos.x(),
            "y": pos.y(),
            "r": self.radius,
            "topic": self.topic,
            "path": self.path,
            "url": self.url,
        }

    def _fill_color(self) -> QColor:
        return BUBBLE_FILL_SEL if self.isSelected() else BUBBLE_FILL

    def _outline_color(self) -> QColor:
        return BUBBLE_OUTLINE_SEL if self.isSelected() else BUBBLE_OUTLINE

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in list(self._edges):
                edge.refresh()
            scene = self.scene()
            if isinstance(scene, MapScene):
                scene.bubble_moved.emit()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # Brush/pen kept for legacy callers; paint() draws the ring look.
            if value:
                self.setBrush(QBrush(BUBBLE_FILL_SEL))
                self.setPen(QPen(BUBBLE_OUTLINE_SEL, 2.4))
            else:
                self.setBrush(QBrush(BUBBLE_FILL))
                self.setPen(QPen(BUBBLE_OUTLINE, 2.0))
            self.update()
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Live bubble (and label child) stay above the water layer — never refracted.
        # Ring look: solid outer stroke; inward from the rim the outline soft-fades
        # into the fill so the center stays readable.
        fill = self._fill_color()
        outline = self._outline_color()
        r = float(self.radius)
        grad = QRadialGradient(QPointF(0, 0), r)
        grad.setColorAt(0.0, fill)
        grad.setColorAt(0.72, fill)
        # Blend outline into fill near the rim
        blend = QColor(
            int(fill.red() * 0.45 + outline.red() * 0.55),
            int(fill.green() * 0.45 + outline.green() * 0.55),
            int(fill.blue() * 0.45 + outline.blue() * 0.55),
            max(fill.alpha(), outline.alpha()),
        )
        grad.setColorAt(0.88, blend)
        rim = QColor(outline)
        rim.setAlpha(min(255, int(outline.alpha() * 0.85)))
        grad.setColorAt(0.97, rim)
        grad.setColorAt(1.0, outline)

        stroke_w = 2.4 if self.isSelected() else 2.0
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(outline, stroke_w, Qt.PenStyle.SolidLine))
        painter.drawEllipse(self.rect())
        # Tiny type hints: path / url badges
        painter.setPen(Qt.PenStyle.NoPen)
        badge_y = self.rect().bottom() - 14
        x0 = self.rect().center().x()
        if self.path.strip():
            painter.setBrush(QColor(232, 212, 139, 220))
            painter.drawEllipse(QPointF(x0 - 8, badge_y), 3.5, 3.5)
        if self.url.strip():
            painter.setBrush(QColor(135, 206, 250, 230))
            painter.drawEllipse(QPointF(x0 + 8, badge_y), 3.5, 3.5)


class MapScene(QGraphicsScene):
    """Scene owning bubbles + edges; optional connect-two mode."""

    bubble_moved = Signal()
    request_edit = Signal(object)  # BubbleItem
    request_activate = Signal(object)  # BubbleItem
    changed_graph = Signal()
    connect_picked = Signal(object)  # BubbleItem while linking

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.transparent))
        self._bubbles: Dict[str, BubbleItem] = {}
        self._edges: Dict[Tuple[str, str], EdgeItem] = {}
        self.connect_mode = False
        self._connect_from: Optional[BubbleItem] = None

    def bubbles(self) -> List[BubbleItem]:
        return list(self._bubbles.values())

    def edges(self) -> List[EdgeItem]:
        return list(self._edges.values())

    def clear_graph(self) -> None:
        self.clear()
        self._bubbles.clear()
        self._edges.clear()
        self._connect_from = None

    def add_bubble_from_dict(self, data: dict) -> BubbleItem:
        item = BubbleItem(
            data["id"],
            topic=data.get("topic", ""),
            path=data.get("path", ""),
            url=data.get("url", ""),
            radius=float(data.get("r", 52) or 52),
        )
        item.setPos(float(data.get("x", 0)), float(data.get("y", 0)))
        self.addItem(item)
        self._bubbles[item.bubble_id] = item
        return item

    def add_edge_between(self, a: BubbleItem, b: BubbleItem) -> Optional[EdgeItem]:
        if a is b:
            return None
        key = (a.bubble_id, b.bubble_id)
        if key[0] > key[1]:
            key = (key[1], key[0])
        if key in self._edges:
            return self._edges[key]
        edge = EdgeItem(a, b)
        self.addItem(edge)
        a.attach_edge(edge)
        b.attach_edge(edge)
        self._edges[key] = edge
        self.changed_graph.emit()
        return edge

    def remove_edge(self, edge: EdgeItem) -> None:
        key = edge.edge_key()
        self._edges.pop(key, None)
        edge.bubble_a.detach_edge(edge)
        edge.bubble_b.detach_edge(edge)
        if edge.scene() is self:
            self.removeItem(edge)
        self.changed_graph.emit()

    def disconnect_bubble(self, item: BubbleItem) -> int:
        """Remove every link attached to ``item``; keep the bubble. Returns count removed."""
        edges = list(item.edges())
        for edge in edges:
            self.remove_edge(edge)
        return len(edges)

    def remove_bubble(self, item: BubbleItem) -> None:
        for edge in list(item.edges()):
            self.remove_edge(edge)
        self._bubbles.pop(item.bubble_id, None)
        if item.scene() is self:
            self.removeItem(item)
        if self._connect_from is item:
            self._connect_from = None
        self.changed_graph.emit()

    def set_connect_mode(self, enabled: bool) -> None:
        self.connect_mode = bool(enabled)
        self._connect_from = None
        for b in self._bubbles.values():
            b.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                not self.connect_mode,
            )
            b.setCursor(
                Qt.CursorShape.PointingHandCursor
                if self.connect_mode
                else Qt.CursorShape.OpenHandCursor
            )

    def _item_at(self, pos) -> Optional[QGraphicsItem]:
        if self.views():
            xform = self.views()[0].transform()
        else:
            xform = QTransform()
        return self.itemAt(pos, xform)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            self.connect_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            item = self._item_at(event.scenePos())
            # Walk up to BubbleItem if we hit the label
            while item is not None and not isinstance(item, BubbleItem):
                item = item.parentItem()
            if isinstance(item, BubbleItem):
                if self._connect_from is None:
                    self._connect_from = item
                    item.setSelected(True)
                    self.connect_picked.emit(item)
                else:
                    if item is not self._connect_from:
                        self.add_edge_between(self._connect_from, item)
                    self._connect_from = None
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        item = self._item_at(event.scenePos())
        while item is not None and not isinstance(item, BubbleItem):
            item = item.parentItem()
        if isinstance(item, BubbleItem) and event.button() == Qt.MouseButton.LeftButton:
            # Left double-click opens path/URL (same as former toolbar Open).
            self.request_activate.emit(item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MapView(QGraphicsView):
    """Pan/zoom view with sea-surface water-ripple backdrop (bubbles stay sharp on top).

    No visible scrollbars — pan by left-drag on empty canvas (ScrollHandDrag).
    Bubble drag / connect / edit still receive events on the items themselves.
    """

    def __init__(self, scene: MapScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Empty-space left-drag pans; items keep their own drag handlers.
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.transparent))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        # Hide scrollbars (pan still works via hidden bars / hand drag).
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.ripple_enabled = True
        self._ripple = WaterRippleSim()
        self._last_drip: Optional[QPointF] = None
        self._cached_frame = None  # QImage | None
        self._backdrop_dirty = True
        self._ripple_painted = False  # last frame drew the refraction overlay
        # Manual empty-space pan (ScrollHandDrag + AlwaysOff bars can be flaky;
        # we also track pan ourselves when the press is not on a bubble).
        self._panning = False
        self._pan_last: Optional[QPointF] = None

        self._tick = QTimer(self)
        self._tick.setInterval(RIPPLE_FPS_MS)
        self._tick.timeout.connect(self._on_ripple_tick)

        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._on_idle_drop)

        self._tick.start()
        self._arm_idle_drop()

    def _item_under(self, view_pos) -> Optional[QGraphicsItem]:
        scene = self.scene()
        if scene is None:
            return None
        sp = self.mapToScene(view_pos.toPoint() if hasattr(view_pos, "toPoint") else view_pos)
        item = scene.itemAt(sp, self.transform())
        while item is not None and not isinstance(item, BubbleItem):
            item = item.parentItem()
        return item

    # --- public helpers -------------------------------------------------

    def fit_bubbles(self) -> None:
        scene = self.scene()
        if not isinstance(scene, MapScene) or not scene.bubbles():
            self.resetTransform()
            return
        rect = QRectF()
        for b in scene.bubbles():
            rect = rect.united(b.sceneBoundingRect())
        rect = rect.adjusted(-40, -40, 40, 40)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def mark_backdrop_dirty(self) -> None:
        """Force sea-texture re-stamp (resize / show). Bubbles are not stamped."""
        self._backdrop_dirty = True

    # --- ripple simulation ----------------------------------------------

    def _arm_idle_drop(self) -> None:
        self._idle.start(random.randint(IDLE_DROP_MIN_MS, IDLE_DROP_MAX_MS))

    def _on_idle_drop(self) -> None:
        if not self.ripple_enabled or not self.isVisible():
            self._arm_idle_drop()
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        self._ripple.ensure_size(vw, vh)
        sx = random.uniform(vw * 0.15, vw * 0.85)
        sy = random.uniform(vh * 0.15, vh * 0.85)
        sim_x, sim_y = self._ripple.view_to_sim(sx, sy, vw, vh)
        self._ripple.disturb(sim_x, sim_y, radius=IDLE_RADIUS, strength=IDLE_STRENGTH)
        self._arm_idle_drop()

    def _splash_at_view(self, vx: float, vy: float, radius: float, strength: float) -> None:
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        self._ripple.ensure_size(vw, vh)
        sx, sy = self._ripple.view_to_sim(vx, vy, vw, vh)
        self._ripple.disturb(sx, sy, radius=radius, strength=strength)

    def _rebuild_backdrop(self) -> None:
        """Paint only the sea-surface texture into the sim backdrop (no bubbles)."""
        sim = self._ripple
        if sim.w < 2 or sim.h < 2:
            return
        sim.paint_base_water()
        self._backdrop_dirty = False

    def _on_ripple_tick(self) -> None:
        if not self.ripple_enabled or not self.isVisible():
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        self._ripple.ensure_size(vw, vh)
        dirty = self._backdrop_dirty
        if dirty:
            self._rebuild_backdrop()
        # Always step so damping settles. Skip the refraction blit when the field
        # is already quiet and the sea backdrop is cached. One extra frame after
        # the field goes flat drops the warped frame so it does not freeze.
        active = self._ripple.step()
        if active or self._cached_frame is None or dirty or self._ripple_painted:
            self._cached_frame = self._ripple.render_upscaled(vw, vh)
            self._ripple_painted = active
            self.viewport().update()

    # --- painting -------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        if not self.ripple_enabled:
            painter.fillRect(rect, SCENE_BG)
            return
        painter.save()
        painter.setWorldTransform(QTransform())
        frame = self._cached_frame
        if frame is None or frame.isNull():
            painter.fillRect(self.viewport().rect(), SCENE_BG)
        else:
            painter.drawImage(0, 0, frame)
        painter.restore()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._backdrop_dirty = True
        self._cached_frame = None

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._backdrop_dirty = True
        self._on_ripple_tick()
        if not self._tick.isActive():
            self._tick.start()
        self._arm_idle_drop()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._tick.stop()
        self._idle.stop()
        super().hideEvent(event)

    # --- input → ripples ------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.scale(factor, factor)
        # Sea texture is viewport-locked; zoom only moves scene items above it.

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.localPos()
        pt = QPointF(pos)
        if self._panning and self._pan_last is not None:
            delta = pt - self._pan_last
            self._pan_last = QPointF(pt)
            # Move the scene under the view (same sense as hand-drag).
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
            # Still drip while panning for calm water feedback.
            if self.ripple_enabled:
                if self._last_drip is None:
                    self._last_drip = QPointF(pt)
                    self._splash_at_view(pt.x(), pt.y(), MOVE_DRIP_RADIUS, MOVE_DRIP_STRENGTH)
                else:
                    dx = pt.x() - self._last_drip.x()
                    dy = pt.y() - self._last_drip.y()
                    if dx * dx + dy * dy >= MOVE_DRIP_MIN_DIST * MOVE_DRIP_MIN_DIST:
                        self._last_drip = QPointF(pt)
                        self._splash_at_view(
                            pt.x(), pt.y(), MOVE_DRIP_RADIUS, MOVE_DRIP_STRENGTH
                        )
            return
        if self.ripple_enabled:
            if self._last_drip is None:
                self._last_drip = QPointF(pt)
                self._splash_at_view(pt.x(), pt.y(), MOVE_DRIP_RADIUS, MOVE_DRIP_STRENGTH)
            else:
                dx = pt.x() - self._last_drip.x()
                dy = pt.y() - self._last_drip.y()
                if dx * dx + dy * dy >= MOVE_DRIP_MIN_DIST * MOVE_DRIP_MIN_DIST:
                    self._last_drip = QPointF(pt)
                    self._splash_at_view(pt.x(), pt.y(), MOVE_DRIP_RADIUS, MOVE_DRIP_STRENGTH)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.ripple_enabled and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position() if hasattr(event, "position") else event.localPos()
            self._splash_at_view(pos.x(), pos.y(), CLICK_RADIUS, CLICK_STRENGTH)
        # Empty-space left-drag pans the canvas (not when connecting / on a bubble).
        scene = self.scene()
        connect_mode = isinstance(scene, MapScene) and scene.connect_mode
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not connect_mode
            and self.dragMode() != QGraphicsView.DragMode.NoDrag
        ):
            pos = event.position() if hasattr(event, "position") else event.localPos()
            if self._item_under(pos) is None:
                self._panning = True
                self._pan_last = QPointF(pos)
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._panning and event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self._pan_last = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._last_drip = None
        if self._panning:
            self._panning = False
            self._pan_last = None
            self.viewport().unsetCursor()
        super().leaveEvent(event)
