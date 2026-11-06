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
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from PySide6.QtCore import (
    Qt, QTimer, QSize, Signal, QEvent, QLockFile, QUrl, QPoint, QPointF,
    QRect, QRectF,
    QObject, QRunnable, QThreadPool, QElapsedTimer, QEasingCurve,
    QPropertyAnimation, Property,
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QCursor, QIcon, QAction, QMovie,
    QDesktopServices,
    QPainterPath, QLinearGradient, QRadialGradient, QBrush, QPen, QFont,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QDialog, QFormLayout, QTabWidget, QComboBox,
    QSpinBox, QDoubleSpinBox, QTimeEdit, QCheckBox, QMessageBox, QMenu, QStyle,
    QSystemTrayIcon, QPlainTextEdit, QFrame, QRadioButton, QButtonGroup,
    QScrollArea, QSizePolicy, QProgressBar,
    QStackedWidget, QTableWidget, QTableWidgetItem, QAbstractItemView,
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
APP_VERSION = "261106.02"

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
        "title": "Document Record 文檔紀錄",
        # "folder" kept for backward compatibility with older builds.
        "folder": "",
        # Primary list of storage folders (supports more than one).
        "folders": [],
        "sort_by": "mtime",
        "files": {}
    },
    # Text records (title + body). Older configs omit this key.
    "text_records": [],
    # Pomodoro mini-program: last used duration in minutes (running state is not saved).
    "pomodoro": {
        "minutes": 25,
    },
    # Free Station dialog: stored backsight records for auto-fill.
    # Shape: {name, easting, northing, rl}. Optional; older configs omit it.
    "free_station_stations": [],
    # 箱庭島: optional NAS server URL (empty = local JSON only).
    "hakoniwa": {
        "server_url": "",
        "api_key": "",
    },
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
            "Text records appear under Mini programs → Text records in the pet menu. "
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

        self.doc_title_edit.setText(
            self.cfg.get("document_area", "title") or DOCUMENT_RECORD_TITLE_DEFAULT
        )
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
            self.doc_title_edit.text().strip() or DOCUMENT_RECORD_TITLE_DEFAULT,
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

# Layered translucency (composites against the desktop; ornate rings stay solid):
#   calcWindowCenter  — interior behind the content panel (~70% opaque)
#   calcOrnateInner   — gray content panel (~80% opaque)
WINDOW_CENTER_ALPHA = 178  # round(255 * 0.70)
CALC_PANEL_ALPHA = 204  # round(255 * 0.80)

# Dark theme for mini-program dialogs.
# IMPORTANT: calcOrnateOuter / Mid must stay background-transparent — their
# chrome is painted as a border RING only (see OrnateBorderFrame). A full-rect
# QSS fill on those layers used to sit under the translucent panel and made
# the window look fully opaque.
CALC_DIALOG_STYLE = f"""
    QDialog {{
        background-color: transparent;
        color: #e8e8e8;
        font-family: "Microsoft JhengHei", "Segoe UI", sans-serif;
        font-size: 9pt;
    }}
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}
    QWidget#calcRoot {{
        background-color: transparent;
        color: #e8e8e8;
        border: none;
    }}
    QLabel {{ color: #d0d0d0; background-color: transparent; }}
    QLabel#calcSectionTitle {{
        color: #f5e6c8;
        font-weight: bold;
        font-size: 10pt;
        background-color: transparent;
    }}
    QLabel#calcResult {{
        background-color: rgba(26, 46, 26, 210);
        color: #7CFC7C;
        border: 1px solid #2d5a2d;
        border-radius: 4px;
        padding: 4px 8px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 9pt;
        margin-top: 2px;
    }}
    QLineEdit#calcNumeric {{
        background-color: rgba(42, 42, 42, 230);
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 2px 6px;
        min-height: 18px;
        max-height: 22px;
        selection-background-color: #3d5a80;
        selection-color: #ffffff;
    }}
    QLineEdit#calcNumeric:focus {{
        border: 1px solid #c9a84c;
    }}
    QPushButton {{
        background-color: rgba(51, 51, 51, 230);
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px 8px;
    }}
    QPushButton:hover {{ background-color: rgba(68, 68, 68, 240); }}
    QPushButton#calcAction {{
        background-color: rgba(44, 44, 44, 230);
        min-height: 22px;
        max-height: 24px;
        max-width: 120px;
        padding: 2px 10px;
        font-size: 9pt;
    }}
    QLabel#calcFieldCaption {{
        color: #d0d0d0;
        font-size: 9pt;
        padding: 0;
        margin: 0;
        background-color: transparent;
    }}
    QRadioButton {{
        color: #e0e0e0;
        spacing: 6px;
        background-color: transparent;
    }}
    QFrame#calcSection {{
        background-color: rgba(37, 37, 37, {CALC_PANEL_ALPHA});
        border: 1px solid rgba(58, 58, 58, 200);
        border-radius: 4px;
    }}
    QFrame#calcOrnateOuter, QFrame#calcOrnateMid {{
        background-color: transparent;
        border: none;
    }}
    /* Fills for calcWindowCenter / calcOrnateInner are painted in
       TranslucentFillFrame.paintEvent — QSS rgba is unreliable with
       WA_TranslucentBackground (often ignores alpha → identical looks). */
    QFrame#calcWindowCenter, QFrame#calcOrnateInner {{
        background-color: transparent;
        border: none;
    }}
"""


# Ornate frame layout margins (px) — only this band is a window-drag zone.
ORNATE_OUTER_MARGIN = 8
ORNATE_MID_MARGIN = 6


def _point_in_border_band(pos, rect, thickness):
    """True if pos lies in the outer ring of `rect` with the given thickness."""
    if thickness <= 0:
        return False
    x, y = pos.x(), pos.y()
    w, h = rect.width(), rect.height()
    if w <= 0 or h <= 0:
        return False
    return (
        x < thickness
        or y < thickness
        or x >= w - thickness
        or y >= h - thickness
    )


class _FrameBorderDragFilter(QObject):
    """
    Drag the frameless window only when the press lands in the ornate frame
    border band (gilt/wood margin). Presses inside the content rect are ignored.
    """

    def __init__(self, window, grip, border_thickness, parent=None):
        super().__init__(parent)
        self._window = window
        self._grip = grip
        self._border_thickness = int(border_thickness)
        self._drag_offset = None

    def eventFilter(self, obj, event):
        if obj is not self._grip:
            return False
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            pos = event.position().toPoint()
            if not _point_in_border_band(pos, self._grip.rect(), self._border_thickness):
                # Click is on the content side of this frame layer — do not drag.
                return False
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            self._grip.grabMouse()
            return True
        if etype == QEvent.Type.MouseMove:
            if self._drag_offset is not None:
                self._window.move(
                    event.globalPosition().toPoint() - self._drag_offset
                )
                return True
            return False
        if etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
                self._drag_offset = None
                self._grip.releaseMouse()
                return True
            return False
        return False


def enable_frame_border_drag(window, widget, border_thickness):
    """Drag `window` only from the border band of `widget` (keeps filter ref)."""
    filt = _FrameBorderDragFilter(window, widget, border_thickness, window)
    widget.installEventFilter(filt)
    widget.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
    grips = getattr(window, "_drag_grips", None)
    if grips is None:
        grips = []
        window._drag_grips = grips
    grips.append(filt)
    return filt


class OrnateBorderFrame(QFrame):
    """
    Ornate picture-frame layer that paints ONLY a border ring.

    Root cause of “no transparency”: a QSS gradient background on this frame
    filled the entire rect (including under the translucent content panel), so
    the panel composited against opaque frame pixels instead of the desktop.
    """

    def __init__(self, object_name, band_thickness, kind, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._band_thickness = int(band_thickness)
        self._kind = kind  # "gilt" | "wood"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        t = self._band_thickness
        if t <= 0:
            return
        r = self.rect()
        if r.width() <= 2 * t or r.height() <= 2 * t:
            return
        outer = QPainterPath()
        outer.addRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()))
        hole = QPainterPath()
        hole.addRect(
            float(r.x() + t),
            float(r.y() + t),
            float(r.width() - 2 * t),
            float(r.height() - 2 * t),
        )
        ring = outer.subtracted(hole)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._kind == "gilt":
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0.0, QColor(42, 28, 14))
            grad.setColorAt(0.22, QColor(107, 78, 30))
            grad.setColorAt(0.45, QColor(212, 175, 55))
            grad.setColorAt(0.55, QColor(240, 215, 140))
            grad.setColorAt(0.68, QColor(212, 175, 55))
            grad.setColorAt(0.85, QColor(107, 78, 30))
            grad.setColorAt(1.0, QColor(42, 28, 14))
            painter.fillPath(ring, QBrush(grad))
            painter.setPen(QPen(QColor(26, 16, 8), 1))
            painter.drawRect(r.adjusted(0, 0, -1, -1))
            painter.setPen(QPen(QColor(232, 212, 139), 1))
            painter.drawRect(r.adjusted(t - 1, t - 1, -(t), -(t)))
        else:
            grad = QLinearGradient(r.topLeft(), r.bottomLeft())
            grad.setColorAt(0.0, QColor(90, 61, 36))
            grad.setColorAt(0.5, QColor(58, 36, 20))
            grad.setColorAt(1.0, QColor(90, 61, 36))
            painter.fillPath(ring, QBrush(grad))
            painter.setPen(QPen(QColor(26, 18, 8), 1))
            painter.drawRect(r.adjusted(0, 0, -1, -1))
        painter.end()


class TranslucentFillFrame(QFrame):
    """
    Panel that paints an ARGB fill via QPainter (not QSS).

    QSS `background-color: rgba(...)` under WA_TranslucentBackground is
    unreliable: on this X11 path the alpha is often dropped so 60% vs 80%
    look identical; Windows can paint it fully opaque. paintEvent writes a
    real alpha into the ARGB window buffer.
    """

    def __init__(self, object_name, fill_color, parent=None, draw_inset_border=False):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._fill = QColor(fill_color)
        self._draw_inset_border = bool(draw_inset_border)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def set_fill_alpha(self, alpha):
        c = QColor(self._fill)
        c.setAlpha(int(alpha))
        self._fill = c
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self._fill)
        if self._draw_inset_border:
            r = self.rect().adjusted(0, 0, -1, -1)
            painter.setPen(QPen(QColor("#e8d48b"), 1))
            painter.drawLine(r.topLeft(), r.topRight())
            painter.drawLine(r.topLeft(), r.bottomLeft())
            painter.setPen(QPen(QColor("#7a5e18"), 1))
            painter.drawLine(r.topRight(), r.bottomRight())
            painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.end()


def install_ornate_calc_frame(dialog):
    """
    Nested gilt/wood picture-frame chrome inside a mini-program dialog.

    Outer/mid paint border rings only. Window center (~70%) and gray panel
    (~80%) are TranslucentFillFrame layers with real ARGB paint. Only the
    border bands drag the window. Returns innermost content layout.
    """
    shell = QVBoxLayout(dialog)
    shell.setContentsMargins(7, 7, 7, 7)
    shell.setSpacing(0)

    outer = OrnateBorderFrame(
        "calcOrnateOuter", ORNATE_OUTER_MARGIN, "gilt", dialog
    )
    outer_l = QVBoxLayout(outer)
    outer_l.setContentsMargins(
        ORNATE_OUTER_MARGIN,
        ORNATE_OUTER_MARGIN,
        ORNATE_OUTER_MARGIN,
        ORNATE_OUTER_MARGIN,
    )
    outer_l.setSpacing(0)

    mid = OrnateBorderFrame("calcOrnateMid", ORNATE_MID_MARGIN, "wood", outer)
    mid_l = QVBoxLayout(mid)
    mid_l.setContentsMargins(
        ORNATE_MID_MARGIN,
        ORNATE_MID_MARGIN,
        ORNATE_MID_MARGIN,
        ORNATE_MID_MARGIN,
    )
    mid_l.setSpacing(0)

    # ~70% opaque window center (behind the gray content panel).
    center_fill = QColor(28, 28, 28, WINDOW_CENTER_ALPHA)
    center = TranslucentFillFrame("calcWindowCenter", center_fill, mid)
    center_l = QVBoxLayout(center)
    center_l.setContentsMargins(0, 0, 0, 0)
    center_l.setSpacing(0)

    # ~80% opaque gray content panel (QPainter ARGB, not QSS rgba).
    panel_fill = QColor(30, 30, 30, CALC_PANEL_ALPHA)
    inner = TranslucentFillFrame(
        "calcOrnateInner", panel_fill, center, draw_inset_border=True
    )
    # Content must keep a normal arrow cursor (not inherit SizeAll from frame).
    inner.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    inner_l = QVBoxLayout(inner)
    inner_l.setContentsMargins(10, 10, 10, 10)
    inner_l.setSpacing(8)

    center_l.addWidget(inner)
    mid_l.addWidget(center)
    outer_l.addWidget(mid)
    shell.addWidget(outer)
    dialog._calc_ornate_outer = outer
    dialog._calc_ornate_mid = mid
    dialog._calc_window_center = center
    dialog._calc_ornate_inner = inner
    # Drag grips: gilt outer ring + wood mid ring only (hit-tested to the band).
    enable_frame_border_drag(dialog, outer, ORNATE_OUTER_MARGIN)
    enable_frame_border_drag(dialog, mid, ORNATE_MID_MARGIN)
    return inner_l


def make_dialog_title(text):
    """Inner window title label (not a drag handle — content stays clickable)."""
    title = QLabel(text)
    title.setObjectName("calcSectionTitle")
    title.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    return title


def make_draggable_title(dialog_or_text, text=None):
    """
    Build the dialog title label. Title is NOT a drag grip (only the ornate
    frame border moves the window). Accepts make_draggable_title(text) or
    the older make_draggable_title(dialog, text) call shape.
    """
    if text is None:
        return make_dialog_title(dialog_or_text)
    return make_dialog_title(text)


class FramelessCalcDialog(QDialog):
    """
    Shared mini-program shell: frameless (no OS title bar), ornate border-ring
    chrome, ~60% opaque content panel that composites against the desktop.
    Window drag only on the ornate border band.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # Required for child rgba() panels to composite against the desktop
        # (otherwise they blend onto an opaque system/back buffer).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(CALC_DIALOG_STYLE)
        self._drag_grips = []


def parse_calc_number(text):
    """Parse a typed calculator field; raises ValueError on empty/invalid input."""
    raw = (text or "").strip().replace(",", "")
    if not raw or raw in ("-", "+", ".", "-.", "+."):
        raise ValueError("Enter a valid number")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError("Enter a valid number") from exc


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
        raise ValueError("Length (L) must not be 0")
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
            raise ValueError("1 in X: X must not be 0")
        one_in_x = value
        fall_pct = 100.0 / one_in_x
        angle_deg = math.degrees(math.atan(1.0 / one_in_x))
        return fall_pct, one_in_x, angle_deg
    if known_kind == "angle":
        angle_deg = value
        if abs(angle_deg) % 180 == 90:
            raise ValueError("Angle must not be ±90°")
        fall_pct = 100.0 * math.tan(math.radians(angle_deg))
        if fall_pct == 0:
            return 0.0, float("inf"), angle_deg
        one_in_x = 100.0 / fall_pct
        return fall_pct, one_in_x, angle_deg
    raise ValueError(f"Unknown slope unit kind: {known_kind}")


def level_at_target(high_level, low_level, full_length, target_distance):
    """
    Level calc (linear interpolate along a grade line).
    Assumes high level at chainage 0 and low level at full_length:
        level = high - (high - low) * (target / full)
    Extrapolation is allowed when target is outside [0, full].
    """
    if full_length <= 0:
        raise ValueError("Full length must be greater than 0")
    return high_level - (high_level - low_level) * (target_distance / full_length)


# ---------------------------------------------------------------------------
# Alignment(1) — chainage ↔ E/N/level along an imported alignment polyline
# ---------------------------------------------------------------------------
# Points are (chainage, easting, northing, level), sorted by chainage.
# Box 1: linear interpolate E/N/level at a query chainage (extrapolate ends).
# Box 2: project observed E/N onto the plan polyline; report design chainage
# plus ΔE / ΔN / Δlevel vs that interpolated design point.
_ALIGN_CHAINAGE_ALIASES = frozenset({"chainage", "chanage", "ch", "chain"})
_ALIGN_EASTING_ALIASES = frozenset({"easting", "east", "e"})
_ALIGN_NORTHING_ALIASES = frozenset({"northing", "north", "n"})
_ALIGN_LEVEL_ALIASES = frozenset({"level", "lv", "rl", "elevation", "elev"})


def _align_header_key(text):
    raw = (text or "").strip().lower().replace(" ", "").replace("_", "")
    if raw in _ALIGN_CHAINAGE_ALIASES:
        return "chainage"
    if raw in _ALIGN_EASTING_ALIASES:
        return "easting"
    if raw in _ALIGN_NORTHING_ALIASES:
        return "northing"
    if raw in _ALIGN_LEVEL_ALIASES:
        return "level"
    return None


def _align_cell_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number:  # NaN
            return None
        return number
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_alignment_sheet_rows(path):
    """Yield row tuples (list of cell values) from the first usable sheet."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read .xlsx/.xlsm "
                "(pip install openpyxl)"
            ) from exc
        wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
        try:
            sheet = wb[wb.sheetnames[0]]
            for row in sheet.iter_rows(values_only=True):
                yield list(row)
        finally:
            wb.close()
        return
    if suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise ImportError(
                "xlrd is required to read .xls (pip install xlrd)"
            ) from exc
        wb = xlrd.open_workbook(path)
        sheet = wb.sheet_by_index(0)
        for r in range(sheet.nrows):
            yield [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        return
    raise ValueError(
        f"Unsupported file type '{suffix or path.name}'. "
        "Use .xlsm, .xlsx, or .xls"
    )


def parse_alignment_workbook(path):
    """
    Import alignment points from Excel.

    Expects a header row with chainage (or misspelled chanage), Easting,
    Northing, level. Returns a list of (chainage, easting, northing, level)
    sorted by chainage. Raises ValueError on missing columns / no data.
    """
    rows = list(_load_alignment_sheet_rows(path))
    header_idx = None
    colmap = {}
    for idx, row in enumerate(rows):
        mapping = {}
        for col, cell in enumerate(row or ()):
            key = _align_header_key(cell)
            if key and key not in mapping:
                mapping[key] = col
        if all(k in mapping for k in ("chainage", "easting", "northing", "level")):
            header_idx = idx
            colmap = mapping
            break
    if header_idx is None:
        raise ValueError(
            "Header row not found. Need columns: chainage (or chanage), "
            "Easting, Northing, level"
        )

    points = []
    for row in rows[header_idx + 1 :]:
        if not row:
            continue
        ch = _align_cell_float(
            row[colmap["chainage"]] if colmap["chainage"] < len(row) else None
        )
        east = _align_cell_float(
            row[colmap["easting"]] if colmap["easting"] < len(row) else None
        )
        north = _align_cell_float(
            row[colmap["northing"]] if colmap["northing"] < len(row) else None
        )
        level = _align_cell_float(
            row[colmap["level"]] if colmap["level"] < len(row) else None
        )
        if ch is None and east is None and north is None and level is None:
            continue
        if None in (ch, east, north, level):
            continue
        points.append((ch, east, north, level))

    if len(points) < 2:
        raise ValueError("Need at least 2 alignment points with chainage/E/N/level")

    points.sort(key=lambda p: p[0])
    # Drop exact duplicate chainages (keep first).
    deduped = [points[0]]
    for pt in points[1:]:
        if abs(pt[0] - deduped[-1][0]) < 1e-12:
            continue
        deduped.append(pt)
    if len(deduped) < 2:
        raise ValueError("Need at least 2 distinct chainage points")
    return deduped


def _lerp(a, b, t):
    return a + (b - a) * t


def alignment_at_chainage(points, chainage):
    """
    Linear interpolate (chainage→E/N/level) along sorted alignment points.

    Returns (easting, northing, level, note) where note is '' | 'exact' |
    'extrapolated'. Extrapolates beyond the first/last chainage using the
    end segment slope.
    """
    if not points or len(points) < 2:
        raise ValueError("Import an alignment first (need ≥2 points)")
    ch = float(chainage)
    # Exact vertex hit.
    for pt in points:
        if abs(pt[0] - ch) < 1e-9:
            return pt[1], pt[2], pt[3], "exact"

    # Before first / after last → extrapolate with end segment.
    if ch < points[0][0]:
        a, b = points[0], points[1]
        span = b[0] - a[0]
        if abs(span) < 1e-15:
            raise ValueError("Degenerate chainage span")
        t = (ch - a[0]) / span
        return (
            _lerp(a[1], b[1], t),
            _lerp(a[2], b[2], t),
            _lerp(a[3], b[3], t),
            "extrapolated",
        )
    if ch > points[-1][0]:
        a, b = points[-2], points[-1]
        span = b[0] - a[0]
        if abs(span) < 1e-15:
            raise ValueError("Degenerate chainage span")
        t = (ch - a[0]) / span
        return (
            _lerp(a[1], b[1], t),
            _lerp(a[2], b[2], t),
            _lerp(a[3], b[3], t),
            "extrapolated",
        )

    # Interior segment.
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a[0] <= ch <= b[0]:
            span = b[0] - a[0]
            if abs(span) < 1e-15:
                return a[1], a[2], a[3], "exact"
            t = (ch - a[0]) / span
            return (
                _lerp(a[1], b[1], t),
                _lerp(a[2], b[2], t),
                _lerp(a[3], b[3], t),
                "",
            )
    raise ValueError("Chainage not on alignment")


def _project_point_to_segment(px, py, ax, ay, bx, by):
    """Project P onto segment AB. Returns (qx, qy, t in [0,1], dist2)."""
    abx, aby = bx - ax, by - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-24:
        dx, dy = px - ax, py - ay
        return ax, ay, 0.0, dx * dx + dy * dy
    t = ((px - ax) * abx + (py - ay) * aby) / ab2
    t_clamp = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    qx = ax + abx * t_clamp
    qy = ay + aby * t_clamp
    dx, dy = px - qx, py - qy
    return qx, qy, t_clamp, dx * dx + dy * dy


def alignment_deviation(points, easting, northing, level):
    """
    Nearest design point on the plan polyline to (easting, northing).

    Returns dict:
      chainage, easting, northing, level (design),
      d_easting, d_northing, d_level (observed − design),
      offset_plan (plan distance to design point).
    Level on the design point is interpolated with the same segment
    parameter t used for E/N.
    """
    if not points or len(points) < 2:
        raise ValueError("Import an alignment first (need ≥2 points)")
    e = float(easting)
    n = float(northing)
    lv = float(level)

    best = None
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        qx, qy, t, dist2 = _project_point_to_segment(
            e, n, a[1], a[2], b[1], b[2]
        )
        ch = _lerp(a[0], b[0], t)
        qlv = _lerp(a[3], b[3], t)
        cand = (dist2, ch, qx, qy, qlv)
        if best is None or cand[0] < best[0]:
            best = cand

    # Also consider exact vertices (covers zero-length edge cases).
    for pt in points:
        dx, dy = e - pt[1], n - pt[2]
        dist2 = dx * dx + dy * dy
        cand = (dist2, pt[0], pt[1], pt[2], pt[3])
        if best is None or cand[0] < best[0]:
            best = cand

    dist2, ch, de, dn, dlv = best
    return {
        "chainage": ch,
        "easting": de,
        "northing": dn,
        "level": dlv,
        "d_easting": e - de,
        "d_northing": n - dn,
        "d_level": lv - dlv,
        "offset_plan": math.sqrt(max(0.0, dist2)),
    }


# ---------------------------------------------------------------------------
# Free Station (resection) math — ported 1:1 from Free_Station_FAI.xls
#
# The workbook's "Free Station" sheet drives the VBA functions below
# (Simple_Utilities_Suite_2010.bas, formulas on sheet rows 20/24/28/33-38).
# Angles are typed as surveying DD.MMSS text (e.g. 330.1402 = 330°14'01.8").
# Vertical angles follow the total-station ZENITH convention (90° = horizon):
# horizontal distance = slope × sin(zenith), vertical delta = slope × cos(zenith).
#
# Triangle (station S, backsights BS1/BS2), sheet pair "From BS1 → To BS2":
#   BRG1 = bearing BS2→BS1, HD1 = |BS2→BS1|            (from control coords)
#   HD2  = SD_to_HD(VA_to, SD_to)                      (observed to "To" BS)
#   RAA  = observed angle at S between BS1 and BS2 bearings
#   RAB  = asin(sin(RAA) × HD2 / HD1)                  (sine rule, angle at BS1)
#   BRG2 = BRG1 − (180 − RAA − RAB)                    (bearing BS2→S)
#   E/N  = HD2·sin(BRG2)+E2, HD2·cos(BRG2)+N2          (polar from BS2)
#   RL   = RL(To) − SD·cos(zenith) + prism_ht − inst_ht
# The mirror branch flips RAB = 180 − RAB (other sine-rule solution) when
# |RAB| > |RAA|; the sheet keeps whichever branch passes the distance check.
# ---------------------------------------------------------------------------
def _survey_round(value, decimals):
    # VBA Format(x, "0.0000")-style rounding used inside DEG/DMS.
    return round(value, decimals)


# ---------------------------------------------------------------------------
# Free Station Excel import (Free Station sheet → dialog fields)
#
# Annotated / 4-BS layout (IMPORT map): standing D12, inst. ht H12; BS1–3
# Name / E / N / RL at D/E/F/G rows 13–15; BS4 Name/E/N/RL at D/E/F/G 17;
# face obs C/D/E/F rows 25–32 (BS1..BS4).
# Classic Free_Station_FAI.xls V1.00: standing D10, inst. ht H10; Name /
# E/N/RL at D/E/F/G rows 14–17 (row 13 is the Station/E/N/RL header);
# BS1–3 faces at rows 20–21 / 24–25 / 28–29. Auto-detected.
# Readers: openpyxl for .xlsx/.xlsm, xlrd for .xls (see requirements.txt).
# ---------------------------------------------------------------------------
_FS_SHEET_NAMES = ("free station", "freestation")
# Template / UI hint strings that must never land as imported field values.
_FS_PLACEHOLDER_TEXTS = frozenset(
    {
        "bs name",
        "dd.mmss",
        "distance",
    }
)


def _excel_cell_to_text(value):
    """Normalize an Excel cell to dialog text; blank / non-scalar → ''."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        if number != number:  # NaN
            return ""
        if abs(number - round(number)) < 1e-12 and abs(number) < 1e12:
            return str(int(round(number)))
        text = f"{number:.10f}".rstrip("0").rstrip(".")
        return text
    return str(value).strip()


def _fs_import_field_text(value):
    """Cell → dialog text; empty Excel / UI placeholder strings → ''."""
    text = _excel_cell_to_text(value)
    if not text:
        return ""
    if text.casefold() in _FS_PLACEHOLDER_TEXTS:
        return ""
    return text


def _excel_a1(col_letters, row_1based):
    col = 0
    for ch in col_letters.upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return row_1based - 1, col - 1


def _load_free_station_sheet_cells(path):
    """
    Return (sheet_title, get_cell) where get_cell('D', 12) → raw value.
    Raises ValueError / ImportError with a user-facing message.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read .xlsx/.xlsm "
                "(pip install openpyxl)"
            ) from exc
        # Avoid read_only: some .xlsx/.xlsm files yield empty cells there.
        wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
        try:
            sheet = _pick_free_station_worksheet(
                list(wb.sheetnames), lambda name: wb[name]
            )
            title = sheet.title
            cache = {}
            for row in sheet.iter_rows(
                min_row=1, max_row=40, min_col=1, max_col=12
            ):
                for cell in row:
                    if cell.value is not None and cell.value != "":
                        cache[(cell.row, cell.column)] = cell.value
        finally:
            wb.close()

        def get_cell(col_letters, row_1based):
            r, c = _excel_a1(col_letters, row_1based)
            return cache.get((r + 1, c + 1))

        return title, get_cell

    if suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise ImportError(
                "xlrd is required to read .xls (pip install xlrd)"
            ) from exc
        wb = xlrd.open_workbook(path)
        sheet = _pick_free_station_worksheet(
            wb.sheet_names(), lambda name: wb.sheet_by_name(name)
        )
        title = sheet.name

        def get_cell(col_letters, row_1based):
            r, c = _excel_a1(col_letters, row_1based)
            if r < 0 or c < 0 or r >= sheet.nrows or c >= sheet.ncols:
                return None
            return sheet.cell_value(r, c)

        return title, get_cell

    raise ValueError(
        f"Unsupported file type '{suffix or path.name}'. "
        "Use .xlsm, .xlsx, or .xls"
    )


