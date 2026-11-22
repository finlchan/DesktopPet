"""MAP window — steel-blue bubble canvas (topic / path / URL)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .save import load_map, make_bubble, save_map
from .scene import BubbleItem, MapScene, MapView

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
    """Edit 主題 / 電腦路徑 / 網站 — at least one required."""

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

        layout.addRow("主題 (topic):", self.topic_edit)
        layout.addRow("電腦路徑 (path):", path_wrap)
        layout.addRow("網站 (URL):", self.url_edit)

        hint = QLabel(
            "Fill at least one field. Double-click a bubble to edit; "
            "Open path/URL (or Enter) activates."
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

    def values(self) -> tuple[str, str, str]:
        return (
            self.topic_edit.text().strip(),
            self.path_edit.text().strip(),
            self.url_edit.text().strip(),
        )


class MapDialog(QDialog):
    """MAP: interconnected bubbles for topic / local path / website."""

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("MAP")
        self.setMinimumSize(640, 480)
        self.resize(760, 560)

        # Match mini-program frameless / ornate chrome when Desktop Pet helpers exist.
        dp = None
        try:
            import desktop_pet as dp  # noqa: F811
        except Exception:
            dp = None

        if dp is not None:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Dialog
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAutoFillBackground(False)
            self._drag_grips = []
            self.setStyleSheet(dp.CALC_DIALOG_STYLE + dp.MINI_PROGRAM_STYLE)
            root = dp.install_ornate_calc_frame(self)
            root.addWidget(dp.make_draggable_title(self, "MAP — bubbles"))
        else:
            self.setWindowFlags(
                Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setStyleSheet(MAP_FALLBACK_STYLE)
            root = QVBoxLayout(self)
            title = QLabel("MAP — bubbles")
            title.setStyleSheet("font-weight: bold; font-size: 12pt;")
            root.addWidget(title)

        root.setSpacing(6)

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
        root.addLayout(bar)

        self.status = QLabel(
            "Water ripple · Move cursor / click for waves · Drag bubbles · "
            "Double-click to edit · Connect · Wheel to zoom"
        )
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #c8d8e8; font-size: 8.5pt;")
        root.addWidget(self.status)

        self.scene = MapScene(self)
        self.view = MapView(self.scene, self)
        root.addWidget(self.view, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

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
            self.view.setDragMode(self.view.DragMode.RubberBandDrag)
            self.status.setText(
                "Water ripple · Move cursor / click for waves · Drag bubbles · "
                "Double-click to edit · Connect · Wheel to zoom"
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
            topic, path, url = dlg.values()
            item.set_fields(topic, path, url)
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
