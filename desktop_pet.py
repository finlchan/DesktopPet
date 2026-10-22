#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop Pet
A floating shortcut menu and document record gadget on the desktop.
"""

import html
import json
import os
import random
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QEvent, QLockFile
from PySide6.QtGui import QPixmap, QPainter, QColor, QCursor, QIcon, QAction, QMovie
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QDialog, QFormLayout, QTabWidget, QComboBox,
    QSpinBox, QCheckBox, QMessageBox, QMenu,
    QSystemTrayIcon, QPlainTextEdit, QFrame
)


SORT_LABELS = {
    "mtime": "File modified time",
    "name": "File name",
    "edit_time": "Edit info Time",
    "publisher": "Publisher",
}
LEGACY_SORT = {label: code for code, label in SORT_LABELS.items()}

WINDOW_LABELS = {
    "normal": "Normal",
    "top": "Always on top",
    "bottom": "Always on bottom",
}
LEGACY_WINDOW = {label: code for code, label in WINDOW_LABELS.items()}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

# App / release version (YYMMDD.NN). Shown in Settings → About.
APP_VERSION = "261022.01"


# ---------------------------------------------------------------------------
# Default settings (blank; safe to ship to other people)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "pet": {
        "image_path": "",
        "image_folder": "",
        "auto_change": False,
        "change_interval_sec": 5,
        "switch_mode": "Loop",
        "size": 120,
        "opacity": 0.9,
        "pos_x": 100,
        "pos_y": 100
    },
    "window": {
        "mode": "normal",
        "stay_on_top": False,
        "stay_on_bottom": False,
        "normal": True
    },
    "shortcuts": [],
    "document_area": {
        "title": "Document record",
        # "folder" kept for backward compatibility with older builds.
        "folder": "",
        # Primary list of storage folders (supports more than one).
        "folders": [],
        "sort_by": "mtime",
        "files": {}
    }
}


def normalize_sort(value):
    if value in SORT_LABELS:
        return value
    return LEGACY_SORT.get(value, "mtime")


def normalize_window_mode(window):
    if not isinstance(window, dict):
        return "normal"
    mode = window.get("mode")
    if mode in WINDOW_LABELS:
        return mode
    if window.get("stay_on_top"):
        return "top"
    if window.get("stay_on_bottom"):
        return "bottom"
    return "normal"


def apply_window_mode(window, mode):
    window["mode"] = mode
    window["normal"] = mode == "normal"
    window["stay_on_top"] = mode == "top"
    window["stay_on_bottom"] = mode == "bottom"


def normalize_document_folders(doc):
    """Ensure document_area has a folders list; migrate legacy single folder."""
    if not isinstance(doc, dict):
        return []

    folders = doc.get("folders")
    if not isinstance(folders, list):
        folders = []

    cleaned = []
    seen = set()
    for item in folders:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if path and path not in seen:
            seen.add(path)
            cleaned.append(path)

    legacy = doc.get("folder")
    if isinstance(legacy, str):
        legacy = legacy.strip()
    else:
        legacy = ""

    # Old configs only had document_area.folder — promote it into folders.
    if legacy and legacy not in seen:
        if not cleaned:
            cleaned = [legacy]
            seen.add(legacy)
        else:
            # Prefer existing folders list; still keep legacy as folder sync below.
            pass

    doc["folders"] = cleaned
    # Keep single folder field in sync (first entry) so older builds still work.
    doc["folder"] = cleaned[0] if cleaned else ""
    return cleaned


def menu_button_style(base_color, hover_factor=0.72):
    """Button style with a visibly darker hover state."""
    hover = darken_color(base_color, hover_factor)
    return (
        f"QPushButton {{ background-color: {base_color}; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
    )


def darken_color(color, factor=0.72):
    """Darken a #RRGGBB color for hover feedback."""
    text = (color or "").strip().lstrip("#")
    if len(text) != 6:
        return "rgba(0, 0, 0, 100)"
    try:
        r = int(int(text[0:2], 16) * factor)
        g = int(int(text[2:4], 16) * factor)
        b = int(int(text[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return "rgba(0, 0, 0, 100)"


def screen_available_geometry(widget):
    """Available area of the screen that contains the widget."""
    center = widget.frameGeometry().center()
    screen = QApplication.screenAt(center)
    if screen is None:
        screen = QApplication.primaryScreen()
    return screen.availableGeometry()


class ConfigManager:
    """Manage reading and writing of config.json."""

    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = {}
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.config = self._merge_defaults(loaded, DEFAULT_CONFIG)
            except Exception as e:
                print(f"Failed to load config, using defaults: {e}")
                self.config = json.loads(json.dumps(DEFAULT_CONFIG))
        else:
            self.config = json.loads(json.dumps(DEFAULT_CONFIG))
            self.save()
        mode = normalize_window_mode(self.config.get("window"))
        apply_window_mode(self.config.setdefault("window", {}), mode)
        doc = self.config.setdefault("document_area", {})
        doc["sort_by"] = normalize_sort(doc.get("sort_by"))
        normalize_document_folders(doc)

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def _merge_defaults(self, loaded, defaults):
        """Deep merge to ensure new fields exist."""
        if isinstance(loaded, dict) and isinstance(defaults, dict):
            result = {}
            for key, val in defaults.items():
                if key in loaded:
                    result[key] = self._merge_defaults(loaded[key], val)
                else:
                    result[key] = json.loads(json.dumps(val))
            for key, val in loaded.items():
                if key not in result:
                    result[key] = val
            return result
        return loaded

    def get(self, *keys):
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def set(self, keys, value, save=True):
        target = self.config
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        if save:
            self.save()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    """Settings dialog."""

    config_changed = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Desktop Pet Settings")
        self.setMinimumSize(600, 500)
        self.build_ui()
        self.load_data()

    def build_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        pet_tab = QWidget()
        pet_layout = QFormLayout(pet_tab)

        self.image_path_edit = QLineEdit()
        self.btn_browse_image = QPushButton("Browse")
        self.btn_browse_image.clicked.connect(self.browse_image)
        h1 = QHBoxLayout()
        h1.addWidget(self.image_path_edit)
        h1.addWidget(self.btn_browse_image)
        pet_layout.addRow("Custom Image:", h1)

        self.image_folder_edit = QLineEdit()
        self.btn_browse_folder = QPushButton("Browse")
        self.btn_browse_folder.clicked.connect(self.browse_image_folder)
        h2 = QHBoxLayout()
        h2.addWidget(self.image_folder_edit)
        h2.addWidget(self.btn_browse_folder)
        pet_layout.addRow("Auto-switch Image Set:", h2)

        self.auto_change_check = QCheckBox("Enable auto-switch")
        pet_layout.addRow("Auto-switch:", self.auto_change_check)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setSuffix(" sec")
        pet_layout.addRow("Switch Interval:", self.interval_spin)

        self.switch_mode = QComboBox()
        self.switch_mode.addItems(["Sequential", "Loop", "Random"])
        pet_layout.addRow("Switch Mode:", self.switch_mode)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(40, 400)
        self.size_spin.setSuffix(" px")
        pet_layout.addRow("Pet Size:", self.size_spin)

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(20, 100)
        self.opacity_spin.setSuffix(" %")
        pet_layout.addRow("Pet Opacity:", self.opacity_spin)

        self.tabs.addTab(pet_tab, "Pet Image")

        shortcut_tab = QWidget()
        shortcut_layout = QVBoxLayout(shortcut_tab)

        self.shortcut_list = QListWidget()
        self.shortcut_list.setMaximumHeight(180)
        shortcut_layout.addWidget(QLabel("Item list (Name | Path | Description):"))
        shortcut_layout.addWidget(self.shortcut_list)

        sc_form = QFormLayout()
        self.sc_name = QLineEdit()
        self.sc_path = QLineEdit()
        self.btn_sc_browse = QPushButton("Browse")
        self.btn_sc_browse.clicked.connect(self.browse_shortcut_path)
        h_sc = QHBoxLayout()
        h_sc.addWidget(self.sc_path)
        h_sc.addWidget(self.btn_sc_browse)
        self.sc_desc = QLineEdit()
        sc_form.addRow("Item Name:", self.sc_name)
        sc_form.addRow("Item Path:", h_sc)
        sc_form.addRow("Description:", self.sc_desc)
        shortcut_layout.addLayout(sc_form)

        btn_layout = QHBoxLayout()
        self.btn_add_sc = QPushButton("Add")
        self.btn_update_sc = QPushButton("Update")
        self.btn_delete_sc = QPushButton("Delete")
        self.btn_move_up_sc = QPushButton("Move Up")
        self.btn_move_down_sc = QPushButton("Move Down")
        self.btn_add_sc.clicked.connect(self.add_shortcut)
        self.btn_update_sc.clicked.connect(self.update_shortcut)
        self.btn_delete_sc.clicked.connect(self.delete_shortcut)
        self.btn_move_up_sc.clicked.connect(self.move_up_shortcut)
        self.btn_move_down_sc.clicked.connect(self.move_down_shortcut)
        btn_layout.addWidget(self.btn_add_sc)
        btn_layout.addWidget(self.btn_update_sc)
        btn_layout.addWidget(self.btn_delete_sc)
        btn_layout.addWidget(self.btn_move_up_sc)
        btn_layout.addWidget(self.btn_move_down_sc)
        shortcut_layout.addLayout(btn_layout)

        self.shortcut_list.currentRowChanged.connect(self.load_shortcut_to_form)
        self.tabs.addTab(shortcut_tab, "Shortcuts")

        doc_tab = QWidget()
        doc_layout = QVBoxLayout(doc_tab)

        doc_form = QFormLayout()
        self.doc_title_edit = QLineEdit()
        doc_form.addRow("Document Record Title:", self.doc_title_edit)

        self.doc_sort_by = QComboBox()
        for code, label in SORT_LABELS.items():
            self.doc_sort_by.addItem(label, code)
        doc_form.addRow("Sort by:", self.doc_sort_by)
        doc_layout.addLayout(doc_form)

        doc_folder_label = QLabel("Data Storage Folders:")
        doc_layout.addWidget(doc_folder_label)

        self.doc_folder_list = QListWidget()
        self.doc_folder_list.setMinimumHeight(100)
        doc_layout.addWidget(self.doc_folder_list)

        self.doc_folder_edit = QLineEdit()
        self.btn_doc_browse = QPushButton("Browse")
        self.btn_doc_browse.clicked.connect(self.browse_doc_folder)
        h_doc = QHBoxLayout()
        h_doc.addWidget(self.doc_folder_edit)
        h_doc.addWidget(self.btn_doc_browse)
        doc_layout.addLayout(h_doc)

        doc_btn_layout = QHBoxLayout()
        self.btn_doc_add = QPushButton("新增")
        self.btn_doc_update = QPushButton("Update")
        self.btn_doc_delete = QPushButton("Delete")
        self.btn_doc_add.clicked.connect(self.add_doc_folder)
        self.btn_doc_update.clicked.connect(self.update_doc_folder)
        self.btn_doc_delete.clicked.connect(self.delete_doc_folder)
        doc_btn_layout.addWidget(self.btn_doc_add)
        doc_btn_layout.addWidget(self.btn_doc_update)
        doc_btn_layout.addWidget(self.btn_doc_delete)
        doc_layout.addLayout(doc_btn_layout)
        self.doc_folder_list.currentRowChanged.connect(self.load_doc_folder_to_form)

        info = QLabel(
            "Files in these folders will be listed automatically. "
            "Click 「新增」 to add more storage folder locations. "
            "You can add Time, Comment, Publisher, and Version for each file."
        )
        info.setWordWrap(True)
        doc_layout.addWidget(info)
        doc_layout.addStretch()

        self.tabs.addTab(doc_tab, "Document Record")

        sys_tab = QWidget()
        sys_layout = QFormLayout(sys_tab)

        self.window_mode = QComboBox()
        for code, label in WINDOW_LABELS.items():
            self.window_mode.addItem(label, code)
        sys_layout.addRow("Window level:", self.window_mode)

        self.tabs.addTab(sys_tab, "System")

        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)

        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml(self.load_about_html())
        about_layout.addWidget(about_text)

        self.tabs.addTab(about_tab, "About")

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(self.btn_save)
        bottom.addWidget(self.btn_cancel)
        layout.addLayout(bottom)

    def load_data(self):
        self.image_path_edit.setText(self.cfg.get("pet", "image_path") or "")
        self.image_folder_edit.setText(self.cfg.get("pet", "image_folder") or "")
        self.auto_change_check.setChecked(bool(self.cfg.get("pet", "auto_change")))
        self.interval_spin.setValue(int(self.cfg.get("pet", "change_interval_sec") or 5))
        self.switch_mode.setCurrentText(self.cfg.get("pet", "switch_mode") or "Loop")
        self.size_spin.setValue(int(self.cfg.get("pet", "size") or 120))
        self.opacity_spin.setValue(int((self.cfg.get("pet", "opacity") or 0.9) * 100))

        self.shortcut_list.clear()
        for sc in self.cfg.get("shortcuts") or []:
            name = sc.get("name", "")
            path = sc.get("path", "")
            desc = sc.get("description", "")
            item = QListWidgetItem(f"{name} | {path} | {desc}")
            item.setData(Qt.ItemDataRole.UserRole, sc)
            self.shortcut_list.addItem(item)

        self.doc_title_edit.setText(self.cfg.get("document_area", "title") or "Document record")
        self.doc_folder_list.clear()
        self.doc_folder_edit.clear()
        folders = normalize_document_folders(self.cfg.get("document_area") or {})
        for folder in folders:
            self.doc_folder_list.addItem(folder)
        sort_code = normalize_sort(self.cfg.get("document_area", "sort_by"))
        sort_index = self.doc_sort_by.findData(sort_code)
        self.doc_sort_by.setCurrentIndex(sort_index if sort_index >= 0 else 0)

        mode = normalize_window_mode(self.cfg.get("window") or {})
        mode_index = self.window_mode.findData(mode)
        self.window_mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)

    def load_about_html(self):
        """Load README.txt and generate the About page HTML."""
        base_dir = get_resource_dir()
        readme_path = base_dir / "README.txt"
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(encoding="utf-8")
            except Exception:
                readme_content = "(Unable to load README.txt)"
        else:
            readme_content = "(README.txt not found)"

        qr_path = base_dir / "paypal_qr.jpg"
        if qr_path.exists():
            qr_img_tag = f'<br><img src="{html.escape(qr_path.as_uri())}" width="180" />'
        else:
            qr_img_tag = "<br>(QR code image not found)"

        return f"""
        <html>
        <body style="font-family: Microsoft JhengHei, Segoe UI, sans-serif; font-size: 13px;">
        <h2>Desktop Pet</h2>
        <p><b>Version:</b> {html.escape(APP_VERSION)}</p>
        <p><b>Developer:</b> pf.chan</p>
        <hr>
        <pre style="white-space: pre-wrap; font-family: Microsoft JhengHei, Segoe UI, sans-serif;">{html.escape(readme_content)}</pre>
        {qr_img_tag}
        </body>
        </html>
        """

    def browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Pet Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if path:
            self.image_path_edit.setText(path)
            self.auto_change_check.setChecked(False)

    def browse_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            self.image_folder_edit.setText(folder)
            self.auto_change_check.setChecked(True)

    def browse_shortcut_path(self):
        menu = QMenu(self)
        menu.addAction("Folder", self._browse_shortcut_folder)
        menu.addAction("File", self._browse_shortcut_file)
        menu.exec(self.btn_sc_browse.mapToGlobal(self.btn_sc_browse.rect().bottomLeft()))

    def _browse_shortcut_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Item Folder")
        if folder:
            self.sc_path.setText(folder)

    def _browse_shortcut_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Item File")
        if path:
            self.sc_path.setText(path)

    def browse_doc_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Data Storage Folder")
        if folder:
            self.doc_folder_edit.setText(folder)

    def load_doc_folder_to_form(self, row):
        if row < 0:
            return
        item = self.doc_folder_list.item(row)
        if item:
            self.doc_folder_edit.setText(item.text())

    def add_doc_folder(self):
        folder = self.doc_folder_edit.text().strip()
        if not folder:
            folder_pick = QFileDialog.getExistingDirectory(self, "Select Data Storage Folder")
            if not folder_pick:
                return
            folder = folder_pick
            self.doc_folder_edit.setText(folder)
        existing = {
            self.doc_folder_list.item(i).text()
            for i in range(self.doc_folder_list.count())
        }
        if folder in existing:
            QMessageBox.information(self, "Already added", "This folder is already in the list.")
            return
        self.doc_folder_list.addItem(folder)
        self.doc_folder_list.setCurrentRow(self.doc_folder_list.count() - 1)

    def update_doc_folder(self):
        row = self.doc_folder_list.currentRow()
        if row < 0:
            return
        folder = self.doc_folder_edit.text().strip()
        if not folder:
            return
        for i in range(self.doc_folder_list.count()):
            if i != row and self.doc_folder_list.item(i).text() == folder:
                QMessageBox.information(self, "Already added", "This folder is already in the list.")
                return
        self.doc_folder_list.item(row).setText(folder)

    def delete_doc_folder(self):
        row = self.doc_folder_list.currentRow()
        if row >= 0:
            self.doc_folder_list.takeItem(row)

    def load_shortcut_to_form(self, row):
        if row < 0:
            return
        item = self.shortcut_list.item(row)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.sc_name.setText(data.get("name", ""))
        self.sc_path.setText(data.get("path", ""))
        self.sc_desc.setText(data.get("description", ""))

    def add_shortcut(self):
        sc = {
            "name": self.sc_name.text().strip() or "Unnamed",
            "path": self.sc_path.text().strip(),
            "description": self.sc_desc.text().strip()
        }
        item = QListWidgetItem(f"{sc['name']} | {sc['path']} | {sc['description']}")
        item.setData(Qt.ItemDataRole.UserRole, sc)
        self.shortcut_list.addItem(item)
        self.shortcut_list.setCurrentItem(item)

    def update_shortcut(self):
        row = self.shortcut_list.currentRow()
        if row < 0:
            return
        item = self.shortcut_list.item(row)
        sc = {
            "name": self.sc_name.text().strip() or "Unnamed",
            "path": self.sc_path.text().strip(),
            "description": self.sc_desc.text().strip()
        }
        item.setText(f"{sc['name']} | {sc['path']} | {sc['description']}")
        item.setData(Qt.ItemDataRole.UserRole, sc)

    def delete_shortcut(self):
        row = self.shortcut_list.currentRow()
        if row >= 0:
            self.shortcut_list.takeItem(row)

    def move_up_shortcut(self):
        row = self.shortcut_list.currentRow()
        if row <= 0:
            return
        item = self.shortcut_list.takeItem(row)
        self.shortcut_list.insertItem(row - 1, item)
        self.shortcut_list.setCurrentItem(item)

    def move_down_shortcut(self):
        row = self.shortcut_list.currentRow()
        if row < 0 or row >= self.shortcut_list.count() - 1:
            return
        item = self.shortcut_list.takeItem(row)
        self.shortcut_list.insertItem(row + 1, item)
        self.shortcut_list.setCurrentItem(item)

    def save_settings(self):
        self.cfg.set(["pet", "image_path"], self.image_path_edit.text().strip(), save=False)
        self.cfg.set(["pet", "image_folder"], self.image_folder_edit.text().strip(), save=False)
        self.cfg.set(["pet", "auto_change"], self.auto_change_check.isChecked(), save=False)
        self.cfg.set(["pet", "change_interval_sec"], self.interval_spin.value(), save=False)
        self.cfg.set(["pet", "switch_mode"], self.switch_mode.currentText(), save=False)
        self.cfg.set(["pet", "size"], self.size_spin.value(), save=False)
        self.cfg.set(["pet", "opacity"], self.opacity_spin.value() / 100.0, save=False)

        shortcuts = []
        for i in range(self.shortcut_list.count()):
            item = self.shortcut_list.item(i)
            shortcuts.append(item.data(Qt.ItemDataRole.UserRole))
        self.cfg.set(["shortcuts"], shortcuts, save=False)

        self.cfg.set(
            ["document_area", "title"],
            self.doc_title_edit.text().strip() or "Document record",
            save=False
        )
        folders = []
        seen = set()
        for i in range(self.doc_folder_list.count()):
            path = self.doc_folder_list.item(i).text().strip()
            if path and path not in seen:
                seen.add(path)
                folders.append(path)
        # Persist folders list; keep legacy "folder" synced to the first entry.
        self.cfg.set(["document_area", "folders"], folders, save=False)
        self.cfg.set(["document_area", "folder"], folders[0] if folders else "", save=False)
        self.cfg.set(["document_area", "sort_by"], self.doc_sort_by.currentData() or "mtime", save=False)

        mode = self.window_mode.currentData() or "normal"
        window = self.cfg.get("window") or {}
        apply_window_mode(window, mode)
        self.cfg.set(["window"], window, save=False)
        self.cfg.save()

        self.config_changed.emit()
        self.accept()


# ---------------------------------------------------------------------------
# File metadata editor dialog
# ---------------------------------------------------------------------------
class FileMetaDialog(QDialog):
    def __init__(self, filename, meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit File Info - {filename}")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)

        self.time_edit = QLineEdit()
        self.comment_edit = QPlainTextEdit()
        self.publisher_edit = QLineEdit()
        self.version_edit = QLineEdit()

        self.time_edit.setText(meta.get("time", ""))
        self.comment_edit.setPlainText(meta.get("comment", ""))
        self.publisher_edit.setText(meta.get("publisher", ""))
        self.version_edit.setText(meta.get("version", ""))

        layout.addRow("Time:", self.time_edit)
        layout.addRow("Comment:", self.comment_edit)
        layout.addRow("Publisher:", self.publisher_edit)
        layout.addRow("Version:", self.version_edit)

        btn = QPushButton("Save")
        btn.clicked.connect(self.accept)
        layout.addRow(btn)

    def get_meta(self):
        return {
            "time": self.time_edit.text().strip(),
            "comment": self.comment_edit.toPlainText().strip(),
            "publisher": self.publisher_edit.text().strip(),
            "version": self.version_edit.text().strip()
        }


MENU_STYLE = """
    QWidget#menuContainer, QWidget#subMenuContainer {
        background-color: rgba(70, 130, 180, 220);
        border: 2px solid rgba(135, 206, 250, 220);
        border-radius: 10px;
    }
    QWidget {
        font-family: "Microsoft JhengHei", "Segoe UI", sans-serif;
        font-size: 9pt;
    }
    QPushButton {
        color: white;
        border: none;
        border-radius: 6px;
        padding: 4px 7px;
        text-align: left;
    }
    QPushButton:hover {
        background-color: rgba(0, 0, 0, 90);
    }
    QLabel {
        color: white;
    }
"""


class PopupPanel(QWidget):
    """Frameless tool window that closes when it loses focus."""

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._suppress_hide = False

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and not self._suppress_hide:
            QTimer.singleShot(0, self._hide_if_inactive)
        return super().event(event)

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        self.hide()


# ---------------------------------------------------------------------------
# Document Record submenu (with pagination)
# ---------------------------------------------------------------------------
class DocumentSubMenu(PopupPanel):
    """Submenu for Document record; auto-paginates when there are many files."""

    open_file_meta = Signal(str)

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        # Each entry is (folder_path, filename)
        self.files = []
        self.files_meta = {}
        self.current_page = 0
        self.items_per_page = 20
        self.build_ui()

    def build_ui(self):
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(4)

        self.title_label = QLabel("Document record")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.main_layout.addWidget(self.title_label)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep)

        self.files_container = QVBoxLayout()
        self.files_container.setSpacing(2)
        self.main_layout.addLayout(self.files_container)

        self.pagination_container = QHBoxLayout()
        self.pagination_container.setSpacing(6)
        self.main_layout.addLayout(self.pagination_container)

        self.setStyleSheet(MENU_STYLE + """
            DocumentSubMenu { background-color: transparent; }
        """)

    def button_style(self, base_color):
        return menu_button_style(base_color)

    def refresh_and_show(self, anchor_geometry):
        self.files = []
        self.files_meta = dict(self.cfg.get("document_area", "files") or {})
        self.title_label.setText(self.cfg.get("document_area", "title") or "Document record")

        folders = normalize_document_folders(self.cfg.get("document_area") or {})
        entries = []
        seen_names = set()
        try:
            for folder in folders:
                folder_path = Path(folder)
                if not folder_path.exists():
                    continue
                for path in folder_path.iterdir():
                    if path.is_file():
                        entries.append((str(folder_path), path.name))
                        seen_names.add(path.name)

            sort_by = normalize_sort(self.cfg.get("document_area", "sort_by"))

            def entry_mtime(item):
                try:
                    return (Path(item[0]) / item[1]).stat().st_mtime
                except OSError:
                    return 0

            if sort_by == "name":
                entries.sort(key=lambda x: x[1].lower())
            elif sort_by == "edit_time":
                entries.sort(
                    key=lambda x: self.files_meta.get(x[1], {}).get("time", ""),
                    reverse=True
                )
            elif sort_by == "publisher":
                entries.sort(
                    key=lambda x: self.files_meta.get(x[1], {}).get("publisher", "").lower()
                )
            else:
                entries.sort(key=entry_mtime, reverse=True)

            stale = [name for name in self.files_meta if name not in seen_names]
            if stale:
                for name in stale:
                    del self.files_meta[name]
                self.cfg.set(["document_area", "files"], self.files_meta)

            self.files = entries
        except Exception:
            self.files = []

        screen_height = screen_available_geometry(self).height()
        self.items_per_page = max(5, int((screen_height / 2) / 22))
        self.current_page = 0

        self.show_page(0)

        self.adjustSize()
        screen_geo = screen_available_geometry(self)
        x = anchor_geometry.x() + anchor_geometry.width()
        y = anchor_geometry.y()
        if x + self.width() > screen_geo.right():
            x = anchor_geometry.x() - self.width()
        if y + self.height() > screen_geo.bottom():
            y = screen_geo.bottom() - self.height()
        self.move(max(screen_geo.left(), x), max(screen_geo.top(), y))
        self.show()
        self.raise_()
        self.activateWindow()

    def show_page(self, page):
        while self.files_container.count():
            item = self.files_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self.pagination_container.count():
            item = self.pagination_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.files:
            lbl = QLabel("(No files)")
            lbl.setStyleSheet("color: #dddddd;")
            self.files_container.addWidget(lbl)
            self.adjustSize()
            return

        total_pages = max(1, (len(self.files) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = max(0, min(page, total_pages - 1))
        start = self.current_page * self.items_per_page
        end = min(start + self.items_per_page, len(self.files))

        for folder, fname in self.files[start:end]:
            fpath = os.path.join(folder, fname)
            meta = self.files_meta.get(fname, {})
            comment = " ".join((meta.get("comment") or "").split())
            if comment:
                display = f"{fname}  —  {comment}"
            else:
                display = fname
            btn = QPushButton(display)
            tip_parts = [
                "Click to open file",
                fpath,
                f"Comment: {meta.get('comment', '')}",
                f"Publisher: {meta.get('publisher', '')}",
            ]
            if meta.get("time"):
                tip_parts.append(f"Time: {meta['time']}")
            if meta.get("version"):
                tip_parts.append(f"Version: {meta['version']}")
            btn.setToolTip("\n".join(tip_parts))
            btn.setStyleSheet(self.button_style("#5c4a72"))
            btn.clicked.connect(lambda checked=False, p=fpath: self.open_path(p))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, fn=fname: self.show_doc_context_menu(fn)
            )
            self.files_container.addWidget(btn)

        if total_pages > 1:
            prev_btn = QPushButton("Prev")
            prev_btn.setEnabled(self.current_page > 0)
            prev_btn.clicked.connect(lambda checked=False: self.show_page(self.current_page - 1))
            page_label = QLabel(f"{self.current_page + 1} / {total_pages}")
            next_btn = QPushButton("Next")
            next_btn.setEnabled(self.current_page < total_pages - 1)
            next_btn.clicked.connect(lambda checked=False: self.show_page(self.current_page + 1))
            self.pagination_container.addWidget(prev_btn)
            self.pagination_container.addWidget(page_label)
            self.pagination_container.addWidget(next_btn)
            self.pagination_container.addStretch()

        self.adjustSize()

    def open_path(self, path):
        try:
            if Path(path).exists():
                os.startfile(path)
            else:
                QMessageBox.warning(self, "Path does not exist", f"Not found:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Open failed", str(e))

    def show_doc_context_menu(self, filename):
        self._suppress_hide = True
        menu = QMenu(self)
        edit_action = QAction("Edit Info", self)
        edit_action.triggered.connect(lambda: self.open_file_meta.emit(filename))
        menu.addAction(edit_action)
        menu.exec(QCursor.pos())
        self._suppress_hide = False

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        active = QApplication.activeWindow()
        if isinstance(active, QMenu):
            return
        self.hide()


# ---------------------------------------------------------------------------
# Main menu (semi-transparent popup)
# ---------------------------------------------------------------------------
class PetMenu(PopupPanel):
    """Semi-transparent menu that pops up when the pet is clicked."""

    open_shortcut = Signal(str)
    open_settings = Signal()
    open_file_meta = Signal(str)

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self.doc_submenu = None
        self.build_ui()

    def build_ui(self):
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("menuContainer")
        top_layout.addWidget(self.container)

        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(4)

        self.shortcuts_title = QLabel("Folder shortcuts")
        self.shortcuts_title.setStyleSheet("color: white; font-weight: bold;")
        self.main_layout.addWidget(self.shortcuts_title)

        self.shortcuts_container = QVBoxLayout()
        self.shortcuts_container.setSpacing(3)
        self.main_layout.addLayout(self.shortcuts_container)

        sep1 = QLabel()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep1)

        doc_header = QHBoxLayout()
        doc_header.setSpacing(4)
        self.doc_title = QLabel("Document record")
        self.doc_title.setStyleSheet("color: white; font-weight: bold;")
        self.btn_doc_open = QPushButton(">>")
        self.btn_doc_open.setFixedWidth(30)
        self.btn_doc_open.setStyleSheet(
            "text-align: center;" + menu_button_style("#4a4a4a")
        )
        self.btn_doc_open.clicked.connect(self.open_document_submenu)
        doc_header.addWidget(self.doc_title)
        doc_header.addStretch()
        doc_header.addWidget(self.btn_doc_open)
        self.main_layout.addLayout(doc_header)

        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep2)

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setStyleSheet(self.button_style("#4a4a4a"))
        self.btn_settings.clicked.connect(self.open_settings.emit)
        self.main_layout.addWidget(self.btn_settings)

        self.setStyleSheet(MENU_STYLE + """
            PetMenu { background-color: transparent; }
        """)

    def button_style(self, base_color):
        return menu_button_style(base_color)

    def refresh(self):
        while self.shortcuts_container.count():
            item = self.shortcuts_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        shortcuts = self.cfg.get("shortcuts") or []
        if not shortcuts:
            btn = QPushButton("-Please add a target in Settings-")
            btn.setEnabled(False)
            btn.setStyleSheet("color: #dddddd; background-color: transparent;")
            self.shortcuts_container.addWidget(btn)
        else:
            for sc in shortcuts:
                name = sc.get("name", "Unnamed")
                path = sc.get("path", "")
                desc = sc.get("description", "")
                text = name
                if desc:
                    text += f" ({desc})"
                btn = QPushButton(text)
                btn.setToolTip(path)
                btn.setStyleSheet(self.button_style("#3d5a80"))
                btn.clicked.connect(lambda checked=False, p=path: self.open_shortcut.emit(p))
                self.shortcuts_container.addWidget(btn)

        title = self.cfg.get("document_area", "title") or "Document record"
        self.doc_title.setText(title)
        self.adjustSize()

    def open_document_submenu(self):
        if self.doc_submenu is None:
            self.doc_submenu = DocumentSubMenu(self.cfg)
            self.doc_submenu.open_file_meta.connect(self.open_file_meta.emit)
        self._suppress_hide = True
        self.doc_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def hideEvent(self, event):
        if self.doc_submenu is not None:
            self.doc_submenu.hide()
        super().hideEvent(event)

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        if self.doc_submenu is not None and (
            self.doc_submenu.isVisible() or self.doc_submenu.isActiveWindow()
        ):
            return
        active = QApplication.activeWindow()
        if isinstance(active, (QMenu, DocumentSubMenu)):
            return
        self.hide()