def _pick_free_station_worksheet(names, getter):
    for name in names:
        if (name or "").strip().lower() in _FS_SHEET_NAMES:
            return getter(name)
    for name in names:
        lowered = (name or "").strip().lower()
        if "free" in lowered and "station" in lowered:
            return getter(name)
    if not names:
        raise ValueError("Workbook has no sheets")
    return getter(names[0])


def parse_free_station_workbook(path):
    """
    Read Free Station sheet fields for IMPORT.

    Returns dict:
      station_name, inst_height,
      backsights: list of 4 dicts {name, easting, northing, rl, f1, f2}
      where f1/f2 are dicts {bearing, va, sd, sh} (strings, possibly '').
    """
    _title, get = _load_free_station_sheet_cells(path)

    def text(col, row):
        return _fs_import_field_text(get(col, row))

    # Layout detect: annotated map uses D12; classic V1.00 uses D10 + "BS1 - FL" @ B20.
    # Prefer annotated whenever D12 is filled (even if classic labels linger).
    d12 = text("D", 12)
    d10 = text("D", 10)
    b20 = text("B", 20).upper()
    if d12:
        classic = False
    elif d10 or b20.startswith("BS1"):
        classic = True
    else:
        classic = False

    if classic:
        station_name = d10
        inst_height = text("H", 10)
        # Classic obs rows (FL/FR); BS4 unused in V1.00 templates.
        obs_rows = [(20, 21), (24, 25), (28, 29), (None, None)]
        # Row 13 is the Station/Easting/Northing/RL header on V1.00 sheets.
        name_rows = (14, 15, 16, 17)
    else:
        station_name = d12
        inst_height = text("H", 12)
        obs_rows = [(25, 26), (27, 28), (29, 30), (31, 32)]
        # Annotated map: BS1–3 Name at D13–D15; BS4 keeps prior D17 mapping.
        name_rows = (13, 14, 15, 17)

    backsights = []
    for idx in range(4):
        row = name_rows[idx]  # Name at D{row}; E/F/G same row for E/N/RL
        name = text("D", row)
        easting = text("E", row)
        northing = text("F", row)
        rl = text("G", row)
        f1_row, f2_row = obs_rows[idx]

        def face(obs_row):
            if obs_row is None:
                return {"bearing": "", "va": "", "sd": "", "sh": ""}
            return {
                "bearing": text("C", obs_row),
                "va": text("D", obs_row),
                "sd": text("E", obs_row),
                "sh": text("F", obs_row),
            }

        # Requirement: only keep face measurements when Name is non-empty.
        if name:
            f1, f2 = face(f1_row), face(f2_row)
        else:
            empty = {"bearing": "", "va": "", "sd": "", "sh": ""}
            f1, f2 = empty, empty
        backsights.append(
            {
                "name": name,
                "easting": easting if name else "",
                "northing": northing if name else "",
                "rl": rl if name else "",
                "f1": f1,
                "f2": f2,
            }
        )

    return {
        "station_name": station_name,
        "inst_height": inst_height,
        "backsights": backsights,
        "layout": "classic" if classic else "annotated",
    }


def survey_deg(ddmmss):
    """VBA DEG(): DD.MMSS number → decimal degrees."""
    if ddmmss == 0:
        return 0.0
    b0 = abs(ddmmss)
    dd = math.floor(b0)
    mm = _survey_round((b0 - math.floor(b0)) * 100, 4)
    ss = _survey_round(mm - math.floor(mm), 4)
    return survey_test_deg(dd + math.floor(mm) / 60 + ss / 36) * abs(ddmmss) / ddmmss


def survey_dms(degrees):
    """VBA DMS(): decimal degrees → DD.MMSS number."""
    if degrees == 0:
        return 0.0
    b0 = abs(degrees)
    dd = math.floor(b0)
    mm = math.floor((b0 - dd) * 60)
    ss = _survey_round(((b0 - dd) * 60 - mm) * 60, 2)
    if ss >= 60:
        ss -= 60
        mm += 1
    if mm >= 60:
        mm -= 60
        dd += 1
    return survey_test_dms(dd + mm / 100 + ss / 10000) * abs(degrees) / degrees


def survey_test_dms(value):
    # Wrap at exactly ±360 as well (> alone left 360 literal → bad averages).
    if abs(value) >= 360:
        value = (abs(value) - math.floor(abs(value) / 360) * 360) * abs(value) / value
    if value < 0:
        value = survey_dms(survey_deg(value) + 360)
    return value


def survey_test_deg(value):
    """VBA TESTDEG(): normalize decimal degrees into [0, 360).

    Must wrap **exactly 360 → 0** (use >= 360, not > 360). Otherwise
    mean_bearing_faces(0, 180) does AVERAGE(0, 360) = 180 instead of 0.
    """
    if abs(value) >= 360:
        value = (abs(value) - math.floor(abs(value) / 360) * 360) * abs(value) / value
    if value < 0:
        value += 360
    return value


def _survey_sin(deg):
    return math.sin(deg * math.pi / 180)


def _survey_cos(deg):
    return math.cos(deg * math.pi / 180)


def _survey_asn(x):
    d = math.sqrt(-x * x + 1)
    if d == 0:
        return x * 90
    return math.atan(x / d) * 180 / math.pi


def _survey_acs(x):
    d = math.sqrt(-x * x + 1)
    if d == 0:
        return (1 - x) * 180 / 2
    return (math.atan(-x / d) + 2 * math.atan(1)) * 180 / math.pi


def survey_polar(se, sn, e, n, kind):
    """VBA Polar(): kind 'D' → horizontal distance, 'B' → bearing (DD.MMSS)."""
    de = e - se
    dn = n - sn
    if kind == "D":
        return math.sqrt(de * de + dn * dn)
    if kind == "B":
        if de >= 0:
            return survey_dms(_survey_acs(dn / math.sqrt(de * de + dn * dn)))
        return survey_dms(360 - _survey_acs(dn / math.sqrt(de * de + dn * dn)))
    raise ValueError(f"Unknown polar kind: {kind}")


def survey_sd_to_hd(sd, zenith_ddmmss):
    """VBA SDtoHD(): slope distance → horizontal distance (zenith angle)."""
    return _survey_sin(survey_deg(zenith_ddmmss)) * sd


def free_station_branch(e1, n1, e2, n2, rl2, brg1, brg2, va2, sd2, sh2, hi, mirror):
    """
    One sine-rule branch of the workbook's FreeStation / FreeStation_Mirror.

    (e1, n1) = "From" backsight control coords (direction only);
    (e2, n2, rl2) = "To" backsight control coords + reduced level;
    (brg1, brg2) = observed mean bearings to From / To (DD.MMSS);
    (va2, sd2, sh2) = observed zenith angle, slope distance, prism height to To;
    hi = instrument height at the free station. Returns (E, N, RL) or None
    when the branch is geometrically invalid (mirror condition not met).
    """
    brg1_deg = survey_deg(survey_polar(e2, n2, e1, n1, "B"))
    hd1 = survey_polar(e2, n2, e1, n1, "D")
    hd2 = _survey_sin(survey_deg(va2)) * sd2
    if hd2 <= 0:
        raise ValueError("Slope distance must give a positive horizontal distance")
    raa = survey_test_deg(survey_deg(brg2) - survey_deg(brg1))
    rab = _survey_asn(_survey_sin(raa) * hd2 / hd1)
    if mirror:
        # VBA FreeStation_Mirror: dead BRG_A line omitted; mirror branch is
        # valid only when |RAB| > |RAA|, then RAB is flipped to 180 − RAB.
        if not 180 - abs(_survey_asn(_survey_sin(rab))) + abs(_survey_asn(_survey_sin(raa))) < 180:
            return None
        rab = 180 - rab
    brg_out = brg1_deg - (180 - raa - rab)
    easting = hd2 * _survey_sin(brg_out) + e2
    northing = hd2 * _survey_cos(brg_out) + n2
    rl = rl2 - _survey_cos(survey_deg(va2)) * sd2 + sh2 - hi
    return easting, northing, rl


def mean_bearing_faces(brg_f1, brg_f2):
    """
    Sheet "Mean B/S" bearing (I20): DMS(AVERAGE(DEG(F1), TESTDEG(DEG(F2)+180)))
    — face-right bearing flipped 180° before averaging with face-left.
    Single face falls back to that face alone (F2 flipped like the sheet).
    """
    if brg_f1 is not None and brg_f2 is not None:
        return survey_dms(
            (survey_deg(brg_f1) + survey_test_deg(survey_deg(brg_f2) + 180)) / 2
        )
    if brg_f1 is not None:
        return brg_f1
    if brg_f2 is not None:
        # Sheet: DMS(TESTDEG(DEG(F2)+180)) — keep DD.MMSS form for downstream.
        return survey_dms(survey_test_deg(survey_deg(brg_f2) + 180))
    return None


def mean_va_faces(va_f1, va_f2):
    """
    Sheet "Mean B/S" vertical angle (J20):
    DMS((360 − (DEG(F1) + DEG(F2))) / 2 + DEG(F1)); F2 alone →
    DMS(TESTDEG(360 − DEG(F2))). Zenith-angle convention.
    """
    if va_f1 is not None and va_f2 is not None:
        return survey_dms((360 - (survey_deg(va_f1) + survey_deg(va_f2))) / 2 + survey_deg(va_f1))
    if va_f1 is not None:
        return va_f1
    if va_f2 is not None:
        return survey_dms(survey_test_deg(360 - survey_deg(va_f2)))
    return None


def mean_faces(a_f1, a_f2):
    """Sheet AVERAGE(E20:E21) — plain mean of the faces that are present."""
    if a_f1 is not None and a_f2 is not None:
        return (a_f1 + a_f2) / 2
    if a_f1 is not None:
        return a_f1
    if a_f2 is not None:
        return a_f2
    return None


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
# ---------------------------------------------------------------------------
# Crumble Down — tilt, fall, fade, then reassemble from above (theme palette)
# ---------------------------------------------------------------------------
# 「崩落（Crumble Down）」: each glyph tilts, then falls with gravity + spin +
# fade; after a beat they drop back in from above to reassemble (~3.4s).
DOCUMENT_RECORD_TITLE_DEFAULT = "Document Record 文檔紀錄"
CRUMBLE_TEXT = QColor(255, 255, 255)
# Soft glow matches Folder Shortcuts／Float Drift (sky halo).
TITLE_GLOW = QColor(135, 206, 250, 100)
TITLE_GLOW_SOFT = QColor(176, 224, 255, 55)
CRUMBLE_GLOW = TITLE_GLOW
CRUMBLE_CYCLE_S = 3.4
CRUMBLE_PAD_X = 6.0
CRUMBLE_PAD_Y = 6.0
CRUMBLE_FALL_ROOM = 36.0   # px below baseline while crumbling
CRUMBLE_DROP_ROOM = 28.0   # px above baseline while reassembling


def draw_title_soft_glow(painter: QPainter, ch: str, advance: float, alpha: float = 1.0) -> None:
    """Folder-Shortcuts-style sky soft glow under a glyph (origin at baseline)."""
    a = max(0.0, min(1.0, float(alpha)))
    if a < 0.02:
        return
    for radius, base in (
        (2.6, TITLE_GLOW_SOFT),
        (1.4, TITLE_GLOW),
    ):
        col = QColor(base)
        col.setAlpha(max(0, min(255, int(base.alpha() * a))))
        painter.setPen(col)
        for ox, oy in (
            (-radius, 0.0),
            (radius, 0.0),
            (0.0, -radius),
            (0.0, radius),
            (-radius * 0.7, -radius * 0.7),
            (radius * 0.7, radius * 0.7),
        ):
            painter.drawText(QPointF(-advance * 0.5 + ox, oy), ch)


class SoftGlowTitleLabel(QWidget):
    """Static bold title with Folder-Shortcuts soft sky glow (no motion)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text or ""
        self._chars = list(self._text)
        font = QFont(self.font())
        font.setFamily("Microsoft JhengHei")
        font.setPointSize(9)
        font.setBold(True)
        self._font = font
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._recompute_size()

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text or ""
        self._chars = list(self._text)
        self._recompute_size()
        self.update()

    def text(self) -> str:
        return self._text

    def _recompute_size(self) -> None:
        fm = QFontMetrics(self._font)
        width = sum(fm.horizontalAdvance(ch) for ch in self._chars)
        self.setMinimumHeight(int(fm.height() + 10))
        self.setMinimumWidth(int(width + 12))
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        return QSize(self.minimumWidth(), self.minimumHeight())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        x = 6.0
        base_y = 5.0 + fm.ascent()
        for ch in self._chars:
            advance = float(fm.horizontalAdvance(ch))
            if ch == " ":
                x += advance
                continue
            painter.save()
            painter.translate(x + advance * 0.5, base_y)
            draw_title_soft_glow(painter, ch, advance, 1.0)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QPointF(-advance * 0.5, 0.0), ch)
            painter.restore()
            x += advance
        painter.end()


class CrumbleDownLabel(QWidget):
    """Title label: per-character Crumble Down → reassemble loop."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        font = QFont(self.font())
        font.setFamily("Microsoft JhengHei")
        font.setPointSize(9)
        font.setBold(True)
        self._font = font

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)

        self._chars: list[str] = []
        self._params: list[dict] = []
        self.setText(text or DOCUMENT_RECORD_TITLE_DEFAULT)

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text or DOCUMENT_RECORD_TITLE_DEFAULT
        self._chars = list(self._text)
        self._params = []
        for i, _ch in enumerate(self._chars):
            # Alternate lean direction; stagger fall / reassemble starts.
            sign = 1.0 if (i % 2 == 0) else -1.0
            self._params.append(
                {
                    "tilt0": sign * (8.0 + (i % 4) * 3.5),
                    "spin": sign * (55.0 + (i % 5) * 12.0),
                    "drift": sign * (4.0 + (i % 3) * 2.5),
                    "fall_t0": 0.14 + i * 0.065,
                    "fall_dur": 0.85 + (i % 3) * 0.04,
                    "reass_t0": 1.88 + i * 0.055,
                    "reass_dur": 0.70 + (i % 3) * 0.03,
                    "g": 62.0 + (i % 4) * 6.0,  # fall distance scale
                }
            )
        self._recompute_size()
        self.update()

    def text(self) -> str:
        return self._text

    def _recompute_size(self) -> None:
        fm = QFontMetrics(self._font)
        width = sum(fm.horizontalAdvance(ch) for ch in self._chars)
        height = (
            fm.height()
            + CRUMBLE_PAD_Y * 2
            + CRUMBLE_FALL_ROOM * 0.35
            + CRUMBLE_DROP_ROOM * 0.25
            + 4
        )
        self.setMinimumHeight(int(height))
        self.setMinimumWidth(int(width + CRUMBLE_PAD_X * 2 + 8))
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        return QSize(self.minimumWidth(), self.minimumHeight())

    def showEvent(self, event) -> None:  # noqa: N802
        if not self._elapsed.isValid():
            self._elapsed.start()
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _state_for(self, p: dict, t: float):
        """Return (dx, dy, rot_deg, alpha) for one glyph at cycle time t."""
        fall_t0 = p["fall_t0"]
        fall_dur = p["fall_dur"]
        reass_t0 = p["reass_t0"]
        reass_dur = p["reass_dur"]
        pre_tilt_start = max(0.0, fall_t0 - 0.22)

        if t < pre_tilt_start:
            return 0.0, 0.0, 0.0, 1.0

        if t < fall_t0:
            # Wind-up tilt before the drop.
            u = (t - pre_tilt_start) / max(1e-6, fall_t0 - pre_tilt_start)
            return 0.0, 0.0, p["tilt0"] * u, 1.0

        if t < fall_t0 + fall_dur:
            # Gravity fall + spin + fade.
            u = (t - fall_t0) / fall_dur  # 0..1
            u2 = u * u
            dy = p["g"] * u2
            dx = p["drift"] * u
            rot = p["tilt0"] + p["spin"] * u
            alpha = max(0.0, 1.0 - u2 * 1.05)
            return dx, dy, rot, alpha

        if t < reass_t0:
            # Off-stage between crumble and reassemble.
            return 0.0, p["g"], p["tilt0"] + p["spin"], 0.0

        if t < reass_t0 + reass_dur:
            # Drop in from above → ease into rest.
            u = (t - reass_t0) / reass_dur  # 0..1
            ease = 1.0 - (1.0 - u) ** 3  # ease-out cubic
            remain = 1.0 - ease
            dy = -CRUMBLE_DROP_ROOM * 1.55 * remain
            dx = p["drift"] * 0.35 * remain
            rot = p["spin"] * 0.35 * remain
            alpha = min(1.0, u * 1.6)
            return dx, dy, rot, alpha

        return 0.0, 0.0, 0.0, 1.0

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        t_sec = (self._elapsed.elapsed() / 1000.0) if self._elapsed.isValid() else 0.0
        t_local = t_sec % CRUMBLE_CYCLE_S

        x = CRUMBLE_PAD_X
        base_y = CRUMBLE_PAD_Y + CRUMBLE_DROP_ROOM * 0.35 + fm.ascent()

        for ch, p in zip(self._chars, self._params):
            advance = float(fm.horizontalAdvance(ch))
            if ch == " ":
                x += advance
                continue

            dx, dy, rot, alpha = self._state_for(p, t_local)
            if alpha < 0.02:
                x += advance
                continue

            cx = x + advance * 0.5 + dx
            cy = base_y + dy

            painter.save()
            painter.translate(cx, cy)
            painter.rotate(rot)

            draw_title_soft_glow(painter, ch, advance, alpha)

            col = QColor(CRUMBLE_TEXT)
            col.setAlpha(int(255 * alpha))
            painter.setPen(col)
            painter.drawText(QPointF(-advance * 0.5, 0.0), ch)
            painter.restore()

            x += advance

        painter.end()


