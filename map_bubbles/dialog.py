"""MAP window — single gold frame, sea backdrop, bubble canvas."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .save import load_map, make_bubble, save_map
from .scene import BubbleItem, MapScene, MapView

# Thin gold line around the whole MAP UI (single border — no multi-layer frames).
MAP_GOLD = QColor(201, 168, 76)          # #c9a84c
MAP_GOLD_BRIGHT = QColor(232, 212, 139)  # #e8d48b
MAP_GOLD_DIM = QColor(122, 94, 24)       # #7a5e18
MAP_BORDER_PX = 1
MAP_CORNER_ARM = 18          # 『 』 bracket arm length
MAP_CORNER_HIT = 22          # resize hit size
MAP_CHROME_PAD = 8           # inset inside the gold line

MAP_FALLBACK_STYLE = """
QDialog {
    background-color: rgba(28, 40, 55, 230);
    color: #e8f2f8;
}
QPushButton {
    background-color: rgba(61, 90, 128, 230);
    color: #f0f6fa;
    border: 1px solid rgba(135, 206, 250, 160);
    border-radius: 3px;
    padding: 4px 10px;
}
QPushButton:hover { background-color: rgba(90, 130, 170, 240); }
QPushButton:checked { background-color: rgba(201, 168, 76, 220); color: #1e2832; }
QLineEdit {
    background-color: rgba(42, 42, 42, 230);
    color: #f0f0f0;
    border: 1px solid #666;
    border-radius: 3px;
    padding: 3px 6px;
}
QLabel { color: #e8f2f8; }
"""

MAP_OVERLAY_STYLE = """
QWidget#mapChromeOverlay, QWidget#mapChromeBottom {
    background-color: transparent;
}
QLabel#mapTitle {
    color: #f5e6c8;
    font-weight: bold;
    font-size: 11pt;
    background-color: transparent;
}
QLabel#mapStatus {
    color: #d0e0f0;
    font-size: 8.5pt;
    background-color: rgba(20, 32, 48, 120);
    padding: 2px 6px;
    border-radius: 2px;
}
QPushButton {
    background-color: rgba(40, 58, 78, 200);
    color: #f0f6fa;
    border: 1px solid rgba(201, 168, 76, 160);
    border-radius: 3px;
    padding: 4px 10px;
}
QPushButton:hover { background-color: rgba(61, 90, 128, 230); }
QPushButton:checked {
    background-color: rgba(201, 168, 76, 220);
    color: #1e2832;
}
"""


def _open_local_path(path: str) -> None:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess

        subprocess.Popen(["open", str(target)])
    else:
        import subprocess

        subprocess.Popen(["xdg-open", str(target)])


def _open_url(url: str) -> None:
    text = (url or "").strip()
    if not text:
        raise ValueError("Empty URL")
    qurl = QUrl.fromUserInput(text)
    if not qurl.isValid():
        raise ValueError(f"Invalid URL: {text}")
    if not QDesktopServices.openUrl(qurl):
        raise RuntimeError(f"Could not open URL: {text}")


class BubbleEditDialog(QDialog):
    """Edit 主題 / 電腦路徑 / 網站 / 大小 — at least one of topic/path/URL required."""

    def __init__(self, bubble: BubbleItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit bubble / 編輯氣泡")
        self.setMinimumWidth(420)
        self.setStyleSheet(MAP_FALLBACK_STYLE)
        layout = QFormLayout(self)

        self.topic_edit = QLineEdit(bubble.topic)
        self.topic_edit.setPlaceholderText("主題 / topic")
        self.path_edit = QLineEdit(bubble.path)
        self.path_edit.setPlaceholderText("電腦路徑 / local file or folder")
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        path_wrap = QWidget()
        path_wrap.setLayout(path_row)

        self.url_edit = QLineEdit(bubble.url)
        self.url_edit.setPlaceholderText("網站 / https://…")

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(36.0, 120.0)
        self.size_spin.setDecimals(0)
        self.size_spin.setSingleStep(4.0)
        self.size_spin.setSuffix(" px")
        self.size_spin.setValue(float(bubble.radius))
        self.size_spin.setToolTip("Bubble radius (config field r); 36–120")

        layout.addRow("主題 (topic):", self.topic_edit)
        layout.addRow("電腦路徑 (path):", path_wrap)
        layout.addRow("網站 (URL):", self.url_edit)
        layout.addRow("大小 (size / r):", self.size_spin)

        hint = QLabel(
            "Fill at least one of topic / path / URL. Size is radius in pixels "
            "(saved as r). Double-click a bubble to edit; Open path/URL (or Enter) activates."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ab; font-size: 8.5pt;")
        layout.addRow(hint)

        buttons = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addRow(buttons)

    def _browse(self) -> None:
        start = self.path_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose file", start)
        if not path:
            path = QFileDialog.getExistingDirectory(self, "Choose folder", start) or ""
        if path:
            self.path_edit.setText(path)

    def _accept(self) -> None:
        topic = self.topic_edit.text().strip()
        path = self.path_edit.text().strip()
        url = self.url_edit.text().strip()
        if not (topic or path or url):
            QMessageBox.warning(
                self,
                "MAP",
                "Please set at least one of: topic, path, or URL.",
            )
            return
        self.accept()

    def values(self) -> tuple[str, str, str, float]:
        return (
            self.topic_edit.text().strip(),
            self.path_edit.text().strip(),
            self.url_edit.text().strip(),
            float(self.size_spin.value()),
        )


class _CornerResizeGrip(QWidget):
    """Transparent 『 or 』 corner hit target that resizes the MAP window."""

    def __init__(self, window: QDialog, mode: str, parent=None):
        super().__init__(parent)
        self._window = window
        self._mode = mode  # "tl" | "br"
        self.setFixedSize(MAP_CORNER_HIT, MAP_CORNER_HIT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        self.setToolTip("Drag to resize MAP")
        self._origin = QPoint()
        self._geom = QRect()
        self._active = False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._active = True
        self._origin = event.globalPosition().toPoint()
        self._geom = QRect(self._window.geometry())
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._active:
            return
        global_pos = event.globalPosition().toPoint()
        dx = global_pos.x() - self._origin.x()
        dy = global_pos.y() - self._origin.y()
        g = QRect(self._geom)
        min_w = max(320, self._window.minimumWidth())
        min_h = max(240, self._window.minimumHeight())
        if self._mode == "br":
            self._window.resize(max(min_w, g.width() + dx), max(min_h, g.height() + dy))
        else:
            new_w = max(min_w, g.width() - dx)
            new_h = max(min_h, g.height() - dy)
            used_dx = g.width() - new_w
            used_dy = g.height() - new_h
            self._window.setGeometry(g.x() + used_dx, g.y() + used_dy, new_w, new_h)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._active:
            self._active = False
            self.releaseMouse()
            event.accept()


class MapGoldShell(QWidget):
    """One thin gold border + 『 / 』 corner brackets that resize the MAP window."""

    def __init__(self, window: QDialog, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName("mapGoldShell")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self._drag_offset: QPoint | None = None

        inner = QVBoxLayout(self)
        inner.setContentsMargins(
            MAP_CHROME_PAD, MAP_CHROME_PAD, MAP_CHROME_PAD, MAP_CHROME_PAD
        )
        inner.setSpacing(0)
        self.content = QWidget(self)
        self.content.setObjectName("mapGoldContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content.setAutoFillBackground(False)
        inner.addWidget(self.content)

        # Raised above content so corner hits are never covered by the sea view.
        self._grip_tl = _CornerResizeGrip(window, "tl", self)
        self._grip_br = _CornerResizeGrip(window, "br", self)
        self._grip_tl.raise_()
        self._grip_br.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._grip_tl.move(0, 0)
        self._grip_br.move(
            self.width() - MAP_CORNER_HIT, self.height() - MAP_CORNER_HIT
        )
        self._grip_tl.raise_()
        self._grip_br.raise_()

    def _border_band_hit(self, pos: QPoint) -> bool:
        t = MAP_CHROME_PAD
        r = self.rect()
        x, y = pos.x(), pos.y()
        return (
            x < t
            or y < t
            or x >= r.width() - t
            or y >= r.height() - t
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(0, 0, -1, -1)

        # Single thin gold line around the whole MAP UI.
        painter.setPen(QPen(MAP_GOLD, MAP_BORDER_PX, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)

        # 『 top-left and 』 bottom-right corner brackets (resize grips).
        arm = MAP_CORNER_ARM
        pen = QPen(MAP_GOLD_BRIGHT, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)
        ox, oy = 3, 3
        painter.drawLine(ox, oy, ox + arm, oy)
        painter.drawLine(ox, oy, ox, oy + arm)
        painter.setPen(QPen(MAP_GOLD_DIM, 1.5))
        painter.drawLine(ox, oy, ox + 5, oy + 5)

        bx = r.right() - 3
        by = r.bottom() - 3
        painter.setPen(pen)
        painter.drawLine(bx - arm, by, bx, by)
        painter.drawLine(bx, by - arm, bx, by)
        painter.setPen(QPen(MAP_GOLD_DIM, 1.5))
        painter.drawLine(bx, by, bx - 5, by - 5)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        if self._border_band_hit(pos):
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._window.move(
                event.globalPosition().toPoint() - self._drag_offset
            )
            event.accept()
            return
        pos = event.position().toPoint()
        if self._border_band_hit(pos):
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.releaseMouse()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MapDialog(QDialog):
    """MAP: interconnected bubbles for topic / local path / website.

    One composition: sea water + title/toolbar chrome inside a single gold border.
    『 / 』 corner brackets resize the window; empty-canvas drag pans the view.
    """

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("MAP")
        self.setMinimumSize(640, 480)
        self.resize(760, 560)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(MAP_OVERLAY_STYLE + MAP_FALLBACK_STYLE)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self._gold = MapGoldShell(self, self)
        shell.addWidget(self._gold)

        # Body: MapView fills the gold frame; title/toolbar overlay on the sea.
        body_layout = QVBoxLayout(self._gold.content)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._body = QWidget(self._gold.content)
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._body.setAutoFillBackground(False)
        body_layout.addWidget(self._body)

        self.scene = MapScene(self)
        self.view = MapView(self.scene, self._body)
        self.view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Overlay chrome (title + toolbar + status) — sits on the sea, not outside.
        self._top = QWidget(self._body)
        self._top.setObjectName("mapChromeOverlay")
        self._top.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        top_col = QVBoxLayout(self._top)
        top_col.setContentsMargins(8, 6, 8, 4)
        top_col.setSpacing(4)

        title = QLabel("MAP")
        title.setObjectName("mapTitle")
        title.setFont(QFont("Microsoft JhengHei", 11, QFont.Weight.Bold))
        top_col.addWidget(title)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_add = QPushButton("Add bubble")
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setCheckable(True)
        self.btn_edit = QPushButton("Edit")
        self.btn_activate = QPushButton("Open path/URL")
        self.btn_delete = QPushButton("Delete")
        self.btn_fit = QPushButton("Fit")
        for b in (
            self.btn_add,
            self.btn_connect,
            self.btn_edit,
            self.btn_activate,
            self.btn_delete,
            self.btn_fit,
        ):
            bar.addWidget(b)
        bar.addStretch()
        top_col.addLayout(bar)

        self.status = QLabel(
            "Pan empty space · Wheel zoom · 『』 corners resize · "
            "Drag bubbles · Double-click edit · Connect"
        )
        self.status.setObjectName("mapStatus")
        self.status.setWordWrap(True)
        top_col.addWidget(self.status)

        self._bottom = QWidget(self._body)
        self._bottom.setObjectName("mapChromeBottom")
        self._bottom.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        bottom_row = QHBoxLayout(self._bottom)
        bottom_row.setContentsMargins(8, 4, 8, 6)
        bottom_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom_row.addWidget(close_btn)

        self._body.installEventFilter(self)

        self.btn_add.clicked.connect(self._add_bubble)
        self.btn_connect.toggled.connect(self._toggle_connect)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_activate.clicked.connect(self._activate_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_fit.clicked.connect(self.view.fit_bubbles)

        self.scene.request_edit.connect(self._edit_bubble)
        self.scene.request_activate.connect(self._activate_bubble)
        self.scene.changed_graph.connect(self._persist)
        self.scene.bubble_moved.connect(self._schedule_persist)
        self.scene.connect_picked.connect(
            lambda _b: self.status.setText("Connect: click the second bubble…")
        )

        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(400)
        self._persist_timer.timeout.connect(self._persist)

        self._load()
        QTimer.singleShot(0, self._layout_overlays)

    def eventFilter(self, obj, event):  # noqa: N802
        from PySide6.QtCore import QEvent

        if obj is self._body and event.type() == QEvent.Type.Resize:
            self._layout_overlays()
        return super().eventFilter(obj, event)

    def _layout_overlays(self) -> None:
        """MapView fills the gold content; title/toolbar/close float on the sea."""
        r = self._body.rect()
        self.view.setGeometry(r)
        self._top.adjustSize()
        top_h = max(self._top.sizeHint().height(), self._top.height())
        self._top.setGeometry(0, 0, r.width(), top_h)
        self._bottom.adjustSize()
        bot_h = max(self._bottom.sizeHint().height(), 36)
        self._bottom.setGeometry(0, r.height() - bot_h, r.width(), bot_h)
        self._top.raise_()
        self._bottom.raise_()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._layout_overlays()

    def _load(self) -> None:
        bubbles, edges = load_map(self.cfg)
        self.scene.clear_graph()
        for data in bubbles:
            self.scene.add_bubble_from_dict(data)
        id_map = {b.bubble_id: b for b in self.scene.bubbles()}
        for e in edges:
            a = id_map.get(e["a"])
            b = id_map.get(e["b"])
            if a and b:
                self.scene.add_edge_between(a, b)
        if not bubbles:
            starter = make_bubble(x=0, y=0, topic="主題 / Topic")
            self.scene.add_bubble_from_dict(starter)
            self._persist()
        QTimer.singleShot(0, self.view.fit_bubbles)

    def _persist(self) -> None:
        bubbles = [b.to_dict() for b in self.scene.bubbles()]
        edges = [
            {"a": e.bubble_a.bubble_id, "b": e.bubble_b.bubble_id}
            for e in self.scene.edges()
        ]
        save_map(self.cfg, bubbles, edges)

    def _schedule_persist(self) -> None:
        self._persist_timer.start()

    def _selected_bubbles(self) -> list[BubbleItem]:
        return [i for i in self.scene.selectedItems() if isinstance(i, BubbleItem)]

    def _add_bubble(self) -> None:
        center = self.view.mapToScene(self.view.viewport().rect().center())
        n = len(self.scene.bubbles())
        data = make_bubble(
            x=center.x() + (n % 5) * 20,
            y=center.y() + (n % 5) * 20,
            topic=f"Bubble {n + 1}",
        )
        item = self.scene.add_bubble_from_dict(data)
        self.scene.clearSelection()
        item.setSelected(True)
        self._edit_bubble(item)
        self._persist()

    def _toggle_connect(self, checked: bool) -> None:
        self.scene.set_connect_mode(checked)
        if checked:
            self.view.setDragMode(self.view.DragMode.NoDrag)
            self.status.setText("Connect mode: click first bubble, then second.")
        else:
            self.view.setDragMode(self.view.DragMode.ScrollHandDrag)
            self.status.setText(
                "Pan empty space · Wheel zoom · 『』 corners resize · "
                "Drag bubbles · Double-click edit · Connect"
            )

    def _edit_selected(self) -> None:
        items = self._selected_bubbles()
        if not items:
            QMessageBox.information(self, "MAP", "Select a bubble first.")
            return
        self._edit_bubble(items[0])

    def _edit_bubble(self, item: BubbleItem) -> None:
        dlg = BubbleEditDialog(item, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            topic, path, url, radius = dlg.values()
            item.set_fields(topic, path, url, radius=radius)
            self.view.mark_backdrop_dirty()
            self._persist()

    def _activate_selected(self) -> None:
        items = self._selected_bubbles()
        if not items:
            QMessageBox.information(self, "MAP", "Select a bubble first.")
            return
        self._activate_bubble(items[0])

    def _activate_bubble(self, item: BubbleItem) -> None:
        path = (item.path or "").strip()
        url = (item.url or "").strip()
        if not path and not url:
            QMessageBox.information(
                self,
                "MAP",
                "This bubble has no path or URL. Edit it to add one.",
            )
            return
        errors = []
        opened = []
        if url:
            try:
                _open_url(url)
                opened.append(f"URL {url}")
            except Exception as exc:
                errors.append(str(exc))
        if path:
            try:
                _open_local_path(path)
                opened.append(f"path {path}")
            except Exception as exc:
                errors.append(str(exc))
        if opened:
            self.status.setText("Opened: " + "; ".join(opened))
        if errors:
            QMessageBox.warning(self, "MAP", "\n".join(errors))

    def _delete_selected(self) -> None:
        items = self._selected_bubbles()
        if not items:
            QMessageBox.information(self, "MAP", "Select a bubble to delete.")
            return
        for item in items:
            self.scene.remove_bubble(item)
        self._persist()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_selected()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.btn_connect.isChecked():
            self.btn_connect.setChecked(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist()
        super().closeEvent(event)
