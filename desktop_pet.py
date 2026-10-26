#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop Pet
A floating shortcut menu and document record gadget on the desktop.
"""

import html
import json
import math
import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QEvent, QLockFile, QUrl, QPoint
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QCursor, QIcon, QAction, QMovie, QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QDialog, QFormLayout, QTabWidget, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QMessageBox, QMenu, QStyle,
    QSystemTrayIcon, QPlainTextEdit, QFrame, QRadioButton, QButtonGroup,
    QScrollArea, QSizePolicy,
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
APP_VERSION = "261026.01"

# Windows Run-key name for "Start with Windows".
AUTOSTART_REG_NAME = "DesktopPet"


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
        "pos_y": 100,
        # Multi-monitor memory (optional; older configs omit these).
        "screen_name": "",
        "rel_x": None,
        "rel_y": None,
    },
    "window": {
        "mode": "normal",
        "stay_on_top": False,
        "stay_on_bottom": False,
        "normal": True
    },
    # System options (autostart is applied on Windows only).
    "system": {
        "start_with_windows": False,
    },
    # Folder shortcuts (name / path / description). Kept for older configs.
    "shortcuts": [],
    # File / URL shortcuts. Shape: {name, path, description, type?}.
    # type: "file" (default) or "url". Older entries without type stay files
    # unless path looks like http(s).
    "file_shortcuts": [],
    "document_area": {
        "title": "Document record",
        # "folder" kept for backward compatibility with older builds.
        "folder": "",
        # Primary list of storage folders (supports more than one).
        "folders": [],
        "sort_by": "mtime",
        "files": {}
    },
    # Text records (title + body). Older configs omit this key.
    "text_records": [],
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


def nearest_screen_for_point(point):
    """Return the screen containing point, or the nearest available screen."""
    screen = QApplication.screenAt(point)
    if screen is not None:
        return screen
    best = None
    best_dist = None
    for candidate in QApplication.screens():
        geo = candidate.availableGeometry()
        cx = max(geo.left(), min(point.x(), geo.right()))
        cy = max(geo.top(), min(point.y(), geo.bottom()))
        dist = (cx - point.x()) ** 2 + (cy - point.y()) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = candidate
    return best or QApplication.primaryScreen()


def clamp_widget_to_screens(widget):
    """Clamp widget onto an available screen (handles monitor unplug / resize)."""
    center = widget.frameGeometry().center()
    screen = nearest_screen_for_point(center)
    if screen is None:
        return
    geo = screen.availableGeometry()
    x = max(geo.left(), min(widget.x(), geo.right() - widget.width() + 1))
    y = max(geo.top(), min(widget.y(), geo.bottom() - widget.height() + 1))
    widget.move(x, y)


def find_screen_by_name(name):
    if not name:
        return None
    for screen in QApplication.screens():
        if screen.name() == name:
            return screen
    return None


def save_pet_geometry(cfg, widget, persist=True):
    """Remember absolute position plus relative placement on the current screen."""
    screen = QApplication.screenAt(widget.frameGeometry().center())
    if screen is None:
        screen = QApplication.primaryScreen()
    cfg.set(["pet", "pos_x"], widget.x(), save=False)
    cfg.set(["pet", "pos_y"], widget.y(), save=False)
    if screen is not None:
        geo = screen.availableGeometry()
        cfg.set(["pet", "screen_name"], screen.name(), save=False)
        cfg.set(
            ["pet", "rel_x"],
            (widget.x() - geo.x()) / max(geo.width(), 1),
            save=False,
        )
        cfg.set(
            ["pet", "rel_y"],
            (widget.y() - geo.y()) / max(geo.height(), 1),
            save=False,
        )
    if persist:
        cfg.save()


def restore_pet_geometry(cfg, widget):
    """Restore pet onto the remembered screen (or nearest), then clamp."""
    screen_name = cfg.get("pet", "screen_name") or ""
    rel_x = cfg.get("pet", "rel_x")
    rel_y = cfg.get("pet", "rel_y")
    pos_x = int(cfg.get("pet", "pos_x") or 100)
    pos_y = int(cfg.get("pet", "pos_y") or 100)

    target = find_screen_by_name(screen_name)
    if target is None:
        target = nearest_screen_for_point(QPoint(pos_x, pos_y))

    if (
        target is not None
        and rel_x is not None
        and rel_y is not None
    ):
        try:
            geo = target.availableGeometry()
            x = geo.x() + int(float(rel_x) * geo.width())
            y = geo.y() + int(float(rel_y) * geo.height())
            widget.move(x, y)
        except (TypeError, ValueError):
            widget.move(pos_x, pos_y)
    else:
        widget.move(pos_x, pos_y)
    clamp_widget_to_screens(widget)


def looks_like_url(value):
    text = (value or "").strip()
    if not text:
        return False
    lower = text.lower()
    if lower.startswith(("http://", "https://", "file://")):
        return True
    parsed = urlparse(text)
    return bool(parsed.scheme and parsed.netloc)


def normalize_file_shortcut(sc):
    """Normalize a file/URL shortcut dict; default type is file."""
    if not isinstance(sc, dict):
        return {"name": "Unnamed", "path": "", "description": "", "type": "file"}
    path = sc.get("path", "")
    if not isinstance(path, str):
        path = str(path or "")
    sc_type = sc.get("type")
    if sc_type not in ("file", "url"):
        sc_type = "url" if looks_like_url(path) else "file"
    return {
        "name": (sc.get("name") or "Unnamed"),
        "path": path.strip(),
        "description": (sc.get("description") or ""),
        "type": sc_type,
    }


def normalize_text_record(rec):
    """Normalize a text record dict: {title, body}."""
    if not isinstance(rec, dict):
        return {"title": "Untitled", "body": ""}
    title = rec.get("title", "")
    body = rec.get("body", "")
    if not isinstance(title, str):
        title = str(title or "")
    if not isinstance(body, str):
        body = str(body or "")
    return {
        "title": title.strip() or "Untitled",
        "body": body,
    }


def open_local_path(path):
    """Open a folder or file with the platform default handler."""
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


def open_url(url):
    """Open a web/internal URL in the default browser."""
    text = (url or "").strip()
    if not text:
        raise ValueError("Empty URL")
    qurl = QUrl.fromUserInput(text)
    if not qurl.isValid():
        raise ValueError(f"Invalid URL: {text}")
    if not QDesktopServices.openUrl(qurl):
        raise RuntimeError(f"Could not open URL: {text}")


def open_shortcut_target(path, sc_type=None):
    """Open a folder/file path or URL shortcut target."""
    kind = sc_type if sc_type in ("file", "url") else None
    if kind is None:
        kind = "url" if looks_like_url(path) else "file"
    if kind == "url":
        open_url(path)
    else:
        open_local_path(path)


def is_windows():
    return sys.platform.startswith("win")


def autostart_command():
    """Command string written to the Windows Run key."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = Path(__file__).resolve()
    return f'"{sys.executable}" "{script}"'


def get_windows_autostart_enabled():
    if not is_windows():
        return False
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_windows_autostart_enabled(enabled):
    """Enable/disable HKCU Run key. No-op (returns False) on non-Windows."""
    if not is_windows():
        return False
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key, AUTOSTART_REG_NAME, 0, winreg.REG_SZ, autostart_command()
            )
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_REG_NAME)
            except FileNotFoundError:
                pass
    return True