# ---------------------------------------------------------------------------
# Bokeh Lights — soft floating orbs for Document Record（文檔紀錄）
# ---------------------------------------------------------------------------
# 「散景光點（Bokeh Lights）」: soft radial discs float upward (~7–14s),
# slight L/R drift, fade in then out. Theme steel-blue / sky / soft gilt.
BOKEH_COUNT = 14
BOKEH_COLORS = (
    QColor(232, 242, 248, 90),    # light sky
    QColor(176, 224, 255, 75),    # soft sky
    QColor(135, 206, 250, 70),    # menu border sky
    QColor(255, 255, 255, 55),    # white mist
    QColor(232, 212, 139, 50),    # existing gilt warm (#e8d48b)
    QColor(201, 168, 76, 45),     # existing gilt (#c9a84c)
)


class BokehLightsCanvas(QWidget):
    """Dreamy soft-circle lights drifting upward behind document UI."""

    def __init__(self, parent=None, *, count: int = BOKEH_COUNT):
        super().__init__(parent)
        self._count = max(10, int(count))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._lights: list[dict] = []
        self._seeded = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps — soft, not frantic
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _spawn(self, w: float, h: float, *, fresh: bool = False) -> dict:
        # Life span 7–14s; progress 0→1 over that window.
        life = random.uniform(7.0, 14.0)
        radius = random.uniform(10.0, 36.0)
        return {
            "x": random.uniform(radius, max(radius + 1.0, w - radius)),
            # Start near bottom (or slightly below) when fresh; else scatter.
            "y": (
                h + random.uniform(4.0, 40.0)
                if fresh
                else random.uniform(0.0, h)
            ),
            "r": radius,
            "life": life,
            "age": 0.0 if fresh else random.uniform(0.0, life * 0.85),
            "drift_amp": random.uniform(6.0, 22.0),
            "drift_freq": random.uniform(0.08, 0.22),
            "drift_phase": random.uniform(0.0, 2.0 * math.pi),
            "base_alpha": random.uniform(0.35, 1.0),
            "color": random.choice(BOKEH_COLORS),
            # Vertical travel covers most of the panel height over life.
            "rise": h + radius * 2.0 + random.uniform(10.0, 40.0),
            "y0": 0.0,  # set on spawn
        }

    def _ensure(self, w: float, h: float) -> None:
        if self._seeded and self._lights:
            return
        self._lights = []
        for _ in range(self._count):
            light = self._spawn(w, h, fresh=False)
            # Back-compute start so current y matches age progress.
            u = light["age"] / light["life"]
            light["y0"] = light["y"] + light["rise"] * u
            self._lights.append(light)
        self._seeded = True

    def _respawn(self, light: dict, w: float, h: float) -> None:
        fresh = self._spawn(w, h, fresh=True)
        fresh["y0"] = fresh["y"]
        light.update(fresh)

    def _tick(self) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        self._ensure(w, h)
        dt = 0.033
        for light in self._lights:
            light["age"] += dt
            u = light["age"] / light["life"]  # 0..1+
            if u >= 1.0 or light["y"] < -light["r"] - 8.0:
                self._respawn(light, w, h)
                continue
            # Ease upward from y0.
            light["y"] = light["y0"] - light["rise"] * u
            light["x"] = light["x"] + (
                light["drift_amp"]
                * 0.02
                * math.sin(
                    light["age"] * light["drift_freq"] * 2.0 * math.pi
                    + light["drift_phase"]
                )
            )
            # Keep gently inside horizontally.
            if light["x"] < -light["r"]:
                light["x"] = w + light["r"] * 0.2
            elif light["x"] > w + light["r"]:
                light["x"] = -light["r"] * 0.2
        self.update()

    @staticmethod
    def _fade(u: float) -> float:
        """Fade in early, hold, fade out near the end (and near top)."""
        if u < 0.0:
            return 0.0
        if u < 0.12:
            return u / 0.12
        if u > 0.78:
            return max(0.0, (1.0 - u) / 0.22)
        return 1.0

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        self._ensure(w, h)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        for light in self._lights:
            u = light["age"] / light["life"]
            fade = self._fade(u) * light["base_alpha"]
            if fade < 0.02:
                continue
            r = light["r"]
            # Soft “blur”: radial gradient disc (CSS bokeh stand-in).
            grad = QRadialGradient(QPointF(light["x"], light["y"]), r)
            core = QColor(light["color"])
            mid = QColor(light["color"])
            edge = QColor(light["color"])
            core.setAlpha(int(core.alpha() * fade))
            mid.setAlpha(int(mid.alpha() * fade * 0.45))
            edge.setAlpha(0)
            grad.setColorAt(0.0, core)
            grad.setColorAt(0.45, mid)
            grad.setColorAt(1.0, edge)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(light["x"], light["y"]), r, r)

        painter.end()


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

        # Layering top→bottom: content (title/text/controls) > bokeh > panel bg
        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        self.bokeh = BokehLightsCanvas(self.container, count=BOKEH_COUNT)
        self.bokeh.lower()

        self.content = QWidget(self.container)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content.setStyleSheet("background: transparent;")
        self.content.raise_()

        self.main_layout = QVBoxLayout(self.content)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(4)
        self.title_label = CrumbleDownLabel(DOCUMENT_RECORD_TITLE_DEFAULT, self.content)
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layers()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_layers()
        self.bokeh.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "bokeh"):
            self.bokeh.stop()
        super().hideEvent(event)

    def _sync_layers(self) -> None:
        if not hasattr(self, "container"):
            return
        r = self.container.rect()
        self.bokeh.setGeometry(r)
        self.content.setGeometry(r)
        self.bokeh.lower()
        self.content.raise_()

    def _fit_to_content(self) -> None:
        self.content.adjustSize()
        hint = self.content.sizeHint()
        self.container.setFixedSize(max(hint.width(), 240), max(hint.height(), 120))
        self.adjustSize()
        self._sync_layers()

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
        self.title_label.setText(
            self.cfg.get("document_area", "title") or DOCUMENT_RECORD_TITLE_DEFAULT
        )
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

        self._fit_to_content()
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
        self.bokeh.start()

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
            lbl.setStyleSheet("color: #dddddd; background: transparent;")
            self.files_container.addWidget(lbl)
            self._fit_to_content()
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
            page_label.setStyleSheet("color: white; background: transparent;")
            next_btn = QPushButton("Next")
            next_btn.setEnabled(self.current_page < total_pages - 1)
            next_btn.clicked.connect(lambda checked=False: self.show_page(self.current_page + 1))
            self.pagination_container.addWidget(prev_btn)
            self.pagination_container.addWidget(page_label)
            self.pagination_container.addWidget(next_btn)
            self.pagination_container.addStretch()

        self._fit_to_content()

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
# ---------------------------------------------------------------------------
# Jitter Settle — strong shake that damps to rest (theme steel-blue palette)
# ---------------------------------------------------------------------------
# 「顫抖穩定（Jitter Settle）」: each glyph shakes hard (XY + rotate), the
# motion damps to rest, pauses, then the cycle restarts (~2.4s).
FILE_URL_SHORTCUTS_TITLE = "File/URL Shortcuts 指定傳送"
JITTER_SETTLE_TEXT = QColor(255, 255, 255)
JITTER_SETTLE_GLOW = TITLE_GLOW
MINI_PROGRAMS_TITLE = "Mini Programs 副程式"
JITTER_SETTLE_CYCLE_S = 2.4
JITTER_SETTLE_SHAKE_S = 1.15  # damp window; remainder is pause at rest
JITTER_SETTLE_PAD_X = 8.0
JITTER_SETTLE_PAD_Y = 7.0


class JitterSettleLabel(QWidget):
    """Title label: per-character Jitter Settle shake → rest → repeat."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text or ""
        self._chars = list(self._text)
        self._params = []
        for i, _ch in enumerate(self._chars):
            self._params.append(
                {
                    "phase": (i * 1.734) % (2.0 * math.pi),
                    "phase2": (i * 2.513) % (2.0 * math.pi),
                    "freq": 38.0 + (i % 5) * 4.5,   # rad/s — fast jitter
                    "freq2": 31.0 + (i % 4) * 5.0,
                    "freq_rot": 44.0 + (i % 3) * 6.0,
                    "amp_x": 3.8 + (i % 5) * 0.55,
                    "amp_y": 3.2 + (i % 4) * 0.6,
                    "amp_rot": 11.0 + (i % 3) * 3.5,  # degrees
                }
            )

        font = QFont(self.font())
        font.setFamily("Microsoft JhengHei")
        font.setPointSize(9)
        font.setBold(True)
        self._font = font

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._recompute_size()

        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps for sharp shake
        self._timer.timeout.connect(self.update)

    def _recompute_size(self) -> None:
        fm = QFontMetrics(self._font)
        width = sum(fm.horizontalAdvance(ch) for ch in self._chars)
        self.setMinimumHeight(int(fm.height() + JITTER_SETTLE_PAD_Y * 2 + 8))
        self.setMinimumWidth(int(width + JITTER_SETTLE_PAD_X * 2 + 10))
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        return QSize(self.minimumWidth(), self.minimumHeight())

    def showEvent(self, event) -> None:  # noqa: N802
        if not self._elapsed.isValid():
            self._elapsed.start()
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _envelope(t_local: float) -> float:
        """Strong start → exponential damp to ~0 by SHAKE_S; 0 during pause."""
        if t_local >= JITTER_SETTLE_SHAKE_S or t_local < 0.0:
            return 0.0
        u = t_local / JITTER_SETTLE_SHAKE_S  # 0..1
        # Fast decay with a little residual taper so it truly settles.
        return math.exp(-4.8 * u) * (1.0 - u * 0.2)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        t_sec = (self._elapsed.elapsed() / 1000.0) if self._elapsed.isValid() else 0.0
        t_local = t_sec % JITTER_SETTLE_CYCLE_S
        env = self._envelope(t_local)

        x = JITTER_SETTLE_PAD_X
        base_y = JITTER_SETTLE_PAD_Y + fm.ascent() + 2.0

        for ch, p in zip(self._chars, self._params):
            advance = float(fm.horizontalAdvance(ch))
            if ch == " ":
                x += advance
                continue

            if env < 0.002:
                dx = dy = rot = 0.0
            else:
                dx = p["amp_x"] * env * math.sin(p["freq"] * t_local + p["phase"])
                dy = p["amp_y"] * env * math.cos(p["freq2"] * t_local + p["phase2"])
                rot = p["amp_rot"] * env * math.sin(
                    p["freq_rot"] * t_local + p["phase"]
                )

            cx = x + advance * 0.5 + dx
            cy = base_y + dy

            painter.save()
            painter.translate(cx, cy)
            painter.rotate(rot)

            # Always soft-glow like Folder Shortcuts; smear a bit harder while shaking.
            glow_a = 1.0 if env < 0.15 else min(1.0, 0.85 + env * 0.3)
            draw_title_soft_glow(painter, ch, advance, glow_a)

            painter.setPen(JITTER_SETTLE_TEXT)
            painter.drawText(QPointF(-advance * 0.5, 0.0), ch)
            painter.restore()

            x += advance

        painter.end()


# File shortcuts submenu (opened via Social Icon Fill on the main menu)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Falling Petals — weather particle layer for File/URL Shortcuts (指定傳送)
# ---------------------------------------------------------------------------
# 「飄落花瓣（Falling Petals）」: Qt / QPainter take on Canvas 2D petals.
# Structured so mode could later swap to snow/rain (same particle loop).
WEATHER_MODE_PETALS = "petals"
PETAL_COUNT = 42
PETAL_COLORS = (
    QColor(232, 242, 248, 200),   # light sky
    QColor(176, 224, 255, 180),   # soft sky
    QColor(135, 206, 250, 170),   # menu border sky
    QColor(255, 255, 255, 160),   # white
    QColor(200, 220, 235, 190),   # cool steel mist
)


class WeatherParticleCanvas(QWidget):
    """Ambient weather particles (petals now; snow/rain-ready structure)."""

    def __init__(self, parent=None, *, mode: str = WEATHER_MODE_PETALS, count: int = PETAL_COUNT):
        super().__init__(parent)
        self._mode = mode
        self._count = max(8, int(count))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._particles: list[dict] = []
        self._seeded = False
        self._cursor = QPointF(-9999.0, -9999.0)
        self._prev_cursor = QPointF(-9999.0, -9999.0)
        self._cursor_vel = QPointF(0.0, 0.0)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def set_mode(self, mode: str) -> None:
        """Swap weather kind (petals / future snow / rain) and reseed."""
        self._mode = mode or WEATHER_MODE_PETALS
        self._seeded = False
        self._particles.clear()
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _spawn_one(self, w: float, h: float, *, at_top: bool = False) -> dict:
        size = random.uniform(5.0, 11.0)
        return {
            "x": random.uniform(-8.0, w + 8.0),
            "y": (random.uniform(-40.0, -6.0) if at_top else random.uniform(-20.0, h)),
            "vy": random.uniform(0.35, 0.95),
            "vx": random.uniform(-0.25, 0.25),
            "push_vx": 0.0,
            "push_vy": 0.0,
            "sway_amp": random.uniform(0.6, 1.8),
            "sway_freq": random.uniform(0.6, 1.4),
            "sway_phase": random.uniform(0.0, 2.0 * math.pi),
            "rot": random.uniform(0.0, 360.0),
            "rot_v": random.uniform(-1.8, 1.8),
            "flip_phase": random.uniform(0.0, 2.0 * math.pi),
            "flip_freq": random.uniform(0.5, 1.2),
            "size": size,
            "color": random.choice(PETAL_COLORS),
            "age": random.uniform(0.0, 100.0),
        }

    def _ensure(self, w: float, h: float) -> None:
        if self._seeded and self._particles:
            return
        self._particles = [
            self._spawn_one(w, h, at_top=False) for _ in range(self._count)
        ]
        self._seeded = True

    def _poll_cursor(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        cur = QPointF(float(local.x()), float(local.y()))
        if self.rect().contains(local):
            self._cursor_vel = QPointF(
                cur.x() - self._prev_cursor.x(),
                cur.y() - self._prev_cursor.y(),
            )
            self._cursor = cur
        else:
            self._cursor = QPointF(-9999.0, -9999.0)
            self._cursor_vel = QPointF(0.0, 0.0)
        self._prev_cursor = cur

    def _tick(self) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        self._ensure(w, h)
        self._poll_cursor()
        cur = self._cursor
        vel = self._cursor_vel
        speed = math.hypot(vel.x(), vel.y())

        for p in self._particles:
            p["age"] += 0.016
            # Natural fall + sway.
            sway = p["sway_amp"] * math.sin(
                p["age"] * p["sway_freq"] * 2.0 * math.pi + p["sway_phase"]
            )
            p["x"] += p["vx"] + sway * 0.08 + p["push_vx"]
            p["y"] += p["vy"] + p["push_vy"]
            p["rot"] += p["rot_v"]

            # Cursor push: nearby petals nudged by cursor velocity, then decay.
            if speed > 0.4 and cur.x() > -9000:
                dx = p["x"] - cur.x()
                dy = p["y"] - cur.y()
                dist = math.hypot(dx, dy)
                if dist < 70.0 and dist > 0.5:
                    strength = (1.0 - dist / 70.0) * min(1.0, speed / 18.0)
                    p["push_vx"] += vel.x() * 0.12 * strength
                    p["push_vy"] += vel.y() * 0.12 * strength

            p["push_vx"] *= 0.90
            p["push_vy"] *= 0.90

            # Respawn at top when past bottom (or far sideways).
            if p["y"] > h + 16.0 or p["x"] < -30.0 or p["x"] > w + 30.0:
                fresh = self._spawn_one(w, h, at_top=True)
                p.update(fresh)

        self.update()

    def _draw_petal(self, painter: QPainter, p: dict) -> None:
        # Fake turn via horizontal scale; slight vertical squash.
        flip = math.sin(p["age"] * p["flip_freq"] * 2.0 * math.pi + p["flip_phase"])
        scale_x = 0.25 + 0.75 * abs(flip)
        size = p["size"]
        painter.save()
        painter.translate(p["x"], p["y"])
        painter.rotate(p["rot"])
        painter.scale(scale_x, 1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p["color"])
        # Soft teardrop / petal: ellipse + tip.
        painter.drawEllipse(QRectF(-size * 0.45, -size * 0.7, size * 0.9, size * 1.35))
        tip = QPainterPath()
        tip.moveTo(0.0, -size * 0.85)
        tip.quadTo(size * 0.35, -size * 0.2, 0.0, size * 0.55)
        tip.quadTo(-size * 0.35, -size * 0.2, 0.0, -size * 0.85)
        painter.drawPath(tip)
        # Vein hint
        vein = QColor(p["color"])
        vein.setAlpha(min(255, p["color"].alpha() + 40))
        pen = QPen(vein)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(0.0, -size * 0.55), QPointF(0.0, size * 0.35))
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        self._ensure(w, h)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._mode == WEATHER_MODE_PETALS:
            for p in self._particles:
                self._draw_petal(painter, p)
        # Future: elif self._mode == "snow": ... elif "rain": ...
        painter.end()


class FileShortcutsSubMenu(PopupPanel):
    """Submenu listing file/URL shortcuts; opened from the main pet menu icon."""

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

        # Layering top→bottom: content (text/controls) > petals > panel bg
        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        self.petals = WeatherParticleCanvas(
            self.container, mode=WEATHER_MODE_PETALS, count=PETAL_COUNT
        )
        self.petals.lower()

        self.content = QWidget(self.container)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content.setStyleSheet("background: transparent;")
        self.content.raise_()

        self.main_layout = QVBoxLayout(self.content)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(4)

        self.title_label = JitterSettleLabel(FILE_URL_SHORTCUTS_TITLE, self.content)
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layers()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_layers()
        self.petals.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "petals"):
            self.petals.stop()
        super().hideEvent(event)

    def _sync_layers(self) -> None:
        if not hasattr(self, "container"):
            return
        r = self.container.rect()
        self.petals.setGeometry(r)
        self.content.setGeometry(r)
        self.petals.lower()
        self.content.raise_()

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
            lbl.setStyleSheet("color: #dddddd; background: transparent;")
            self.items_container.addWidget(lbl)
        elif not shortcuts:
            lbl = QLabel("(No matching shortcuts)")
            lbl.setStyleSheet("color: #dddddd; background: transparent;")
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
        self.content.adjustSize()
        hint = self.content.sizeHint()
        self.container.setFixedSize(max(hint.width(), 220), max(hint.height(), 120))
        self.adjustSize()
        self._sync_layers()

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

        self._sync_layers()
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
        self.petals.start()

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        self.hide()


# ---------------------------------------------------------------------------
# Mini-program calculators: Level calc / Slope calc
# ---------------------------------------------------------------------------
class LevelCalcDialog(FramelessCalcDialog):
    """Level calc — linear interpolate level at a target chainage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Level calc")
        self.setMinimumSize(540, 200)
        self.resize(560, 220)
        root = install_ornate_calc_frame(self)
        root.setSpacing(6)

        root.addWidget(make_draggable_title(self, "Level calc"))

        # Captions above; edits + Calc level share one baseline row (button right).
        cluster, fields = build_calc_action_cluster(
            [
                ("High level", 100.0, 3, 88),
                ("Low level", 90.0, 3, 88),
                ("Full length", 50.0, 3, 88),
                ("Target dist", 25.0, 3, 88),
            ],
            "Calc level",
            self._calculate,
        )
        self.high, self.low, self.full, self.target = fields
        root.addWidget(cluster, 0, Qt.AlignmentFlag.AlignLeft)

        self.result = QLabel("Result will appear here")
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
                note = "\n(Target outside [0, full length]; extrapolated)"
            elif abs(target) < 1e-12:
                note = "\n(At start / high point)"
            elif abs(target - full) < 1e-12:
                note = "\n(At end / low point)"
            self.result.setText(
                f"◆ Level at target: {level:.3f}{note}"
            )
        except ValueError as exc:
            self.result.setText(f"Input error: {exc}")


