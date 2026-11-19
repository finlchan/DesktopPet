"""QGraphicsView/Scene bubble graph for MAP (static drag; no physics yet)."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
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

# Steel-blue theme (Desktop Pet / menu palette)
BUBBLE_FILL = QColor(61, 90, 128, 210)          # #3d5a80
BUBBLE_FILL_SEL = QColor(90, 130, 170, 230)
BUBBLE_OUTLINE = QColor(135, 206, 250, 220)     # sky
BUBBLE_OUTLINE_SEL = QColor(232, 212, 139, 240)  # soft gilt
BUBBLE_TEXT = QColor(240, 246, 250)
EDGE_COLOR = QColor(176, 224, 255, 200)
EDGE_PREVIEW = QColor(232, 212, 139, 180)
SCENE_BG = QColor(28, 40, 55, 230)


class EdgeItem(QGraphicsLineItem):
    """Undirected link between two bubbles."""

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
        self.setLine(c1.x(), c1.y(), c2.x(), c2.y())


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
        if len(text) > 18:
            text = text[:16] + "…"
        self._label.setText(text)
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2.0, -br.height() / 2.0)

    def set_fields(self, topic: str, path: str, url: str) -> None:
        self.topic = (topic or "").strip()
        self.path = (path or "").strip()
        self.url = (url or "").strip()
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

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in list(self._edges):
                edge.refresh()
            scene = self.scene()
            if isinstance(scene, MapScene):
                scene.bubble_moved.emit()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.setBrush(QBrush(BUBBLE_FILL_SEL))
                self.setPen(QPen(BUBBLE_OUTLINE_SEL, 2.4))
            else:
                self.setBrush(QBrush(BUBBLE_FILL))
                self.setPen(QPen(BUBBLE_OUTLINE, 2.0))
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
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
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
        self.setBackgroundBrush(QBrush(SCENE_BG))
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
        if isinstance(item, BubbleItem):
            # Double-click: edit; Ctrl+double-click: activate
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.request_activate.emit(item)
            else:
                self.request_edit.emit(item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MapView(QGraphicsView):
    """Pan/zoom view for the bubble scene."""

    def __init__(self, scene: MapScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(SCENE_BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.scale(factor, factor)

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