def filter_list_widget(list_widget, query):
    """Hide QListWidget rows that do not match the query (case-insensitive)."""
    text = (query or "").strip().lower()
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        if item is None:
            continue
        if not text:
            item.setHidden(False)
        else:
            item.setHidden(text not in (item.text() or "").lower())


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
        system = self.config.setdefault("system", {})
        if not isinstance(system, dict):
            self.config["system"] = {"start_with_windows": False}
        else:
            system.setdefault("start_with_windows", False)
        raw_file_sc = self.config.get("file_shortcuts")
        if isinstance(raw_file_sc, list):
            self.config["file_shortcuts"] = [
                normalize_file_shortcut(sc) for sc in raw_file_sc if isinstance(sc, dict)
            ]
        else:
            self.config["file_shortcuts"] = []
        raw_text = self.config.get("text_records")
        if isinstance(raw_text, list):
            self.config["text_records"] = [
                normalize_text_record(rec) for rec in raw_text if isinstance(rec, dict)
            ]
        else:
            self.config["text_records"] = []

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
# Prompt when adding a shortcut via drag-and-drop
# ---------------------------------------------------------------------------
class ShortcutPromptDialog(QDialog):
    """Ask for name / description when dropping a path or URL onto the pet."""

    def __init__(self, title, default_name, default_path, kind_label="Path", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(default_name or "")
        self.path_edit = QLineEdit(default_path or "")
        self.path_edit.setReadOnly(True)
        self.desc_edit = QLineEdit()
        layout.addRow("Item Name:", self.name_edit)
        layout.addRow(f"{kind_label}:", self.path_edit)
        layout.addRow("Description:", self.desc_edit)
        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("Add")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)

    def result_data(self):
        return {
            "name": self.name_edit.text().strip() or "Unnamed",
            "path": self.path_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
        }


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
        self.setMinimumSize(600, 520)
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

        # --- Folder shortcuts (existing config key: "shortcuts") ---
        shortcut_tab = QWidget()
        shortcut_layout = QVBoxLayout(shortcut_tab)

        self.shortcut_list = QListWidget()
        self.shortcut_list.setMaximumHeight(180)
        shortcut_layout.addWidget(QLabel("Item list (Name | Path | Description):"))
        self.shortcut_filter = QLineEdit()
        self.shortcut_filter.setPlaceholderText("Search / filter folder shortcuts…")
        self.shortcut_filter.textChanged.connect(
            lambda text: filter_list_widget(self.shortcut_list, text)
        )
        shortcut_layout.addWidget(self.shortcut_filter)
        shortcut_layout.addWidget(self.shortcut_list)

        sc_form = QFormLayout()
        self.sc_name = QLineEdit()
        self.sc_path = QLineEdit()
        self.btn_sc_browse = QPushButton("Browse")
        self.btn_sc_browse.clicked.connect(self.browse_shortcut_folder)
        h_sc = QHBoxLayout()
        h_sc.addWidget(self.sc_path)
        h_sc.addWidget(self.btn_sc_browse)
        self.sc_desc = QLineEdit()
        sc_form.addRow("Item Name:", self.sc_name)
        sc_form.addRow("Folder Path:", h_sc)
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
        self.tabs.addTab(shortcut_tab, "Folder Shortcuts")

        # --- File / URL shortcuts (config key: "file_shortcuts") ---
        file_sc_tab = QWidget()
        file_sc_layout = QVBoxLayout(file_sc_tab)

        self.file_shortcut_list = QListWidget()
        self.file_shortcut_list.setMaximumHeight(180)
        file_sc_layout.addWidget(
            QLabel("Item list (Type | Name | Path/URL | Description):")
        )
        self.file_shortcut_filter = QLineEdit()
        self.file_shortcut_filter.setPlaceholderText(
            "Search / filter file & URL shortcuts…"
        )
        self.file_shortcut_filter.textChanged.connect(
            lambda text: filter_list_widget(self.file_shortcut_list, text)
        )
        file_sc_layout.addWidget(self.file_shortcut_filter)
        file_sc_layout.addWidget(self.file_shortcut_list)

        fsc_form = QFormLayout()
        self.fsc_name = QLineEdit()
        self.fsc_type = QComboBox()
        self.fsc_type.addItem("File", "file")
        self.fsc_type.addItem("URL", "url")
        self.fsc_type.currentIndexChanged.connect(self._on_fsc_type_changed)
        self.fsc_path = QLineEdit()
        self.btn_fsc_browse = QPushButton("Browse")
        self.btn_fsc_browse.clicked.connect(self.browse_file_shortcut)
        h_fsc = QHBoxLayout()
        h_fsc.addWidget(self.fsc_path)
        h_fsc.addWidget(self.btn_fsc_browse)
        self.fsc_path_row = QWidget()
        self.fsc_path_row.setLayout(h_fsc)
        self.fsc_desc = QLineEdit()
        self.fsc_path_label = QLabel("File Path:")
        fsc_form.addRow("Item Name:", self.fsc_name)
        fsc_form.addRow("Type:", self.fsc_type)
        fsc_form.addRow(self.fsc_path_label, self.fsc_path_row)
        fsc_form.addRow("Description:", self.fsc_desc)
        file_sc_layout.addLayout(fsc_form)

        fsc_btn_layout = QHBoxLayout()
        self.btn_add_fsc = QPushButton("Add")
        self.btn_update_fsc = QPushButton("Update")
        self.btn_delete_fsc = QPushButton("Delete")
        self.btn_move_up_fsc = QPushButton("Move Up")
        self.btn_move_down_fsc = QPushButton("Move Down")
        self.btn_add_fsc.clicked.connect(self.add_file_shortcut)
        self.btn_update_fsc.clicked.connect(self.update_file_shortcut)
        self.btn_delete_fsc.clicked.connect(self.delete_file_shortcut)
        self.btn_move_up_fsc.clicked.connect(self.move_up_file_shortcut)
        self.btn_move_down_fsc.clicked.connect(self.move_down_file_shortcut)
        fsc_btn_layout.addWidget(self.btn_add_fsc)
        fsc_btn_layout.addWidget(self.btn_update_fsc)
        fsc_btn_layout.addWidget(self.btn_delete_fsc)
        fsc_btn_layout.addWidget(self.btn_move_up_fsc)
        fsc_btn_layout.addWidget(self.btn_move_down_fsc)
        file_sc_layout.addLayout(fsc_btn_layout)

        self.file_shortcut_list.currentRowChanged.connect(self.load_file_shortcut_to_form)
        self.tabs.addTab(file_sc_tab, "File Shortcuts")

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
        self.btn_doc_add = QPushButton("Add")
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
            "Click Add to add more storage folder locations. "
            "You can add Time, Comment, Publisher, and Version for each file."
        )
        info.setWordWrap(True)
        doc_layout.addWidget(info)
        doc_layout.addStretch()

        self.tabs.addTab(doc_tab, "Document Record")

        # --- Text records ---
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)

        text_layout.addWidget(QLabel("Item list (Title):"))
        self.text_record_list = QListWidget()
        self.text_record_list.setMaximumHeight(160)
        self.text_record_filter = QLineEdit()
        self.text_record_filter.setPlaceholderText("Search / filter text records…")
        self.text_record_filter.textChanged.connect(
            lambda text: filter_list_widget(self.text_record_list, text)
        )
        text_layout.addWidget(self.text_record_filter)
        text_layout.addWidget(self.text_record_list)

        text_form = QFormLayout()
        self.tr_title = QLineEdit()
        self.tr_body = QPlainTextEdit()
        self.tr_body.setMinimumHeight(120)
        text_form.addRow("Title:", self.tr_title)
        text_form.addRow("Body:", self.tr_body)
        text_layout.addLayout(text_form)

        tr_btn_layout = QHBoxLayout()
        self.btn_add_tr = QPushButton("Add")
        self.btn_update_tr = QPushButton("Update")
        self.btn_delete_tr = QPushButton("Delete")
        self.btn_move_up_tr = QPushButton("Move Up")
        self.btn_move_down_tr = QPushButton("Move Down")
        self.btn_add_tr.clicked.connect(self.add_text_record)
        self.btn_update_tr.clicked.connect(self.update_text_record)
        self.btn_delete_tr.clicked.connect(self.delete_text_record)
        self.btn_move_up_tr.clicked.connect(self.move_up_text_record)
        self.btn_move_down_tr.clicked.connect(self.move_down_text_record)
        tr_btn_layout.addWidget(self.btn_add_tr)
        tr_btn_layout.addWidget(self.btn_update_tr)
        tr_btn_layout.addWidget(self.btn_delete_tr)
        tr_btn_layout.addWidget(self.btn_move_up_tr)
        tr_btn_layout.addWidget(self.btn_move_down_tr)
        text_layout.addLayout(tr_btn_layout)

        tr_info = QLabel(
            "Text records appear under 小程式 → Text records in the pet menu. "
            "Click >> to browse titles; click a title to read the body."
        )
        tr_info.setWordWrap(True)
        text_layout.addWidget(tr_info)
        text_layout.addStretch()

        self.text_record_list.currentRowChanged.connect(self.load_text_record_to_form)
        self.tabs.addTab(text_tab, "Text records")

        sys_tab = QWidget()
        sys_layout = QFormLayout(sys_tab)

        self.window_mode = QComboBox()
        for code, label in WINDOW_LABELS.items():
            self.window_mode.addItem(label, code)
        sys_layout.addRow("Window level:", self.window_mode)

        self.start_with_windows_check = QCheckBox("Start with Windows")
        self.start_with_windows_check.setToolTip(
            "Adds/removes a HKCU Run key so Desktop Pet starts at login."
        )
        if not is_windows():
            self.start_with_windows_check.setEnabled(False)
            self.start_with_windows_check.setToolTip(
                "Available on Windows only (login autostart via registry Run key)."
            )
        sys_layout.addRow("Startup:", self.start_with_windows_check)

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
        if hasattr(self, "shortcut_filter"):
            filter_list_widget(self.shortcut_list, self.shortcut_filter.text())

        self.file_shortcut_list.clear()
        for sc in self.cfg.get("file_shortcuts") or []:
            sc = normalize_file_shortcut(sc)
            item = QListWidgetItem(self._file_shortcut_list_text(sc))
            item.setData(Qt.ItemDataRole.UserRole, sc)
            self.file_shortcut_list.addItem(item)
        if hasattr(self, "file_shortcut_filter"):
            filter_list_widget(
                self.file_shortcut_list, self.file_shortcut_filter.text()
            )
        self._on_fsc_type_changed()

        self.doc_title_edit.setText(self.cfg.get("document_area", "title") or "Document record")
        self.doc_folder_list.clear()
        self.doc_folder_edit.clear()
        folders = normalize_document_folders(self.cfg.get("document_area") or {})
        for folder in folders:
            self.doc_folder_list.addItem(folder)
        sort_code = normalize_sort(self.cfg.get("document_area", "sort_by"))
        sort_index = self.doc_sort_by.findData(sort_code)
        self.doc_sort_by.setCurrentIndex(sort_index if sort_index >= 0 else 0)

        self.text_record_list.clear()
        self.tr_title.clear()
        self.tr_body.clear()
        for rec in self.cfg.get("text_records") or []:
            rec = normalize_text_record(rec)
            item = QListWidgetItem(rec.get("title", "Untitled"))
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.text_record_list.addItem(item)
        if hasattr(self, "text_record_filter"):
            filter_list_widget(self.text_record_list, self.text_record_filter.text())

        mode = normalize_window_mode(self.cfg.get("window") or {})
        mode_index = self.window_mode.findData(mode)
        self.window_mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)

        want_autostart = bool(self.cfg.get("system", "start_with_windows"))
        if is_windows():
            # Prefer live registry state so Settings matches Windows.
            self.start_with_windows_check.setChecked(get_windows_autostart_enabled())
        else:
            self.start_with_windows_check.setChecked(want_autostart)

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

    def browse_shortcut_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.sc_path.setText(folder)

    def browse_file_shortcut(self):
        if self.fsc_type.currentData() == "url":
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self.fsc_path.setText(path)

    def _on_fsc_type_changed(self, *_args):
        is_url = self.fsc_type.currentData() == "url"
        self.btn_fsc_browse.setVisible(not is_url)
        self.fsc_path_label.setText("URL:" if is_url else "File Path:")
        if is_url:
            self.fsc_path.setPlaceholderText("https://example.com or internal URL")
        else:
            self.fsc_path.setPlaceholderText("")

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

    def _text_record_from_form(self):
        return normalize_text_record({
            "title": self.tr_title.text().strip(),
            "body": self.tr_body.toPlainText(),
        })

    def load_text_record_to_form(self, row):
        if row < 0:
            return
        item = self.text_record_list.item(row)
        if not item:
            return
        data = normalize_text_record(item.data(Qt.ItemDataRole.UserRole) or {})
        self.tr_title.setText(data.get("title", ""))
        self.tr_body.setPlainText(data.get("body", ""))

    def add_text_record(self):
        rec = self._text_record_from_form()
        item = QListWidgetItem(rec.get("title", "Untitled"))
        item.setData(Qt.ItemDataRole.UserRole, rec)
        self.text_record_list.addItem(item)
        self.text_record_list.setCurrentItem(item)
        filter_list_widget(self.text_record_list, self.text_record_filter.text())

    def update_text_record(self):
        row = self.text_record_list.currentRow()
        if row < 0:
            return
        item = self.text_record_list.item(row)
        rec = self._text_record_from_form()
        item.setText(rec.get("title", "Untitled"))
        item.setData(Qt.ItemDataRole.UserRole, rec)
        filter_list_widget(self.text_record_list, self.text_record_filter.text())

    def delete_text_record(self):
        row = self.text_record_list.currentRow()
        if row >= 0:
            self.text_record_list.takeItem(row)

    def move_up_text_record(self):
        row = self.text_record_list.currentRow()
        if row <= 0:
            return
        item = self.text_record_list.takeItem(row)
        self.text_record_list.insertItem(row - 1, item)
        self.text_record_list.setCurrentItem(item)

    def move_down_text_record(self):
        row = self.text_record_list.currentRow()
        if row < 0 or row >= self.text_record_list.count() - 1:
            return
        item = self.text_record_list.takeItem(row)
        self.text_record_list.insertItem(row + 1, item)
        self.text_record_list.setCurrentItem(item)

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

    def _file_shortcut_list_text(self, sc):
        sc = normalize_file_shortcut(sc)
        kind = "URL" if sc["type"] == "url" else "File"
        return f"{kind} | {sc['name']} | {sc['path']} | {sc['description']}"

    def _file_shortcut_from_form(self):
        return normalize_file_shortcut({
            "name": self.fsc_name.text().strip() or "Unnamed",
            "path": self.fsc_path.text().strip(),
            "description": self.fsc_desc.text().strip(),
            "type": self.fsc_type.currentData() or "file",
        })

    def load_file_shortcut_to_form(self, row):
        if row < 0:
            return
        item = self.file_shortcut_list.item(row)
        if not item:
            return
        data = normalize_file_shortcut(item.data(Qt.ItemDataRole.UserRole) or {})
        self.fsc_name.setText(data.get("name", ""))
        self.fsc_path.setText(data.get("path", ""))
        self.fsc_desc.setText(data.get("description", ""))
        type_index = self.fsc_type.findData(data.get("type") or "file")
        self.fsc_type.setCurrentIndex(type_index if type_index >= 0 else 0)
        self._on_fsc_type_changed()

    def add_file_shortcut(self):
        sc = self._file_shortcut_from_form()
        if sc["type"] == "url" and not sc["path"]:
            QMessageBox.information(self, "URL required", "Please enter a URL.")
            return
        item = QListWidgetItem(self._file_shortcut_list_text(sc))
        item.setData(Qt.ItemDataRole.UserRole, sc)
        self.file_shortcut_list.addItem(item)
        self.file_shortcut_list.setCurrentItem(item)
        filter_list_widget(self.file_shortcut_list, self.file_shortcut_filter.text())

    def update_file_shortcut(self):
        row = self.file_shortcut_list.currentRow()
        if row < 0:
            return
        item = self.file_shortcut_list.item(row)
        sc = self._file_shortcut_from_form()
        if sc["type"] == "url" and not sc["path"]:
            QMessageBox.information(self, "URL required", "Please enter a URL.")
            return
        item.setText(self._file_shortcut_list_text(sc))
        item.setData(Qt.ItemDataRole.UserRole, sc)
        filter_list_widget(self.file_shortcut_list, self.file_shortcut_filter.text())

    def delete_file_shortcut(self):
        row = self.file_shortcut_list.currentRow()
        if row >= 0:
            self.file_shortcut_list.takeItem(row)

    def move_up_file_shortcut(self):
        row = self.file_shortcut_list.currentRow()
        if row <= 0:
            return
        item = self.file_shortcut_list.takeItem(row)
        self.file_shortcut_list.insertItem(row - 1, item)
        self.file_shortcut_list.setCurrentItem(item)

    def move_down_file_shortcut(self):
        row = self.file_shortcut_list.currentRow()
        if row < 0 or row >= self.file_shortcut_list.count() - 1:
            return
        item = self.file_shortcut_list.takeItem(row)
        self.file_shortcut_list.insertItem(row + 1, item)
        self.file_shortcut_list.setCurrentItem(item)

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

        file_shortcuts = []
        for i in range(self.file_shortcut_list.count()):
            item = self.file_shortcut_list.item(i)
            file_shortcuts.append(
                normalize_file_shortcut(item.data(Qt.ItemDataRole.UserRole) or {})
            )
        self.cfg.set(["file_shortcuts"], file_shortcuts, save=False)

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

        text_records = []
        for i in range(self.text_record_list.count()):
            item = self.text_record_list.item(i)
            text_records.append(
                normalize_text_record(item.data(Qt.ItemDataRole.UserRole) or {})
            )
        self.cfg.set(["text_records"], text_records, save=False)

        mode = self.window_mode.currentData() or "normal"
        window = self.cfg.get("window") or {}
        apply_window_mode(window, mode)
        self.cfg.set(["window"], window, save=False)

        want_autostart = self.start_with_windows_check.isChecked()
        self.cfg.set(["system", "start_with_windows"], want_autostart, save=False)
        if is_windows():
            try:
                set_windows_autostart_enabled(want_autostart)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Autostart failed",
                    f"Could not update Windows startup entry:\n{e}",
                )

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