class SlopeCalcDialog(FramelessCalcDialog):
    """Slope calc — three calculators matching the surveying reference UIs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slope calc")
        self.setMinimumSize(520, 560)
        self.resize(560, 620)

        frame_root = install_ornate_calc_frame(self)
        frame_root.setContentsMargins(6, 6, 6, 6)
        frame_root.setSpacing(6)

        frame_root.addWidget(make_draggable_title(self, "Slope calc"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        scroll.viewport().setAutoFillBackground(False)
        frame_root.addWidget(scroll)

        root_w = QWidget()
        root_w.setObjectName("calcRoot")
        root_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
        frame, layout = self._section_frame("1", "Slope from two-point level difference")
        cluster, fields = build_calc_action_cluster(
            [
                ("Length (L)", 10.0, 3, 88),
                ("High LV", 10.0, 3, 88),
                ("Low LV", 9.5, 3, 88),
            ],
            "Calc slope",
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
        frame, layout = self._section_frame("2", "Level from slope")
        cluster, fields = build_calc_action_cluster(
            [
                ("Length (L)", 10.0, 3, 88),
                ("Start LV", 10.0, 3, 88),
                ("Fall (%)", 5.0, 3, 88),
            ],
            "Calc level",
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
        frame, layout = self._section_frame("3", "Slope unit conversion")
        layout.addWidget(QLabel("Known value:"))
        self.c_group = QButtonGroup(self)
        self.radio_fall = QRadioButton("Fall (%)")
        self.radio_xin = QRadioButton("1 in X")
        self.radio_angle = QRadioButton("Angle (DD.MMSS)")
        self.radio_fall.setChecked(True)
        for i, radio in enumerate(
            (self.radio_fall, self.radio_xin, self.radio_angle)
        ):
            self.c_group.addButton(radio, i)
            layout.addWidget(radio)
        self.c_group.idClicked.connect(lambda _id: self._on_c_kind_changed())

        self.c_input_label = QLabel("Enter Fall (%)")
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
                "◆ Fall: "
                f"{fall:.3f} %\n"
                f"◆ 1 IN X: {format_one_in_x(xin)}\n"
                f"◆ Angle: {format_dms(ang)}"
            )
            self.a_result.show()
        except ValueError as exc:
            self.a_result.setText(f"Input error: {exc}")
            self.a_result.show()

    def _calc_b(self):
        try:
            ending, xin, ang = ending_lv_from_fall(
                self.b_length.value(), self.b_start.value(), self.b_fall.value()
            )
            self.b_result.setText(
                f"◆ Ending LV: {ending:.3f}\n"
                f"◆ 1 IN X: {format_one_in_x(xin)}\n"
                f"◆ Angle: {format_dms(ang)}"
            )
            self.b_result.show()
        except ValueError as exc:
            self.b_result.setText(f"Input error: {exc}")
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
            self.c_input_label.setText("Enter Fall (%)")
        elif kind == "xin":
            self.c_input_label.setText("Enter 1 in X")
        else:
            self.c_input_label.setText("Enter Angle (DD.MMSS)")
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
                lines.append(f"◆ Fall: {fall:.3f} %")
            if kind != "xin":
                lines.append(f"◆ 1 IN X: {format_one_in_x(xin)}")
            if kind != "angle":
                lines.append(
                    f"◆ Angle: {format_dms(ang)}  (DD.MMSS: {degrees_to_ddmmss(ang):.6f})"
                )
            else:
                # Still show DMS for clarity when DD.MMSS was the input.
                lines.append(f"◆ Angle (DMS): {format_dms(ang)}")
            self.c_result.setText("\n".join(lines) if lines else "—")
        except ValueError as exc:
            self.c_result.setText(f"Input error: {exc}")


class AlignmentCalcDialog(FramelessCalcDialog):
    """Alignment(1) — import chainage/E/N/level; interpolate or deviation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alignment(1)")
        self.setMinimumSize(560, 420)
        self.resize(600, 460)
        self._points = []  # session-only; not persisted to config

        root = install_ornate_calc_frame(self)
        root.setSpacing(6)
        root.addWidget(make_draggable_title(self, "Alignment(1)"))

        # IMPORT row
        import_row = QHBoxLayout()
        import_row.setSpacing(6)
        import_btn = QPushButton("IMPORT")
        import_btn.setObjectName("calcAction")
        import_btn.setFixedHeight(24)
        import_btn.setToolTip(
            "Import alignment points from Excel "
            "(chainage/chanage, Easting, Northing, level)"
        )
        import_btn.clicked.connect(self._import_from_excel)
        import_row.addWidget(import_btn)
        self.status = QLabel("No alignment loaded")
        self.status.setObjectName("calcFieldCaption")
        self.status.setWordWrap(True)
        import_row.addWidget(self.status, 1)
        root.addLayout(import_row)

        # Box 1 — chainage → E/N/level
        box1, box1_l = self._section_frame(
            "1", "Chainage → Easting / Northing / level"
        )
        cluster1, fields1 = build_calc_action_cluster(
            [("Chainage", 0.0, 3, 100)],
            "Calc E/N/Lv",
            self._calc_from_chainage,
        )
        self.ch_in = fields1[0]
        box1_l.addWidget(cluster1, 0, Qt.AlignmentFlag.AlignLeft)
        self.result1 = QLabel("")
        self.result1.setObjectName("calcResult")
        self.result1.setWordWrap(True)
        self.result1.hide()
        box1_l.addWidget(self.result1)
        root.addWidget(box1)

        # Box 2 — E/N/level → chainage + deviation
        box2, box2_l = self._section_frame(
            "2", "Easting / Northing / level → chainage + deviation"
        )
        cluster2, fields2 = build_calc_action_cluster(
            [
                ("Easting", 0.0, 3, 100),
                ("Northing", 0.0, 3, 100),
                ("Level", 0.0, 4, 90),
            ],
            "Calc chainage",
            self._calc_from_en,
        )
        self.e_in, self.n_in, self.lv_in = fields2
        box2_l.addWidget(cluster2, 0, Qt.AlignmentFlag.AlignLeft)
        self.result2 = QLabel("")
        self.result2.setObjectName("calcResult")
        self.result2.setWordWrap(True)
        self.result2.hide()
        box2_l.addWidget(self.result2)
        root.addWidget(box2)

        root.addStretch()
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

    def _require_points(self):
        if len(self._points) < 2:
            raise ValueError("Import an alignment Excel first")

    def _import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import alignment points",
            "",
            "Excel workbooks (*.xlsx *.xlsm *.xls);;All files (*)",
        )
        if not path:
            return
        try:
            points = parse_alignment_workbook(path)
        except Exception as exc:
            self.status.setText(f"Import failed: {exc}")
            QMessageBox.warning(self, "Alignment(1)", f"Import failed:\n{exc}")
            return
        self._points = points
        ch0, ch1 = points[0][0], points[-1][0]
        self.status.setText(
            f"Loaded {len(points)} points  ·  chainage {ch0:g} → {ch1:g}"
        )
        # Seed box defaults from mid alignment for quick try.
        mid_ch = (ch0 + ch1) / 2.0
        self.ch_in.setValue(mid_ch)
        try:
            e, n, lv, _note = alignment_at_chainage(points, mid_ch)
            self.e_in.setValue(e)
            self.n_in.setValue(n)
            self.lv_in.setValue(lv)
        except ValueError:
            pass

    def _calc_from_chainage(self):
        try:
            self._require_points()
            ch = self.ch_in.value()
            e, n, lv, note = alignment_at_chainage(self._points, ch)
            extra = ""
            if note == "exact":
                extra = "\n(Exact chainage on alignment)"
            elif note == "extrapolated":
                extra = "\n(Outside imported range; extrapolated)"
            self.result1.setText(
                f"◆ Easting: {e:.3f}\n"
                f"◆ Northing: {n:.3f}\n"
                f"◆ Level: {lv:.4f}{extra}"
            )
            self.result1.show()
        except ValueError as exc:
            self.result1.setText(f"Input error: {exc}")
            self.result1.show()

    def _calc_from_en(self):
        try:
            self._require_points()
            out = alignment_deviation(
                self._points,
                self.e_in.value(),
                self.n_in.value(),
                self.lv_in.value(),
            )
            self.result2.setText(
                f"◆ Chainage: {out['chainage']:.3f}\n"
                f"◆ Design E: {out['easting']:.3f}   "
                f"ΔE: {out['d_easting']:+.3f}\n"
                f"◆ Design N: {out['northing']:.3f}   "
                f"ΔN: {out['d_northing']:+.3f}\n"
                f"◆ Design Lv: {out['level']:.4f}   "
                f"ΔLv: {out['d_level']:+.4f}\n"
                f"◆ Plan offset: {out['offset_plan']:.3f} m"
            )
            self.result2.show()
        except ValueError as exc:
            self.result2.setText(f"Input error: {exc}")
            self.result2.show()


