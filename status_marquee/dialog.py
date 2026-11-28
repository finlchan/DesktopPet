"""Always-on-top desktop status marquee — Diagonal Text Bands.

Two slanted bands cross the view with theme steel-blue / gold fills,
repeated status text scrolling in opposite directions, soft shadows,
and a light playful cycle. Top-right gear toggles an *inline* settings
panel on the same window (no separate dialog).
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .save import (
    COLOR_PRESETS,
    DISPLAY_MODE_DUAL_SPAN,
    DISPLAY_MODE_LABELS,
    DISPLAY_MODE_SINGLE,
    MAX_BAND_SIZE,
    MAX_SCROLL_SPEED,
    MIN_BAND_SIZE,
    MIN_SCROLL_SPEED,
    cycle_ms_for_speed,
    effective_band_size,
    effective_color_key,
    effective_display_mode,
    effective_scroll_speed,
    effective_text,
    load_settings,
    save_settings,
)

TICK_MS = 33
BAND_ANGLE_DEG = 14.0
GAP = "   ·   "
GEAR_SIZE = 28

TITLE = "桌面跑馬燈／視窗跑馬燈"

DIALOG_STYLE = """
QDialog#StatusMarqueeDialog {
    background-color: transparent;
}
"""

GEAR_STYLE = """
QToolButton#statusMarqueeGear {
    background-color: rgba(40, 58, 78, 200);
    color: #f5e6c8;
    border: 1px solid rgba(201, 168, 76, 180);
    border-radius: 14px;
    padding: 0px;
    margin: 0px;
}
QToolButton#statusMarqueeGear:hover {
    background-color: rgba(61, 90, 128, 230);
    border: 1px solid rgba(232, 212, 139, 220);
}
QToolButton#statusMarqueeGear:checked {
    background-color: rgba(61, 90, 128, 240);
    border: 1px solid rgba(232, 212, 139, 240);
}
"""

PANEL_STYLE = """
QFrame#statusMarqueePanel {
    background-color: rgba(28, 40, 55, 235);
    color: #e8f2f8;
    border: 1px solid rgba(201, 168, 76, 160);
    border-radius: 8px;
    font-family: "Microsoft JhengHei", "Segoe UI", sans-serif;
}
QFrame#statusMarqueePanel QLabel { color: #e8f2f8; }
QFrame#statusMarqueePanel QLineEdit,
QFrame#statusMarqueePanel QComboBox {
    background-color: rgba(42, 42, 42, 230);
    color: #f0f0f0;
    border: 1px solid #666;
    border-radius: 3px;
    padding: 3px 6px;
}
QFrame#statusMarqueePanel QLineEdit:focus,
QFrame#statusMarqueePanel QComboBox:focus { border: 1px solid #c9a84c; }
QFrame#statusMarqueePanel QRadioButton { color: #e8f2f8; spacing: 6px; }
QFrame#statusMarqueePanel QSlider::groove:horizontal {
    height: 6px;
    background: rgba(42, 42, 42, 230);
    border-radius: 3px;
}
QFrame#statusMarqueePanel QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #c9a84c;
    border-radius: 7px;
}
QFrame#statusMarqueePanel QPushButton {
    background-color: rgba(61, 90, 128, 230);
    color: #f0f6fa;
    border: 1px solid rgba(135, 206, 250, 160);
    border-radius: 3px;
    padding: 4px 12px;
}
QFrame#statusMarqueePanel QPushButton:hover { background-color: rgba(90, 130, 170, 240); }
QFrame#statusMarqueePanel QPushButton#dangerClose {
    background-color: rgba(90, 50, 40, 230);
    border: 1px solid rgba(201, 120, 76, 180);
}
QFrame#statusMarqueePanel QPushButton#dangerClose:hover {
    background-color: rgba(120, 60, 45, 240);
}
"""


def _hex_color(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


def _virtual_desktop_geometry() -> QRect:
    """Union of all screen geometries (bands can span dual monitors)."""
    screens = QApplication.screens()
    if not screens:
        primary = QApplication.primaryScreen()
        return primary.geometry() if primary else QRect(0, 0, 1280, 720)
    rect = QRect()
    for screen in screens:
        rect = rect.united(screen.geometry())
    return rect


def _single_screen_geometry(hint: Optional[QPoint] = None) -> QRect:
    """Full geometry of one monitor (hint point, else primary)."""
    screen = None
    if hint is not None:
        screen = QApplication.screenAt(hint)
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1280, 720)
    return screen.geometry()


class CenteredGearButton(QToolButton):
    """Circular gear control with the glyph optically centered in the circle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusMarqueeGear")
        self.setFixedSize(GEAR_SIZE, GEAR_SIZE)
        self.setCheckable(True)
        self.setToolTip("設定／Settings")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(GEAR_STYLE)
        # Text is painted manually so Qt's label metrics cannot offset it.
        self.setText("")

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont("Segoe UI Symbol", 13)
        if not font.exactMatch():
            font = QFont("Microsoft JhengHei", 12)
        painter.setFont(font)
        painter.setPen(QColor("#f5e6c8"))
        # AlignCenter on the full button rect centers the glyph in the circle.
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "⚙")
        painter.end()