# Dark theme + gilt/wood picture-frame chrome for calculator dialogs.
CALC_DIALOG_STYLE = """
    QDialog {
        background-color: #1a1410;
        color: #e8e8e8;
        font-family: "Microsoft JhengHei", "Segoe UI", sans-serif;
        font-size: 9pt;
    }
    QScrollArea, QWidget#calcRoot {
        background-color: #1e1e1e;
        color: #e8e8e8;
        border: none;
    }
    QLabel { color: #d0d0d0; }
    QLabel#calcSectionTitle {
        color: #f5e6c8;
        font-weight: bold;
        font-size: 10pt;
    }
    QLabel#calcResult {
        background-color: #1a2e1a;
        color: #7CFC7C;
        border: 1px solid #2d5a2d;
        border-radius: 4px;
        padding: 4px 8px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 9pt;
        margin-top: 2px;
    }
    QLineEdit#calcNumeric {
        background-color: #2a2a2a;
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 2px 6px;
        min-height: 18px;
        max-height: 22px;
        selection-background-color: #3d5a80;
        selection-color: #ffffff;
    }
    QLineEdit#calcNumeric:focus {
        border: 1px solid #c9a84c;
    }
    QPushButton {
        background-color: #333333;
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px 8px;
    }
    QPushButton:hover { background-color: #444444; }
    QPushButton#calcAction {
        background-color: #2c2c2c;
        min-height: 22px;
        max-height: 24px;
        max-width: 120px;
        padding: 2px 10px;
        font-size: 9pt;
    }
    QLabel#calcFieldCaption {
        color: #d0d0d0;
        font-size: 9pt;
        padding: 0;
        margin: 0;
    }
    QRadioButton { color: #e0e0e0; spacing: 6px; }
    QFrame#calcSection {
        background-color: #252525;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
    }
    QFrame#calcOrnateOuter {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 #2a1c0e, stop:0.22 #6b4e1e, stop:0.45 #d4af37,
            stop:0.55 #f0d78c, stop:0.68 #d4af37, stop:0.85 #6b4e1e, stop:1 #2a1c0e
        );
        border: 1px solid #1a1008;
    }
    QFrame#calcOrnateMid {
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #5a3d24, stop:0.5 #3a2414, stop:1 #5a3d24
        );
        border: 1px solid #1a1208;
    }
    QFrame#calcOrnateInner {
        background-color: #1e1e1e;
        border: 1px solid #c9a84c;
        border-top-color: #e8d48b;
        border-left-color: #e8d48b;
        border-right-color: #7a5e18;
        border-bottom-color: #7a5e18;
    }
"""