class Alignment2CalcDialog(FramelessCalcDialog):
    """Alignment(2) — OSCH design Hv/Va import; densify AOut; query."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alignment(2)")
        self.setMinimumSize(580, 500)
        self.resize(640, 540)
        self._points = []  # densified (ch, E, N, Lv); session-only
        self._aout = []  # densified AOut rows; session-only
        self._horiz = []
        self._verts = []
        self._cross = []

        root = install_ornate_calc_frame(self)
        root.setSpacing(6)
        root.addWidget(make_draggable_title(self, "Alignment(2)"))

        import_row = QHBoxLayout()
        import_row.setSpacing(6)
        import_btn = QPushButton("IMPORT")
        import_btn.setObjectName("calcAction")
        import_btn.setFixedHeight(24)
        import_btn.setToolTip(
            "Import OSCH design workbook "
            "(OSCH2_AIn / OSCH2_VIn·Vln / OSCH3_LRHS)"
        )
        import_btn.clicked.connect(self._import_from_excel)
        import_row.addWidget(import_btn)
        output_btn = QPushButton("Output")
        output_btn.setObjectName("calcAction")
        output_btn.setFixedHeight(24)
        output_btn.setToolTip(
            "Save densified design as OSCH2_AOut Excel "
            "(CHAINAGE / E / N / LHS·RHS edge coords)"
        )
        output_btn.clicked.connect(self._output_aout_excel)
        import_row.addWidget(output_btn)
        self.status = QLabel("No design alignment loaded")
        self.status.setObjectName("calcFieldCaption")
        self.status.setWordWrap(True)
        import_row.addWidget(self.status, 1)
        root.addLayout(import_row)

        # Sampling interval — every ? m = 1 point (feeds densify + AOut)
        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        step_cap = QLabel("every")
        step_cap.setObjectName("calcFieldCaption")
        step_row.addWidget(step_cap)
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.01, 1000.0)
        self.step_spin.setDecimals(3)
        self.step_spin.setSingleStep(0.5)
        self.step_spin.setValue(1.0)
        self.step_spin.setSuffix(" m")
        self.step_spin.setFixedWidth(110)
        self.step_spin.setToolTip(
            "Sampling interval for densify / OSCH2_AOut "
            "(default 1 m = 1 point)"
        )
        self.step_spin.valueChanged.connect(self._on_step_changed)
        step_row.addWidget(self.step_spin)
        step_tail = QLabel("= 1 point")
        step_tail.setObjectName("calcFieldCaption")
        step_row.addWidget(step_tail)
        step_row.addStretch()
        root.addLayout(step_row)

        # Box 1 — design chainage → E/N/level (+ crossfall levels)
        box1, box1_l = self._section_frame(
            "1", "Design chainage → Easting / Northing / level"
        )
        cluster1, fields1 = build_calc_action_cluster(
            [("Chainage", 0.0, 3, 100)],
            "Calc E/N/Lv",
            self._calc_from_chainage,
        )
        self.ch_in = fields1[0]
        box1_l.addWidget(cluster1, 0, Qt.AlignmentFlag.AlignLeft)
        self.result1 = QLabel("")
        self.result1.setObjectName("calcResult")
        self.result1.setWordWrap(True)
        self.result1.hide()
        box1_l.addWidget(self.result1)
        root.addWidget(box1)

        # Box 2 — survey N/E/Lv → offset / chainage / level diff (OSCH_SUR)
        box2, box2_l = self._section_frame(
            "2", "Survey Northing / Easting / level → O/S + chainage"
        )
        cluster2, fields2 = build_calc_action_cluster(
            [
                ("Northing", 0.0, 3, 100),
                ("Easting", 0.0, 3, 100),
                ("Level", 0.0, 4, 90),
            ],
            "Calc O/S",
            self._calc_from_survey,
        )
        self.n_in, self.e_in, self.lv_in = fields2
        box2_l.addWidget(cluster2, 0, Qt.AlignmentFlag.AlignLeft)
        self.result2 = QLabel("")
        self.result2.setObjectName("calcResult")
        self.result2.setWordWrap(True)
        self.result2.hide()
        box2_l.addWidget(self.result2)
        root.addWidget(box2)

        root.addStretch()
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

    def _require_points(self):
        if len(self._points) < 2:
            raise ValueError("Import an OSCH design Excel first")

    def _apply_loaded(self, data, *, seed_inputs=False):
        self._horiz = data.get("horizontal") or []
        self._verts = data.get("vertical") or []
        self._cross = data.get("crossfall") or []
        self._aout = data.get("aout") or []
        self._points = data["points"]
        meta = data["meta"]
        step = float(meta.get("step") or self.step_spin.value())
        self.status.setText(
            f"Loaded {meta['count']} design pts  ·  "
            f"AOut {meta.get('aout_count', len(self._aout))}  ·  "
            f"every {step:g} m  ·  "
            f"chainage {meta['ch_start']:g} → {meta['ch_end']:g}"
        )
        if not seed_inputs:
            return
        mid = 0.5 * (meta["ch_start"] + meta["ch_end"])
        self.ch_in.setValue(mid)
        try:
            import alignment2 as a2

            des = a2.design_at_chainage(self._points, mid, self._cross)
            self.n_in.setValue(des["northing"])
            self.e_in.setValue(des["easting"])
            self.lv_in.setValue(des["level"])
        except ValueError:
            pass

    def _import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import OSCH design alignment",
            "",
            "Excel workbooks (*.xlsx *.xlsm *.xls);;All files (*)",
        )
        if not path:
            return
        try:
            import alignment2 as a2

            data = a2.parse_alignment2_workbook(
                path, step=float(self.step_spin.value())
            )
        except Exception as exc:
            self.status.setText(f"Import failed: {exc}")
            QMessageBox.warning(self, "Alignment(2)", f"Import failed:\n{exc}")
            return
        self._apply_loaded(data, seed_inputs=True)

    def _on_step_changed(self, _value=None):
        if not self._horiz:
            return
        try:
            import alignment2 as a2

            data = a2.rebuild_design(
                self._horiz,
                self._verts,
                self._cross,
                step=float(self.step_spin.value()),
            )
        except Exception as exc:
            self.status.setText(f"Resample failed: {exc}")
            return
        self._apply_loaded(data, seed_inputs=False)

    def _output_aout_excel(self):
        if not self._aout:
            QMessageBox.warning(
                self,
                "Alignment(2)",
                "Import an OSCH design Excel first, then Output.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save OSCH2_AOut Excel",
            "OSCH2_AOut.xlsx",
            "Excel workbooks (*.xlsx);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm", ".xls")):
            path = path + ".xlsx"
        try:
            import alignment2 as a2

            a2.write_aout_workbook(path, self._aout)
        except Exception as exc:
            QMessageBox.warning(self, "Alignment(2)", f"Output failed:\n{exc}")
            return
        self.status.setText(
            f"Saved AOut · {len(self._aout)} pts · every "
            f"{float(self.step_spin.value()):g} m → {path}"
        )

    def _calc_from_chainage(self):
        try:
            import alignment2 as a2

            self._require_points()
            des = a2.design_at_chainage(
                self._points, self.ch_in.value(), self._cross
            )
            lines = [
                f"◆ Easting: {des['easting']:.3f}",
                f"◆ Northing: {des['northing']:.3f}",
                f"◆ Level: {des['level']:.4f}",
            ]
            if "left_level" in des:
                lines.append(
                    f"◆ LHS Lv: {des['left_level']:.4f}  "
                    f"(fall {des['left_fall']:.2f}%)"
                )
                lines.append(
                    f"◆ RHS Lv: {des['right_level']:.4f}  "
                    f"(fall {des['right_fall']:.2f}%)"
                )
            self.result1.setText("\n".join(lines))
            self.result1.show()
        except ValueError as exc:
            self.result1.setText(f"Input error: {exc}")
            self.result1.show()

    def _calc_from_survey(self):
        try:
            import alignment2 as a2

            self._require_points()
            out = a2.survey_vs_design(
                self._points,
                self.n_in.value(),
                self.e_in.value(),
                self.lv_in.value(),
            )
            side = "left (−)" if out["offset"] < 0 else (
                "right (+)" if out["offset"] > 0 else "on line"
            )
            self.result2.setText(
                f"◆ Chainage: {out['chainage']:.3f}\n"
                f"◆ Offset (O/S): {out['offset']:+.3f} m  ({side})\n"
                f"◆ Level diff: {out['level_diff']:+.4f} m\n"
                f"◆ Design E: {out['design_easting']:.3f}\n"
                f"◆ Design N: {out['design_northing']:.3f}\n"
                f"◆ Design Lv: {out['design_level']:.4f}"
            )
            self.result2.show()
        except ValueError as exc:
            self.result2.setText(f"Input error: {exc}")
            self.result2.show()


class FreeStationDialog(FramelessCalcDialog):
    """
    Free Station (resection) — mirrors the Free_Station_FAI.xls sheet math.

    Page 1: standing station + up to four backsight rows, each with face-left
    (F1) and face-right (F2) observations averaged like the sheet's "Mean B/S"
    formulas, plus the per-pair review table (Preliminary / Mirror / chosen
    E/N, Reduced Lv., Distance Check) with the sheet's Reject Both (Y) /
    Use Mirror Angle (Y) overrides. IMPORT (left of Calculate) loads the Free
    Station sheet from .xlsm/.xlsx/.xls. Page 2: stored backsight records
    (Name, Easting, Northing, RL) persisted in config as
    "free_station_stations"; typing a known Name on page 1 auto-fills E/N/RL.
    """

    BS_ROWS = 4
    STORE_KEY = "free_station_stations"

    PAIR_COLUMNS = [
        "From", "To", "Prelim E", "Prelim N", "Mirror E", "Mirror N",
        "Easting", "Northing", "RL", "Dist.\ncheck", "Reject\nboth", "Use\nmirror",
    ]

    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Free Station")
        self.setMinimumSize(700, 420)
        self.resize(860, 690)
        self.setStyleSheet(
            CALC_DIALOG_STYLE
            + MINI_PROGRAM_STYLE
            + """
            QTableWidget#fsTable {
                background-color: transparent;
                color: #e8e8e8;
                gridline-color: rgba(90, 90, 90, 160);
                border: 1px solid rgba(90, 90, 90, 160);
                font-size: 8pt;
            }
            QTableWidget#fsTable QHeaderView {
                background-color: rgba(45, 45, 45, 220);
                border: none;
            }
            QTableWidget#fsTable QHeaderView::section {
                background-color: rgba(45, 45, 45, 220);
                color: #f5e6c8;
                border: none;
                padding: 2px 4px;
                font-size: 8pt;
            }
            QTableWidget#fsTable QLineEdit {
                background-color: rgba(42, 42, 42, 230);
            }
            QScrollBar:vertical {
                background: rgba(30, 30, 30, 200); width: 10px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 96, 96, 220); min-height: 20px; border-radius: 4px;
            }
            QScrollBar:horizontal {
                background: rgba(30, 30, 30, 200); height: 10px; margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: rgba(96, 96, 96, 220); min-width: 20px; border-radius: 4px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0; height: 0;
            }}
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: transparent;
            }}
        """
        )
        root = install_ornate_calc_frame(self)
        root.setSpacing(6)

        # Title row: dialog title left, << 1 / 2 >> pager top-right.
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.addWidget(make_draggable_title(self, "Free Station"))
        title_row.addStretch()
        self.page_prev_btn = QPushButton("<<")
        self.page_prev_btn.setObjectName("calcAction")
        self.page_prev_btn.setFixedWidth(34)
        self.page_prev_btn.clicked.connect(lambda: self._flip_page(-1))
        self.page_label = QLabel("1 / 2")
        self.page_label.setObjectName("calcFieldCaption")
        self.page_next_btn = QPushButton(">>")
        self.page_next_btn.setObjectName("calcAction")
        self.page_next_btn.setFixedWidth(34)
        self.page_next_btn.clicked.connect(lambda: self._flip_page(1))
        title_row.addWidget(self.page_prev_btn)
        title_row.addWidget(self.page_label)
        title_row.addWidget(self.page_next_btn)
        root.addLayout(title_row)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_input_page())
        self.pages.addWidget(self._build_store_page())
        root.addWidget(self.pages, 1)

        # Shared bottom row.
        close_row = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("calcAction")
        copy_btn.clicked.connect(self._copy_result)
        close_row.addWidget(copy_btn)
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self._pair_choices = {}  # (from_tag, to_tag) -> "reject" | "mirror" | ""
        self._station_records = self._load_station_records()
        self._reload_store_table()

    def accept(self):
        # Prune blank store rows on close so they do not accumulate in config.
        kept = [
            rec for rec in self._station_records
            if (rec.get("name") or "").strip()
            or rec.get("e") is not None or rec.get("n") is not None
        ]
        if len(kept) != len(self._station_records):
            self._station_records = kept
            self._save_station_records()
        super().accept()

    # ------------------------------------------------------------------ page 1
    def _build_input_page(self):
        outer = QWidget()
        outer.setObjectName("calcRoot")
        outer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_l = QVBoxLayout(outer)
        outer_l.setContentsMargins(0, 0, 0, 0)
        outer_l.setSpacing(0)

        # Scrollable so long pair tables / summaries never overflow the frame.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        scroll.viewport().setAutoFillBackground(False)
        outer_l.addWidget(scroll)

        page = QWidget()
        page.setObjectName("calcRoot")
        page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 2, 0)
        layout.setSpacing(6)
        scroll.setWidget(page)

        # Standing station row: name + instrument height + Calculate button.
        stand_row = QHBoxLayout()
        stand_row.setSpacing(4)
        stand_caption = QLabel("Standing station")
        stand_caption.setObjectName("calcFieldCaption")
        stand_row.addWidget(stand_caption)
        self.station_name = QLineEdit()
        self.station_name.setObjectName("calcNumeric")
        self.station_name.setFixedWidth(90)
        self.station_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stand_row.addWidget(self.station_name)
        hi_caption = QLabel("Inst. ht (m)")
        hi_caption.setObjectName("calcFieldCaption")
        stand_row.addWidget(hi_caption)
        self.inst_height = make_calc_line_edit(0.0, decimals=3, max_edit_width=64)
        stand_row.addWidget(self.inst_height)
        stand_row.addStretch()
        import_btn = QPushButton("IMPORT")
        import_btn.setObjectName("calcAction")
        import_btn.setFixedHeight(24)
        import_btn.setToolTip(
            "Import standing station, instrument height, and BS rows "
            "from a Free Station sheet (.xlsm / .xlsx / .xls)"
        )
        import_btn.clicked.connect(self._import_from_excel)
        stand_row.addWidget(import_btn)
        calc_btn = QPushButton("Calculate")
        calc_btn.setObjectName("calcAction")
        calc_btn.setFixedHeight(24)
        calc_btn.clicked.connect(self._calculate)
        stand_row.addWidget(calc_btn)
        layout.addLayout(stand_row)

        # Backsight grid: one coordinate row (F1 observations) + one F2
        # observation sub-row per backsight, mirroring the Excel's
        # "BSx - FL" / "BSx - FR" rows under one known-station block.
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        headers = [
            "", "Name", "Easting", "Northing", "RL",
            "Bearing", "Vert. angle", "Slope dist", "Spot ht",
        ]
        for col, text in enumerate(headers):
            cell = QLabel(text)
            cell.setObjectName("calcFieldCaption")
            grid.addWidget(cell, 0, col)
        self.bs_fields = []
        for row_idx in range(self.BS_ROWS):
            tag = QLabel(f"BS{row_idx + 1}")
            tag.setObjectName("calcFieldCaption")
            grid.addWidget(tag, row_idx * 2 + 1, 0)
            f1 = self._add_obs_row(grid, row_idx * 2 + 1, with_station=True)
            f2 = self._add_obs_row(grid, row_idx * 2 + 2, with_station=False)
            self.bs_fields.append({"f1": f1, "f2": f2})
            f1["name"].textChanged.connect(
                lambda text, idx=row_idx: self._autofill_from_store(idx, text)
            )
        grid_wrap = QWidget()
        grid_wrap.setObjectName("calcRoot")
        grid_wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        grid_wrap.setLayout(grid)
        layout.addWidget(grid_wrap)

        # Per-pair review table (Excel columns incl. Reject Both / Use Mirror).
        self.pair_table = QTableWidget(0, len(self.PAIR_COLUMNS))
        self.pair_table.setObjectName("fsTable")
        self.pair_table.setHorizontalHeaderLabels(self.PAIR_COLUMNS)
        self.pair_table.verticalHeader().setVisible(False)
        self.pair_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pair_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pair_table.setFixedHeight(158)
        self.pair_table.horizontalHeader().setMinimumSectionSize(40)
        self.pair_table.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate([50, 50, 82, 82, 82, 82, 82, 82, 46, 54, 46, 48]):
            self.pair_table.setColumnWidth(col, width)
        layout.addWidget(self.pair_table)

        self.result = QLabel("Result will appear here")
        self.result.setObjectName("calcResult")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result)
        return outer

    def _add_obs_row(self, grid, row, with_station):
        """
        One observation row. with_station (F1) → Name/E/N/RL cells in
        columns 1-4; observations always land in columns 5-8 so the F2
        sub-row aligns under the F1 observation cells.
        """
        fields = {}
        if with_station:
            name = QLineEdit()
            name.setObjectName("calcNumeric")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setFixedWidth(76)
            name.setPlaceholderText("BS name")
            grid.addWidget(name, row, 1)
            fields["name"] = name
            for col, (key, width) in enumerate(
                [("easting", 88), ("northing", 88), ("rl", 56)], start=2
            ):
                edit = QLineEdit()
                edit.setObjectName("calcNumeric")
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                edit.setFixedWidth(width)
                grid.addWidget(edit, row, col)
                fields[key] = edit
        obs_specs = [
            ("bearing", 86, None), ("va", 86, None), ("sd", 72, 3), ("sh", 52, 3),
        ]
        for col, (key, width, decimals) in enumerate(obs_specs, start=5):
            edit = QLineEdit()
            edit.setObjectName("calcNumeric")
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.setFixedWidth(width)
            grid.addWidget(edit, row, col)
            fields[key] = edit
        return fields

    # ------------------------------------------------------------------ page 2
    def _build_store_page(self):
        page = QWidget()
        page.setObjectName("calcRoot")
        page.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        caption = QLabel("Stored backsight records (auto-fills page 1 by Name)")
        caption.setObjectName("calcSectionTitle")
        layout.addWidget(caption)

        self.store_table = QTableWidget(0, 4)
        self.store_table.setObjectName("fsTable")
        self.store_table.setHorizontalHeaderLabels(["Name", "Easting", "Northing", "RL"])
        self.store_table.verticalHeader().setVisible(False)
        self.store_table.horizontalHeader().setMinimumSectionSize(46)
        self.store_table.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate([110, 130, 130, 90]):
            self.store_table.setColumnWidth(col, width)
        self.store_table.cellChanged.connect(self._on_store_cell_changed)
        layout.addWidget(self.store_table, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.setObjectName("calcAction")
        add_btn.clicked.connect(self._store_add_row)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("Delete selected")
        del_btn.setObjectName("calcAction")
        del_btn.clicked.connect(self._store_delete_selected)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return page

    def _flip_page(self, delta):
        new_index = (self.pages.currentIndex() + delta) % self.pages.count()
        self.pages.setCurrentIndex(new_index)
        self.page_label.setText(f"{new_index + 1} / {self.pages.count()}")

    # ------------------------------------------------------- stored records
    def _load_station_records(self):
        if self.cfg is None:
            return []
        records = self.cfg.get(self.STORE_KEY) or []
        out = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            out.append(
                {
                    "name": str(rec.get("name", "") or ""),
                    "e": self._to_float_or_none(rec.get("e")),
                    "n": self._to_float_or_none(rec.get("n")),
                    "rl": self._to_float_or_none(rec.get("rl")),
                }
            )
        return out

    @staticmethod
    def _to_float_or_none(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _save_station_records(self):
        # Keep row indices in sync with the table; empty rows are harmless
        # (auto-fill skips them) and are pruned when the dialog closes.
        if self.cfg is not None:
            self.cfg.set([self.STORE_KEY], self._station_records)

    def _reload_store_table(self):
        self.store_table.blockSignals(True)
        self.store_table.setRowCount(0)
        for rec in self._station_records:
            self._append_store_row(rec)
        self.store_table.blockSignals(False)

    def _append_store_row(self, rec):
        row = self.store_table.rowCount()
        self.store_table.insertRow(row)
        values = [
            rec.get("name", ""),
            "" if rec.get("e") is None else f"{rec['e']:.3f}",
            "" if rec.get("n") is None else f"{rec['n']:.3f}",
            "" if rec.get("rl") is None else f"{rec['rl']:.3f}",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            self.store_table.setItem(row, col, item)

    def _store_add_row(self):
        self._station_records.append({"name": "", "e": None, "n": None, "rl": None})
        self.store_table.blockSignals(True)
        self._append_store_row(self._station_records[-1])
        self.store_table.blockSignals(False)
        self._save_station_records()

    def _store_delete_selected(self):
        rows = sorted(
            {index.row() for index in self.store_table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            return
        self.store_table.blockSignals(True)
        for row in rows:
            self.store_table.removeRow(row)
            if 0 <= row < len(self._station_records):
                del self._station_records[row]
        self.store_table.blockSignals(False)
        self._save_station_records()

    def _on_store_cell_changed(self, row, col):
        if not (0 <= row < len(self._station_records)):
            return
        text = (self.store_table.item(row, col).text() or "").strip()
        rec = self._station_records[row]
        if col == 0:
            rec["name"] = text
        else:
            rec[["e", "n", "rl"][col - 1]] = self._to_float_or_none(text)
        self._save_station_records()

    def _autofill_from_store(self, idx, text):
        name = (text or "").strip().lower()
        if not name:
            return
        for rec in self._station_records:
            if (rec.get("name") or "").strip().lower() == name:
                fields = self.bs_fields[idx]["f1"]
                if rec.get("e") is not None:
                    fields["easting"].setText(_format_calc_value(rec["e"], 3))
                if rec.get("n") is not None:
                    fields["northing"].setText(_format_calc_value(rec["n"], 3))
                if rec.get("rl") is not None:
                    fields["rl"].setText(_format_calc_value(rec["rl"], 3))
                return

    # ------------------------------------------------------------- Excel IMPORT
    def _import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Free Station sheet",
            "",
            "Excel workbooks (*.xlsm *.xlsx *.xls);;All files (*)",
        )
        if not path:
            return
        try:
            data = parse_free_station_workbook(path)
        except (OSError, ValueError, ImportError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        except Exception as exc:  # openpyxl/xlrd can raise assorted errors
            QMessageBox.warning(self, "Import failed", f"Could not read file:\n{exc}")
            return

        def _set_import_text(edit, value):
            """Write imported text; empty / placeholder tokens clear the field."""
            text = _fs_import_field_text(value)
            edit.setText(text)

        _set_import_text(self.station_name, data.get("station_name") or "")
        hi_text = _fs_import_field_text(data.get("inst_height") or "")
        self.inst_height.setText(hi_text if hi_text else "0.000")

        for idx, bs in enumerate(data.get("backsights") or []):
            if idx >= len(self.bs_fields):
                break
            f1, f2 = self.bs_fields[idx]["f1"], self.bs_fields[idx]["f2"]
            # Block store auto-fill while we set Name so Excel E/N/RL win.
            f1["name"].blockSignals(True)
            _set_import_text(f1["name"], bs.get("name") or "")
            f1["name"].blockSignals(False)
            _set_import_text(f1["easting"], bs.get("easting") or "")
            _set_import_text(f1["northing"], bs.get("northing") or "")
            _set_import_text(f1["rl"], bs.get("rl") or "")
            for face_fields, face_data in ((f1, bs.get("f1") or {}), (f2, bs.get("f2") or {})):
                _set_import_text(face_fields["bearing"], face_data.get("bearing") or "")
                _set_import_text(face_fields["va"], face_data.get("va") or "")
                _set_import_text(face_fields["sd"], face_data.get("sd") or "")
                _set_import_text(face_fields["sh"], face_data.get("sh") or "")

        named = sum(1 for bs in data.get("backsights") or [] if (bs.get("name") or "").strip())
        self.result.setText(
            f"Imported from {Path(path).name} "
            f"({data.get('layout', 'annotated')} layout): "
            f"{named} backsight name(s). Press Calculate when ready."
        )

    # ------------------------------------------------------------------ math
    def _parse_optional(self, edit, label):
        """Parse a grid cell; '' → None. DD.MMSS values are kept as typed
        (survey_deg inside the math helpers decodes them)."""
        raw = (edit.text() or "").strip().replace(",", "")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"{label}: enter a valid number") from exc

    def _parse_required(self, edit, label):
        value = self._parse_optional(edit, label)
        if value is None:
            raise ValueError(f"{label}: coordinate is required")
        return value

    def _read_backsights(self):
        rows = []
        for idx, fields in enumerate(self.bs_fields, start=1):
            f1, f2 = fields["f1"], fields["f2"]
            name = (f1["name"].text() or "").strip()
            if not name:
                continue
            label = f"BS{idx} ({name})"
            try:
                e = self._parse_required(f1["easting"], label)
                n = self._parse_required(f1["northing"], label)
                brg = mean_bearing_faces(
                    self._parse_optional(f1["bearing"], label),
                    self._parse_optional(f2["bearing"], label),
                )
                va = mean_va_faces(
                    self._parse_optional(f1["va"], label),
                    self._parse_optional(f2["va"], label),
                )
                sd = mean_faces(
                    self._parse_optional(f1["sd"], label),
                    self._parse_optional(f2["sd"], label),
                )
                sh = mean_faces(
                    self._parse_optional(f1["sh"], label),
                    self._parse_optional(f2["sh"], label),
                )
                rl = self._parse_optional(f1["rl"], label)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            if brg is None:
                raise ValueError(f"{label}: mean bearing is required (DD.MMSS)")
            rows.append(
                {
                    "tag": f"BS{idx}", "name": name, "e": e, "n": n, "rl": rl,
                    "brg": brg, "va": va, "sd": sd, "sh": sh or 0.0,
                }
            )
        if len(rows) < 2:
            raise ValueError("At least two backsight rows with names are required")
        return rows

    def _solve_pair(self, src, dst, hi):
        """Solve one From→To pair; returns dict with prelim/mirror branches."""
        prelim = free_station_branch(
            src["e"], src["n"], dst["e"], dst["n"], dst["rl"] or 0.0,
            src["brg"], dst["brg"], dst["va"], dst["sd"], dst["sh"],
            hi, mirror=False,
        )
        mirror = free_station_branch(
            src["e"], src["n"], dst["e"], dst["n"], dst["rl"] or 0.0,
            src["brg"], dst["brg"], dst["va"], dst["sd"], dst["sh"],
            hi, mirror=True,
        )
        return prelim, mirror

    def _pair_residual(self, easting, northing, src):
        if src["va"] is None or src["sd"] is None:
            return None
        return (
            survey_polar(easting, northing, src["e"], src["n"], "D")
            - survey_sd_to_hd(src["sd"], src["va"])
        )

    def _select_branch(self, prelim, mirror, resid_prelim):
        """Sheet branch rule (H33/I33) — keep preliminary when its distance
        check is < 0.05 m, otherwise the mirror branch when it exists."""
        if resid_prelim is not None and abs(resid_prelim) < 0.05:
            return prelim, "direct"
        if mirror is not None:
            return mirror, "mirror"
        return prelim, "direct (check)"

    def _calculate(self):
        try:
            hi = parse_calc_number(self.inst_height.text())
            rows = self._read_backsights()
        except ValueError as exc:
            self.result.setText(f"Input error: {exc}")
            return
        self._last_hi = hi
        station = (self.station_name.text() or "").strip() or "(unnamed)"
        solutions = {}
        for src in rows:
            for dst in rows:
                if src is dst or dst["va"] is None or dst["sd"] is None:
                    continue
                try:
                    prelim, mirror = self._solve_pair(src, dst, hi)
                except ValueError as exc:
                    self.result.setText(f"Input error: {exc}")
                    return
                key = (src["tag"], dst["tag"])
                solutions[key] = {
                    "src": src, "dst": dst,
                    "prelim": prelim, "mirror": mirror,
                    "resid_prelim": self._pair_residual(prelim[0], prelim[1], src),
                }
        self._rebuild_pair_table(solutions)
        self._update_summary(station, solutions)

    def _rebuild_pair_table(self, solutions):
        self.pair_table.blockSignals(True)
        self.pair_table.setRowCount(0)
        for (src_tag, dst_tag), sol in solutions.items():
            row = self.pair_table.rowCount()
            self.pair_table.insertRow(row)
            choice = self._pair_choices.get((src_tag, dst_tag), "")
            prelim, mirror = sol["prelim"], sol["mirror"]
            chosen, branch = self._chosen_for(sol, choice)
            resid = self._pair_residual(chosen[0], chosen[1], sol["src"]) if chosen else None
            cells = [
                sol["src"]["name"], sol["dst"]["name"],
                "" if prelim is None else f"{prelim[0]:.4f}",
                "" if prelim is None else f"{prelim[1]:.4f}",
                "" if mirror is None else f"{mirror[0]:.4f}",
                "" if mirror is None else f"{mirror[1]:.4f}",
                "" if chosen is None else f"{chosen[0]:.4f}",
                "" if chosen is None else f"{chosen[1]:.4f}",
                "n/a" if sol["dst"]["rl"] is None else f"{chosen[2]:.3f}",
                "" if resid is None else f"{resid:+.3f}",
            ]
            for col, value in enumerate(cells):
                self.pair_table.setItem(row, col, QTableWidgetItem(value))
            for col, checked in ((10, choice == "reject"), (11, choice == "mirror")):
                box = QCheckBox()
                box.setStyleSheet("QCheckBox { background-color: transparent; }")
                if checked:
                    box.setChecked(True)
                box.toggled.connect(
                    lambda checked, r=row, t=(src_tag, dst_tag), c=col,
                           b=box: self._on_pair_choice(r, t, c, b)
                )
                wrap = QWidget()
                wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                lay = QHBoxLayout(wrap)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(box)
                lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pair_table.setCellWidget(row, col, wrap)
        self.pair_table.blockSignals(False)
        self._current_solutions = solutions

    def _on_pair_choice(self, row, key, col, box):
        if col == 10:
            choice = "reject" if box.isChecked() else ""
            sibling = self.pair_table.cellWidget(row, 11).findChild(QCheckBox)
        else:
            choice = "mirror" if box.isChecked() else ""
            sibling = self.pair_table.cellWidget(row, 10).findChild(QCheckBox)
        if choice and sibling is not None and sibling.isChecked():
            sibling.blockSignals(True)
            sibling.setChecked(False)
            sibling.blockSignals(False)
        self._pair_choices[key] = choice
        self._refresh_pair_row(row, key)
        self._update_summary(
            (self.station_name.text() or "").strip() or "(unnamed)",
            self._current_solutions,
        )

    def _chosen_for(self, sol, choice):
        """Apply a pair choice to a solution; returns (branch_tuple, tag)."""
        prelim, mirror = sol["prelim"], sol["mirror"]
        if choice == "reject":
            return None, "rejected"
        if choice == "mirror":
            if mirror is not None:
                return mirror, "mirror (Y)"
            return prelim, "mirror n/a"
        return self._select_branch(prelim, mirror, sol["resid_prelim"])

    def _refresh_pair_row(self, row, key):
        sol = self._current_solutions[key]
        choice = self._pair_choices.get(key, "")
        chosen, branch = self._chosen_for(sol, choice)
        resid = self._pair_residual(chosen[0], chosen[1], sol["src"]) if chosen else None
        values = {
            6: "" if chosen is None else f"{chosen[0]:.4f}",
            7: "" if chosen is None else f"{chosen[1]:.4f}",
            8: "" if chosen is None else f"{chosen[2]:.3f}",
            9: "" if resid is None else f"{resid:+.3f}",
        }
        for col, value in values.items():
            self.pair_table.setItem(row, col, QTableWidgetItem(value))

    def _update_summary(self, station, solutions):
        try:
            hi = parse_calc_number(self.inst_height.text())
        except ValueError:
            hi = getattr(self, "_last_hi", 0.0)
        lines = [f"◆ Free station {station}   inst. ht {hi:.3f} m"]
        kept = 0
        accepted = []  # (e, n, rl_or_None) for Average line
        for (src_tag, dst_tag), sol in solutions.items():
            choice = self._pair_choices.get((src_tag, dst_tag), "")
            chosen, branch = self._chosen_for(sol, choice)
            if chosen is None:
                lines.append(f"  {sol['src']['name']} → {sol['dst']['name']} : rejected")
                continue
            resid = self._pair_residual(chosen[0], chosen[1], sol["src"])
            resid_text = f"{resid:+.3f}" if resid is not None else "n/a"
            has_rl = sol["dst"]["rl"] is not None
            rl_text = f"{chosen[2]:.3f}" if has_rl else "n/a"
            lines.append(
                f"  {sol['src']['name']} → {sol['dst']['name']} :  "
                f"E {chosen[0]:.4f}  N {chosen[1]:.4f}  RL {rl_text}  "
                f"ΔHD {resid_text}  ({branch})"
            )
            accepted.append((chosen[0], chosen[1], chosen[2] if has_rl else None))
            kept += 1
        if not solutions:
            self.result.setText(
                "Input error: at least one backsight needs a vertical angle and slope distance"
            )
            return
        if kept == 0:
            lines.append("  (all pairs rejected — nothing to report)")
        else:
            avg_e = sum(e for e, _n, _rl in accepted) / kept
            avg_n = sum(n for _e, n, _rl in accepted) / kept
            rl_vals = [rl for _e, _n, rl in accepted if rl is not None]
            if rl_vals:
                avg_rl_text = f"{sum(rl_vals) / len(rl_vals):.3f}"
            else:
                avg_rl_text = "n/a"
            lines.append(
                f"  Average :  E {avg_e:.4f}  N {avg_n:.4f}  RL {avg_rl_text}  "
                f"({kept} pair{'s' if kept != 1 else ''})"
            )
            lines.append("  ΔHD = distance check residual (m); direct/mirror = branch used")
        self.result.setText("\n".join(lines))

    def _copy_result(self):
        text = self.result.text()
        if text and text != "Result will appear here":
            QApplication.clipboard().setText(text)


# ---------------------------------------------------------------------------
# Mini-program: Pomodoro / Translate
# ---------------------------------------------------------------------------
MINI_PROGRAM_STYLE = f"""
    /* Countdown chrome on the wrapper frame; digit QLabel has no QSS padding
       (padding+border inside a tight QLabel clips glyph descents on Windows). */
    QFrame#pomodoroDisplayFrame {{
        background-color: rgba(16, 26, 16, {CALC_PANEL_ALPHA});
        border: 1px solid #2d5a2d;
        border-radius: 4px;
        min-height: 110px;
    }}
    QLabel#pomodoroDisplay {{
        color: #7CFC7C;
        background-color: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
    }}
    QLabel#pomodoroClockRow {{
        color: #d8d8d8;
        font-size: 10pt;
        padding: 2px 2px;
        min-height: 20px;
    }}
    QLabel#pomodoroClockValue {{
        color: #e8f5e8;
        background-color: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
    }}
    QPushButton#pomodoroWideAction {{
        background-color: rgba(44, 44, 44, 230);
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 3px;
        min-height: 24px;
        max-height: 30px;
        min-width: 180px;
        max-width: 260px;
        padding: 3px 12px;
        font-size: 9pt;
    }}
    QProgressBar#pomodoroProgress {{
        background-color: rgba(42, 42, 42, 210);
        color: #f0f0f0;
        border: 1px solid #555;
        border-radius: 3px;
        min-height: 14px;
        max-height: 16px;
        text-align: center;
    }}
    QProgressBar#pomodoroProgress::chunk {{
        background-color: #3f8f3f;
        border-radius: 2px;
    }}
    QSpinBox {{
        background-color: rgba(42, 42, 42, 230);
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 2px 4px;
        min-height: 18px;
        max-height: 22px;
        selection-background-color: #3d5a80;
        selection-color: #ffffff;
    }}
    QSpinBox:focus {{ border: 1px solid #c9a84c; }}
    QTimeEdit {{
        background-color: rgba(42, 42, 42, 230);
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 2px 4px;
        min-height: 22px;
        max-height: 28px;
    }}
    QTimeEdit:focus {{ border: 1px solid #c9a84c; }}
    QPlainTextEdit#translateSource {{
        background-color: rgba(42, 42, 42, 230);
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 3px 5px;
        selection-background-color: #3d5a80;
        selection-color: #ffffff;
    }}
    QPlainTextEdit#translateSource:focus {{ border: 1px solid #c9a84c; }}
    QComboBox#translateLang {{
        background-color: rgba(42, 42, 42, 230);
        color: #f0f0f0;
        border: 1px solid #666;
        border-radius: 3px;
        padding: 2px 6px;
        min-height: 18px;
        max-height: 22px;
    }}
    QComboBox#translateLang:focus {{ border: 1px solid #c9a84c; }}
    QComboBox#translateLang QAbstractItemView {{
        background-color: rgba(42, 42, 42, 245);
        color: #f0f0f0;
        selection-background-color: #3d5a80;
        selection-color: #ffffff;
    }}
