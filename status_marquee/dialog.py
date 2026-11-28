"""Always-on-top desktop status marquee — Diagonal Text Bands.

Two slanted bands cross the view with theme steel-blue / gold fills,
repeated status text scrolling in opposite directions, soft shadows,
and a light ~8s playful cycle. Top-right gear opens settings.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .save import (
    COLOR_PRESETS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    effective_color_key,
    effective_text,
    load_settings,
    save_settings,
)

# Motion: one playful loop ~7–9s (text cycle + light opacity pulse).
CYCLE_MS = 8000
TICK_MS = 33
BAND_ANGLE_DEG = 14.0
BAND_HEIGHT = 56
GAP = "   ·   "

TITLE = "桌面跑馬燈／視窗跑馬燈"

DIALOG_STYLE = """
QDialog#StatusMarqueeDialog {
    background-color: transparent;
}
QToolButton#statusMarqueeGear {
    background-color: rgba(40, 58, 78, 200);
    color: #f5e6c8;
    border: 1px solid rgba(201, 168, 76, 180);
    border-radius: 14px;
    font-size: 13pt;
    padding: 0;
}
QToolButton#statusMarqueeGear:hover {
    background-color: rgba(61, 90, 128, 230);
    border: 1px solid rgba(232, 212, 139, 220);
}
"""

SETTINGS_STYLE = """
QDialog {
    background-color: rgba(28, 40, 55, 240);
    color: #e8f2f8;
    font-family: "Microsoft JhengHei", "Segoe UI", sans-serif;
}
QLabel { color: #e8f2f8; }
QLineEdit, QComboBox {
    background-color: rgba(42, 42, 42, 230);
    color: #f0f0f0;
    border: 1px solid #666;
    border-radius: 3px;
    padding: 3px 6px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #c9a84c; }
QPushButton {
    background-color: rgba(61, 90, 128, 230);
    color: #f0f6fa;
    border: 1px solid rgba(135, 206, 250, 160);
    border-radius: 3px;
    padding: 4px 12px;
}
QPushButton:hover { background-color: rgba(90, 130, 170, 240); }
QPushButton#dangerClose {
    background-color: rgba(90, 50, 40, 230);
    border: 1px solid rgba(201, 120, 76, 180);
}
QPushButton#dangerClose:hover { background-color: rgba(120, 60, 45, 240); }
"""


def _hex_color(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


class DiagonalBandsCanvas(QWidget):
    """Paints two crossing diagonal text bands with opposite scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._text1 = "休息中..."
        self._text2 = "休息中..."
        self._color_key = "steel"
        self._phase = 0.0  # 0..1 over CYCLE_MS
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    def set_status(self, text1: str, text2: str, color_key: str) -> None:
        self._text1 = text1 or "休息中..."
        self._text2 = text2 or "休息中..."
        self._color_key = color_key if color_key in COLOR_PRESETS else "steel"
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + TICK_MS / CYCLE_MS) % 1.0
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Soft translucent desk underlay so bands read on busy wallpapers.
        under = QColor(28, 40, 55, 90)
        painter.fillRect(self.rect(), under)

        preset = COLOR_PRESETS.get(self._color_key, COLOR_PRESETS["steel"])
        # Light pulse (~0.92–1.0) for a gentle transition feel across the cycle.
        pulse = 0.92 + 0.08 * (0.5 + 0.5 * math.sin(self._phase * math.tau))

        # Band A: −angle, scrolls left; Band B: +angle, scrolls right.
        # Each band can show independent text (settings 文字1／文字2).
        self._paint_band(
            painter,
            text=self._text1,
            angle_deg=-BAND_ANGLE_DEG,
            bg=_hex_color(preset["band_a"], int(230 * pulse)),
            fg=_hex_color(preset["text"], int(245 * pulse)),
            scroll_dir=-1.0,
            z_shadow=True,
        )
        self._paint_band(
            painter,
            text=self._text2,
            angle_deg=BAND_ANGLE_DEG,
            bg=_hex_color(preset["band_b"], int(220 * pulse)),
            fg=_hex_color(preset["text"], int(245 * pulse)),
            scroll_dir=1.0,
            z_shadow=True,
        )
        painter.end()

    def _paint_band(
        self,
        painter: QPainter,
        *,
        text: str,
        angle_deg: float,
        bg: QColor,
        fg: QColor,
        scroll_dir: float,
        z_shadow: bool,
    ) -> None:
        w, h = self.width(), self.height()
        cx, cy = w * 0.5, h * 0.5
        # Extra length so rotated band covers corners.
        span = int(math.hypot(w, h) * 1.35)
        band_h = BAND_HEIGHT

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(angle_deg)

        band_rect = QRectF(-span * 0.5, -band_h * 0.5, span, band_h)

        if z_shadow:
            shadow = QColor(0, 0, 0, 90)
            painter.fillRect(band_rect.adjusted(4, 5, 4, 5), shadow)

        painter.fillRect(band_rect, bg)

        # Thin gold edge so bands stay in-theme.
        edge = QPen(QColor(201, 168, 76, 140), 1.0)
        painter.setPen(edge)
        painter.drawRect(band_rect)

        font = QFont("Microsoft JhengHei", 16)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)

        unit = (text or "休息中...") + GAP
        fm = painter.fontMetrics()
        unit_w = max(fm.horizontalAdvance(unit), 1)
        # Opposite directions: phase drives offset; dir flips sense.
        offset = scroll_dir * self._phase * unit_w
        # Tile enough copies to cover the long band.
        start_x = -span * 0.5 - (offset % unit_w)
        y = band_rect.center().y() + fm.ascent() * 0.35 - fm.height() * 0.5
        x = start_x
        end_x = span * 0.5 + unit_w
        while x < end_x:
            painter.drawText(int(x), int(y + fm.ascent() * 0.55), unit)
            x += unit_w

        painter.restore()