def install_ornate_calc_frame(dialog):
    """
    Nested gilt/wood picture-frame chrome inside a calc dialog.
    Returns the innermost QVBoxLayout for dialog content.
    """
    shell = QVBoxLayout(dialog)
    shell.setContentsMargins(7, 7, 7, 7)
    shell.setSpacing(0)

    outer = QFrame()
    outer.setObjectName("calcOrnateOuter")
    outer_l = QVBoxLayout(outer)
    outer_l.setContentsMargins(4, 4, 4, 4)
    outer_l.setSpacing(0)

    mid = QFrame()
    mid.setObjectName("calcOrnateMid")
    mid_l = QVBoxLayout(mid)
    mid_l.setContentsMargins(5, 5, 5, 5)
    mid_l.setSpacing(0)

    inner = QFrame()
    inner.setObjectName("calcOrnateInner")
    inner_l = QVBoxLayout(inner)
    inner_l.setContentsMargins(10, 10, 10, 10)
    inner_l.setSpacing(8)

    mid_l.addWidget(inner)
    outer_l.addWidget(mid)
    shell.addWidget(outer)
    return inner_l


def parse_calc_number(text):
    """Parse a typed calculator field; raises ValueError on empty/invalid input."""
    raw = (text or "").strip().replace(",", "")
    if not raw or raw in ("-", "+", ".", "-.", "+."):
        raise ValueError("請輸入有效數值")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError("請輸入有效數值") from exc


# ---------------------------------------------------------------------------
# Surveying / slope math helpers
# ---------------------------------------------------------------------------
def format_dms(degrees):
    """Format decimal degrees as D° M' S.ss\" (survey display)."""
    sign = "-" if degrees < 0 else ""
    deg = abs(degrees)
    d = int(deg)
    m_float = (deg - d) * 60.0
    m = int(m_float)
    s = (m_float - m) * 60.0
    # Handle float carry (e.g. 59.999 → 60).
    if s >= 59.995:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        d += 1
    return f"{sign}{d}° {m}' {s:05.2f}\""


def degrees_to_ddmmss(degrees):
    """Encode decimal degrees as surveying DD.MMSS (e.g. 2°51'44.66\" → 2.514466)."""
    sign = -1.0 if degrees < 0 else 1.0
    deg = abs(degrees)
    d = int(deg)
    m_float = (deg - d) * 60.0
    m = int(m_float)
    s = (m_float - m) * 60.0
    if s >= 59.995:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        d += 1
    return sign * (d + m / 100.0 + s / 10000.0)


def ddmmss_to_degrees(ddmmss):
    """Decode surveying DD.MMSS to decimal degrees."""
    sign = -1.0 if ddmmss < 0 else 1.0
    v = abs(ddmmss)
    d = int(v)
    frac = round(v - d, 10)
    mm_ss = frac * 100.0
    m = int(mm_ss)
    s = (mm_ss - m) * 100.0
    return sign * (d + m / 60.0 + s / 3600.0)


def slope_from_length_diff(length, high_lv, low_lv):
    """
    Type A: two-point height difference → slope.
    rise = high_lv - low_lv; Fall% = rise/L*100; 1 in X = L/rise; angle = atan(rise/L).
    """
    if length == 0:
        raise ValueError("長度 (L) 必須不為 0")
    rise = high_lv - low_lv
    if rise == 0:
        return 0.0, float("inf"), 0.0
    fall_pct = (rise / length) * 100.0
    one_in_x = length / rise
    angle_deg = math.degrees(math.atan(rise / length))
    return fall_pct, one_in_x, angle_deg


def ending_lv_from_fall(length, start_lv, fall_pct):
    """
    Type B: slope → ending elevation (survey “fall” convention).
    drop = L * fall%/100; ending = start - drop (positive fall = downhill).
    """
    drop = length * (fall_pct / 100.0)
    ending = start_lv - drop
    if fall_pct == 0:
        return ending, float("inf"), 0.0
    one_in_x = 100.0 / fall_pct
    angle_deg = math.degrees(math.atan(fall_pct / 100.0))
    return ending, one_in_x, angle_deg


def convert_slope_units(known_kind, value):
    """
    Live convert between Fall %, 1 in X, and angle (decimal degrees).
    known_kind: 'fall' | 'xin' | 'angle'
    Returns (fall_pct, one_in_x, angle_deg).
    """
    if known_kind == "fall":
        fall_pct = value
        if fall_pct == 0:
            return 0.0, float("inf"), 0.0
        one_in_x = 100.0 / fall_pct
        angle_deg = math.degrees(math.atan(fall_pct / 100.0))
        return fall_pct, one_in_x, angle_deg
    if known_kind == "xin":
        if value == 0:
            raise ValueError("1 in X 的 X 不可為 0")
        one_in_x = value
        fall_pct = 100.0 / one_in_x
        angle_deg = math.degrees(math.atan(1.0 / one_in_x))
        return fall_pct, one_in_x, angle_deg
    if known_kind == "angle":
        angle_deg = value
        if abs(angle_deg) % 180 == 90:
            raise ValueError("角度不可為 ±90°")
        fall_pct = 100.0 * math.tan(math.radians(angle_deg))
        if fall_pct == 0:
            return 0.0, float("inf"), angle_deg
        one_in_x = 100.0 / fall_pct
        return fall_pct, one_in_x, angle_deg
    raise ValueError(f"Unknown slope unit kind: {known_kind}")


def level_at_target(high_level, low_level, full_length, target_distance):
    """
    平水計算 (linear interpolate along a grade line).
    Assumes high level at chainage 0 and low level at full_length:
        level = high - (high - low) * (target / full)
    Extrapolation is allowed when target is outside [0, full].
    """
    if full_length <= 0:
        raise ValueError("全長必須大於 0")
    return high_level - (high_level - low_level) * (target_distance / full_length)


def format_one_in_x(xin):
    if xin == float("inf") or xin == float("-inf"):
        return "1 in ∞"
    return f"1 in {xin:.3f}"


def _format_calc_value(value, decimals=3):
    text = f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def make_calc_line_edit(value=0.0, decimals=3, max_edit_width=90):
    """Compact keyboard-editable decimal QLineEdit for calculator rows."""
    edit = QLineEdit()
    edit.setObjectName("calcNumeric")
    edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
    edit.setText(_format_calc_value(value, decimals))
    edit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    edit.setFixedHeight(24)
    if max_edit_width:
        edit.setFixedWidth(max_edit_width)
    return edit


class NumericField:
    """Accessor for a calculator QLineEdit (parse on read; decimals on write)."""

    def __init__(self, edit, decimals=3):
        self.edit = edit
        self._decimals = decimals
        self.textChanged = edit.textChanged

    def value(self):
        return parse_calc_number(self.edit.text())

    def setValue(self, value):
        self.edit.setText(_format_calc_value(value, self._decimals))