"""

# Preset durations offered on the Pomodoro dialog (minutes).
POMODORO_PRESETS = (25, 5, 15)


class PomodoroDialog(FramelessCalcDialog):
    """Pomodoro — duration presets or wall-clock target; Now / Target / Countdown."""

    MODE_DURATION = "duration"
    MODE_WALLCLOCK = "wallclock"

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Pomodoro")
        # Tall enough that large countdown + clock rows are not vertically crushed.
        self.setMinimumSize(460, 460)
        self.resize(480, 500)
        self.setStyleSheet(CALC_DIALOG_STYLE + MINI_PROGRAM_STYLE)
        root = install_ornate_calc_frame(self)
        root.setSpacing(8)

        root.addWidget(make_draggable_title(self, "Pomodoro"))

        try:
            saved = int(self.cfg.get("pomodoro", "minutes") or 0)
        except (TypeError, ValueError):
            saved = 0
        self.total_seconds = min(max(saved or 25, 1), 600) * 60
        self.remaining_seconds = self.total_seconds
        self.running = False
        self.target_end = None  # datetime when active / planned session should end
        self.mode = self.MODE_DURATION

        # 現在時間 / 目標時間 — QFont only (no QSS padding on value labels).
        clock_grid = QGridLayout()
        clock_grid.setHorizontalSpacing(8)
        clock_grid.setVerticalSpacing(10)
        now_cap = QLabel("現在時間／Now")
        now_cap.setObjectName("pomodoroClockRow")
        self.now_value = QLabel("--:--:--")
        self.now_value.setObjectName("pomodoroClockValue")
        target_cap = QLabel("目標時間／Target")
        target_cap.setObjectName("pomodoroClockRow")
        self.target_value = QLabel("—")
        self.target_value.setObjectName("pomodoroClockValue")
        clock_font = QFont("Consolas")
        if not clock_font.exactMatch():
            clock_font = QFont("Courier New")
        clock_font.setStyleHint(QFont.StyleHint.TypeWriter)
        clock_font.setPixelSize(18)
        clock_font.setBold(True)
        for lbl in (now_cap, target_cap):
            lbl.setMinimumHeight(24)
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        for lbl in (self.now_value, self.target_value):
            lbl.setFont(clock_font)
            fm = lbl.fontMetrics()
            # Extra headroom for Windows DPI / ClearType glyph overhang.
            lbl.setFixedHeight(max(40, fm.lineSpacing() + 20))
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        clock_grid.addWidget(now_cap, 0, 0)
        clock_grid.addWidget(self.now_value, 0, 1)
        clock_grid.addWidget(target_cap, 1, 0)
        clock_grid.addWidget(self.target_value, 1, 1)
        clock_grid.setColumnStretch(1, 1)
        root.addLayout(clock_grid)

        countdown_cap = QLabel("倒數／Countdown")
        countdown_cap.setObjectName("pomodoroClockRow")
        countdown_cap.setMinimumHeight(24)
        root.addWidget(countdown_cap)

        # Frame owns border/background; inner QLabel is only the digits.
        display_frame = QFrame()
        display_frame.setObjectName("pomodoroDisplayFrame")
        display_frame.setMinimumHeight(110)
        display_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(16, 20, 16, 20)
        display_layout.setSpacing(0)
        self.display = QLabel(self._format_clock(self.remaining_seconds))
        self.display.setObjectName("pomodoroDisplay")
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        display_font = QFont("Consolas")
        if not display_font.exactMatch():
            display_font = QFont("Courier New")
        display_font.setStyleHint(QFont.StyleHint.TypeWriter)
        display_font.setPixelSize(40)
        display_font.setBold(True)
        self.display.setFont(display_font)
        self.display.setMinimumHeight(self.display.fontMetrics().lineSpacing() + 12)
        self.display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.display.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        display_layout.addWidget(self.display)
        root.addWidget(display_frame)

        self.progress = QProgressBar()
        self.progress.setObjectName("pomodoroProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # Mode A — duration presets + custom minutes (kept).
        duration_cap = QLabel("時長模式／Duration")
        duration_cap.setObjectName("pomodoroClockRow")
        root.addWidget(duration_cap)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for minutes in POMODORO_PRESETS:
            btn = QPushButton(f"{minutes} min")
            btn.setObjectName("calcAction")
            btn.clicked.connect(lambda checked=False, m=minutes: self._set_minutes(m))
            preset_row.addWidget(btn)
        custom_caption = QLabel("Custom (min)")
        custom_caption.setObjectName("calcFieldCaption")
        preset_row.addWidget(custom_caption)
        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(1, 600)
        self.minutes_spin.setValue(self.total_seconds // 60)
        self.minutes_spin.setFixedWidth(64)
        self.minutes_spin.valueChanged.connect(self._set_minutes)
        preset_row.addWidget(self.minutes_spin)
        preset_row.addStretch()
        root.addLayout(preset_row)

        # Mode B — wall-clock target; auto-compute seconds until that time.
        wall_cap = QLabel("鐘點模式／End at (wall clock)")
        wall_cap.setObjectName("pomodoroClockRow")
        root.addWidget(wall_cap)
        wall_row = QHBoxLayout()
        wall_row.setSpacing(4)
        self.wall_time_edit = QTimeEdit()
        self.wall_time_edit.setDisplayFormat("HH:mm:ss")
        self.wall_time_edit.setTime(datetime.now().time())
        self.wall_time_edit.setFixedWidth(110)
        wall_row.addWidget(self.wall_time_edit)
        apply_wall_btn = QPushButton("套用目標／Apply target")
        apply_wall_btn.setObjectName("pomodoroWideAction")
        apply_wall_btn.clicked.connect(self._apply_wall_target)
        wall_row.addWidget(apply_wall_btn)
        wall_row.addStretch()
        root.addLayout(wall_row)

        control_row = QHBoxLayout()
        control_row.setSpacing(4)
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        reset_btn = QPushButton("Reset")
        for btn in (self.start_btn, self.pause_btn, reset_btn):
            btn.setObjectName("calcAction")
            control_row.addWidget(btn)
        control_row.addStretch()
        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._pause)
        reset_btn.clicked.connect(self._reset)
        root.addLayout(control_row)

        self.status = QLabel("Ready · 時長模式／Duration")
        self.status.setObjectName("calcResult")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._on_clock_tick)
        self.clock_timer.start()
        self._refresh_clock_rows()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _format_clock(self, total_seconds):
        total_seconds = int(max(total_seconds, 0))
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_wall_time(when):
        return when.strftime("%H:%M:%S")

    def _resolve_wall_target(self, now=None):
        """Map QTimeEdit to the next datetime at that clock (today, or tomorrow if past)."""
        now = now or datetime.now()
        qtime = self.wall_time_edit.time()
        candidate = now.replace(
            hour=qtime.hour(),
            minute=qtime.minute(),
            second=qtime.second(),
            microsecond=0,
        )
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate

    def _seconds_until(self, target, now=None):
        now = now or datetime.now()
        return max(0, int((target - now).total_seconds()))

    def _on_clock_tick(self):
        # While idle in wall-clock mode, keep remaining aligned to the chosen end time.
        if (
            not self.running
            and self.mode == self.MODE_WALLCLOCK
            and self.target_end is not None
        ):
            secs = self._seconds_until(self.target_end)
            self.remaining_seconds = secs
            self.total_seconds = max(self.total_seconds, secs) if secs else self.total_seconds
            if secs <= 0:
                self.target_end = None
                self.status.setText("目標已過／Target passed — pick a new time")
        self._refresh()

    def _refresh_clock_rows(self):
        now = datetime.now()
        self.now_value.setText(self._format_wall_time(now))
        if self.target_end is not None and (
            self.running or self.mode == self.MODE_WALLCLOCK
        ):
            self.target_value.setText(self._format_wall_time(self.target_end))
        elif self.remaining_seconds > 0 and self.remaining_seconds < self.total_seconds:
            preview = now + timedelta(seconds=self.remaining_seconds)
            self.target_value.setText(
                f"{self._format_wall_time(preview)} (if resume／若繼續)"
            )
        else:
            self.target_value.setText("—")

    def _set_minutes(self, minutes):
        self.mode = self.MODE_DURATION
        self.total_seconds = int(minutes) * 60
        self.remaining_seconds = self.total_seconds
        self.target_end = None
        self._stop_ticking()
        self.minutes_spin.blockSignals(True)
        self.minutes_spin.setValue(int(minutes))
        self.minutes_spin.blockSignals(False)
        self._persist_minutes(int(minutes))
        self._refresh(reset_status=True)

    def _apply_wall_target(self):
        """Switch to wall-clock mode: remaining = now → chosen clock time."""
        if self.running:
            self.status.setText("請先暫停／Pause before changing target")
            return
        now = datetime.now()
        target = self._resolve_wall_target(now)
        secs = self._seconds_until(target, now)
        if secs <= 0:
            self.status.setText("目標須晚於現在／Target must be after now")
            return
        self.mode = self.MODE_WALLCLOCK
        self.target_end = target
        self.total_seconds = secs
        self.remaining_seconds = secs
        # Sync spin for display only (may exceed 600 for long waits — clamp UI spin).
        self.minutes_spin.blockSignals(True)
        self.minutes_spin.setValue(min(600, max(1, (secs + 59) // 60)))
        self.minutes_spin.blockSignals(False)
        self._stop_ticking()
        self.status.setText(
            f"鐘點模式／End at {self._format_wall_time(target)} "
            f"({self._format_clock(secs)} left／剩餘)"
        )
        self._refresh()

    def _persist_minutes(self, minutes):
        if self.cfg is not None:
            self.cfg.set(["pomodoro", "minutes"], int(minutes))

    def _start(self):
        if self.running:
            return
        if self.mode == self.MODE_WALLCLOCK:
            # Re-resolve so Start uses the live wall clock (and next-day if needed).
            now = datetime.now()
            target = self._resolve_wall_target(now)
            secs = self._seconds_until(target, now)
            if secs <= 0:
                self.status.setText("目標須晚於現在／Target must be after now")
                return
            self.target_end = target
            self.total_seconds = secs
            self.remaining_seconds = secs
        elif self.remaining_seconds <= 0:
            return
        else:
            self.target_end = datetime.now() + timedelta(seconds=self.remaining_seconds)
        self.running = True
        self.timer.start()
        self.status.setText(
            "Running… 鐘點模式／wall clock"
            if self.mode == self.MODE_WALLCLOCK
            else "Running… 時長模式／duration"
        )
        if self.mode == self.MODE_DURATION:
            self._persist_minutes(max(1, self.total_seconds // 60))
        self._refresh_clock_rows()
        self._refresh()

    def _pause(self):
        if not self.running:
            return
        self._stop_ticking()
        if self.mode != self.MODE_WALLCLOCK:
            self.target_end = None
        self.status.setText("Paused")
        self._refresh_clock_rows()

    def _reset(self):
        self._stop_ticking()
        if self.mode == self.MODE_WALLCLOCK:
            # Re-apply current wall edit as a fresh plan.
            self._apply_wall_target()
            return
        self.remaining_seconds = self.total_seconds
        self.target_end = None
        self._refresh(reset_status=True)

    def _stop_ticking(self):
        self.running = False
        self.timer.stop()

    def _tick(self):
        if self.mode == self.MODE_WALLCLOCK and self.target_end is not None:
            self.remaining_seconds = self._seconds_until(self.target_end)
        else:
            self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.remaining_seconds = 0
            self.target_end = None
            self._stop_ticking()
            self._on_finished()
        self._refresh()

    def _refresh(self, reset_status=False):
        self.display.setText(self._format_clock(self.remaining_seconds))
        elapsed = self.total_seconds - self.remaining_seconds
        self.progress.setValue(
            round(elapsed * 100.0 / self.total_seconds) if self.total_seconds else 0
        )
        self._refresh_clock_rows()
        if reset_status and not self.running:
            mode_zh = (
                "鐘點模式／wall clock"
                if self.mode == self.MODE_WALLCLOCK
                else "時長模式／Duration"
            )
            self.status.setText(f"Ready · {mode_zh}")

    def _on_finished(self):
        self.status.setText("Time is up!／時間到")
        self._refresh_clock_rows()
        QApplication.beep()
        tray = getattr(QApplication.instance(), "_tray_icon", None)
        if tray is not None:
            tray.showMessage(
                "Pomodoro",
                "Time is up.／時間到",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )



class TranslateError(Exception):
    """Raised with a user-facing (English) message when translation fails."""


def translate_text(text, target_lang, timeout=10):
    """
    Translate via Google Translate's public web endpoint (no API key).

    Uses translate.googleapis.com/translate_a/single?client=gtx with sl=auto
    (source auto-detect). Returns (translated_text, detected_lang).
    Raises TranslateError with a friendly message on network/HTTP problems.
    Request text is never printed or logged.
    """
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={quote(target_lang)}&dt=t&q={quote(text)}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise TranslateError("Too many requests, please try again later.") from exc
        raise TranslateError(f"Translation service error (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranslateError("Cannot reach the translation service, check the network and try again.") from exc
    except ValueError as exc:
        raise TranslateError("Unexpected translation service response format.") from exc

    segments = data[0] if isinstance(data, list) and data else None
    if not segments:
        raise TranslateError("Translation service returned no result.")
    translated = "".join(
        seg[0] for seg in segments if isinstance(seg, (list, tuple)) and seg and seg[0]
    )
    detected = ""
    if len(data) > 2 and isinstance(data[2], str):
        detected = data[2]
    return translated, detected


class _TranslateWorkerSignals(QObject):
    finished = Signal(int, str, str)   # request_id, translated text, detected lang
    failed = Signal(int, str)          # request_id, friendly error message


class _TranslateWorker(QRunnable):
    """Runs one web-translation request off the UI thread."""

    def __init__(self, request_id, text, target_lang):
        super().__init__()
        self.request_id = request_id
        self.text = text
        self.target_lang = target_lang
        self.signals = _TranslateWorkerSignals()

    def run(self):
        try:
            translated, detected = translate_text(self.text, self.target_lang)
            self.signals.finished.emit(self.request_id, translated, detected)
        except TranslateError as exc:
            self.signals.failed.emit(self.request_id, str(exc))
        except Exception:
            # Never surface or log the request text.
            self.signals.failed.emit(self.request_id, "Translation failed, please try again later.")


class TranslateDialog(FramelessCalcDialog):
    """Translate — text translation via the public web endpoint (no API key, no persistence)."""

    AUTO_DEBOUNCE_MS = 800
    CACHE_LIMIT = 8

    LANGUAGES = (
        ("zh-TW", "Chinese (Traditional)"),
        ("en", "English"),
        ("zh-CN", "Chinese (Simplified)"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("fr", "Français"),
        ("de", "Deutsch"),
        ("es", "Español"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate")
        self.setMinimumSize(520, 340)
        self.resize(560, 380)
        self.setStyleSheet(CALC_DIALOG_STYLE + MINI_PROGRAM_STYLE)
        root = install_ornate_calc_frame(self)
        root.setSpacing(6)

        root.addWidget(make_draggable_title(self, "Translate"))

        lang_row = QHBoxLayout()
        lang_row.setSpacing(4)
        lang_caption = QLabel("Target language")
        lang_caption.setObjectName("calcFieldCaption")
        lang_row.addWidget(lang_caption)
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("translateLang")
        for _code, label in self.LANGUAGES:
            self.lang_combo.addItem(label)
        self.lang_combo.setCurrentIndex(0)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.lang_combo)
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setObjectName("calcAction")
        self.translate_btn.clicked.connect(self._translate_now)
        lang_row.addWidget(self.translate_btn)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("calcAction")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_result)
        lang_row.addWidget(self.copy_btn)
        lang_row.addStretch()
        root.addLayout(lang_row)

        self.source_edit = QPlainTextEdit()
        self.source_edit.setObjectName("translateSource")
        self.source_edit.setPlaceholderText("Type text to translate… (auto-detect source)")
        self.source_edit.setFixedHeight(76)
        self.source_edit.textChanged.connect(self._on_source_changed)
        root.addWidget(self.source_edit)

        self.result = QLabel("Result will appear here")
        self.result.setObjectName("calcResult")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.result)

        root.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self.AUTO_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._translate_now)
        self._request_counter = 0
        self._pending_request = None
        # In-memory only; user text is never written to disk.
        self._cache = OrderedDict()

    def _lang_code(self):
        index = self.lang_combo.currentIndex()
        if 0 <= index < len(self.LANGUAGES):
            return self.LANGUAGES[index][0]
        return self.LANGUAGES[0][0]

    def _on_source_changed(self):
        if not self.source_edit.toPlainText().strip():
            self._debounce.stop()
            self.result.setText("Result will appear here")
            self.copy_btn.setEnabled(False)
            self._pending_request = None
            return
        self._debounce.start()

    def _on_language_changed(self, _index):
        if self.source_edit.toPlainText().strip():
            self._debounce.start()

    def _translate_now(self):
        text = self.source_edit.toPlainText().strip()
        if not text:
            return
        target = self._lang_code()
        cache_key = (text, target)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            self._show_result(*self._cache[cache_key])
            return
        self._request_counter += 1
        request_id = self._request_counter
        self._pending_request = request_id
        self.result.setText("Translating…")
        worker = _TranslateWorker(request_id, text, target)
        worker.signals.finished.connect(self._on_translated)
        worker.signals.failed.connect(self._on_translate_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_translated(self, request_id, translated, detected):
        if self._pending_request != request_id:
            return
        self._pending_request = None
        payload = (translated, detected)
        self._cache[(self.source_edit.toPlainText().strip(), self._lang_code())] = payload
        while len(self._cache) > self.CACHE_LIMIT:
            self._cache.popitem(last=False)
        self._show_result(translated, detected)

    def _on_translate_failed(self, request_id, message):
        if self._pending_request != request_id:
            return
        self._pending_request = None
        self.result.setText(message)
        self.copy_btn.setEnabled(False)

    def _show_result(self, translated, detected):
        lines = [f"◆ {translated}"]
        if detected:
            lines.append(f"(Detected language: {detected})")
        self.result.setText("\n".join(lines))
        self.copy_btn.setEnabled(bool(translated))

    def _copy_result(self):
        text = self.result.text().splitlines()
        if text and text[0].startswith("◆ "):
            QApplication.clipboard().setText(text[0][2:])


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
# Calculations submenu (third level under Mini programs)
# ---------------------------------------------------------------------------
class OperationsSubMenu(PopupPanel):
    """Third-level menu: Level / Slope / Free station / Alignment(1)/(2)."""

    def __init__(self, config_manager=None):
        super().__init__()
        self.cfg = config_manager
        self._level_dialog = None
        self._slope_dialog = None
        self._free_station_dialog = None
        self._alignment_dialog = None
        self._alignment2_dialog = None
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

        title = QLabel("Calculations")
        title.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(title)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        layout.addWidget(sep)

        btn_level = QPushButton("Level calc")
        btn_level.setStyleSheet(menu_button_style("#5a4a6e"))
        btn_level.clicked.connect(self.open_level_calc)
        layout.addWidget(btn_level)

        btn_slope = QPushButton("Slope calc")
        btn_slope.setStyleSheet(menu_button_style("#4a5a6e"))
        btn_slope.clicked.connect(self.open_slope_calc)
        layout.addWidget(btn_slope)

        btn_free_station = QPushButton("Free station")
        btn_free_station.setStyleSheet(menu_button_style("#6e5a4a"))
        btn_free_station.clicked.connect(self.open_free_station)
        layout.addWidget(btn_free_station)

        btn_alignment = QPushButton("Alignment(1)")
        btn_alignment.setStyleSheet(menu_button_style("#4a6e5a"))
        btn_alignment.clicked.connect(self.open_alignment)
        layout.addWidget(btn_alignment)

        btn_alignment2 = QPushButton("Alignment(2)")
        btn_alignment2.setStyleSheet(menu_button_style("#3a6e6a"))
        btn_alignment2.clicked.connect(self.open_alignment2)
        layout.addWidget(btn_alignment2)

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

    def open_free_station(self):
        self._suppress_hide = True
        if self._free_station_dialog is None:
            self._free_station_dialog = FreeStationDialog(self.cfg, None)
        self._free_station_dialog.show()
        self._free_station_dialog.raise_()
        self._free_station_dialog.activateWindow()
        QTimer.singleShot(200, self._release_suppress)

    def open_alignment(self):
        self._suppress_hide = True
        if self._alignment_dialog is None:
            self._alignment_dialog = AlignmentCalcDialog(None)
        self._alignment_dialog.show()
        self._alignment_dialog.raise_()
        self._alignment_dialog.activateWindow()
        QTimer.singleShot(200, self._release_suppress)

    def open_alignment2(self):
        self._suppress_hide = True
        if self._alignment2_dialog is None:
            self._alignment2_dialog = Alignment2CalcDialog(None)
        self._alignment2_dialog.show()
        self._alignment2_dialog.raise_()
        self._alignment2_dialog.activateWindow()
        QTimer.singleShot(200, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def _hide_if_inactive(self):
        if self._suppress_hide or self.isActiveWindow():
            return
        active = QApplication.activeWindow()
        if isinstance(
            active,
            (
                LevelCalcDialog,
                SlopeCalcDialog,
                FreeStationDialog,
                AlignmentCalcDialog,
                Alignment2CalcDialog,
            ),
        ):
            return
        if self._level_dialog is not None and self._level_dialog.isVisible():
            return
        if self._slope_dialog is not None and self._slope_dialog.isVisible():
            return
        if self._free_station_dialog is not None and self._free_station_dialog.isVisible():
            return
        if self._alignment_dialog is not None and self._alignment_dialog.isVisible():
            return
        if self._alignment2_dialog is not None and self._alignment2_dialog.isVisible():
            return
        self.hide()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Particle Network — Mini programs panel ambient (theme steel-blue palette)
# ---------------------------------------------------------------------------
# 「粒子連線（Particle Network）」: Qt take on Canvas 2D + rAF + DPR demos.
# Particles drift & bounce; nearby pairs link (opacity ∝ distance); cursor
# attracts nearby dots and draws links. Layering (top→bottom):
#   text → program button solid fills → particle canvas → translucent panel bg
PARTICLE_COUNT = 48
PARTICLE_LINK_DIST = 72.0
PARTICLE_CURSOR_DIST = 96.0
PARTICLE_CURSOR_PULL = 0.045
PARTICLE_DOT = QColor(232, 242, 248, 200)         # light sky
PARTICLE_DOT_CORE = QColor(255, 255, 255, 230)
PARTICLE_LINK = QColor(135, 206, 250, 160)        # menu border sky
PARTICLE_CURSOR_LINK = QColor(176, 224, 255, 200)


class ParticleNetworkCanvas(QWidget):
    """HiDPI particle-network layer (QPainter ≈ Canvas2D, QTimer ≈ rAF)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._particles: list[dict] = []
        self._cursor: QPointF | None = None
        self._seeded = False
        self._buf: QImage | None = None
        self._buf_w = 0
        self._buf_h = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps requestAnimationFrame stand-in
        self._timer.timeout.connect(self._tick)

    def _ensure_particles(self, w: float, h: float) -> None:
        if self._seeded and self._particles:
            return
        self._particles = []
        for i in range(PARTICLE_COUNT):
            self._particles.append(
                {
                    "x": random.uniform(4.0, max(5.0, w - 4.0)),
                    "y": random.uniform(4.0, max(5.0, h - 4.0)),
                    "vx": random.uniform(-0.55, 0.55),
                    "vy": random.uniform(-0.55, 0.55),
                    "r": random.uniform(1.3, 2.4),
                }
            )
        self._seeded = True

    def _sync_buffer(self, logical_w: int, logical_h: int) -> tuple[QImage, float]:
        dpr = float(self.devicePixelRatioF())
        bw = max(1, int(math.ceil(logical_w * dpr)))
        bh = max(1, int(math.ceil(logical_h * dpr)))
        if (
            self._buf is None
            or self._buf_w != bw
            or self._buf_h != bh
            or self._buf.isNull()
        ):
            self._buf = QImage(bw, bh, QImage.Format.Format_ARGB32_Premultiplied)
            self._buf.setDevicePixelRatio(dpr)
            self._buf_w = bw
            self._buf_h = bh
        return self._buf, dpr

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _poll_cursor(self) -> None:
        # Poll global cursor (canvas ignores mouse so buttons stay clickable).
        local = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(local):
            self._cursor = QPointF(float(local.x()), float(local.y()))
        else:
            self._cursor = None

    def _tick(self) -> None:
        w = float(max(1, self.width()))
        h = float(max(1, self.height()))
        self._ensure_particles(w, h)
        self._poll_cursor()
        cur = self._cursor

        for p in self._particles:
            if cur is not None:
                dx = cur.x() - p["x"]
                dy = cur.y() - p["y"]
                dist = math.hypot(dx, dy)
                if 0.5 < dist < PARTICLE_CURSOR_DIST:
                    # Soft attract toward cursor.
                    pull = PARTICLE_CURSOR_PULL * (1.0 - dist / PARTICLE_CURSOR_DIST)
                    p["vx"] += dx / dist * pull
                    p["vy"] += dy / dist * pull

            # Light damping so attract doesn't runaway.
            p["vx"] *= 0.992
            p["vy"] *= 0.992
            # Keep a minimum drift so the field never freezes.
            speed = math.hypot(p["vx"], p["vy"])
            if speed < 0.12:
                ang = random.uniform(0.0, 2.0 * math.pi)
                p["vx"] += 0.08 * math.cos(ang)
                p["vy"] += 0.08 * math.sin(ang)
            elif speed > 1.35:
                p["vx"] *= 1.35 / speed
                p["vy"] *= 1.35 / speed

            p["x"] += p["vx"]
            p["y"] += p["vy"]

            # Bounce off edges.
            if p["x"] < 2.0:
                p["x"] = 2.0
                p["vx"] = abs(p["vx"])
            elif p["x"] > w - 2.0:
                p["x"] = w - 2.0
                p["vx"] = -abs(p["vx"])
            if p["y"] < 2.0:
                p["y"] = 2.0
                p["vy"] = abs(p["vy"])
            elif p["y"] > h - 2.0:
                p["y"] = h - 2.0
                p["vy"] = -abs(p["vy"])

        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        lw = max(1, self.width())
        lh = max(1, self.height())
        self._ensure_particles(float(lw), float(lh))
        buf, dpr = self._sync_buffer(lw, lh)
        buf.fill(Qt.GlobalColor.transparent)

        painter = QPainter(buf)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Draw in logical pixels; QImage DPR handles device pixels.
        painter.scale(dpr, dpr)

        pts = self._particles
        n = len(pts)
        # Pair links — opacity by distance.
        for i in range(n):
            a = pts[i]
            for j in range(i + 1, n):
                b = pts[j]
                dx = a["x"] - b["x"]
                dy = a["y"] - b["y"]
                dist = math.hypot(dx, dy)
                if dist > PARTICLE_LINK_DIST or dist < 0.01:
                    continue
                alpha = int(PARTICLE_LINK.alpha() * (1.0 - dist / PARTICLE_LINK_DIST))
                if alpha < 8:
                    continue
                col = QColor(PARTICLE_LINK)
                col.setAlpha(alpha)
                pen = QPen(col)
                pen.setWidthF(1.0)
                painter.setPen(pen)
                painter.drawLine(QPointF(a["x"], a["y"]), QPointF(b["x"], b["y"]))

        # Cursor links + attract halo.
        cur = self._cursor
        if cur is not None:
            for p in pts:
                dx = p["x"] - cur.x()
                dy = p["y"] - cur.y()
                dist = math.hypot(dx, dy)
                if dist > PARTICLE_CURSOR_DIST or dist < 0.01:
                    continue
                alpha = int(
                    PARTICLE_CURSOR_LINK.alpha()
                    * (1.0 - dist / PARTICLE_CURSOR_DIST)
                )
                if alpha < 10:
                    continue
                col = QColor(PARTICLE_CURSOR_LINK)
                col.setAlpha(alpha)
                pen = QPen(col)
                pen.setWidthF(1.15)
                painter.setPen(pen)
                painter.drawLine(cur, QPointF(p["x"], p["y"]))

        # Dots
        painter.setPen(Qt.PenStyle.NoPen)
        for p in pts:
            r = p["r"]
            painter.setBrush(PARTICLE_DOT)
            painter.drawEllipse(QPointF(p["x"], p["y"]), r, r)
            painter.setBrush(PARTICLE_DOT_CORE)
            painter.drawEllipse(QPointF(p["x"], p["y"]), r * 0.45, r * 0.45)

        painter.end()

        screen = QPainter(self)
        screen.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        screen.drawImage(0, 0, buf)
        screen.end()