class StatusMarqueeSettingsDialog(QDialog):
    """Configure per-band text / theme color / close window."""

    def __init__(self, host: "StatusMarqueeDialog"):
        super().__init__(host)
        self.host = host
        self.setWindowTitle("跑馬燈設定／Marquee settings")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setStyleSheet(SETTINGS_STYLE)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Show stored values (may be blank); placeholder hints the default.
        self.text1_edit = QLineEdit(host._settings.get("text1") or "")
        self.text1_edit.setPlaceholderText("例：休息中...（帶一）")
        form.addRow("文字1／帶一", self.text1_edit)

        self.text2_edit = QLineEdit(host._settings.get("text2") or "")
        self.text2_edit.setPlaceholderText("例：會議中...（帶二）")
        form.addRow("文字2／帶二", self.text2_edit)

        self.color_combo = QComboBox()
        current = effective_color_key(host._settings)
        for key, preset in COLOR_PRESETS.items():
            self.color_combo.addItem(preset["label"], key)
        idx = self.color_combo.findData(current)
        if idx >= 0:
            self.color_combo.setCurrentIndex(idx)
        form.addRow("顏色／Color", self.color_combo)

        layout.addLayout(form)

        row = QHBoxLayout()
        apply_btn = QPushButton("套用／Apply")
        apply_btn.clicked.connect(self._apply)
        row.addWidget(apply_btn)

        close_win = QPushButton("關閉視窗／Close window")
        close_win.setObjectName("dangerClose")
        close_win.clicked.connect(self._close_host)
        row.addWidget(close_win)

        cancel = QPushButton("取消／Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def _apply(self) -> None:
        text1 = self.text1_edit.text().strip()
        text2 = self.text2_edit.text().strip()
        color_key = self.color_combo.currentData()
        self.host.apply_settings(text1=text1, text2=text2, color_key=color_key)
        self.accept()

    def _close_host(self) -> None:
        self.accept()
        self.host.close()


class StatusMarqueeDialog(QDialog):
    """Frameless always-on-top desktop status marquee."""

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self._settings = load_settings(config_manager)
        self._drag_origin: Optional[QPoint] = None
        self._win_origin: Optional[QPoint] = None

        self.setObjectName("StatusMarqueeDialog")
        self.setWindowTitle(TITLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(DIALOG_STYLE)

        w = self._settings.get("width") or DEFAULT_WIDTH
        h = self._settings.get("height") or DEFAULT_HEIGHT
        self.resize(int(w), int(h))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = DiagonalBandsCanvas(self)
        root.addWidget(self.canvas)

        self.gear = QToolButton(self)
        self.gear.setObjectName("statusMarqueeGear")
        self.gear.setText("⚙")
        self.gear.setFixedSize(28, 28)
        self.gear.setToolTip("設定／Settings")
        self.gear.clicked.connect(self.open_settings)
        self.gear.raise_()

        self._apply_visual()
        self._restore_position()

    def _apply_visual(self) -> None:
        self.canvas.set_status(
            effective_text(self._settings, band=1),
            effective_text(self._settings, band=2),
            effective_color_key(self._settings),
        )

    def _restore_position(self) -> None:
        x, y = self._settings.get("pos_x"), self._settings.get("pos_y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def apply_settings(self, *, text1: str, text2: str, color_key: str) -> None:
        self._settings["text1"] = text1
        self._settings["text2"] = text2
        self._settings["color_key"] = color_key
        self._persist()
        self._apply_visual()

    def _persist(self) -> None:
        self._settings["pos_x"] = self.x()
        self._settings["pos_y"] = self.y()
        self._settings["width"] = self.width()
        self._settings["height"] = self.height()
        save_settings(self.cfg, self._settings)

    def open_settings(self) -> None:
        dlg = StatusMarqueeSettingsDialog(self)
        dlg.exec()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.gear.move(self.width() - self.gear.width() - 8, 8)
        self.gear.raise_()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is self.gear:
                super().mousePressEvent(event)
                return
            self._drag_origin = event.globalPosition().toPoint()
            self._win_origin = self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and self._win_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            self.move(self._win_origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None:
            self._drag_origin = None
            self._win_origin = None
            self._persist()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.canvas.start()
        self.gear.raise_()