# ---------------------------------------------------------------------------
# Main pet window
# ---------------------------------------------------------------------------
class PetWindow(QWidget):
    def __init__(self, config_manager):
        super().__init__(None)
        self.cfg = config_manager
        self.setWindowIcon(load_app_icon())
        self.menu = None
        self.drag_pos = None
        self.moved_distance = 0
        self._ignore_release = False
        self.image_list = []
        self.current_image_index = 0
        self._movie = None
        self.image_timer = QTimer(self)
        self.image_timer.timeout.connect(self.next_image)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.show_menu)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )

        self.label = QLabel(self)
        self.label.setScaledContents(False)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        self.apply_window_mode()
        self.load_pet_settings()
        self.move(self.cfg.get("pet", "pos_x") or 100, self.cfg.get("pet", "pos_y") or 100)
        self.clamp_to_screen()

    def clamp_to_screen(self):
        """Keep the pet within the available screen area."""
        screen_geo = screen_available_geometry(self)
        x = max(screen_geo.left(), min(self.x(), screen_geo.right() - self.width() + 1))
        y = max(screen_geo.top(), min(self.y(), screen_geo.bottom() - self.height() + 1))
        self.move(x, y)

    def apply_window_mode(self):
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
        flags &= ~Qt.WindowType.WindowStaysOnBottomHint

        mode = normalize_window_mode(self.cfg.get("window") or {})
        if mode == "top":
            flags |= Qt.WindowType.WindowStaysOnTopHint
        elif mode == "bottom":
            flags |= Qt.WindowType.WindowStaysOnBottomHint

        self.setWindowFlags(flags | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.show()

    def load_pet_settings(self):
        size = int(self.cfg.get("pet", "size") or 120)
        opacity = float(self.cfg.get("pet", "opacity") or 0.9)
        self.setFixedSize(size, size)
        self.setWindowOpacity(opacity)

        auto_change = bool(self.cfg.get("pet", "auto_change"))
        folder = self.cfg.get("pet", "image_folder") or ""
        single = self.cfg.get("pet", "image_path") or ""

        self.image_list = []
        self.current_image_index = 0

        if auto_change and folder and Path(folder).exists():
            self.image_list = sorted(
                str(p) for p in Path(folder).iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS
            )
        elif single and Path(single).exists():
            self.image_list = [single]

        if self.image_list:
            self.show_image(self.image_list[0])
        else:
            self.draw_default_pet()

        interval = int(self.cfg.get("pet", "change_interval_sec") or 5) * 1000
        self.image_timer.stop()
        if auto_change and len(self.image_list) > 1:
            self.image_timer.setInterval(interval)
            self.image_timer.start()

    def next_image(self):
        if not self.image_list:
            return

        switch_mode = self.cfg.get("pet", "switch_mode") or "Loop"
        total = len(self.image_list)

        if switch_mode == "Sequential":
            self.current_image_index += 1
            if self.current_image_index >= total:
                self.current_image_index = total - 1
                self.image_timer.stop()
                return
        elif switch_mode == "Random":
            if total > 1:
                next_index = self.current_image_index
                while next_index == self.current_image_index:
                    next_index = random.randrange(total)
                self.current_image_index = next_index
        else:
            self.current_image_index = (self.current_image_index + 1) % total

        self.show_image(self.image_list[self.current_image_index])

    def _clear_movie(self):
        if self._movie is not None:
            self._movie.stop()
            self.label.setMovie(None)
            self._movie = None

    def show_image(self, path):
        if not path or not Path(path).exists():
            self._clear_movie()
            self.draw_default_pet()
            return
        try:
            if Path(path).suffix.lower() == ".gif":
                self._clear_movie()
                movie = QMovie(path)
                movie.setScaledSize(QSize(self.width(), self.height()))
                self.label.setPixmap(QPixmap())
                self.label.setMovie(movie)
                movie.start()
                self._movie = movie
                return
            self._clear_movie()
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self.draw_default_pet()
                return
            scaled = pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.label.setPixmap(scaled)
        except Exception:
            self._clear_movie()
            self.draw_default_pet()

    def draw_default_pet(self):
        self._clear_movie()
        size = self.width()
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(100, 149, 237))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, size - 8, size - 8)
        painter.setBrush(QColor(255, 255, 255))
        eye_y = size // 3
        painter.drawEllipse(size // 4 - 6, eye_y, 12, 16)
        painter.drawEllipse(size * 3 // 4 - 6, eye_y, 12, 16)
        painter.setBrush(QColor(50, 50, 50))
        painter.drawEllipse(size // 4 - 3, eye_y + 3, 6, 8)
        painter.drawEllipse(size * 3 // 4 - 3, eye_y + 3, 6, 8)
        painter.setBrush(QColor(255, 105, 180))
        mouth_w = size // 3
        painter.drawEllipse(size // 2 - mouth_w // 2, size // 2 + 8, mouth_w, mouth_w // 2)
        painter.end()
        self.label.setPixmap(pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
            self.moved_distance = 0
        elif event.button() == Qt.MouseButton.RightButton:
            self.click_timer.stop()
            self.show_menu()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self.drag_pos
            self.moved_distance += abs(delta.x()) + abs(delta.y())
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.clamp_to_screen()
            self.drag_pos = new_pos

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._ignore_release:
            self._ignore_release = False
            self.drag_pos = None
            self.moved_distance = 0
            return
        self.clamp_to_screen()
        moved = self.moved_distance
        self.drag_pos = None
        self.moved_distance = 0
        if moved >= 8:
            self.cfg.set(["pet", "pos_x"], self.x(), save=False)
            self.cfg.set(["pet", "pos_y"], self.y(), save=False)
            self.cfg.save()
        else:
            self.click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.click_timer.stop()
        self._ignore_release = True
        self.open_settings()

    def show_menu(self):
        if self.menu is None:
            self.menu = PetMenu(self.cfg)
            self.menu.open_shortcut.connect(self.open_shortcut)
            self.menu.open_settings.connect(self.open_settings)
            self.menu.open_file_meta.connect(self.edit_file_meta)
        self.menu.refresh()

        screen_geo = screen_available_geometry(self)
        pet_geo = self.geometry()
        menu_size = self.menu.sizeHint()

        x = pet_geo.x() + (pet_geo.width() - menu_size.width()) // 2
        y = pet_geo.y() - menu_size.height()

        if x + menu_size.width() > screen_geo.right():
            x = screen_geo.right() - menu_size.width()
        if x < screen_geo.left():
            x = screen_geo.left()

        if y < screen_geo.top():
            y = screen_geo.top()

        self.menu.move(x, y)
        self.menu.show()
        self.menu.raise_()
        self.menu.activateWindow()

    def open_shortcut(self, path):
        try:
            if Path(path).exists():
                os.startfile(path)
            else:
                QMessageBox.warning(self, "Path does not exist", f"Not found:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Open failed", str(e))

    def edit_file_meta(self, filename):
        if self.menu is not None:
            self.menu._suppress_hide = True
            if self.menu.doc_submenu is not None:
                self.menu.doc_submenu._suppress_hide = True
        meta = (self.cfg.get("document_area", "files") or {}).get(filename, {})
        dialog = FileMetaDialog(filename, meta, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if self.menu is not None:
            self.menu._suppress_hide = False
            if self.menu.doc_submenu is not None:
                self.menu.doc_submenu._suppress_hide = False
        if accepted:
            files_meta = dict(self.cfg.get("document_area", "files") or {})
            files_meta[filename] = dialog.get_meta()
            self.cfg.set(["document_area", "files"], files_meta)
            if self.menu and self.menu.doc_submenu and self.menu.doc_submenu.isVisible():
                self.menu.doc_submenu.refresh_and_show(self.menu.geometry())

    def open_settings(self):
        if self.menu is not None:
            self.menu.hide()
        dialog = SettingsDialog(self.cfg, self)
        dialog.config_changed.connect(self.on_config_changed)
        dialog.exec()

    def on_config_changed(self):
        self.load_pet_settings()
        self.apply_window_mode()
        self.clamp_to_screen()
        if self.menu:
            self.menu.refresh()


def get_resource_dir():
    """Return the directory containing bundled resource files."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def get_config_dir():
    """Return the directory where config.json should be read/written."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def load_app_icon():
    """Load the application logo icon from the resource directory."""
    base_dir = get_resource_dir()
    icon_path = base_dir / "logo.ico"
    if not icon_path.exists():
        icon_path = base_dir / "logo.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def acquire_single_instance():
    """Return a lock kept for the process lifetime, or None if another copy is running."""
    lock_path = Path(os.environ.get("TEMP", ".")) / "DesktopPet.lock"
    lock = QLockFile(str(lock_path))
    if not lock.tryLock(100):
        return None
    return lock


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    base_font = app.font()
    base_font.setPointSize(9)
    app.setFont(base_font)

    instance_lock = acquire_single_instance()
    if instance_lock is None:
        QMessageBox.information(
            None,
            "Desktop Pet",
            "Desktop Pet is already running. Use the tray icon to show it."
        )
        return 0
    app._instance_lock = instance_lock

    # Config next to the executable. A bundled blank config is copied on first run.
    config_dir = get_config_dir()
    resource_dir = get_resource_dir()
    config_path = config_dir / "config.json"
    bundled_config = resource_dir / "config.json"
    if bundled_config.exists() and not config_path.exists() and bundled_config.resolve() != config_path.resolve():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(str(bundled_config), str(config_path))
        except Exception as e:
            print(f"Failed to copy default config: {e}")

    cfg = ConfigManager(config_path)

    pet = PetWindow(cfg)
    pet.show()

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(app)
        tray.setToolTip("Desktop Pet")
        tray.setIcon(load_app_icon())
        tray_menu = QMenu()
        show_action = QAction("Show", tray)
        hide_action = QAction("Hide", tray)
        settings_action = QAction("Settings", tray)
        quit_action = QAction("Exit", tray)

        def show_pet():
            pet.show()
            pet.raise_()
            pet.activateWindow()

        show_action.triggered.connect(show_pet)
        hide_action.triggered.connect(pet.hide)
        settings_action.triggered.connect(pet.open_settings)
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addAction(settings_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        tray.setContextMenu(tray_menu)

        def on_tray_activated(reason):
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            ):
                if pet.isVisible():
                    pet.hide()
                else:
                    show_pet()

        tray.activated.connect(on_tray_activated)
        tray.show()
        app._tray_icon = tray

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