# ---------------------------------------------------------------------------
# Shine Sweep Button — metal/glass glint on solid Mini-program tiles
# ---------------------------------------------------------------------------
# 「光澤掃過按鈕（Shine Sweep Button）」: Qt take on CSS overflow:hidden +
# ::after skewX(-20deg) gradient band sweeping left→right (~2.4s idle;
# faster on hover) with slight lift + deeper shadow.
SHINE_IDLE_MS = 2400
SHINE_HOVER_MS = 900
SHINE_LIFT_PX = 3.0
SHINE_BAND_FRAC = 0.32
SHINE_SKEW_DEG = -20.0
SHINE_BTN_H = 28
SHINE_RADIUS = 6.0


def _qcolor_from_hex(hex_color: str, alpha: int = 255) -> QColor:
    text = (hex_color or "").strip().lstrip("#")
    if len(text) != 6:
        return QColor(74, 74, 74, alpha)
    try:
        return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)
    except ValueError:
        return QColor(74, 74, 74, alpha)


class ShineSweepButton(QWidget):
    """Opaque solid tile with a looping diagonal shine sweep."""

    clicked = Signal()

    def __init__(self, text: str, base_color: str, parent=None):
        super().__init__(parent)
        self._text = text or ""
        self._base = _qcolor_from_hex(base_color, 255)
        self._hover_fill = _qcolor_from_hex(darken_color(base_color, 0.72), 255)
        self._hovering = False
        self._lift_t = 0.0  # 0 idle → 1 full hover lift
        self.setMinimumHeight(SHINE_BTN_H + int(SHINE_LIFT_PX) + 2)
        self.setMinimumWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._lift_anim = QPropertyAnimation(self, b"liftProgress", self)
        self._lift_anim.setDuration(180)
        self._lift_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)

    def _get_lift_progress(self) -> float:
        return self._lift_t

    def _set_lift_progress(self, value: float) -> None:
        self._lift_t = max(0.0, min(1.0, float(value)))
        self.update()

    liftProgress = Property(float, _get_lift_progress, _set_lift_progress)

    def showEvent(self, event) -> None:  # noqa: N802
        if not self._elapsed.isValid():
            self._elapsed.start()
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovering = True
        self._lift_anim.stop()
        self._lift_anim.setStartValue(self._lift_t)
        self._lift_anim.setEndValue(1.0)
        self._lift_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovering = False
        self._lift_anim.stop()
        self._lift_anim.setStartValue(self._lift_t)
        self._lift_anim.setEndValue(0.0)
        self._lift_anim.start()
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

    def _shine_progress(self) -> float:
        period = SHINE_HOVER_MS if self._hovering else SHINE_IDLE_MS
        if not self._elapsed.isValid() or period <= 0:
            return 0.0
        return (self._elapsed.elapsed() % period) / float(period)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        w = float(self.width())
        h = float(self.height())
        lift = self._lift_t * SHINE_LIFT_PX
        btn_h = float(SHINE_BTN_H)
        # Button rests near the bottom; hover lifts it (paint-only).
        top = h - btn_h - 1.0 - lift
        rect = QRectF(0.5, top, w - 1.0, btn_h)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Soft shadow under the tile (deepens with lift).
        if self._lift_t > 0.01:
            shadow = QColor(0, 0, 0, int(40 + 70 * self._lift_t))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow)
            painter.drawRoundedRect(
                QRectF(rect.left() + 1.0, rect.top() + lift + 2.5, rect.width(), rect.height()),
                SHINE_RADIUS,
                SHINE_RADIUS,
            )

        # Clip = overflow:hidden
        clip = QPainterPath()
        clip.addRoundedRect(rect, SHINE_RADIUS, SHINE_RADIUS)
        painter.setClipPath(clip)

        fill = self._hover_fill if self._hovering else self._base
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, SHINE_RADIUS, SHINE_RADIUS)

        # Diagonal shine band (skewX ≈ -20°), sweeps left → right.
        t = self._shine_progress()
        band_w = max(18.0, rect.width() * SHINE_BAND_FRAC)
        # Travel from fully left of tile to fully right.
        x = rect.left() - band_w + t * (rect.width() + 2.0 * band_w)
        painter.save()
        painter.translate(x + band_w * 0.5, rect.center().y())
        painter.shear(math.tan(math.radians(SHINE_SKEW_DEG)), 0.0)
        grad = QLinearGradient(-band_w * 0.5, 0.0, band_w * 0.5, 0.0)
        peak = QColor(255, 255, 255, 95 if self._hovering else 70)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.45, peak)
        grad.setColorAt(0.55, peak)
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(-band_w * 0.5, -rect.height(), band_w, rect.height() * 2.0))
        painter.restore()

        painter.setClipping(False)

        # Label — match menu QPushButton (white, left, padded).
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        text_rect = QRectF(rect.left() + 7.0, rect.top(), rect.width() - 14.0, rect.height())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )
        painter.end()


class MiniProgramsSubMenu(PopupPanel):
    """Second-level menu under Mini programs: Text records + Calculations."""

    def __init__(self, config_manager):
        super().__init__()
        self.cfg = config_manager
        self.text_records_submenu = None
        self.operations_submenu = None
        self.pomodoro_dialog = None
        self.translate_dialog = None
        self.hakoniwa_dialog = None
        self.fish_tank_dialog = None
        self.build_ui()

    def build_ui(self):
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # Layering top→bottom: content (text/buttons) > particles > panel bg
        self.container = QFrame(self)
        self.container.setObjectName("subMenuContainer")
        top_layout.addWidget(self.container)

        self.particles = ParticleNetworkCanvas(self.container)
        self.particles.lower()

        self.content = QWidget(self.container)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content.setStyleSheet("background: transparent;")
        self.content.raise_()

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = SoftGlowTitleLabel(MINI_PROGRAMS_TITLE, self.content)
        layout.addWidget(title)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,120);")
        layout.addWidget(sep)

        # Text records / Calculations — Folder Shortcuts List Row Fill (no shine).
        self.btn_text_records = ListRowFillItem(1, "Text records", self.content)
        self.btn_text_records.clicked.connect(self.open_text_records)
        layout.addWidget(self.btn_text_records)

        self.btn_calculations = ListRowFillItem(2, "Calculations", self.content)
        self.btn_calculations.clicked.connect(self.open_operations)
        layout.addWidget(self.btn_calculations)

        # Solid Mini-program tiles — Shine Sweep (existing tile colors kept).
        self.btn_pomodoro = ShineSweepButton("Pomodoro", "#6e4a2a", self.content)
        self.btn_pomodoro.clicked.connect(self.open_pomodoro)
        layout.addWidget(self.btn_pomodoro)

        self.btn_translate = ShineSweepButton("Translate", "#2a5a4a", self.content)
        self.btn_translate.clicked.connect(self.open_translate)
        layout.addWidget(self.btn_translate)

        # Marked unfinished per user 2026-11-02 — keep entry, show WIP clearly.
        self.btn_hakoniwa = ShineSweepButton(
            "箱庭島（未完成）／Hakoniwa (WIP)", "#2a4a6e", self.content
        )
        self.btn_hakoniwa.clicked.connect(self.open_hakoniwa)
        layout.addWidget(self.btn_hakoniwa)

        # Transparent Fish Tank — below 箱庭島; marked unfinished (2026-11-02).
        self.btn_fish_tank = ShineSweepButton(
            "透明魚缸（未完成）／Fish Tank (WIP)", "#1a5a6e", self.content
        )
        self.btn_fish_tank.clicked.connect(self.open_fish_tank)
        layout.addWidget(self.btn_fish_tank)

        self.setStyleSheet(MENU_STYLE + """
            MiniProgramsSubMenu { background-color: transparent; }
        """)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layers()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_layers()
        self.particles.start()

    def _sync_layers(self) -> None:
        if not hasattr(self, "container"):
            return
        r = self.container.rect()
        self.particles.setGeometry(r)
        self.content.setGeometry(r)
        self.particles.lower()
        self.content.raise_()

    def refresh_and_show(self, anchor_geometry):
        self.content.adjustSize()
        # Size the panel from the content layout, not the empty container.
        hint = self.content.sizeHint()
        margins = 0
        self.container.setFixedSize(
            max(hint.width(), 220),
            max(hint.height(), 160),
        )
        self.adjustSize()
        self._sync_layers()
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
        self.particles.start()

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
            self.operations_submenu = OperationsSubMenu(self.cfg)
        self._hide_nested(keep="ops")
        self._suppress_hide = True
        self.operations_submenu.refresh_and_show(self.geometry())
        QTimer.singleShot(300, self._release_suppress)

    def open_pomodoro(self):
        self._suppress_hide = True
        if self.pomodoro_dialog is None:
            self.pomodoro_dialog = PomodoroDialog(self.cfg, None)
        self.pomodoro_dialog.show()
        self.pomodoro_dialog.raise_()
        self.pomodoro_dialog.activateWindow()
        QTimer.singleShot(300, self._release_suppress)

    def open_translate(self):
        self._suppress_hide = True
        if self.translate_dialog is None:
            self.translate_dialog = TranslateDialog(None)
        self.translate_dialog.show()
        self.translate_dialog.raise_()
        self.translate_dialog.activateWindow()
        QTimer.singleShot(300, self._release_suppress)

    def open_hakoniwa(self):
        self._suppress_hide = True
        if self.hakoniwa_dialog is None:
            from hakoniwa import HakoniwaIslandDialog

            self.hakoniwa_dialog = HakoniwaIslandDialog(self.cfg, None)
        self.hakoniwa_dialog.show()
        self.hakoniwa_dialog.raise_()
        self.hakoniwa_dialog.activateWindow()
        QTimer.singleShot(300, self._release_suppress)

    def open_fish_tank(self):
        self._suppress_hide = True
        if self.fish_tank_dialog is None:
            from fish_tank import FishTankDialog

            self.fish_tank_dialog = FishTankDialog(self.cfg, None)
        self.fish_tank_dialog.show()
        self.fish_tank_dialog.raise_()
        self.fish_tank_dialog.activateWindow()
        QTimer.singleShot(300, self._release_suppress)

    def _release_suppress(self):
        self._suppress_hide = False

    def hideEvent(self, event):
        if hasattr(self, "particles"):
            self.particles.stop()
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
        try:
            from hakoniwa import HakoniwaIslandDialog as _HakoniwaIslandDialog
        except Exception:
            _HakoniwaIslandDialog = type(None)
        try:
            from fish_tank import FishTankDialog as _FishTankDialog
            from fish_tank.dialog import CaptureCardDialog as _CaptureCardDialog
        except Exception:
            _FishTankDialog = type(None)
            _CaptureCardDialog = type(None)
        if isinstance(
            active,
            (
                TextRecordsSubMenu,
                TextRecordViewDialog,
                OperationsSubMenu,
                LevelCalcDialog,
                SlopeCalcDialog,
                FreeStationDialog,
                AlignmentCalcDialog,
                Alignment2CalcDialog,
                PomodoroDialog,
                TranslateDialog,
                _HakoniwaIslandDialog,
                _FishTankDialog,
                _CaptureCardDialog,
            ),
        ):
            return
        self.hide()


# ---------------------------------------------------------------------------
# Float Drift — dreamy per-character title motion (theme steel-blue palette)
# ---------------------------------------------------------------------------
# 「漂浮（Float Drift）」: each glyph drifts up/down/left/right at its own
# speed (~3–4.5s cycle), with a slight rotation and soft sky glow.
FOLDER_SHORTCUTS_TITLE = "Folder Shortcuts フォルダー ショートカット"
FLOAT_DRIFT_TEXT = QColor(255, 255, 255)
FLOAT_DRIFT_GLOW = QColor(135, 206, 250, 100)     # menu border sky
FLOAT_DRIFT_GLOW_SOFT = QColor(176, 224, 255, 55)
FLOAT_DRIFT_PAD_X = 6.0
FLOAT_DRIFT_PAD_Y = 5.0