def build_calc_action_cluster(field_specs, button_text, button_slot):
    """
    Two-row cluster: captions on row 0; edits + action button on row 1.

    field_specs: list of (label, value, decimals=3, max_edit_width=90)
    Returns (widget, list[NumericField]).
    """
    wrap = QWidget()
    grid = QGridLayout(wrap)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(2)
    grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    fields = []
    for col, spec in enumerate(field_specs):
        label = spec[0]
        value = spec[1] if len(spec) > 1 else 0.0
        decimals = spec[2] if len(spec) > 2 else 3
        max_w = spec[3] if len(spec) > 3 else 90
        caption = QLabel(label)
        caption.setObjectName("calcFieldCaption")
        edit = make_calc_line_edit(value, decimals=decimals, max_edit_width=max_w)
        grid.addWidget(caption, 0, col, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(edit, 1, col, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        fields.append(NumericField(edit, decimals=decimals))

    btn = QPushButton(button_text)
    btn.setObjectName("calcAction")
    btn.setFixedHeight(24)
    btn.clicked.connect(button_slot)
    # Same baseline as the edit row (not the caption row).
    grid.addWidget(
        btn,
        1,
        len(field_specs),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    return wrap, fields


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

        header = QHBoxLayout()
        header.setSpacing(4)
        self.title_label = QLabel("Document record")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.btn_open_folder = QPushButton()
        self.btn_open_folder.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.btn_open_folder.setToolTip("Open folder")
        self.btn_open_folder.setFixedSize(28, 24)
        self.btn_open_folder.setStyleSheet(
            "text-align: center; padding: 2px;" + menu_button_style("#4a4a4a")
        )
        self.btn_open_folder.clicked.connect(self.open_storage_folder)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.btn_open_folder)
        self.main_layout.addLayout(header)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search files…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,230); color: #222; "
            "border-radius: 4px; padding: 3px 6px; }"
        )
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.main_layout.addWidget(self.search_edit)

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

    def open_storage_folder(self):
        """Open document storage folder(s) in the OS file manager."""
        folders = normalize_document_folders(self.cfg.get("document_area") or {})
        if not folders:
            QMessageBox.information(
                self,
                "No storage folder",
                "Add a data storage folder in Settings → Document Record.",
            )
            return
        if len(folders) == 1:
            self._open_folder_path(folders[0])
            return
        # Multiple folders: pick via menu (least surprising; user chooses).
        self._suppress_hide = True
        menu = QMenu(self)
        for folder in folders:
            label = folder
            try:
                name = Path(folder).name
                if name:
                    label = f"{name}  —  {folder}"
            except Exception:
                pass
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, p=folder: self._open_folder_path(p)
            )
            menu.addAction(action)
        menu.exec(self.btn_open_folder.mapToGlobal(self.btn_open_folder.rect().bottomLeft()))
        self._suppress_hide = False

    def _open_folder_path(self, folder):
        try:
            open_local_path(folder)
        except FileNotFoundError:
            QMessageBox.warning(self, "Path does not exist", f"Not found:\n{folder}")
        except Exception as e:
            QMessageBox.warning(self, "Open failed", str(e))

    def _on_search_changed(self, _text):
        self.show_page(0)

    def _filtered_files(self):
        query = (self.search_edit.text() or "").strip().lower()
        if not query:
            return list(self.files)
        matched = []
        for folder, fname in self.files:
            meta = self.files_meta.get(fname, {}) or {}
            haystack = " ".join(
                [
                    fname,
                    folder,
                    meta.get("comment", "") or "",
                    meta.get("publisher", "") or "",
                    meta.get("version", "") or "",
                    meta.get("time", "") or "",
                ]
            ).lower()
            if query in haystack:
                matched.append((folder, fname))
        return matched

    def refresh_and_show(self, anchor_geometry):
        self.files = []
        self.files_meta = dict(self.cfg.get("document_area", "files") or {})
        self.title_label.setText(self.cfg.get("document_area", "title") or "Document record")
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)

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

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def show_page(self, page):
        self._clear_layout(self.files_container)
        self._clear_layout(self.pagination_container)

        visible = self._filtered_files()
        if not visible:
            hint = "(No matching files)" if (self.search_edit.text() or "").strip() else "(No files)"
            lbl = QLabel(hint)
            lbl.setStyleSheet("color: #dddddd;")
            self.files_container.addWidget(lbl)
            self.adjustSize()
            return

        total_pages = max(1, (len(visible) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = max(0, min(page, total_pages - 1))
        start = self.current_page * self.items_per_page
        end = min(start + self.items_per_page, len(visible))

        for folder, fname in visible[start:end]:
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
            open_local_path(path)
        except FileNotFoundError:
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
# File shortcuts submenu (opened via >> like Document record)
# ---------------------------------------------------------------------------
class FileShortcutsSubMenu(PopupPanel):
    """Submenu listing file/URL shortcuts; opened from the main pet menu >> control."""

    open_shortcut = Signal(str, str)  # path, type

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self._all_shortcuts = []
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

        self.title_label = QLabel("File shortcuts")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.main_layout.addWidget(self.title_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search file / URL shortcuts…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,230); color: #222; "
            "border-radius: 4px; padding: 3px 6px; }"
        )
        self.search_edit.textChanged.connect(self._rebuild_items)
        self.main_layout.addWidget(self.search_edit)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep)

        self.items_container = QVBoxLayout()
        self.items_container.setSpacing(2)
        self.main_layout.addLayout(self.items_container)

        self.setStyleSheet(MENU_STYLE + """
            FileShortcutsSubMenu { background-color: transparent; }
        """)

    def button_style(self, base_color):
        return menu_button_style(base_color)

    def _filtered_shortcuts(self):
        query = (self.search_edit.text() or "").strip().lower()
        if not query:
            return list(self._all_shortcuts)
        matched = []
        for sc in self._all_shortcuts:
            haystack = " ".join(
                [
                    sc.get("type", ""),
                    sc.get("name", ""),
                    sc.get("path", ""),
                    sc.get("description", ""),
                ]
            ).lower()
            if query in haystack:
                matched.append(sc)
        return matched

    def _rebuild_items(self):
        while self.items_container.count():
            item = self.items_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        shortcuts = self._filtered_shortcuts()
        if not self._all_shortcuts:
            lbl = QLabel("(No file shortcuts)")
            lbl.setStyleSheet("color: #dddddd;")
            self.items_container.addWidget(lbl)
        elif not shortcuts:
            lbl = QLabel("(No matching shortcuts)")
            lbl.setStyleSheet("color: #dddddd;")
            self.items_container.addWidget(lbl)
        else:
            for sc in shortcuts:
                sc = normalize_file_shortcut(sc)
                name = sc.get("name", "Unnamed")
                path = sc.get("path", "")
                desc = sc.get("description", "")
                sc_type = sc.get("type", "file")
                text = name
                if sc_type == "url":
                    text = f"[URL] {name}"
                if desc:
                    text += f" ({desc})"
                btn = QPushButton(text)
                tip = path if sc_type == "file" else f"URL: {path}"
                btn.setToolTip(tip)
                color = "#1f6b8a" if sc_type == "url" else "#2a6f6f"
                btn.setStyleSheet(self.button_style(color))
                btn.clicked.connect(
                    lambda checked=False, p=path, t=sc_type: self.open_shortcut.emit(p, t)
                )
                self.items_container.addWidget(btn)
        self.adjustSize()

    def refresh_and_show(self, anchor_geometry):
        self._all_shortcuts = [
            normalize_file_shortcut(sc)
            for sc in (self.cfg.get("file_shortcuts") or [])
            if isinstance(sc, dict)
        ]
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._rebuild_items()

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

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        self.hide()