class DiagonalBandsCanvas(QWidget):
    """Paints two crossing diagonal text bands with opposite scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._text1 = "休息中..."
        self._text2 = "休息中..."
        self._color_key = "steel"
        self._band_size = 56
        self._cycle_ms = 8000
        self._phase = 0.0  # 0..1 over cycle_ms
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    def set_status(
        self,
        text1: str,
        text2: str,
        color_key: str,
        *,
        band_size: int = 56,
        cycle_ms: int = 8000,
    ) -> None:
        self._text1 = text1 or "休息中..."
        self._text2 = text2 or "休息中..."
        self._color_key = color_key if color_key in COLOR_PRESETS else "steel"
        self._band_size = max(MIN_BAND_SIZE, min(MAX_BAND_SIZE, int(band_size)))
        self._cycle_ms = max(2000, int(cycle_ms))
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + TICK_MS / float(self._cycle_ms)) % 1.0
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
        band_h = self._band_size

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

        # Scale type with band thickness so thick bands stay readable.
        point_size = max(11, min(28, int(band_h * 0.32)))
        font = QFont("Microsoft JhengHei", point_size)
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


class StatusMarqueeSettingsPanel(QFrame):
    """Inline settings overlay (same window as the diagonal bands)."""

    def __init__(self, host: "StatusMarqueeDialog"):
        super().__init__(host)
        self.host = host
        self.setObjectName("statusMarqueePanel")
        self.setStyleSheet(PANEL_STYLE)
        self.setFixedWidth(360)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("跑馬燈設定／Marquee settings")
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(6)

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

        # Display mode radios.
        mode_box = QVBoxLayout()
        mode_box.setSpacing(4)
        self.mode_single = QRadioButton(DISPLAY_MODE_LABELS[DISPLAY_MODE_SINGLE])
        self.mode_dual = QRadioButton(DISPLAY_MODE_LABELS[DISPLAY_MODE_DUAL_SPAN])
        mode = effective_display_mode(host._settings)
        if mode == DISPLAY_MODE_DUAL_SPAN:
            self.mode_dual.setChecked(True)
        else:
            self.mode_single.setChecked(True)
        mode_box.addWidget(self.mode_single)
        mode_box.addWidget(self.mode_dual)
        form.addRow("顯示模式／Display", mode_box)

        # Scroll speed slider.
        speed_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(MIN_SCROLL_SPEED, MAX_SCROLL_SPEED)
        self.speed_slider.setValue(effective_scroll_speed(host._settings))
        self.speed_slider.setToolTip("文字移動速度／Scroll speed")
        self.speed_value = QLabel(str(self.speed_slider.value()))
        self.speed_value.setMinimumWidth(18)
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_value.setText(str(v))
        )
        speed_row.addWidget(self.speed_slider, 1)
        speed_row.addWidget(self.speed_value)
        form.addRow("文字移動速度", speed_row)

        # Band size slider.
        size_row = QHBoxLayout()
        self.band_slider = QSlider(Qt.Orientation.Horizontal)
        self.band_slider.setRange(MIN_BAND_SIZE, MAX_BAND_SIZE)
        self.band_slider.setValue(effective_band_size(host._settings))
        self.band_slider.setToolTip("斜線帶的大小／Band thickness")
        self.band_value = QLabel(str(self.band_slider.value()))
        self.band_value.setMinimumWidth(28)
        self.band_slider.valueChanged.connect(
            lambda v: self.band_value.setText(str(v))
        )
        size_row.addWidget(self.band_slider, 1)
        size_row.addWidget(self.band_value)
        form.addRow("斜線帶的大小", size_row)

        layout.addLayout(form)

        row = QHBoxLayout()
        apply_btn = QPushButton("套用／Apply")
        apply_btn.clicked.connect(self._apply)
        row.addWidget(apply_btn)

        close_win = QPushButton("關閉視窗／Close window")
        close_win.setObjectName("dangerClose")
        close_win.clicked.connect(self._close_host)
        row.addWidget(close_win)

        hide_btn = QPushButton("關閉設定／Close")
        hide_btn.clicked.connect(self.host.hide_settings)
        row.addWidget(hide_btn)
        layout.addLayout(row)

    def reload_from_host(self) -> None:
        """Refresh controls from the latest host settings."""
        s = self.host._settings
        self.text1_edit.setText(s.get("text1") or "")
        self.text2_edit.setText(s.get("text2") or "")
        idx = self.color_combo.findData(effective_color_key(s))
        if idx >= 0:
            self.color_combo.setCurrentIndex(idx)
        if effective_display_mode(s) == DISPLAY_MODE_DUAL_SPAN:
            self.mode_dual.setChecked(True)
        else:
            self.mode_single.setChecked(True)
        self.speed_slider.setValue(effective_scroll_speed(s))
        self.band_slider.setValue(effective_band_size(s))

    def _apply(self) -> None:
        text1 = self.text1_edit.text().strip()
        text2 = self.text2_edit.text().strip()
        color_key = self.color_combo.currentData()
        display_mode = (
            DISPLAY_MODE_DUAL_SPAN
            if self.mode_dual.isChecked()
            else DISPLAY_MODE_SINGLE
        )
        scroll_speed = int(self.speed_slider.value())
        band_size = int(self.band_slider.value())
        self.host.apply_settings(
            text1=text1,
            text2=text2,
            color_key=color_key,
            display_mode=display_mode,
            scroll_speed=scroll_speed,
            band_size=band_size,
        )

    def _close_host(self) -> None:
        self._apply()
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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = DiagonalBandsCanvas(self)
        root.addWidget(self.canvas)

        self.gear = CenteredGearButton(self)
        self.gear.clicked.connect(self.toggle_settings)
        self.gear.raise_()

        # Inline panel — child of this dialog, not a separate window.
        self.settings_panel = StatusMarqueeSettingsPanel(self)
        self.settings_panel.raise_()

        self._apply_visual()
        self._apply_display_geometry(initial=True)

    def _apply_visual(self) -> None:
        speed = effective_scroll_speed(self._settings)
        self.canvas.set_status(
            effective_text(self._settings, band=1),
            effective_text(self._settings, band=2),
            effective_color_key(self._settings),
            band_size=effective_band_size(self._settings),
            cycle_ms=cycle_ms_for_speed(speed),
        )

    def _apply_display_geometry(self, *, initial: bool = False) -> None:
        """Resize/position for single fullscreen or dual-monitor span."""
        mode = effective_display_mode(self._settings)
        if mode == DISPLAY_MODE_DUAL_SPAN:
            geo = _virtual_desktop_geometry()
        else:
            hint = None
            if not initial:
                hint = self.frameGeometry().center()
            elif self._settings.get("pos_x") is not None and self._settings.get(
                "pos_y"
            ) is not None:
                hint = QPoint(int(self._settings["pos_x"]), int(self._settings["pos_y"]))
            geo = _single_screen_geometry(hint)
        self.setGeometry(geo)

    def apply_settings(
        self,
        *,
        text1: str,
        text2: str,
        color_key: str,
        display_mode: str,
        scroll_speed: int,
        band_size: int,
    ) -> None:
        self._settings["text1"] = text1
        self._settings["text2"] = text2
        self._settings["color_key"] = color_key
        self._settings["display_mode"] = display_mode
        self._settings["scroll_speed"] = scroll_speed
        self._settings["band_size"] = band_size
        self._apply_visual()
        self._apply_display_geometry(initial=False)
        self._persist()
        self._layout_chrome()

    def _persist(self) -> None:
        self._settings["pos_x"] = self.x()
        self._settings["pos_y"] = self.y()
        self._settings["width"] = self.width()
        self._settings["height"] = self.height()
        save_settings(self.cfg, self._settings)

    def toggle_settings(self) -> None:
        if self.settings_panel.isVisible():
            self.hide_settings()
        else:
            self.open_settings()

    def open_settings(self) -> None:
        self.settings_panel.reload_from_host()
        self.settings_panel.show()
        self.gear.setChecked(True)
        self._layout_chrome()
        self.settings_panel.raise_()
        self.gear.raise_()

    def hide_settings(self) -> None:
        self.settings_panel.hide()
        self.gear.setChecked(False)
        self.gear.raise_()

    def _layout_chrome(self) -> None:
        margin = 8
        self.gear.move(self.width() - self.gear.width() - margin, margin)
        self.gear.raise_()
        if self.settings_panel.isVisible():
            # Panel sits under the gear, inset from the top-right.
            pw = self.settings_panel.width()
            self.settings_panel.adjustSize()
            ph = self.settings_panel.sizeHint().height()
            # Cap height so it fits on small single screens.
            max_h = max(160, self.height() - margin * 2 - self.gear.height() - 4)
            ph = min(ph, max_h)
            self.settings_panel.setFixedHeight(ph)
            x = max(margin, self.width() - pw - margin)
            y = margin + self.gear.height() + 4
            self.settings_panel.setGeometry(x, y, pw, ph)
            self.settings_panel.raise_()
            self.gear.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_chrome()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            # Don't start a drag from gear or the settings panel.
            walk = child
            while walk is not None and walk is not self:
                if walk is self.gear or walk is self.settings_panel:
                    super().mousePressEvent(event)
                    return
                walk = walk.parentWidget()
            # Fullscreen / span modes: no free drag (geometry is display-driven).
            mode = effective_display_mode(self._settings)
            if mode in (DISPLAY_MODE_SINGLE, DISPLAY_MODE_DUAL_SPAN):
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
        self._apply_display_geometry(initial=False)
        self._layout_chrome()
        self.gear.raise_()


# Back-compat alias: older smoke tests imported StatusMarqueeSettingsDialog.
StatusMarqueeSettingsDialog = StatusMarqueeSettingsPanel