class FloatDriftLabel(QWidget):
    """Title label: each character floats independently (Float Drift)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text or ""
        self._chars = list(self._text)
        self._params = []
        for i, _ch in enumerate(self._chars):
            # Periods spread across 3.0–4.5s; phases staggered for a dreamy feel.
            period = 3.0 + ((i * 0.41) % 1.5)
            phase = (i * 1.6180339887) % (2.0 * math.pi)
            phase2 = (i * 2.399) % (2.0 * math.pi)
            amp_x = 1.2 + (i % 5) * 0.35
            amp_y = 1.8 + (i % 4) * 0.45
            amp_rot = 3.5 + (i % 3) * 2.0  # degrees
            self._params.append(
                {
                    "period": period,
                    "phase": phase,
                    "phase2": phase2,
                    "amp_x": amp_x,
                    "amp_y": amp_y,
                    "amp_rot": amp_rot,
                    # Slightly different horizontal vs vertical tempo.
                    "period_y": 3.0 + ((i * 0.53) % 1.5),
                }
            )

        font = QFont(self.font())
        font.setFamily("Microsoft JhengHei")
        font.setPointSize(9)
        font.setBold(True)
        self._font = font

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._recompute_size()

        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps — soft, not frantic
        self._timer.timeout.connect(self.update)

    def _recompute_size(self) -> None:
        fm = QFontMetrics(self._font)
        width = sum(fm.horizontalAdvance(ch) for ch in self._chars)
        # Room for drift + glow halo.
        self.setMinimumHeight(int(fm.height() + FLOAT_DRIFT_PAD_Y * 2 + 6))
        self.setMinimumWidth(int(width + FLOAT_DRIFT_PAD_X * 2 + 8))
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        return QSize(self.minimumWidth(), self.minimumHeight())

    def showEvent(self, event) -> None:  # noqa: N802
        if not self._elapsed.isValid():
            self._elapsed.start()
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        t_sec = (self._elapsed.elapsed() / 1000.0) if self._elapsed.isValid() else 0.0

        x = FLOAT_DRIFT_PAD_X
        base_y = FLOAT_DRIFT_PAD_Y + fm.ascent() + 2.0

        for ch, p in zip(self._chars, self._params):
            advance = float(fm.horizontalAdvance(ch))
            if ch == " ":
                x += advance
                continue

            ang_x = (2.0 * math.pi * t_sec / p["period"]) + p["phase"]
            ang_y = (2.0 * math.pi * t_sec / p["period_y"]) + p["phase2"]
            dx = p["amp_x"] * math.sin(ang_x)
            dy = p["amp_y"] * math.sin(ang_y)
            # Soft secondary sway so paths feel less circular.
            dx += 0.4 * p["amp_x"] * math.sin(ang_y * 0.7 + 0.5)
            dy += 0.35 * p["amp_y"] * math.cos(ang_x * 0.85)
            rot = p["amp_rot"] * math.sin(ang_x * 0.9 + p["phase2"])

            cx = x + advance * 0.5 + dx
            cy = base_y + dy

            painter.save()
            painter.translate(cx, cy)
            painter.rotate(rot)

            # Soft glow (outer sky → inner), then solid glyph.
            draw_title_soft_glow(painter, ch, advance, 1.0)

            painter.setPen(FLOAT_DRIFT_TEXT)
            painter.drawText(QPointF(-advance * 0.5, 0.0), ch)
            painter.restore()

            x += advance

        painter.end()


# ---------------------------------------------------------------------------
# List Row Fill — folder-shortcut row (theme steel-blue palette)
# ---------------------------------------------------------------------------
# Qt take on CSS “List Row Fill”:
# - Row: index number · name · right arrow; thin divider under each row
# - Hover (~0.5s): solid fill scaleX 0→1 from left origin; name shifts right;
#   arrow slides in from the left; text color inverts
# - Leave: fill scaleX 1→0 with origin on the right (exits to the right)
LIST_ROW_IDLE_BG = QColor(61, 90, 128, 230)       # #3d5a80 (folder btn)
LIST_ROW_FILL = QColor(232, 242, 248, 245)        # light sky (menu border family)
LIST_ROW_TEXT_IDLE = QColor(255, 255, 255)
LIST_ROW_TEXT_ON = QColor(42, 58, 74)             # dark steel on light fill
LIST_ROW_DIVIDER = QColor(135, 206, 250, 110)     # menu border sky, soft
LIST_ROW_ANIM_MS = 500
LIST_ROW_NAME_SHIFT = 10.0
LIST_ROW_ARROW_SLIDE = 18.0
LIST_ROW_HEIGHT = 28


class ListRowFillItem(QWidget):
    """One Folder-shortcuts row with List Row Fill hover."""

    clicked = Signal()

    def __init__(self, index: int, name: str, parent=None):
        super().__init__(parent)
        self._index = int(index)
        self._name = name or "Unnamed"
        self._hover_t = 0.0
        self._origin_left = True  # enter: left; leave: right
        self.setFixedHeight(LIST_ROW_HEIGHT)
        self.setMinimumWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(LIST_ROW_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

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
        w = float(self.width())
        h = float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Idle face
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(LIST_ROW_IDLE_BG)
        painter.drawRect(QRectF(0, 0, w, h))

        # Solid fill — enter: scaleX from left; leave: scaleX toward right
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
        font.setPointSize(9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        pad_l = 8.0
        pad_r = 10.0
        num_w = float(fm.horizontalAdvance("00"))
        arrow = "→"
        arrow_w = float(fm.horizontalAdvance(arrow))
        baseline = (h + fm.ascent() - fm.descent()) * 0.5

        num_text = f"{self._index:02d}"
        name_x = pad_l + num_w + 10.0 + LIST_ROW_NAME_SHIFT * t
        name_right = w - pad_r - arrow_w - 8.0
        name_max = max(20.0, name_right - name_x)
        elided = fm.elidedText(self._name, Qt.TextElideMode.ElideRight, int(name_max))
        arrow_rest_x = w - pad_r - arrow_w
        arrow_x = arrow_rest_x - LIST_ROW_ARROW_SLIDE * (1.0 - t)
        arrow_alpha = int(40 + 215 * t)

        def _draw_row_text(color: QColor) -> None:
            painter.setPen(color)
            painter.drawText(QPointF(pad_l, baseline), num_text)
            painter.drawText(QPointF(name_x, baseline), elided)
            ac = QColor(color)
            ac.setAlpha(min(255, arrow_alpha))
            painter.setPen(ac)
            painter.drawText(QPointF(arrow_x, baseline), arrow)

        # Idle (light) text on uncovered area; inverted (dark) text clipped to fill
        if fill_rect.width() > 0.5:
            # Uncovered = full row minus fill
            uncovered = QPainterPath()
            uncovered.addRect(QRectF(0.0, 0.0, w, h))
            filled = QPainterPath()
            filled.addRect(fill_rect)
            uncovered = uncovered.subtracted(filled)
            painter.setClipPath(uncovered)
            _draw_row_text(LIST_ROW_TEXT_IDLE)
            painter.setClipPath(filled)
            _draw_row_text(LIST_ROW_TEXT_ON)
            painter.setClipping(False)
        else:
            _draw_row_text(LIST_ROW_TEXT_IDLE)

        # Thin divider along the bottom edge
        painter.setPen(QPen(LIST_ROW_DIVIDER, 1.0))
        y = h - 0.5
        painter.drawLine(QPointF(0.0, y), QPointF(w, y))
        painter.end()


# ---------------------------------------------------------------------------
# Menu Social Icon Fill — first-page circular nav (theme steel-blue palette)
# ---------------------------------------------------------------------------
# Qt take on CSS “Social Icon Fill” (same motion as fish_tank/social_toolbar):
# - Circular outline + centered line icon
# - Hover (~0.45s): solid fill rises from bottom; idle icon slides up out;
#   inverted icon slides up from below; button lifts; leave reverses.
MENU_SIF_OUTLINE = QColor(135, 206, 250, 200)       # menu border sky
MENU_SIF_OUTLINE_HOVER = QColor(176, 224, 255, 230)
MENU_SIF_ICON_IDLE = QColor(232, 242, 248)          # light on glass
MENU_SIF_ICON_ON = QColor(42, 58, 74)               # dark steel on light fill
MENU_SIF_FILL = QColor(232, 242, 248, 245)          # light sky fill
MENU_SIF_BG_IDLE = QColor(61, 90, 128, 90)          # soft #3d5a80 glass
MENU_SIF_BTN_SIZE = 44
MENU_SIF_ANIM_MS = 450
MENU_SIF_LIFT_PX = 5.0


def _menu_sif_pen(color: QColor, width: float = 1.8) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_menu_icon_shortcut(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Diagonal NE shortcut arrow (line icon; matches shortcut-arrow ref)."""
    p.setPen(_menu_sif_pen(color, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Shaft: lower-left → upper-right
    x0, y0 = c.x() - r * 0.42, c.y() + r * 0.42
    x1, y1 = c.x() + r * 0.38, c.y() - r * 0.38
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    # Arrowhead
    head = r * 0.42
    p.drawLine(QPointF(x1, y1), QPointF(x1 - head, y1))
    p.drawLine(QPointF(x1, y1), QPointF(x1, y1 + head))


def draw_menu_icon_document(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Paper / document page with folded corner + lines."""
    p.setPen(_menu_sif_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    left = c.x() - r * 0.4
    top = c.y() - r * 0.5
    w = r * 0.8
    h = r * 1.0
    fold = r * 0.28
    path = QPainterPath()
    path.moveTo(left, top)
    path.lineTo(left + w - fold, top)
    path.lineTo(left + w, top + fold)
    path.lineTo(left + w, top + h)
    path.lineTo(left, top + h)
    path.closeSubpath()
    p.drawPath(path)
    # Fold lines
    p.drawLine(
        QPointF(left + w - fold, top),
        QPointF(left + w - fold, top + fold),
    )
    p.drawLine(
        QPointF(left + w - fold, top + fold),
        QPointF(left + w, top + fold),
    )
    # Text lines
    for i in range(3):
        y = c.y() - r * 0.08 + i * r * 0.22
        p.drawLine(
            QPointF(c.x() - r * 0.28, y),
            QPointF(c.x() + r * 0.22, y),
        )


def draw_menu_icon_calculator(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Calculator — mini programs."""
    p.setPen(_menu_sif_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    body = QRectF(c.x() - r * 0.45, c.y() - r * 0.55, r * 0.9, r * 1.1)
    p.drawRoundedRect(body, 3.0, 3.0)
    # Display
    disp = QRectF(c.x() - r * 0.32, c.y() - r * 0.42, r * 0.64, r * 0.28)
    p.drawRoundedRect(disp, 2.0, 2.0)
    # Button grid 3×3 dots/rects
    for row in range(3):
        for col in range(3):
            bx = c.x() - r * 0.28 + col * r * 0.28
            by = c.y() - r * 0.02 + row * r * 0.26
            p.drawRoundedRect(QRectF(bx - r * 0.08, by - r * 0.08, r * 0.16, r * 0.16), 1.5, 1.5)


def draw_menu_icon_gear(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
    """Settings gear."""
    p.setPen(_menu_sif_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Outer ring
    p.drawEllipse(QRectF(c.x() - r * 0.32, c.y() - r * 0.32, r * 0.64, r * 0.64))
    # Hub
    p.drawEllipse(QRectF(c.x() - r * 0.12, c.y() - r * 0.12, r * 0.24, r * 0.24))
    # Teeth (8 radial ticks)
    for i in range(8):
        ang = i * (math.pi / 4.0)
        inner = r * 0.38
        outer = r * 0.58
        p.drawLine(
            QPointF(c.x() + inner * math.cos(ang), c.y() + inner * math.sin(ang)),
            QPointF(c.x() + outer * math.cos(ang), c.y() + outer * math.sin(ang)),
        )


MENU_SIF_DRAWERS = {
    "shortcut": draw_menu_icon_shortcut,
    "document": draw_menu_icon_document,
    "calculator": draw_menu_icon_calculator,
    "gear": draw_menu_icon_gear,
}


class MenuSocialIconFillButton(QWidget):
    """One circular Social Icon Fill control for the pet main menu."""

    clicked = Signal()

    def __init__(self, icon_key: str, tip: str, parent=None):
        super().__init__(parent)
        self.icon_key = icon_key
        self._drawer = MENU_SIF_DRAWERS[icon_key]
        self._hover_t = 0.0
        self.setFixedSize(
            MENU_SIF_BTN_SIZE,
            MENU_SIF_BTN_SIZE + int(MENU_SIF_LIFT_PX) + 2,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(MENU_SIF_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _get_hover_progress(self) -> float:
        return self._hover_t

    def _set_hover_progress(self, value: float) -> None:
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_t)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate_to(0.0)
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
        lift = t * MENU_SIF_LIFT_PX
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        size = float(MENU_SIF_BTN_SIZE)
        rect = QRectF(
            0.5,
            float(self.height() - MENU_SIF_BTN_SIZE) + 0.5,
            size - 1.0,
            size - 1.0,
        )
        rect.translate(0.0, -lift)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(MENU_SIF_BG_IDLE)
        painter.drawEllipse(rect)

        clip = QPainterPath()
        clip.addEllipse(rect)
        painter.setClipPath(clip)

        if t > 0.001:
            h = rect.height()
            fill_top = rect.top() + h * (1.0 - t)
            fill_rect = QRectF(rect.left() - 1, fill_top, rect.width() + 2, h * t + 3)
            painter.setBrush(MENU_SIF_FILL)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(fill_rect)

        center = rect.center()
        icon_r = size * 0.30
        idle_y = center.y() - t * rect.height()
        hover_y = center.y() + (1.0 - t) * rect.height()
        self._drawer(painter, QPointF(center.x(), idle_y), icon_r, MENU_SIF_ICON_IDLE)
        self._drawer(painter, QPointF(center.x(), hover_y), icon_r, MENU_SIF_ICON_ON)

        painter.setClipping(False)

        pen = QPen(MENU_SIF_OUTLINE_HOVER if t > 0.2 else MENU_SIF_OUTLINE)
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        painter.end()


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

        self.shortcuts_title = FloatDriftLabel(FOLDER_SHORTCUTS_TITLE, self)
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
        self.shortcuts_container.setSpacing(0)
        self.main_layout.addLayout(self.shortcuts_container)

        sep0 = QLabel()
        sep0.setFixedHeight(1)
        sep0.setStyleSheet("background-color: rgba(255,255,255,120);")
        self.main_layout.addWidget(sep0)

        # First-page nav: Social Icon Fill circles (shortcut / document / mini / settings)
        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)
        nav_row.setContentsMargins(4, 6, 4, 2)
        nav_row.addStretch()

        self.btn_file_sc_open = MenuSocialIconFillButton(
            "shortcut", FILE_URL_SHORTCUTS_TITLE, self
        )
        self.btn_file_sc_open.clicked.connect(self.open_file_shortcuts_submenu)
        nav_row.addWidget(self.btn_file_sc_open)

        self.btn_doc_open = MenuSocialIconFillButton(
            "document", DOCUMENT_RECORD_TITLE_DEFAULT, self
        )
        self.btn_doc_open.clicked.connect(self.open_document_submenu)
        nav_row.addWidget(self.btn_doc_open)

        self.btn_mini_open = MenuSocialIconFillButton(
            "calculator", MINI_PROGRAMS_TITLE, self
        )
        self.btn_mini_open.clicked.connect(self.open_mini_programs_submenu)
        nav_row.addWidget(self.btn_mini_open)

        self.btn_settings = MenuSocialIconFillButton("gear", "Settings", self)
        self.btn_settings.clicked.connect(self.open_settings.emit)
        nav_row.addWidget(self.btn_settings)

        nav_row.addStretch()
        self.main_layout.addLayout(nav_row)

        # Captions under the icon row (document caption updates from Settings title)
        cap_row = QHBoxLayout()
        cap_row.setSpacing(6)
        cap_row.setContentsMargins(2, 0, 2, 2)
        cap_style = (
            "color: rgba(255,255,255,210); font-size: 7.5pt; "
            "background: transparent; font-weight: normal;"
        )
        cap_w = MENU_SIF_BTN_SIZE + 8

        def _cap(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            lab.setWordWrap(True)
            lab.setFixedWidth(cap_w)
            lab.setStyleSheet(cap_style)
            return lab

        cap_row.addStretch()
        cap_row.addWidget(_cap("File/URL"))
        self.doc_title = _cap("Document Record")
        cap_row.addWidget(self.doc_title)
        cap_row.addWidget(_cap("Mini Programs"))
        cap_row.addWidget(_cap("Settings"))
        cap_row.addStretch()
        self.main_layout.addLayout(cap_row)

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
            for i, sc in enumerate(shortcuts, start=1):
                name = sc.get("name", "Unnamed")
                path = sc.get("path", "")
                desc = sc.get("description", "")
                label = name
                if desc:
                    label += f" ({desc})"
                row = ListRowFillItem(i, label, self)
                row.setToolTip(path)
                row.clicked.connect(
                    lambda p=path: self.open_shortcut.emit(p, "folder")
                )
                self.shortcuts_container.addWidget(row)
        self.adjustSize()

    def refresh(self):
        self._folder_shortcuts = list(self.cfg.get("shortcuts") or [])
        self.folder_search_edit.blockSignals(True)
        self.folder_search_edit.clear()
        self.folder_search_edit.blockSignals(False)
        # Hide search box when there is nothing to filter.
        self.folder_search_edit.setVisible(bool(self._folder_shortcuts))
        self._rebuild_folder_shortcuts()

        title = self.cfg.get("document_area", "title") or DOCUMENT_RECORD_TITLE_DEFAULT
        self.doc_title.setText(title)
        self.btn_doc_open.setToolTip(title)
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
        try:
            from hakoniwa import HakoniwaIslandDialog as _HakoniwaIslandDialog
        except Exception:
            _HakoniwaIslandDialog = type(None)
        try:
            from fish_tank import FishTankDialog as _FishTankDialog
            from fish_tank.dialog import CaptureCardDialog as _CaptureCardDialog
        except Exception:
            _FishTankDialog = type(None)
            _CaptureCardDialog = type(None)
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
                FreeStationDialog,
                AlignmentCalcDialog,
                Alignment2CalcDialog,
                PomodoroDialog,
                TranslateDialog,
                _HakoniwaIslandDialog,
                _FishTankDialog,
                _CaptureCardDialog,
            ),
        ):
            return
        self.hide()


# ---------------------------------------------------------------------------
# Main pet window
# ---------------------------------------------------------------------------
# Heartbeat Zoom — one thud + two fading ripples (~1.3s). Theme gilt accents.
HEARTBEAT_DURATION_MS = 1300
HEARTBEAT_SCALE_PEAK = 1.20
# Match ornate / focus golds already used in CALC_DIALOG_STYLE (no new palette).
HEARTBEAT_RIPPLE_A = QColor(201, 168, 76, 220)   # #c9a84c
HEARTBEAT_RIPPLE_B = QColor(232, 212, 139, 200)  # #e8d48b


class HeartbeatOverlay(QWidget):
    """Frameless overlay: scale pet pixmap once, paint two center ripples that fade.

    Scale is applied around the pet's current screen center (transform origin =
    widget/pixmap center). Grab() device-pixel size is mapped back to the host's
    logical size so HiDPI never inflates the first frame toward the top-left.
    """

    def __init__(self, host: "PetWindow", pet_pixmap: QPixmap):
        super().__init__(None)
        self._host = host
        self._pix = QPixmap(pet_pixmap)
        self._progress = 0.0
        self._saved_opacity = host.windowOpacity()
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # Logical pet box (matches PetWindow fixed square), not grab() pixels.
        self._pet_w = max(1, host.width())
        self._pet_h = max(1, host.height())
        pet_size = max(self._pet_w, self._pet_h, 48)
        # Normalize grab so logical size == host (keeps HiDPI sharpness).
        dpr = max(float(self._pix.devicePixelRatio()), 1.0)
        phys_w = max(1, int(round(self._pet_w * dpr)))
        phys_h = max(1, int(round(self._pet_h * dpr)))
        normalized = self._pix.scaled(
            phys_w,
            phys_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        normalized.setDevicePixelRatio(dpr)
        self._pix = normalized
        # Room for ripples beyond the scaled pet.
        side = int(pet_size * 2.6)
        self._pet_size = pet_size
        self.setFixedSize(side, side)
        self._recenter_on_host()

    def _recenter_on_host(self) -> None:
        """Pin overlay so its center == host widget center in global coords."""
        host = self._host
        try:
            center = host.mapToGlobal(host.rect().center())
        except RuntimeError:
            return
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def start(self):
        self._recenter_on_host()
        self._host.setWindowOpacity(0.0)
        self._elapsed.start()
        self._progress = 0.0
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def _tick(self):
        t = min(1.0, self._elapsed.elapsed() / float(HEARTBEAT_DURATION_MS))
        self._progress = t
        self.update()
        if t >= 1.0:
            self._finish()

    def _finish(self):
        self._timer.stop()
        try:
            self._host.setWindowOpacity(self._saved_opacity)
        except RuntimeError:
            pass
        self.close()
        self.deleteLater()

    def _scale_at(self, t: float) -> float:
        """One thud: ease up to peak ~28% through the beat, then ease back to 1."""
        peak_t = 0.28
        if t <= 0.0:
            return 1.0
        if t >= 1.0:
            return 1.0
        if t <= peak_t:
            u = t / peak_t
            eased = QEasingCurve(QEasingCurve.Type.OutCubic).valueForProgress(u)
            return 1.0 + (HEARTBEAT_SCALE_PEAK - 1.0) * eased
        u = (t - peak_t) / (1.0 - peak_t)
        eased = QEasingCurve(QEasingCurve.Type.InOutCubic).valueForProgress(u)
        return HEARTBEAT_SCALE_PEAK + (1.0 - HEARTBEAT_SCALE_PEAK) * eased

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        t = self._progress
        max_r = min(self.width(), self.height()) * 0.48

        # Two circular ripples from center (staggered), fade out.
        ripples = (
            (0.00, HEARTBEAT_RIPPLE_A, 1.0),
            (0.18, HEARTBEAT_RIPPLE_B, 0.92),
        )
        for start, color, reach in ripples:
            if t <= start:
                continue
            local = (t - start) / max(1e-6, 1.0 - start)
            local = min(1.0, local)
            radius = max_r * reach * QEasingCurve(
                QEasingCurve.Type.OutCubic
            ).valueForProgress(local)
            alpha = int(color.alpha() * (1.0 - local) * (1.0 - local))
            if alpha <= 0 or radius <= 0.5:
                continue
            pen_c = QColor(color)
            pen_c.setAlpha(alpha)
            fill_c = QColor(color)
            fill_c.setAlpha(max(0, alpha // 5))
            pen = QPen(pen_c, max(2.0, 3.0 * (1.0 - local)))
            painter.setPen(pen)
            painter.setBrush(QBrush(fill_c))
            painter.drawEllipse(
                QPoint(int(cx), int(cy)), int(radius), int(radius)
            )

        # Pet thud: scale around center (no top-left origin offset).
        scale = self._scale_at(t)
        if not self._pix.isNull():
            dpr = max(float(self._pix.devicePixelRatio()), 1.0)
            lw = self._pix.width() / dpr
            lh = self._pix.height() / dpr
            painter.save()
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            # drawPixmap respects pixmap DPR → logical lw×lh, origin top-left of pet.
            painter.drawPixmap(QPointF(-lw / 2.0, -lh / 2.0), self._pix)
            painter.restore()
        painter.end()


class PetWindow(QWidget):
    def __init__(self, config_manager):
        super().__init__(None)
        self.cfg = config_manager
        self.setWindowIcon(load_app_icon())
        self.menu = None
        self.drag_pos = None
        self.moved_distance = 0
        self._ignore_release = False
        self._menu_open_at_press = False
        self._heartbeat = None
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
            # Close on press when open so focus-deactivate cannot race a reopen.
            self._menu_open_at_press = self._folder_menu_is_open()
            if self._menu_open_at_press:
                self.hide_folder_menu()
        elif event.button() == Qt.MouseButton.RightButton:
            self.click_timer.stop()
            self.toggle_folder_menu()

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
            self._menu_open_at_press = False
            self.drag_pos = None
            self.moved_distance = 0
            return
        self.clamp_to_screen()
        moved = self.moved_distance
        self.drag_pos = None
        self.moved_distance = 0
        if moved >= 8:
            self._menu_open_at_press = False
            save_pet_geometry(self.cfg, self, persist=True)
        else:
            # 心跳放大／Heartbeat Zoom on pet image click.
            self.play_heartbeat()
            if self._menu_open_at_press:
                # Second click: whole Folder Shortcuts UI already dismissed.
                self._menu_open_at_press = False
                self.click_timer.stop()
            else:
                # First click: open after double-click window.
                self.click_timer.start(QApplication.doubleClickInterval())

    def play_heartbeat(self):
        """One ~1.3s thud + two theme-gold ripples from the pet center."""
        if self._heartbeat is not None:
            try:
                if self._heartbeat.isVisible():
                    return
            except RuntimeError:
                self._heartbeat = None
        pix = self.grab()
        if pix.isNull():
            pix = self.label.grab()
        overlay = HeartbeatOverlay(self, pix)
        self._heartbeat = overlay
        overlay.destroyed.connect(lambda *_: setattr(self, "_heartbeat", None))
        overlay.start()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.click_timer.stop()
        self._ignore_release = True
        self._menu_open_at_press = False
        self.open_settings()

    def _folder_menu_is_open(self) -> bool:
        """True if PetMenu or any of its submenus is visible."""
        if self.menu is None:
            return False
        if self.menu.isVisible():
            return True
        for sub in (
            self.menu.doc_submenu,
            self.menu.file_shortcuts_submenu,
            self.menu.mini_programs_submenu,
        ):
            if sub is not None and sub.isVisible():
                return True
        return False

    def hide_folder_menu(self):
        """Dismiss the whole Folder Shortcuts UI (main panel + submenus)."""
        if self.menu is None:
            return
        # PetMenu.hideEvent already hides doc / file / mini submenus.
        self.menu.hide()

    def toggle_folder_menu(self):
        """Open Folder Shortcuts if closed; close the entire UI if open."""
        if self._folder_menu_is_open():
            self.hide_folder_menu()
        else:
            self.show_menu()

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