# ---------------------------------------------------------------------------
# Mini-program calculators: 平水計算 / 坡度運算
# ---------------------------------------------------------------------------
class LevelCalcDialog(QDialog):
    """平水計算 — linear interpolate level at a target chainage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("平水計算")
        self.setMinimumSize(540, 200)
        self.resize(560, 220)
        self.setStyleSheet(CALC_DIALOG_STYLE)
        root = install_ornate_calc_frame(self)
        root.setSpacing(6)

        title = QLabel("平水計算")
        title.setObjectName("calcSectionTitle")
        root.addWidget(title)

        # Captions above; edits + 計算平水 share one baseline row (button right).
        cluster, fields = build_calc_action_cluster(
            [
                ("高位平水", 100.0, 3, 88),
                ("低位平水", 90.0, 3, 88),
                ("全長", 50.0, 3, 88),
                ("目標距離", 25.0, 3, 88),
            ],
            "計算平水",
            self._calculate,
        )
        self.high, self.low, self.full, self.target = fields
        root.addWidget(cluster, 0, Qt.AlignmentFlag.AlignLeft)

        self.result = QLabel("結果將顯示於此")
        self.result.setObjectName("calcResult")
        self.result.setWordWrap(True)
        root.addWidget(self.result)
        root.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _calculate(self):
        try:
            full = self.full.value()
            target = self.target.value()
            level = level_at_target(
                self.high.value(), self.low.value(), full, target
            )
            note = ""
            if target < 0 or target > full:
                note = "\n（目標距離超出 [0, 全長]，已外插）"
            elif abs(target) < 1e-12:
                note = "\n（位於起點／高位）"
            elif abs(target - full) < 1e-12:
                note = "\n（位於終點／低位）"
            self.result.setText(
                f"◆ 目標距離的平水: {level:.3f}{note}"
            )
        except ValueError as exc:
            self.result.setText(f"輸入錯誤: {exc}")


class SlopeCalcDialog(QDialog):
    """坡度運算 — three calculators matching the surveying reference UIs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("坡度運算")
        self.setMinimumSize(520, 560)
        self.resize(560, 620)
        self.setStyleSheet(CALC_DIALOG_STYLE)

        frame_root = install_ornate_calc_frame(self)
        frame_root.setContentsMargins(6, 6, 6, 6)
        frame_root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        frame_root.addWidget(scroll)

        root_w = QWidget()
        root_w.setObjectName("calcRoot")
        scroll.setWidget(root_w)
        root = QVBoxLayout(root_w)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        root.addWidget(self._build_section_a())
        root.addWidget(self._build_section_b())
        root.addWidget(self._build_section_c())

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _section_frame(self, number, title):
        frame = QFrame()
        frame.setObjectName("calcSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        head = QLabel(f"{number}  {title}")
        head.setObjectName("calcSectionTitle")
        layout.addWidget(head)
        return frame, layout

    def _build_section_a(self):
        frame, layout = self._section_frame("1", "兩點高差求坡度")
        cluster, fields = build_calc_action_cluster(
            [
                ("長度 (L)", 10.0, 3, 88),
                ("高位 LV", 10.0, 3, 88),
                ("低位 LV", 9.5, 3, 88),
            ],
            "計算坡度",
            self._calc_a,
        )
        self.a_length, self.a_high, self.a_low = fields
        layout.addWidget(cluster, 0, Qt.AlignmentFlag.AlignLeft)

        self.a_result = QLabel("")
        self.a_result.setObjectName("calcResult")
        self.a_result.setWordWrap(True)
        self.a_result.hide()
        layout.addWidget(self.a_result)
        return frame

    def _build_section_b(self):
        frame, layout = self._section_frame("2", "坡度推算高程")
        cluster, fields = build_calc_action_cluster(
            [
                ("長度 (L)", 10.0, 3, 88),
                ("起始 LV", 10.0, 3, 88),
                ("坡度 Fall (%)", 5.0, 3, 88),
            ],
            "計算高程",
            self._calc_b,
        )
        self.b_length, self.b_start, self.b_fall = fields
        layout.addWidget(cluster, 0, Qt.AlignmentFlag.AlignLeft)

        self.b_result = QLabel("")
        self.b_result.setObjectName("calcResult")
        self.b_result.setWordWrap(True)
        self.b_result.hide()
        layout.addWidget(self.b_result)
        return frame

    def _build_section_c(self):
        frame, layout = self._section_frame("3", "坡度單位互相運算框")
        layout.addWidget(QLabel("選擇已知條件:"))
        self.c_group = QButtonGroup(self)
        self.radio_fall = QRadioButton("已知 坡度 (Fall %)")
        self.radio_xin = QRadioButton("已知 1 in X")
        self.radio_angle = QRadioButton("已知 角度 (DD.MMSS)")
        self.radio_fall.setChecked(True)
        for i, radio in enumerate(
            (self.radio_fall, self.radio_xin, self.radio_angle)
        ):
            self.c_group.addButton(radio, i)
            layout.addWidget(radio)
        self.c_group.idClicked.connect(lambda _id: self._on_c_kind_changed())

        self.c_input_label = QLabel("輸入 坡度 (Fall %)")
        self.c_input_label.setObjectName("calcFieldCaption")
        layout.addWidget(self.c_input_label)
        c_edit = make_calc_line_edit(1.0, decimals=6, max_edit_width=140)
        self.c_value = NumericField(c_edit, decimals=6)
        self.c_value.textChanged.connect(self._calc_c_live)
        layout.addWidget(c_edit, 0, Qt.AlignmentFlag.AlignLeft)

        self.c_result = QLabel("")
        self.c_result.setObjectName("calcResult")
        self.c_result.setWordWrap(True)
        layout.addWidget(self.c_result)
        self._calc_c_live()
        return frame

    def _calc_a(self):
        try:
            fall, xin, ang = slope_from_length_diff(
                self.a_length.value(), self.a_high.value(), self.a_low.value()
            )
            self.a_result.setText(
                "◆ 坡度 Fall: "
                f"{fall:.3f} %\n"
                f"◆ 1 IN X: {format_one_in_x(xin)}\n"
                f"◆ 角度: {format_dms(ang)}"
            )
            self.a_result.show()
        except ValueError as exc:
            self.a_result.setText(f"輸入錯誤: {exc}")
            self.a_result.show()

    def _calc_b(self):
        try:
            ending, xin, ang = ending_lv_from_fall(
                self.b_length.value(), self.b_start.value(), self.b_fall.value()
            )
            self.b_result.setText(
                f"◆ 結尾 LV: {ending:.3f}\n"
                f"◆ 1 IN X: {format_one_in_x(xin)}\n"
                f"◆ 角度: {format_dms(ang)}"
            )
            self.b_result.show()
        except ValueError as exc:
            self.b_result.setText(f"輸入錯誤: {exc}")
            self.b_result.show()

    def _c_kind(self):
        if self.radio_xin.isChecked():
            return "xin"
        if self.radio_angle.isChecked():
            return "angle"
        return "fall"

    def _on_c_kind_changed(self):
        kind = self._c_kind()
        if kind == "fall":
            self.c_input_label.setText("輸入 坡度 (Fall %)")
        elif kind == "xin":
            self.c_input_label.setText("輸入 1 in X")
        else:
            self.c_input_label.setText("輸入 角度 (DD.MMSS)")
        self._calc_c_live()

    def _calc_c_live(self, *_args):
        kind = self._c_kind()
        try:
            raw = self.c_value.value()
            if kind == "angle":
                # Input is DD.MMSS surveying encoding; convert to decimal degrees.
                angle_deg = ddmmss_to_degrees(raw)
                fall, xin, ang = convert_slope_units("angle", angle_deg)
            else:
                fall, xin, ang = convert_slope_units(kind, raw)
            lines = []
            if kind != "fall":
                lines.append(f"◆ 坡度 Fall: {fall:.3f} %")
            if kind != "xin":
                lines.append(f"◆ 1 IN X: {format_one_in_x(xin)}")
            if kind != "angle":
                lines.append(
                    f"◆ 角度: {format_dms(ang)}  (DD.MMSS: {degrees_to_ddmmss(ang):.6f})"
                )
            else:
                # Still show DMS for clarity when DD.MMSS was the input.
                lines.append(f"◆ 角度 (DMS): {format_dms(ang)}")
            self.c_result.setText("\n".join(lines) if lines else "—")
        except ValueError as exc:
            self.c_result.setText(f"輸入錯誤: {exc}")


# ---------------------------------------------------------------------------
# Text record readable view
# ---------------------------------------------------------------------------
class TextRecordViewDialog(QDialog):
    """Read-only dialog showing a text record title + body."""

    def __init__(self, title, body, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "Text records")
        self.setMinimumSize(420, 320)
        layout = QVBoxLayout(self)
        title_lbl = QLabel(title or "Untitled")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11pt;")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)
        body_edit = QPlainTextEdit()
        body_edit.setReadOnly(True)
        body_edit.setPlainText(body or "")
        layout.addWidget(body_edit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)


# ---------------------------------------------------------------------------
# Text records submenu (opened via >> like Document record)
# ---------------------------------------------------------------------------
class TextRecordsSubMenu(PopupPanel):
    """Submenu listing text-record titles; click opens the article body."""

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self._all_records = []
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

        self.title_label = QLabel("Text records")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.main_layout.addWidget(self.title_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search text records…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,230); color: #222; "
            "border-radius: 4px; padding: 3px 6px; }"
        )
        self.search_edit.textChanged.connect(self._rebuild_items)
        self.main_layout.addWidget(self.search_edit)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep)

        self.items_container = QVBoxLayout()
        self.items_container.setSpacing(2)
        self.main_layout.addLayout(self.items_container)

        self.setStyleSheet(MENU_STYLE + """
            TextRecordsSubMenu { background-color: transparent; }
        """)

    def button_style(self, base_color):
        return menu_button_style(base_color)

    def _filtered_records(self):
        query = (self.search_edit.text() or "").strip().lower()
        if not query:
            return list(self._all_records)
        matched = []
        for rec in self._all_records:
            haystack = " ".join(
                [rec.get("title", ""), rec.get("body", "")]
            ).lower()
            if query in haystack:
                matched.append(rec)
        return matched

    def _rebuild_items(self):
        while self.items_container.count():
            item = self.items_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        records = self._filtered_records()
        if not self._all_records:
            lbl = QLabel("(No text records)")
            lbl.setStyleSheet("color: #dddddd;")
            self.items_container.addWidget(lbl)
        elif not records:
            lbl = QLabel("(No matching records)")
            lbl.setStyleSheet("color: #dddddd;")
            self.items_container.addWidget(lbl)
        else:
            for rec in records:
                title = rec.get("title", "Untitled")
                btn = QPushButton(title)
                preview = " ".join((rec.get("body") or "").split())[:80]
                btn.setToolTip(preview or title)
                btn.setStyleSheet(self.button_style("#5a6e3a"))
                btn.clicked.connect(
                    lambda checked=False, r=rec: self._open_record(r)
                )
                self.items_container.addWidget(btn)
        self.adjustSize()

    def _open_record(self, rec):
        self._suppress_hide = True
        dlg = TextRecordViewDialog(
            rec.get("title", "Untitled"),
            rec.get("body", ""),
            parent=self,
        )
        dlg.exec()
        self._suppress_hide = False

    def refresh_and_show(self, anchor_geometry):
        self._all_records = [
            normalize_text_record(rec)
            for rec in (self.cfg.get("text_records") or [])
            if isinstance(rec, dict)
        ]
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.search_edit.setVisible(bool(self._all_records))
        self._rebuild_items()

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

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        active = QApplication.activeWindow()
        if isinstance(active, (QMenu, TextRecordViewDialog)):
            return
        self.hide()


# ---------------------------------------------------------------------------
# 運算 submenu (third level under 小程式)
# ---------------------------------------------------------------------------
class OperationsSubMenu(PopupPanel):
    """Third-level menu: 平水計算 / 坡度運算."""

    def __init__(self):
        super().__init__()
        self._level_dialog = None
        self._slope_dialog = None
        self.build_ui()

    def build_ui(self):
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = QLabel("運算")
        title.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(title)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        layout.addWidget(sep)

        btn_level = QPushButton("平水計算")
        btn_level.setStyleSheet(menu_button_style("#5a4a6e"))
        btn_level.clicked.connect(self.open_level_calc)
        layout.addWidget(btn_level)

        btn_slope = QPushButton("坡度運算")
        btn_slope.setStyleSheet(menu_button_style("#4a5a6e"))
        btn_slope.clicked.connect(self.open_slope_calc)
        layout.addWidget(btn_slope)

        self.setStyleSheet(MENU_STYLE + """
            OperationsSubMenu { background-color: transparent; }
        """)

    def refresh_and_show(self, anchor_geometry):
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

    def open_level_calc(self):
        self._suppress_hide = True
        if self._level_dialog is None:
            self._level_dialog = LevelCalcDialog(None)
        self._level_dialog.show()
        self._level_dialog.raise_()
        self._level_dialog.activateWindow()
        QTimer.singleShot(200, self._release_suppress)

    def open_slope_calc(self):
        self._suppress_hide = True
        if self._slope_dialog is None:
            self._slope_dialog = SlopeCalcDialog(None)
        self._slope_dialog.show()
        self._slope_dialog.raise_()
        self._slope_dialog.activateWindow()
        QTimer.singleShot(200, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        active = QApplication.activeWindow()
        if isinstance(active, (LevelCalcDialog, SlopeCalcDialog)):
            return
        if self._level_dialog is not None and self._level_dialog.isVisible():
            return
        if self._slope_dialog is not None and self._slope_dialog.isVisible():
            return
        self.hide()


# ---------------------------------------------------------------------------
# 小程式 submenu (Text records + 運算)
# ---------------------------------------------------------------------------
class MiniProgramsSubMenu(PopupPanel):
    """Second-level menu under 小程式: Text records + 運算."""

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self.text_records_submenu = None
        self.operations_submenu = None
        self.build_ui()

    def build_ui(self):
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = QLabel("小程式")
        title.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(title)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        layout.addWidget(sep)

        # Text records >>
        text_row = QHBoxLayout()
        text_row.setSpacing(4)
        text_lbl = QLabel("Text records")
        text_lbl.setStyleSheet("color: white; font-weight: bold;")
        btn_text = QPushButton(">>")
        btn_text.setFixedWidth(30)
        btn_text.setStyleSheet("text-align: center;" + menu_button_style("#4a4a4a"))
        btn_text.clicked.connect(self.open_text_records)
        text_row.addWidget(text_lbl)
        text_row.addStretch()
        text_row.addWidget(btn_text)
        layout.addLayout(text_row)

        # 運算 >>
        ops_row = QHBoxLayout()
        ops_row.setSpacing(4)
        ops_lbl = QLabel("運算")
        ops_lbl.setStyleSheet("color: white; font-weight: bold;")
        btn_ops = QPushButton(">>")
        btn_ops.setFixedWidth(30)
        btn_ops.setStyleSheet("text-align: center;" + menu_button_style("#4a4a4a"))
        btn_ops.clicked.connect(self.open_operations)
        ops_row.addWidget(ops_lbl)
        ops_row.addStretch()
        ops_row.addWidget(btn_ops)
        layout.addLayout(ops_row)

        self.setStyleSheet(MENU_STYLE + """
            MiniProgramsSubMenu { background-color: transparent; }
        """)

    def refresh_and_show(self, anchor_geometry):
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

    def _hide_nested(self, keep=None):
        if keep != "text" and self.text_records_submenu is not None:
            self.text_records_submenu.hide()
        if keep != "ops" and self.operations_submenu is not None:
            self.operations_submenu.hide()

    def open_text_records(self):
        if self.text_records_submenu is None:
            self.text_records_submenu = TextRecordsSubMenu(self.cfg)
        self._hide_nested(keep="text")
        self._suppress_hide = True
        self.text_records_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def open_operations(self):
        if self.operations_submenu is None:
            self.operations_submenu = OperationsSubMenu()
        self._hide_nested(keep="ops")
        self._suppress_hide = True
        self.operations_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def hideEvent(self, event):
        if self.text_records_submenu is not None:
            self.text_records_submenu.hide()
        if self.operations_submenu is not None:
            self.operations_submenu.hide()
        super().hideEvent(event)

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        if self.text_records_submenu is not None and (
            self.text_records_submenu.isVisible()
            or self.text_records_submenu.isActiveWindow()
        ):
            return
        if self.operations_submenu is not None and (
            self.operations_submenu.isVisible()
            or self.operations_submenu.isActiveWindow()
        ):
            return
        active = QApplication.activeWindow()
        if isinstance(
            active,
            (
                TextRecordsSubMenu,
                TextRecordViewDialog,
                OperationsSubMenu,
                LevelCalcDialog,
                SlopeCalcDialog,
            ),
        ):
            return
        self.hide()


# ---------------------------------------------------------------------------
# Main menu (semi-transparent popup)
# ---------------------------------------------------------------------------
class PetMenu(PopupPanel):
    """Semi-transparent menu that pops up when the pet is clicked."""

    open_shortcut = Signal(str, str)  # path, type ("folder" / "file" / "url")
    open_settings = Signal()
    open_file_meta = Signal(str)

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self.doc_submenu = None
        self.file_shortcuts_submenu = None
        self.mini_programs_submenu = None
        self._folder_shortcuts = []
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

        self.folder_search_edit = QLineEdit()
        self.folder_search_edit.setPlaceholderText("Search folder shortcuts…")
        self.folder_search_edit.setClearButtonEnabled(True)
        self.folder_search_edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,230); color: #222; "
            "border-radius: 4px; padding: 3px 6px; }"
        )
        self.folder_search_edit.textChanged.connect(self._rebuild_folder_shortcuts)
        self.main_layout.addWidget(self.folder_search_edit)

        self.shortcuts_container = QVBoxLayout()
        self.shortcuts_container.setSpacing(3)
        self.main_layout.addLayout(self.shortcuts_container)

        sep0 = QLabel()
        sep0.setFixedHeight(1)
        sep0.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep0)

        # File / URL shortcuts: collapsed header + >> (same pattern as Document record)
        file_sc_header = QHBoxLayout()
        file_sc_header.setSpacing(4)
        self.file_shortcuts_title = QLabel("File / URL shortcuts")
        self.file_shortcuts_title.setStyleSheet("color: white; font-weight: bold;")
        self.btn_file_sc_open = QPushButton(">>")
        self.btn_file_sc_open.setFixedWidth(30)
        self.btn_file_sc_open.setStyleSheet(
            "text-align: center;" + menu_button_style("#4a4a4a")
        )
        self.btn_file_sc_open.clicked.connect(self.open_file_shortcuts_submenu)
        file_sc_header.addWidget(self.file_shortcuts_title)
        file_sc_header.addStretch()
        file_sc_header.addWidget(self.btn_file_sc_open)
        self.main_layout.addLayout(file_sc_header)

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

        # 小程式: collapsed header + >> (Text records + 運算 live inside)
        mini_header = QHBoxLayout()
        mini_header.setSpacing(4)
        self.mini_programs_title = QLabel("小程式")
        self.mini_programs_title.setStyleSheet("color: white; font-weight: bold;")
        self.btn_mini_open = QPushButton(">>")
        self.btn_mini_open.setFixedWidth(30)
        self.btn_mini_open.setStyleSheet(
            "text-align: center;" + menu_button_style("#4a4a4a")
        )
        self.btn_mini_open.clicked.connect(self.open_mini_programs_submenu)
        mini_header.addWidget(self.mini_programs_title)
        mini_header.addStretch()
        mini_header.addWidget(self.btn_mini_open)
        self.main_layout.addLayout(mini_header)

        sep3 = QLabel()
        sep3.setFixedHeight(1)
        sep3.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep3)

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setStyleSheet(self.button_style("#4a4a4a"))
        self.btn_settings.clicked.connect(self.open_settings.emit)
        self.main_layout.addWidget(self.btn_settings)

        self.setStyleSheet(MENU_STYLE + """
            PetMenu { background-color: transparent; }
        """)

    def button_style(self, base_color):
        return menu_button_style(base_color)

    def _rebuild_folder_shortcuts(self):
        while self.shortcuts_container.count():
            item = self.shortcuts_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = (self.folder_search_edit.text() or "").strip().lower()
        shortcuts = []
        for sc in self._folder_shortcuts:
            if not isinstance(sc, dict):
                continue
            if query:
                haystack = " ".join(
                    [
                        sc.get("name", ""),
                        sc.get("path", ""),
                        sc.get("description", ""),
                    ]
                ).lower()
                if query not in haystack:
                    continue
            shortcuts.append(sc)

        if not self._folder_shortcuts:
            btn = QPushButton("-Please add a folder in Settings-")
            btn.setEnabled(False)
            btn.setStyleSheet("color: #dddddd; background-color: transparent;")
            self.shortcuts_container.addWidget(btn)
        elif not shortcuts:
            btn = QPushButton("(No matching folders)")
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
                btn.clicked.connect(
                    lambda checked=False, p=path: self.open_shortcut.emit(p, "folder")
                )
                self.shortcuts_container.addWidget(btn)
        self.adjustSize()

    def refresh(self):
        self._folder_shortcuts = list(self.cfg.get("shortcuts") or [])
        self.folder_search_edit.blockSignals(True)
        self.folder_search_edit.clear()
        self.folder_search_edit.blockSignals(False)
        # Hide search box when there is nothing to filter.
        self.folder_search_edit.setVisible(bool(self._folder_shortcuts))
        self._rebuild_folder_shortcuts()

        title = self.cfg.get("document_area", "title") or "Document record"
        self.doc_title.setText(title)
        self.adjustSize()

    def _hide_other_submenus(self, keep=None):
        pairs = (
            ("doc", self.doc_submenu),
            ("file", self.file_shortcuts_submenu),
            ("mini", self.mini_programs_submenu),
        )
        for key, submenu in pairs:
            if keep == key:
                continue
            if submenu is not None and submenu.isVisible():
                submenu.hide()

    def open_file_shortcuts_submenu(self):
        if self.file_shortcuts_submenu is None:
            self.file_shortcuts_submenu = FileShortcutsSubMenu(self.cfg)
            self.file_shortcuts_submenu.open_shortcut.connect(self.open_shortcut.emit)
        self._hide_other_submenus(keep="file")
        self._suppress_hide = True
        self.file_shortcuts_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def open_document_submenu(self):
        if self.doc_submenu is None:
            self.doc_submenu = DocumentSubMenu(self.cfg)
            self.doc_submenu.open_file_meta.connect(self.open_file_meta.emit)
        self._hide_other_submenus(keep="doc")
        self._suppress_hide = True
        self.doc_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def open_mini_programs_submenu(self):
        if self.mini_programs_submenu is None:
            self.mini_programs_submenu = MiniProgramsSubMenu(self.cfg)
        self._hide_other_submenus(keep="mini")
        self._suppress_hide = True
        self.mini_programs_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def hideEvent(self, event):
        if self.doc_submenu is not None:
            self.doc_submenu.hide()
        if self.file_shortcuts_submenu is not None:
            self.file_shortcuts_submenu.hide()
        if self.mini_programs_submenu is not None:
            self.mini_programs_submenu.hide()
        super().hideEvent(event)

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        if self.doc_submenu is not None and (
            self.doc_submenu.isVisible() or self.doc_submenu.isActiveWindow()
        ):
            return
        if self.file_shortcuts_submenu is not None and (
            self.file_shortcuts_submenu.isVisible()
            or self.file_shortcuts_submenu.isActiveWindow()
        ):
            return
        if self.mini_programs_submenu is not None and (
            self.mini_programs_submenu.isVisible()
            or self.mini_programs_submenu.isActiveWindow()
        ):
            return
        active = QApplication.activeWindow()
        if isinstance(
            active,
            (
                QMenu,
                DocumentSubMenu,
                FileShortcutsSubMenu,
                MiniProgramsSubMenu,
                TextRecordsSubMenu,
                TextRecordViewDialog,
                OperationsSubMenu,
                LevelCalcDialog,
                SlopeCalcDialog,
            ),
        ):
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
        self._screen_signal_bound = set()
        self.image_timer = QTimer(self)
        self.image_timer.timeout.connect(self.next_image)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.show_menu)
        self._screen_change_timer = QTimer(self)
        self._screen_change_timer.setSingleShot(True)
        self._screen_change_timer.timeout.connect(self._on_screens_changed)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAcceptDrops(True)

        self.label = QLabel(self)
        self.label.setScaledContents(False)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.label.setAcceptDrops(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        self.apply_window_mode()
        self.load_pet_settings()
        restore_pet_geometry(self.cfg, self)
        self._bind_screen_signals()

    def clamp_to_screen(self):
        """Keep the pet within an available screen area (multi-monitor safe)."""
        clamp_widget_to_screens(self)

    def _bind_screen_signals(self):
        app = QApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._schedule_screen_reclamp)
        for screen in app.screens():
            self._bind_one_screen(screen)

    def _bind_one_screen(self, screen):
        if screen is None:
            return
        key = id(screen)
        if key in self._screen_signal_bound:
            return
        screen.geometryChanged.connect(self._schedule_screen_reclamp)
        screen.availableGeometryChanged.connect(self._schedule_screen_reclamp)
        self._screen_signal_bound.add(key)

    def _on_screen_added(self, screen):
        self._bind_one_screen(screen)
        self._schedule_screen_reclamp()

    def _schedule_screen_reclamp(self, *_args):
        self._screen_change_timer.start(150)

    def _on_screens_changed(self):
        """Re-apply remembered relative position, then clamp onto live screens."""
        restore_pet_geometry(self.cfg, self)
        save_pet_geometry(self.cfg, self, persist=True)

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
            save_pet_geometry(self.cfg, self, persist=True)
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

    def open_shortcut(self, path, sc_type="file"):
        try:
            if sc_type == "folder":
                open_local_path(path)
            else:
                open_shortcut_target(path, sc_type if sc_type in ("file", "url") else None)
        except FileNotFoundError:
            QMessageBox.warning(self, "Path does not exist", f"Not found:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Open failed", str(e))

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime is not None and (mime.hasUrls() or mime.hasText()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime is not None and (mime.hasUrls() or mime.hasText()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime is None:
            event.ignore()
            return
        handled = False
        if mime.hasUrls():
            for qurl in mime.urls():
                local = qurl.toLocalFile()
                if local:
                    if self._prompt_add_local_path(local):
                        handled = True
                else:
                    url_text = qurl.toString().strip()
                    if url_text and self._prompt_add_url(url_text):
                        handled = True
        elif mime.hasText():
            text = mime.text().strip()
            if looks_like_url(text) and self._prompt_add_url(text):
                handled = True
        if handled:
            event.acceptProposedAction()
            if self.menu is not None and self.menu.isVisible():
                self.menu.refresh()
        else:
            event.ignore()

    def _prompt_add_local_path(self, local_path):
        path = Path(local_path)
        if not path.exists():
            QMessageBox.warning(self, "Not found", f"Path does not exist:\n{local_path}")
            return False
        if path.is_dir():
            dialog = ShortcutPromptDialog(
                "Add folder shortcut",
                path.name or str(path),
                str(path),
                kind_label="Folder Path",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            data = dialog.result_data()
            shortcuts = list(self.cfg.get("shortcuts") or [])
            shortcuts.append({
                "name": data["name"],
                "path": data["path"],
                "description": data["description"],
            })
            self.cfg.set(["shortcuts"], shortcuts)
            return True

        dialog = ShortcutPromptDialog(
            "Add file shortcut",
            path.name or str(path),
            str(path),
            kind_label="File Path",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        data = dialog.result_data()
        file_shortcuts = [
            normalize_file_shortcut(sc)
            for sc in (self.cfg.get("file_shortcuts") or [])
            if isinstance(sc, dict)
        ]
        file_shortcuts.append(normalize_file_shortcut({
            "name": data["name"],
            "path": data["path"],
            "description": data["description"],
            "type": "file",
        }))
        self.cfg.set(["file_shortcuts"], file_shortcuts)
        return True

    def _prompt_add_url(self, url_text):
        default_name = url_text
        try:
            parsed = urlparse(url_text)
            default_name = parsed.netloc or parsed.path or url_text
        except Exception:
            pass
        dialog = ShortcutPromptDialog(
            "Add URL shortcut",
            default_name,
            url_text,
            kind_label="URL",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        data = dialog.result_data()
        file_shortcuts = [
            normalize_file_shortcut(sc)
            for sc in (self.cfg.get("file_shortcuts") or [])
            if isinstance(sc, dict)
        ]
        file_shortcuts.append(normalize_file_shortcut({
            "name": data["name"],
            "path": data["path"],
            "description": data["description"],
            "type": "url",
        }))
        self.cfg.set(["file_shortcuts"], file_shortcuts)
        return True

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
