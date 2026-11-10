"""箱庭島 window — FramelessCalcDialog chrome + map + turn / terrain / guestbook / 觀光.

Local-play UX: named toolbar with costs + disable rules, status bar,
pan/zoom map (via HakoniwaMapWidget), optional keyboard shortcuts.

Numeric / function chrome lives as **overlays inside the map viewport**
(status, tile info, action log, icon bar → drawers, guestbook) — not as
outside columns or strips. Guestbook is closed by default (留言 icon).
Action log + guestbook frames are ~70% transparent.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPen,
    QResizeEvent,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


from .alert_marquee import AlertMarquee
from .build_tree import (
    build_tree_categories,
    cost_for_kind,
    display_label,
    effect_lines,
    placement_blurb,
    settlement_keys_for_tree,
    unlock_met,
    unlock_prereq,
)
from .hud_icons import HakoniwaIconBar
from .list_row_fill import HakoniwaListRowFillItem
from .timeline_draw import TimelineDrawPanel, TimelineNodeData

from .demos import island_summary, local_demo_islands
from .model import (
    asset_grade,
    BANK_TRANSFER_LOT,
    BUILDABLE,
    BUILDINGS,
    COASTAL_BUILDINGS,
    COST_AFFOREST,
    COST_AIRPORT,
    COST_AMUSEMENT_PARK,
    COST_AQUAFARM,
    COST_ATTRACT,
    COST_BANK,
    COST_BREAKWATER,
    COST_DEFENSE,
    COST_DECOY,
    COST_EXCAVATE,
    COST_FACTORY,
    COST_FARM,
    COST_POWER_PLANT,
    COST_CASINO,
    COST_HARBOR,
    COST_HARVEST,
    COST_HOTEL,
    COST_LANDFILL,
    COST_RESEARCH_LAB,
    COST_UNIVERSITY,
    COST_LEVEL,
    COST_MISSILE,
    COST_MISSILE_BASE,
    COST_MONUMENT,
    COST_PARK,
    COST_QUARRY,
    COST_RAISE,
    COST_ROCKET_BASE,
    COST_ROCKET_LAUNCH,
    COST_SHIPYARD,
    COST_SHRINE,
    COST_SUPERMARKET,
    COST_UNDERSEA_BASE,
    FOOD_BUY_LOT,
    FOOD_EXPORT_LOT,
    FUNDS_PER_FOOD_BUY,
    FUNDS_PER_FOOD_LOT,
    FUNDS_SOFT_CAP,
    GuestbookEntry,
    MAX_GUEST_NAME,
    MAX_GUEST_TEXT,
    ACHIEVEMENT_INCOME_EACH,
    ACHIEVEMENTS,
    HARD_LOCKED_BUILDINGS,
    POLICY_GROUPS,
    POLICY_LEAD_TURNS,
    POLICY_SPECS,
    POLICY_SWAP_COST,
    RESEARCH_DRONE,
    RESEARCH_GREENHOUSE,
    RESEARCH_LURE,
    SECRETARY_EXPAND_COST,
    SECRETARY_HEADHUNT_COST,
    SECRETARY_INTERVIEW_COST,
    SECRETARY_SWITCH_COST,
    SECRETARY_TEN_COST,
    TOWN_TO_CITY_POP,
    VILLAGE_TO_TOWN_POP,
    policy_effect_text,
    MOUNTAIN_FAMILY,
    MOUNTAIN_ONLY_BUILDINGS,
    PLACEABLE_BUILDINGS,
    SEA_ONLY_BUILDINGS,
    SHALLOW_ONLY_BUILDINGS,
    TREE_MIN,
    food_buy_cost,
    food_export_funds,
    timber_funds,
    TERRAIN,
    IslandState,
)
from .odometer import (
    HakoniwaStatusBar,
    load_status_seen,
    save_status_seen,
    snapshot_from_state,
    status_seen_path,
)
from .remote import HakoniwaRemote, HakoniwaRemoteError, try_connect
from .save import default_save_path, load_island, save_island
from .tiles import ATLAS
from .user_art import configure_user_art
from .view import HakoniwaMapWidget

# Overlay frames (action log / guestbook): 70% transparent ≈ 30% opaque.
# Align with icon-bar teal glass (hud_icons._ICON_*), not olive/amber.
_OVERLAY_BG = "rgba(14, 32, 36, 77)"
_OVERLAY_BORDER = "rgba(90, 200, 190, 140)"

# Drawer / icon-bar shared HUD chrome (deep teal glass · cyan border · orange).
_DRAWER_BG = "rgba(18, 36, 40, 230)"
_DRAWER_BORDER = "rgba(90, 200, 190, 210)"
_ACCENT_BG = "rgba(176, 96, 36, 230)"
_ACCENT_BG_HOVER = "rgba(196, 110, 42, 245)"
_ACCENT_BORDER = "rgba(220, 140, 60, 230)"
_HUD_TEXT = "#e6f8f5"
_HUD_TEXT_DIM = "#a8d0c8"

# 資訊 drawer pages. Only the first has rows; the rest stay blank on purpose.
_PROFILE_PAGES: Tuple[Tuple[str, str], ...] = (
    ("basic", "基本資料"),
    ("policy", "島嶼方針"),
    ("secretary", "秘書助理"),
    ("achievements", "成就系統"),
)
_PROFILE_BLANK = "尚未決定。"


def _format_signed(value: int) -> str:
    """Show a balance as +2, +0, or -1."""
    value = int(value)
    if value > 0:
        return f"+{value}"
    if value < 0:
        return str(value)
    return "+0"


def _format_percent(chance: float) -> str:
    """Show a model rate as a percent. Whole numbers stay whole."""
    pct = max(0.0, float(chance)) * 100.0
    nearest = round(pct)
    if abs(pct - nearest) < 0.05:
        return f"{int(nearest)}%"
    return f"{pct:.1f}%"

# In-map HUD styles (status / tile / log / guestbook / tools).
# Status strip: fully frameless over the map (no green box); digit cells
# carry their own dark fill in odometer.DigitReel.
HAKONIWA_HUD_STYLE = f"""
QWidget#hakoniwaHudStatus {{
    background: transparent;
    background-color: transparent;
    color: #ffffff;
    border: none;
    padding: 2px 4px;
    font-weight: bold;
    /* Frameless odometer strip floating on the map. */
}}
QLabel#hakoniwaHudStatusPlain {{
    background: transparent;
    color: #ffffff;
    border: none;
    font-weight: bold;
}}
QLabel#hakoniwaHudTile {{
    background-color: rgba(16, 40, 44, 170);
    color: {_HUD_TEXT};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 3px;
    padding: 4px 8px;
}}
QPlainTextEdit#hakoniwaHudLog,
QPlainTextEdit#hakoniwaHudGuestbook {{
    background-color: {_OVERLAY_BG};
    color: {_HUD_TEXT};
    border: 1px solid {_OVERLAY_BORDER};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: rgba(176, 96, 36, 180);
}}
QFrame#hakoniwaHudGuestbookFrame {{
    background-color: {_OVERLAY_BG};
    border: 1px solid {_OVERLAY_BORDER};
    border-radius: 4px;
}}
/* Tools／settings／island-profile drawers: same deep-teal glass + cyan as icon bar. */
QFrame#hakoniwaToolsDrawer,
QFrame#hakoniwaSettingsDrawer,
QFrame#hakoniwaIslandProfile {{
    background-color: {_DRAWER_BG};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 4px;
}}
QLabel#hakoniwaHudCaption {{
    color: {_HUD_TEXT_DIM};
    background: transparent;
    border: none;
    padding: 0;
}}
QPushButton#hakoniwaIslandProfileTab {{
    background-color: rgba(14, 32, 36, 180);
    color: {_HUD_TEXT_DIM};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 3px;
    padding: 4px 2px;
    font-size: 9pt;
    font-weight: bold;
}}
QPushButton#hakoniwaIslandProfileTab:checked {{
    background-color: {_ACCENT_BG};
    color: #fff8f0;
    border: 1px solid {_ACCENT_BORDER};
}}
QPushButton#hakoniwaIslandProfileTab:hover:!checked {{
    background-color: rgba(28, 52, 56, 220);
}}
QPushButton#hakoniwaIslandProfileTab[policyChoice="true"] {{
    text-align: left;
    padding: 1px 6px;
}}
QPushButton#hakoniwaIslandProfileTab:disabled {{
    background-color: rgba(14, 32, 36, 140);
    color: rgba(168, 208, 200, 120);
    border: 1px solid rgba(90, 200, 190, 90);
}}
QLabel#hakoniwaIslandProfileBody,
QLabel#hakoniwaProfileSectionTitle {{
    color: {_HUD_TEXT_DIM};
    background: transparent;
    border: none;
    font-size: 9pt;
}}
QLabel#hakoniwaProfileSectionTitle {{
    color: {_HUD_TEXT};
    font-weight: bold;
}}
QWidget#hakoniwaProfileHeader {{
    background: transparent;
    border: none;
}}
QScrollArea#hakoniwaProfileScroll {{
    background: transparent;
    border: none;
}}
QFrame#hakoniwaSecretaryPanel {{
    background-color: #1a232a;
    border: 1px solid #4ae3ff;
    border-radius: 3px;
}}
QLabel#hakoniwaSecretaryTitle {{
    color: #ffffff;
    background: transparent;
    border: none;
    font-size: 9pt;
    font-weight: bold;
}}
QLabel#hakoniwaSecretaryBody {{
    color: #ffffff;
    background: transparent;
    border: none;
    font-size: 9pt;
}}
QLabel#hakoniwaSecretaryValue {{
    color: #4ae3ff;
    background: transparent;
    border: none;
    font-size: 9pt;
}}
QLabel#hakoniwaSecretaryGood {{
    color: #53e685;
    background: transparent;
    border: none;
    font-size: 9pt;
}}
QPushButton#hakoniwaSecretaryBtn {{
    background-color: #1a232a;
    color: #ffffff;
    border: 1px solid #4ae3ff;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 9pt;
    text-align: left;
}}
QPushButton#hakoniwaSecretaryBtn:checked {{
    background-color: #d46b18;
    color: #ffffff;
    border: 1px solid #d46b18;
}}
QPushButton#hakoniwaSecretaryBtn:disabled {{
    color: #4ae3ff;
    border: 1px solid #4ae3ff;
}}
QScrollArea#hakoniwaSecretaryScroll, QWidget#hakoniwaSecretaryPage {{
    background: #1a232a;
    border: none;
}}
QWidget#hakoniwaProfileAccordion {{
    background: transparent;
}}
QLineEdit#hakoniwaHudInput {{
    background-color: rgba(14, 28, 32, 180);
    color: {_HUD_TEXT};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 3px;
    padding: 2px 4px;
}}
/* Building nav — category List Row Fill + Timeline Draw children. */
QScrollArea#hakoniwaBuildNav {{
    background: transparent;
    border: none;
}}
QWidget#hakoniwaBuildNavBody {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(90, 200, 190, 120);
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QFrame#hakoniwaBuildDetailPane {{
    background-color: rgba(14, 28, 32, 120);
    border: none;
    border-left: 1px solid {_DRAWER_BORDER};
}}
QLabel#hakoniwaBuildDetailTitle {{
    color: {_HUD_TEXT};
    font-size: 13pt;
    font-weight: bold;
    background: transparent;
    border: none;
}}
QLabel#hakoniwaBuildDetailBody {{
    color: {_HUD_TEXT_DIM};
    background: transparent;
    border: none;
}}
QPushButton#hakoniwaBuildPlace {{
    background-color: {_ACCENT_BG};
    color: #fff8f0;
    border: 1px solid {_ACCENT_BORDER};
    border-radius: 3px;
    min-height: 30px;
    font-weight: bold;
}}
QPushButton#hakoniwaBuildPlace:disabled {{
    background-color: rgba(28, 44, 48, 180);
    color: rgba(168, 190, 188, 140);
    border: 1px solid rgba(70, 110, 108, 120);
}}
QPushButton#hakoniwaBuildPlace:hover:!disabled {{
    background-color: {_ACCENT_BG_HOVER};
}}
/* Drawer footer actions — teal glass chips, not calcAction gray. */
QPushButton#hakoniwaDrawerAction {{
    background-color: rgba(18, 36, 40, 210);
    color: {_HUD_TEXT};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 3px;
    min-height: 22px;
    padding: 2px 8px;
    font-size: 9pt;
}}
QPushButton#hakoniwaDrawerAction:hover {{
    background-color: rgba(28, 52, 56, 230);
}}
"""


_ACCORDION_MS = 450  # ease-in-out, about 0.45s


class _RotatingPlus(QWidget):
    """Plus mark. A 135° turn reads as a times mark."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = float(value)
        self.update()

    angle = Property(float, get_angle, set_angle)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        pen = QPen(QColor(_HUD_TEXT))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(-5, 0, 5, 0)
        painter.drawLine(0, -5, 0, 5)
        painter.end()


class _AccordionSection(QWidget):
    """One FAQ block. The clip height animates 0 → content.

    Outer fixed height is the grid row (0fr → 1fr). The inner label stays
    at full height and is clipped, which is overflow:hidden.
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.title_text = title
        self._open = False
        self._full = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(0)
        self.header = QWidget(self)
        self.header.setObjectName("hakoniwaProfileHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        head = QHBoxLayout(self.header)
        head.setContentsMargins(0, 3, 0, 3)
        head.setSpacing(6)
        self.title = QLabel(self.header)
        self.title.setObjectName("hakoniwaProfileSectionTitle")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.title.setText(
            '<span style="color:#5ac8be;">── </span>'
            f'<span style="color:{_HUD_TEXT};">{html.escape(title)}</span>'
            '<span style="color:#5ac8be;"> ──</span>'
        )
        head.addWidget(self.title, stretch=1)
        self.plus = _RotatingPlus(self.header)
        head.addWidget(self.plus, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.header)
        # Outer wrapper: animated row size. Inner: full text, clipped.
        self.clip = QWidget(self)
        self.clip.setFixedHeight(0)
        self.body = QLabel(self.clip)
        self.body.setObjectName("hakoniwaIslandProfileBody")
        self.body.setWordWrap(True)
        self.body.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        lay.addWidget(self.clip)
        self.header.mouseReleaseEvent = self._header_mouse  # type: ignore[method-assign]
        self._height_anim = QVariantAnimation(self)
        self._height_anim.setDuration(_ACCORDION_MS)
        self._height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._height_anim.valueChanged.connect(self._apply_height)
        self._angle_anim = QPropertyAnimation(self.plus, b"angle", self)
        self._angle_anim.setDuration(_ACCORDION_MS)
        self._angle_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _header_mouse(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            host = self.parent()
            toggle = getattr(host, "toggle_section", None)
            if toggle is not None:
                toggle(self)
        QWidget.mouseReleaseEvent(self.header, event)

    def set_rows(self, lines: List[str]) -> None:
        self.body.setText("\n".join(lines))
        self._place_body()
        if self._open and self._height_anim.state() != QAbstractAnimation.State.Running:
            self.clip.setFixedHeight(self._full)

    def _place_body(self) -> None:
        width = max(self.clip.width(), self.width() - 4, 80)
        self.body.setFixedWidth(width)
        height = max(self.body.sizeHint().height(), 0)
        self.body.setFixedHeight(height)
        self.body.move(0, 0)
        self._full = height

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_body()
        if self._height_anim.state() == QAbstractAnimation.State.Running:
            self._height_anim.setEndValue(self._full if self._open else 0)
        elif self._open:
            self.clip.setFixedHeight(self._full)

    def is_open(self) -> bool:
        return self._open

    def set_open(self, open_: bool, *, animate: bool) -> None:
        self._open = bool(open_)
        self._place_body()
        target = self._full if self._open else 0
        angle = 135.0 if self._open else 0.0
        if not animate:
            self._height_anim.stop()
            self._angle_anim.stop()
            self.clip.setFixedHeight(target)
            self.plus.set_angle(angle)
            return
        self._run(self._height_anim, self.clip.height(), target)
        self._run(self._angle_anim, self.plus.get_angle(), angle)

    def _run(self, anim, start: float, end: float) -> None:
        anim.stop()
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()

    def _apply_height(self, value) -> None:
        self.clip.setFixedHeight(max(0, int(value)))


class _ProfileAccordion(QWidget):
    """FAQ list. Opening one section closes whichever was open."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("hakoniwaProfileAccordion")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._sections: List[_AccordionSection] = []
        self._open: Optional[_AccordionSection] = None
        self._ready = False

    def set_sections(self, sections: List[Tuple[str, List[str]]]) -> None:
        if not self._ready:
            for title, rows in sections:
                sec = _AccordionSection(title, self)
                sec.set_rows(rows)
                self._lay.addWidget(sec)
                self._sections.append(sec)
            self._lay.addStretch(1)
            self._ready = True
            if self._sections:
                self.toggle_section(self._sections[0], animate=False)
            return
        for sec, (_title, rows) in zip(self._sections, sections):
            sec.set_rows(rows)

    def toggle_section(self, section: _AccordionSection, animate: bool = True) -> None:
        if section is self._open:
            section.set_open(False, animate=animate)
            self._open = None
            return
        if self._open is not None:
            self._open.set_open(False, animate=animate)
        section.set_open(True, animate=animate)
        self._open = section

    def toggle_title(self, title: str) -> None:
        for sec in self._sections:
            if sec.title_text == title:
                self.toggle_section(sec, animate=True)
                return

    def open_title(self) -> str:
        return self._open.title_text if self._open is not None else ""

    def open_count(self) -> int:
        return sum(1 for sec in self._sections if sec.is_open())

    def plain_text(self) -> str:
        chunks: List[str] = []
        for sec in self._sections:
            chunks.append(sec.title_text)
            chunks.append(sec.body.text())
        return "\n".join(chunks)

    def section(self, title: str) -> _AccordionSection:
        for sec in self._sections:
            if sec.title_text == title:
                return sec
        raise KeyError(title)


class _PixelPortrait(QWidget):
    """點陣占位。用戶日後提供 2D 動態角色圖，再換掉這個方框。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mood = "開心"
        self.setFixedSize(52, 60)

    def set_mood(self, mood: str) -> None:
        self._mood = mood or "開心"
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.scale(self.width() / 52.0, self.height() / 60.0)
        painter.setPen(QPen(QColor("#4ae3ff"), 2))
        painter.setBrush(QColor("#1a232a"))
        painter.drawRect(1, 1, 49, 57)
        skin = QColor("#d46b18")
        ice = QColor("#4ae3ff")
        good = QColor("#53e685")
        white = QColor("#ffffff")

        def px(x: int, y: int, color: QColor, n: int = 1) -> None:
            painter.fillRect(6 + x * 4, 8 + y * 4, 4 * n, 4, color)

        for x in range(1, 9):
            px(x, 0, ice)
        for y in range(2, 7):
            for x in range(2, 8):
                px(x, y, skin)
        if self._mood == "開心":
            px(3, 3, white)
            px(6, 3, white)
            px(3, 5, good, 4)
        elif self._mood == "警告":
            px(3, 3, white)
            px(6, 3, white)
            px(2, 2, white)
            px(7, 2, white)
            px(4, 5, white, 2)
        else:
            px(3, 4, white)
            px(6, 4, white)
            px(3, 6, ice, 4)
        painter.end()


class HakoniwaMapHud(QWidget):
    """Hosts the map and positions HUD overlays inside the map viewport.

    Layout (user-locked annotation):
      - status bar → top center
      - alert marquee → under status (警報走馬燈; 通知→警報; hidden without alerts)
      - tile info → top-left (below status／marquee; 通知→方格資訊)
      - icon bar → bottom-left (通知／建築／資訊／留言／設定)
      - guestbook → bottom center (~70% transparent; **closed by default**)
      - action log → bottom-right (~70% transparent; 通知→歷史記錄框)
      - tools / settings / island-profile drawers → above icon bar when open

    「通知」opens a small menu: 歷史記錄框 / 警報 / 方格資訊 (independent).
    「資訊」shows four pages. 基本資料 is the island profile; the other three stay blank.
    """

    def __init__(self, map_widget: HakoniwaMapWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet(HAKONIWA_HUD_STYLE)
        self.map = map_widget
        self.map.setParent(self)
        self.map.lower()

        # Odometer status strip (狀態 text + digit reels); no frame; bold.
        self.stats = HakoniwaStatusBar(self)
        # User-locked: status HUD is one horizontal line (no wrap).
        self.stats.setWordWrap(False)
        self.stats.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.stats.setTextFormat(Qt.TextFormat.PlainText)

        # Alert marquee under status — hidden until alerts exist + 通知 chrome on.
        self.alert_marquee = AlertMarquee(self)
        self.alert_marquee.hide()

        self.sel_label = QLabel("未選取格子", self)
        self.sel_label.setObjectName("hakoniwaHudTile")
        self.sel_label.setWordWrap(True)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setObjectName("hakoniwaHudLog")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("行動日誌")

        # Bottom-left icon bar replaces the old orange 「工具／設定」 button.
        self.icon_bar = HakoniwaIconBar(self)
        # Compat alias: build icon is the former tools toggle.
        self.tools_btn = self.icon_bar.button("build")

        self.tools_drawer = QFrame(self)
        self.tools_drawer.setObjectName("hakoniwaToolsDrawer")
        self.tools_drawer.setVisible(False)
        drawer_outer = QVBoxLayout(self.tools_drawer)
        drawer_outer.setContentsMargins(6, 6, 6, 6)
        drawer_outer.setSpacing(4)

        # Content browse/build: left category List Row Fill nav + right detail.
        # (Custom scroll list — not QTreeWidget setItemWidget — so number / → /
        # separators always paint.)
        browse_row = QHBoxLayout()
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.setSpacing(6)

        self.build_nav = QScrollArea()
        self.build_nav.setObjectName("hakoniwaBuildNav")
        self.build_nav.setWidgetResizable(True)
        self.build_nav.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.build_nav.setFrameShape(QFrame.Shape.NoFrame)
        self.build_nav_body = QWidget()
        self.build_nav_body.setObjectName("hakoniwaBuildNavBody")
        self.build_nav_layout = QVBoxLayout(self.build_nav_body)
        self.build_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.build_nav_layout.setSpacing(0)
        self.build_nav_layout.addStretch(1)
        self.build_nav.setWidget(self.build_nav_body)
        # Compat alias used by older tests / call sites.
        self.build_tree = self.build_nav
        browse_row.addWidget(self.build_nav, stretch=2)

        detail = QFrame()
        detail.setObjectName("hakoniwaBuildDetailPane")
        detail_lay = QVBoxLayout(detail)
        detail_lay.setContentsMargins(8, 4, 4, 4)
        detail_lay.setSpacing(4)
        self.build_detail_title = QLabel("選擇建築／指令")
        self.build_detail_title.setObjectName("hakoniwaBuildDetailTitle")
        self.build_detail_title.setWordWrap(True)
        detail_lay.addWidget(self.build_detail_title)
        self.build_detail_cost = QLabel("")
        self.build_detail_cost.setObjectName("hakoniwaBuildDetailBody")
        self.build_detail_cost.setWordWrap(True)
        detail_lay.addWidget(self.build_detail_cost)
        self.build_detail_status = QLabel("")
        self.build_detail_status.setObjectName("hakoniwaBuildDetailBody")
        self.build_detail_status.setWordWrap(True)
        detail_lay.addWidget(self.build_detail_status)
        self.build_detail_place = QLabel("")
        self.build_detail_place.setObjectName("hakoniwaBuildDetailBody")
        self.build_detail_place.setWordWrap(True)
        detail_lay.addWidget(self.build_detail_place)
        self.build_detail_effects = QLabel("")
        self.build_detail_effects.setObjectName("hakoniwaBuildDetailBody")
        self.build_detail_effects.setWordWrap(True)
        self.build_detail_effects.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        detail_lay.addWidget(self.build_detail_effects, stretch=1)
        self.build_place_btn = QPushButton("放置")
        self.build_place_btn.setObjectName("hakoniwaBuildPlace")
        self.build_place_btn.setEnabled(False)
        detail_lay.addWidget(self.build_place_btn)
        browse_row.addWidget(detail, stretch=3)
        drawer_outer.addLayout(browse_row, stretch=1)

        # Selected tree key (tool / building); None when category or empty.
        self._build_tree_key: Optional[str] = None

        # Settings live in their own drawer (opened by 設定 icon).
        self.settings_drawer = QFrame(self)
        self.settings_drawer.setObjectName("hakoniwaSettingsDrawer")
        self.settings_drawer.setVisible(False)
        settings_outer = QVBoxLayout(self.settings_drawer)
        settings_outer.setContentsMargins(6, 6, 6, 6)
        settings_outer.setSpacing(4)
        self.settings_body = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_body)
        self.settings_layout.setContentsMargins(2, 2, 2, 2)
        self.settings_layout.setSpacing(4)
        settings_outer.addWidget(self.settings_body)

        # 資訊 → four pages. The old title is the tab row (not tile info).
        self.island_profile = QFrame(self)
        self.island_profile.setObjectName("hakoniwaIslandProfile")
        self.island_profile.setVisible(False)
        profile_lay = QVBoxLayout(self.island_profile)
        profile_lay.setContentsMargins(6, 4, 6, 2)
        profile_lay.setSpacing(2)
        self._profile_page = "basic"
        self._profile_basic_text = ""
        self._profile_tab_buttons: Dict[str, QPushButton] = {}
        self._profile_tabs = QButtonGroup(self.island_profile)
        self._profile_tabs.setExclusive(True)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)
        for key, label in _PROFILE_PAGES:
            btn = QPushButton(label)
            btn.setObjectName("hakoniwaIslandProfileTab")
            btn.setCheckable(True)
            btn.setChecked(key == "basic")
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._profile_tabs.addButton(btn)
            self._profile_tab_buttons[key] = btn
            btn.clicked.connect(
                lambda _checked=False, page=key: self.show_island_profile_page(page)
            )
            tab_row.addWidget(btn)
        profile_lay.addLayout(tab_row)
        self._profile_secretary_text = ""
        self._profile_achievement_text = ""
        self._profile_sections: List[Tuple[str, List[str]]] = []
        self._profile_accordion = _ProfileAccordion()
        self._profile_scroll = QScrollArea(self.island_profile)
        self._profile_scroll.setObjectName("hakoniwaProfileScroll")
        self._profile_scroll.setWidgetResizable(True)
        self._profile_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._profile_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._profile_scroll.setWidget(self._profile_accordion)
        profile_lay.addWidget(self._profile_scroll, stretch=1)
        self.island_profile_body = QLabel("")
        self.island_profile_body.setObjectName("hakoniwaIslandProfileBody")
        self.island_profile_body.setWordWrap(True)
        self.island_profile_body.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.island_profile_body.setVisible(False)
        profile_lay.addWidget(self.island_profile_body, stretch=1)
        self._policy_panel = QScrollArea(self.island_profile)
        self._policy_panel.setObjectName("hakoniwaProfileScroll")
        self._policy_panel.setWidgetResizable(True)
        self._policy_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._policy_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._policy_body = QWidget()
        self._policy_body.setObjectName("hakoniwaProfileAccordion")
        policy_col = QVBoxLayout(self._policy_body)
        policy_col.setContentsMargins(0, 0, 0, 0)
        policy_col.setSpacing(0)
        self._policy_header = QLabel("")
        self._policy_header.setObjectName("hakoniwaIslandProfileBody")
        self._policy_header.setWordWrap(True)
        self._policy_header.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        policy_col.addWidget(self._policy_header)
        self._policy_group_labels: List[QLabel] = []
        self._policy_buttons: Dict[str, QPushButton] = {}
        for title, ids in POLICY_GROUPS:
            group = QLabel(title)
            group.setObjectName("hakoniwaProfileSectionTitle")
            group.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self._policy_group_labels.append(group)
            policy_col.addWidget(group)
            for pid in ids:
                choice = QPushButton(POLICY_SPECS[pid]["label"])
                choice.setObjectName("hakoniwaIslandProfileTab")
                choice.setProperty("policyChoice", "true")
                choice.setCheckable(True)
                choice.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
                )
                choice.clicked.connect(
                    lambda _checked=False, policy=pid: self._choose_policy(policy)
                )
                self._policy_buttons[pid] = choice
                policy_col.addWidget(choice)
        policy_col.addStretch(1)
        self._policy_panel.setWidget(self._policy_body)
        self._policy_panel.setVisible(False)
        profile_lay.addWidget(self._policy_panel, stretch=1)
        self._switch_armed = ""
        self._build_secretary_panel(profile_lay)

        # Guestbook cluster (view + form) — closed by default; open via 留言.
        self.guestbook_frame = QFrame(self)
        self.guestbook_frame.setObjectName("hakoniwaHudGuestbookFrame")
        self.guestbook_frame.setVisible(False)
        gb_col = QVBoxLayout(self.guestbook_frame)
        gb_col.setContentsMargins(6, 4, 6, 4)
        gb_col.setSpacing(3)
        gb_cap = QLabel("訪客留言板")
        gb_cap.setObjectName("hakoniwaHudCaption")
        gb_col.addWidget(gb_cap)
        self.guestbook_view = QPlainTextEdit()
        self.guestbook_view.setObjectName("hakoniwaHudGuestbook")
        self.guestbook_view.setReadOnly(True)
        self.guestbook_view.setPlaceholderText("尚無留言 — 留下第一則吧")
        self.guestbook_view.setMaximumHeight(72)
        gb_col.addWidget(self.guestbook_view)
        self.guestbook_form = QHBoxLayout()
        self.guestbook_form.setSpacing(4)
        gb_col.addLayout(self.guestbook_form)

        # Independent panel flags (通知 menu + defaults).
        self._log_visible = True
        self._marquee_enabled = True
        self._tile_info_visible = True

        # Wire icons after drawers exist (setChecked emits and may layout).
        self.icon_bar.iconToggled.connect(self._on_icon_toggled)
        self.icon_bar.iconClicked.connect(self._on_icon_clicked)
        # 通知 = menu launcher. 資訊 = island profile drawer (starts closed).
        notify_btn = self.icon_bar.button("notify")
        if notify_btn is not None:
            notify_btn.setToolTip("通知：歷史記錄框／警報／方格資訊")

        self._apply_panel_visibility()
        self._sync_notify_button()

        self.setMinimumSize(480, 480)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    def _apply_panel_visibility(self) -> None:
        """Apply independent log / tile-info / marquee flags to widgets."""
        self.log_view.setVisible(self._log_visible)
        self.sel_label.setVisible(self._tile_info_visible)
        self._sync_marquee_visibility()

    def _sync_marquee_visibility(self) -> None:
        show = self._marquee_enabled and self.alert_marquee.has_alerts()
        self.alert_marquee.setVisible(show)

    def _sync_notify_button(self) -> None:
        """Bell looks active when any notify-menu option is on."""
        btn = self.icon_bar.button("notify")
        if btn is None:
            return
        want = (
            self._log_visible
            or self._marquee_enabled
            or self._tile_info_visible
        )
        if btn.isChecked() != want:
            btn.blockSignals(True)
            btn.setChecked(want)
            btn.blockSignals(False)

    def set_log_visible(self, on: bool) -> None:
        """Toggle 歷史記錄框 (action log) independently."""
        on = bool(on)
        if self._log_visible == on:
            return
        self._log_visible = on
        self.log_view.setVisible(on)
        self._sync_notify_button()
        self._layout_overlays()
        self._raise_overlays()

    def set_marquee_enabled(self, on: bool) -> None:
        """Toggle 警報 preference; marquee still needs queued alerts to show."""
        on = bool(on)
        if self._marquee_enabled == on:
            return
        self._marquee_enabled = on
        self._sync_marquee_visibility()
        self._sync_notify_button()
        self._layout_overlays()
        self._raise_overlays()

    def set_tile_info_visible(self, on: bool) -> None:
        """Toggle 方格資訊 only — does not touch log／marquee／資訊 profile."""
        on = bool(on)
        if self._tile_info_visible == on:
            return
        self._tile_info_visible = on
        self.sel_label.setVisible(on)
        self._sync_notify_button()
        self._layout_overlays()
        self._raise_overlays()

    def set_alerts(self, texts) -> None:
        """Replace alert marquee lines; visibility follows 警報 flag + queue."""
        self.alert_marquee.set_alerts(texts)
        self._sync_marquee_visibility()
        self._layout_overlays()

    def set_sample_alerts(self) -> None:
        self.alert_marquee.set_sample_alerts()
        self._sync_marquee_visibility()
        self._layout_overlays()

    def refresh_island_profile(self, state: IslandState) -> None:
        """Fill the four 資訊 pages from the island's policy, secretary, and achievements."""
        created = str(getattr(state, "created_at", "") or "").strip() or "—"
        player = str(getattr(state, "player_name", "") or "").strip() or "—"
        spawn = _format_percent(state._monster_spawn_chance())
        funds_delta, food_delta, people_delta = state.shown_turn_balances()
        # 居民滿意度 is happiness_bonus. 綜合評分 is island_score.
        # 失業率、犯罪率、綠化率、軍事防衛力評級 sum 生效中 policies.
        # Tax, power, coastal grade, intercept, damage, and rank stay 0.
        identity = [
            f"島名：{state.name}",
            f"玩家：{player}",
            f"建島：{created}",
            f"編號：{state.island_id}",
            f"回合：{state.turn}",
            f"格寬：{state.size}×{state.size}",
            f"陸地：{state.land_count()} 格",
            f"人口：{state.population}",
            f"資金：{state.funds}",
            f"糧食：{state.food}",
        ]
        balances = [
            f"每回合資金收支：{_format_signed(funds_delta)}",
            f"每回合糧食收支：{_format_signed(food_delta)}",
            f"每回合人口變化：{_format_signed(people_delta)}",
        ]
        residents = [
            f"居民滿意度：{state.happiness_bonus()}",
            "稅率：0",
            f"失業率：{state.shown_unemployment()}",
            f"犯罪率：{state.shown_crime()}",
        ]
        demands = [
            "住宅需求：0",
            "商店需求：0",
            "工廠需求：0",
        ]
        environment = [
            "電力供需：0",
            f"綠化率：{state.shown_green()}",
            "淺灘及防波堤等級：0",
            f"空氣污染指數：{state.shown_air()}",
            f"水源污染指數：{state.shown_water()}",
            f"天災機會率：{state.shown_disaster()}",
            f"怪物出現率：{spawn}",
        ]
        military = [
            f"軍事防衛力評級：{state.shown_defense()}",
            "發射飛彈數目：0",
            "擊退本島怪物數次：0",
            "擊退其他島怪物數次：0",
            "飛彈自動迎擊成功率：0",
            "被攻擊／受損次數：0",
        ]
        # No separate 總資產 is stored. The number is island_score().
        assets = state.island_score()
        standing = [
            f"島嶼總資產：{assets}",
            "伺服器排名：0",
            f"綜合評分：{asset_grade(assets)}",
        ]
        self._profile_sections = [
            ("島嶼身分", identity),
            ("資源收益", balances),
            ("居民", residents),
            ("需求", demands),
            ("環境", environment),
            ("軍事", military),
            ("評價", standing),
        ]
        self._profile_basic_text = ""
        self._sync_policy_panel(state)
        self._sync_secretary_panel(state)
        have = set(state.achievements)
        earned_lines = []
        for key, label, funds in ACHIEVEMENTS:
            if key in have:
                earned_lines.append(f"{label}：已達成（分數 +{funds}）")
            else:
                earned_lines.append(f"{label}：未達成")
        extra = ACHIEVEMENT_INCOME_EACH * len(state.achievements)
        if state.achievement_unlocks("onsen_village"):
            earned_lines.append("溫泉村已可直接建設")
        else:
            earned_lines.append("溫泉開村達成後，溫泉村解鎖建設")
        earned_lines.append(f"已達成 {len(state.achievements)}／{len(ACHIEVEMENTS)}")
        earned_lines.append(f"成就加成：每回合資金收支 +{extra}")
        self._profile_achievement_text = "\n".join(earned_lines)
        self.show_island_profile_page(self._profile_page)

    def _sync_policy_panel(self, state: IslandState) -> None:
        used = state.policy_slots_used()
        slots = state.policy_slot_count()
        self._policy_header.setText(
            f"方針欄位 {used}／{slots}　"
            f"更換費用 {POLICY_SWAP_COST} 資金，緩衝 {POLICY_LEAD_TURNS} 回合\n"
            f"人口未滿{VILLAGE_TO_TOWN_POP}為1欄，"
            f"滿{VILLAGE_TO_TOWN_POP}為3欄，滿{TOWN_TO_CITY_POP}為4欄"
        )
        full = used >= slots
        for pid, btn in self._policy_buttons.items():
            turns = state.policy_turns(pid)
            label = str(POLICY_SPECS[pid]["label"])
            locked = not state.policy_unlocked(pid)
            if turns is None and locked:
                title = f"{label}　未解鎖"
            elif turns is None:
                title = label
            elif turns > 0:
                title = f"{label}　實施中　剩餘 {turns} 回合"
            else:
                title = f"{label}　生效中"
            btn.setText(f"{title}\n{policy_effect_text(pid)}")
            btn.blockSignals(True)
            btn.setChecked(turns is not None)
            btn.setEnabled(turns is not None or (not full and not locked))
            btn.blockSignals(False)

    def policy_page_text(self) -> str:
        lines = [self._policy_header.text()]
        for lab in self._policy_group_labels:
            lines.append(lab.text())
        for btn in self._policy_buttons.values():
            lines.append(btn.text())
        return "\n".join(lines)

    def _secretary_label(self, text: str, kind: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName(kind)
        lab.setWordWrap(True)
        lab.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return lab

    def _secretary_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("hakoniwaSecretaryBtn")
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        return btn

    def _secretary_frame(self, title: str) -> Tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("hakoniwaSecretaryPanel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        lay.addWidget(self._secretary_label(title, "hakoniwaSecretaryTitle"))
        return frame, lay

    def _build_secretary_panel(self, profile_lay: QVBoxLayout) -> None:
        self._secretary_panel = QScrollArea(self.island_profile)
        self._secretary_panel.setObjectName("hakoniwaSecretaryScroll")
        self._secretary_panel.setWidgetResizable(True)
        self._secretary_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._secretary_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page = QWidget()
        page.setObjectName("hakoniwaSecretaryPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        columns = QHBoxLayout()
        columns.setSpacing(4)
        left = QVBoxLayout()
        right = QVBoxLayout()
        left.setSpacing(2)
        right.setSpacing(2)

        card, card_lay = self._secretary_frame("執勤中祕書資訊")
        head = QHBoxLayout()
        self._sec_portrait = _PixelPortrait()
        head.addWidget(self._sec_portrait, 0, Qt.AlignmentFlag.AlignTop)
        head_text = QVBoxLayout()
        self._sec_name = self._secretary_label("", "hakoniwaSecretaryTitle")
        self._sec_level = self._secretary_label("", "hakoniwaSecretaryValue")
        self._sec_art = self._secretary_label(
            "2D 動態角色圖待島主提供", "hakoniwaSecretaryBody"
        )
        head_text.addWidget(self._sec_name)
        head_text.addWidget(self._sec_level)
        head_text.addWidget(self._sec_art)
        head.addLayout(head_text, 1)
        card_lay.addLayout(head)
        self._sec_perk_radar = self._secretary_label("", "hakoniwaSecretaryGood")
        self._sec_perk_farm = self._secretary_label("", "hakoniwaSecretaryGood")
        self._sec_upkeep = self._secretary_label("", "hakoniwaSecretaryValue")
        card_lay.addWidget(self._sec_perk_radar)
        card_lay.addWidget(self._sec_perk_farm)
        card_lay.addWidget(self._sec_upkeep)
        left.addWidget(card)

        talk, talk_lay = self._secretary_frame("建議與實時對話")
        mood_row = QHBoxLayout()
        self._sec_mini = _PixelPortrait()
        self._sec_mini.setFixedSize(36, 42)
        mood_row.addWidget(self._sec_mini, 0, Qt.AlignmentFlag.AlignTop)
        self._sec_mood = self._secretary_label("", "hakoniwaSecretaryValue")
        mood_row.addWidget(self._sec_mood, 1)
        talk_lay.addLayout(mood_row)
        self._sec_dialogue = self._secretary_label("", "hakoniwaSecretaryBody")
        talk_lay.addWidget(self._sec_dialogue)
        actions = QHBoxLayout()
        self._sec_apply = self._secretary_button("執行建議政策")
        self._sec_ignore = self._secretary_button("忽略")
        self._sec_apply.clicked.connect(self._apply_dialogue)
        self._sec_ignore.clicked.connect(self._ignore_dialogue)
        actions.addWidget(self._sec_apply)
        actions.addWidget(self._sec_ignore)
        talk_lay.addLayout(actions)
        left.addWidget(talk)

        market, market_lay = self._secretary_frame("人才市場／行政總署人才招募")
        market_lay.addWidget(
            self._secretary_label("優秀的顧問是島嶼繁榮的基石。", "hakoniwaSecretaryBody")
        )
        self._sec_interview = self._secretary_button(
            f"普通面試 {SECRETARY_INTERVIEW_COST}　C～R"
        )
        self._sec_headhunt = self._secretary_button(
            f"獵頭招聘 {SECRETARY_HEADHUNT_COST}　SR 以上"
        )
        self._sec_ten = self._secretary_button(
            f"十連聘僱 {SECRETARY_TEN_COST}　9 折"
        )
        self._sec_interview.clicked.connect(lambda: self._recruit("interview"))
        self._sec_headhunt.clicked.connect(lambda: self._recruit("headhunt"))
        self._sec_ten.clicked.connect(lambda: self._recruit("ten"))
        market_lay.addWidget(self._sec_interview)
        market_lay.addWidget(self._sec_headhunt)
        market_lay.addWidget(self._sec_ten)
        market_lay.addWidget(
            self._secretary_label(
                "剩餘免費次數 0　普通面試 C 70%／R 30%　獵頭 SSR 10%，其餘 SR（含克里斯）",
                "hakoniwaSecretaryValue",
            )
        )
        self._sec_result = self._secretary_label("", "hakoniwaSecretaryValue")
        market_lay.addWidget(self._sec_result)
        right.addWidget(market)

        lab, lab_lay = self._secretary_frame("行政研究院／政策研發中心")
        self._sec_research_buttons: Dict[str, QPushButton] = {}
        self._sec_research_notes: Dict[str, QLabel] = {}
        research_rows = (
            (
                RESEARCH_DRONE,
                "科技　智慧型無人機防禦網",
                "資金 1,000、3 回合。完成後解鎖『防空戰備戒嚴』。",
            ),
            (
                RESEARCH_GREENHOUSE,
                "經濟　氣候溫室農業發展",
                "資金 800、糧食 300、3 回合。本島沒有寒冬減產，完成後每回合糧食 +8。",
            ),
            (
                RESEARCH_LURE,
                "特別　怪獸引誘與生態研究",
                "需要秘書克里斯 LV.3。完成後可實施『怪獸誘捕與引流協議』。",
            ),
        )
        for key, title, blurb in research_rows:
            lab_lay.addWidget(self._secretary_label(title, "hakoniwaSecretaryTitle"))
            note = self._secretary_label(blurb, "hakoniwaSecretaryBody")
            self._sec_research_notes[key] = note
            lab_lay.addWidget(note)
            btn = self._secretary_button("可研發")
            btn.clicked.connect(lambda _checked=False, project=key: self._start_research(project))
            self._sec_research_buttons[key] = btn
            lab_lay.addWidget(btn)
        right.addWidget(lab)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns)

        roster, roster_lay = self._secretary_frame("內閣秘書處／換崗調配")
        roster_lay.addWidget(
            self._secretary_label(
                f"交接費 {SECRETARY_SWITCH_COST} 資金，再點一次確認。",
                "hakoniwaSecretaryBody",
            )
        )
        self._sec_roster_host = QWidget()
        self._sec_roster_row = QHBoxLayout(self._sec_roster_host)
        self._sec_roster_row.setContentsMargins(0, 0, 0, 0)
        self._sec_roster_row.setSpacing(4)
        roster_lay.addWidget(self._sec_roster_host)
        self._sec_expand = self._secretary_button(
            f"+擴充欄位 {SECRETARY_EXPAND_COST}"
        )
        self._sec_expand.clicked.connect(self._expand_roster)
        roster_lay.addWidget(self._sec_expand)
        outer.addWidget(roster)
        outer.addStretch(1)
        self._secretary_panel.setWidget(page)
        self._secretary_panel.setVisible(False)
        profile_lay.addWidget(self._secretary_panel, stretch=1)
        self._sec_notice = ""

    def _sync_secretary_panel(self, state: IslandState) -> None:
        sec = state.active_secretary()
        if sec is None:
            return
        spec = sec.spec()
        self._sec_portrait.set_mood(str(state.dialogue_state()["mood"]))
        self._sec_name.setText(f"{sec.name()} · {sec.title()}")
        efficiency = int(spec.get("efficiency") or 0)
        self._sec_level.setText(f"LV.{sec.level}（政務效率 +{efficiency}%）")
        if "radar" in sec.perks():
            cut = int(round((1.0 - float(spec.get("spawn") or 1.0)) * 100))
            self._sec_perk_radar.setText(
                f"專長：防災雷達 怪物出現率 -{cut}%、天災警告提前 1 回合"
            )
        elif "efficiency" in sec.perks():
            self._sec_perk_radar.setText(f"專長：政務效率 +{efficiency}%")
        else:
            self._sec_perk_radar.setText("專長：見習事務")
        if "farming" in sec.perks():
            self._sec_perk_farm.setText("被動：農務指導 糧食產量 +10%（無產量時 +2）")
        else:
            self._sec_perk_farm.setText("被動：無農業指導")
        self._sec_upkeep.setText(f"維護成本：資金 -{int(spec['upkeep'])}／回合")
        info = state.dialogue_state()
        self._sec_mini.set_mood(str(info["mood"]))
        self._sec_mood.setText(f"表情：{info['mood']}")
        if info["dismissed"]:
            self._sec_dialogue.setText("已忽略，下回合再看。")
            self._sec_apply.setEnabled(False)
            self._sec_ignore.setEnabled(False)
        else:
            self._sec_dialogue.setText(str(info["text"]))
            policy = str(info["policy"] or "")
            can_apply = bool(policy) and state.policy_unlocked(policy)
            self._sec_apply.setEnabled(can_apply)
            self._sec_ignore.setEnabled(True)
        self._sec_result.setText(self._sec_notice)
        for key, btn in self._sec_research_buttons.items():
            status = state.research_status(key)
            btn.setText(status)
            btn.setEnabled(status == "可研發")
        while self._sec_roster_row.count():
            item = self._sec_roster_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for member in state.secretaries:
            if member.id == state.active_secretary_id:
                label = f"{member.name()} 上陣中"
            elif self._switch_armed == member.id:
                label = f"{member.name()} 確認 {SECRETARY_SWITCH_COST}"
            else:
                label = f"{member.name()} 待命"
            btn = self._secretary_button(label)
            btn.setCheckable(True)
            btn.setChecked(member.id == state.active_secretary_id)
            btn.clicked.connect(
                lambda _checked=False, sid=member.id: self._pick_secretary(sid)
            )
            self._sec_roster_row.addWidget(btn)
        self._sec_roster_row.addStretch(1)
        self._sec_expand.setEnabled(state.secretary_slots < 12)

    def secretary_page_text(self) -> str:
        parts = [
            self._sec_name.text(),
            self._sec_level.text(),
            self._sec_perk_radar.text(),
            self._sec_perk_farm.text(),
            self._sec_upkeep.text(),
            self._sec_mood.text(),
            self._sec_dialogue.text(),
            self._sec_result.text(),
            "人才市場／行政總署人才招募",
            "行政研究院／政策研發中心",
            "內閣秘書處／換崗調配",
            "執行建議政策",
            "忽略",
        ]
        parts.extend(btn.text() for btn in self._sec_research_buttons.values())
        return "\n".join(parts)

    def _after_secretary(self, state: IslandState) -> None:
        self.refresh_island_profile(state)
        refresh = getattr(self, "_refresh_profile", None)
        if refresh is not None:
            refresh()
        persist = getattr(self, "_persist_profile", None)
        if persist is not None:
            persist()

    def _recruit(self, kind: str) -> None:
        state = self.map.state
        self._sec_notice = state.recruit(kind)
        self._switch_armed = ""
        self._after_secretary(state)

    def _pick_secretary(self, sid: str) -> None:
        state = self.map.state
        spend = False
        if sid == state.active_secretary_id:
            self._switch_armed = ""
        elif self._switch_armed != sid:
            self._switch_armed = sid
        else:
            self._sec_notice = state.appoint(sid)
            self._switch_armed = ""
            spend = True
        if spend:
            QTimer.singleShot(0, lambda: self._after_secretary(state))
        else:
            QTimer.singleShot(0, lambda: self._sync_secretary_panel(state))

    def _expand_roster(self) -> None:
        state = self.map.state
        self._sec_notice = state.expand_secretary_slots()
        self._after_secretary(state)

    def _start_research(self, key: str) -> None:
        state = self.map.state
        self._sec_notice = state.start_research(key)
        self._after_secretary(state)

    def _apply_dialogue(self) -> None:
        state = self.map.state
        if state.apply_dialogue_policy():
            self._sec_notice = "已交給島嶼方針。"
        else:
            self._sec_notice = "現在不能實施這條方針。"
        self._after_secretary(state)

    def _ignore_dialogue(self) -> None:
        state = self.map.state
        state.dismiss_dialogue()
        self._sec_notice = "已忽略。"
        self._after_secretary(state)

    def _choose_policy(self, key: str) -> None:
        state = self.map.state
        state.toggle_policy(key)
        refresh = getattr(self, "_refresh_profile", None)
        if refresh is not None:
            refresh()
        else:
            self.refresh_island_profile(state)
        persist = getattr(self, "_persist_profile", None)
        if persist is not None:
            persist()

    def show_island_profile_page(self, key: str) -> None:
        """Switch the 資訊 drawer among the four pages."""
        if key not in self._profile_tab_buttons:
            key = "basic"
        self._profile_page = key
        btn = self._profile_tab_buttons[key]
        if not btn.isChecked():
            btn.setChecked(True)
        basic = key == "basic"
        self._profile_scroll.setVisible(basic)
        self._policy_panel.setVisible(key == "policy")
        self._secretary_panel.setVisible(key == "secretary")
        self.island_profile_body.setVisible(key not in ("basic", "policy", "secretary"))
        if basic:
            self._profile_accordion.set_sections(self._profile_sections)
            self.island_profile_body.setText(self._profile_accordion.plain_text())
        elif key == "policy":
            self.island_profile_body.setText(self.policy_page_text())
        elif key == "secretary":
            self.island_profile_body.setText(self.secretary_page_text())
        else:
            self.island_profile_body.setText(self._profile_achievement_text)
        self._layout_overlays()

    def _show_notify_menu(self) -> None:
        """Popup: checkable 歷史記錄框 / 警報 / 方格資訊 under the bell."""
        btn = self.icon_bar.button("notify")
        menu = QMenu(self)
        menu.setObjectName("hakoniwaNotifyMenu")
        menu.setStyleSheet(
            "QMenu#hakoniwaNotifyMenu {"
            "  background: rgba(18, 36, 40, 235);"
            "  color: rgb(230, 248, 245);"
            "  border: 1px solid rgba(90, 200, 190, 210);"
            "  padding: 4px;"
            "}"
            "QMenu#hakoniwaNotifyMenu::item {"
            "  padding: 6px 28px 6px 28px;"
            "  border-radius: 3px;"
            "}"
            "QMenu#hakoniwaNotifyMenu::item:selected {"
            "  background: rgba(28, 52, 56, 240);"
            "}"
            "QMenu#hakoniwaNotifyMenu::indicator {"
            "  width: 14px; height: 14px;"
            "}"
        )
        act_log = QAction("歷史記錄框", menu)
        act_log.setCheckable(True)
        act_log.setChecked(self._log_visible)
        act_log.toggled.connect(self.set_log_visible)
        menu.addAction(act_log)

        act_alert = QAction("警報", menu)
        act_alert.setCheckable(True)
        act_alert.setChecked(self._marquee_enabled)
        act_alert.toggled.connect(self.set_marquee_enabled)
        menu.addAction(act_alert)

        act_tile = QAction("方格資訊", menu)
        act_tile.setCheckable(True)
        act_tile.setChecked(self._tile_info_visible)
        act_tile.toggled.connect(self.set_tile_info_visible)
        menu.addAction(act_tile)

        if btn is not None:
            global_tl = btn.mapToGlobal(QPoint(0, 0))
            hint = menu.sizeHint()
            menu.exec(QPoint(global_tl.x(), global_tl.y() - hint.height() - 4))
        else:
            menu.exec(self.cursor().pos())

    def _on_icon_clicked(self, kind: str) -> None:
        if kind == "notify":
            self._show_notify_menu()

    def _on_icon_toggled(self, kind: str, checked: bool) -> None:
        """Wire icon checks to panels; build／info／guestbook／settings exclusive."""
        # 通知 is a menu launcher (not a drawer / not a master chrome toggle).
        exclusive = ("build", "info", "guestbook", "settings")
        if kind in exclusive and checked:
            for other in exclusive:
                if other != kind:
                    btn = self.icon_bar.button(other)
                    if btn is not None and btn.isChecked():
                        btn.setChecked(False)

        if kind == "notify":
            # Cosmetic checked state only (synced from menu options).
            return
        if kind == "build":
            self.tools_drawer.setVisible(checked)
        elif kind == "info":
            self.island_profile.setVisible(checked)
        elif kind == "guestbook":
            self.guestbook_frame.setVisible(checked)
        elif kind == "settings":
            self.settings_drawer.setVisible(checked)

        self._layout_overlays()
        self._raise_overlays()

    def toggle_tools(self) -> None:
        btn = self.icon_bar.button("build")
        if btn is not None:
            btn.toggle()

    def close_tools(self) -> None:
        btn = self.icon_bar.button("build")
        if btn is not None and btn.isChecked():
            btn.setChecked(False)

    def close_bottom_panels(self) -> None:
        """Close build / info / guestbook / settings drawers (notify stays)."""
        for kind in ("build", "info", "guestbook", "settings"):
            btn = self.icon_bar.button(kind)
            if btn is not None and btn.isChecked():
                btn.setChecked(False)

    def set_tourism_chrome(self) -> None:
        """Tourism: hide build tools; keep guestbook／info／notify／settings icons."""
        self.icon_bar.set_icon_visible("build", False)
        self.tools_drawer.hide()
        # Ensure guestbook starts closed (open via 留言).
        gb = self.icon_bar.button("guestbook")
        if gb is not None and gb.isChecked():
            gb.setChecked(False)
        self.guestbook_frame.hide()
        info = self.icon_bar.button("info")
        if info is not None and info.isChecked():
            info.setChecked(False)
        self.island_profile.hide()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_overlays()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        # Parent show can leave overlay geometry stale if resize did not fire
        # after isHidden()-safe layout (icon bar would stick at 0,0).
        super().showEvent(event)
        self._layout_overlays()

    def eventFilter(self, watched, event):  # noqa: N802
        # Keep overlays above the map if something re-raises the map.
        if watched is self.map and event.type() == QEvent.Type.Show:
            self._raise_overlays()
        return super().eventFilter(watched, event)

    def _raise_overlays(self) -> None:
        for w in (
            self.stats,
            self.alert_marquee,
            self.sel_label,
            self.log_view,
            self.guestbook_frame,
            self.tools_drawer,
            self.settings_drawer,
            self.island_profile,
            self.icon_bar,
        ):
            # isHidden() = explicit hide; isVisible() is false before ancestors show.
            if not w.isHidden():
                w.raise_()

    def _layout_overlays(self) -> None:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        self.map.setGeometry(0, 0, w, h)
        self.map.lower()

        margin = 8
        # Status — top center, single horizontal line (odometer strip; no wrap).
        fm = self.stats.fontMetrics()
        hint = self.stats.sizeHint()
        text = self.stats.text() or ""
        text_w = max(hint.width(), fm.horizontalAdvance(text) + 24)
        status_h = max(hint.height(), fm.height() + 10, 26)
        status_w = min(max(text_w, 200), w - 2 * margin)
        status_x = (w - status_w) // 2
        self.stats.setGeometry(status_x, margin, status_w, status_h)


        # Alert marquee — directly under the status strip (same width band).
        below = margin + status_h
        if not self.alert_marquee.isHidden():
            mq_h = self.alert_marquee.height()
            mq_w = min(max(status_w, 280), w - 2 * margin)
            mq_x = (w - mq_w) // 2
            self.alert_marquee.setGeometry(mq_x, below + 4, mq_w, mq_h)
            below = below + 4 + mq_h

        # Tile info — top-left below status／marquee
        if not self.sel_label.isHidden():
            self.sel_label.adjustSize()
            tile_w = min(220, max(140, w // 4))
            tile_h = max(self.sel_label.sizeHint().height() + 8, 56)
            self.sel_label.setGeometry(margin, below + 6, tile_w, tile_h)


        # Icon bar — bottom-left (replaces orange 工具／設定).
        # Use isHidden(), not isVisible(): during __init__ / pre-show layout,
        # isVisible() is False for every child.
        btn_x = margin
        if not self.icon_bar.isHidden():
            bar_w = self.icon_bar.width()
            bar_h = self.icon_bar.height()
            btn_y = h - margin - bar_h
            self.icon_bar.setGeometry(btn_x, btn_y, bar_w, bar_h)
            btn_w, btn_h = bar_w, bar_h
        else:
            btn_w = 0
            btn_h = 0
            btn_y = h - margin

        # Drawers — left side. Build drawer is full height (prefs 建築抽屜樹);
        # settings／island profile stay compact above the icon bar.
        build_w = min(460, max(320, w // 2))
        settings_w = min(280, max(200, w // 3))
        page = getattr(self, "_profile_page", "")
        if page == "policy":
            profile_w = min(480, max(440, w // 2))
        elif page == "secretary":
            profile_w = min(680, max(600, (w * 2) // 3))
        else:
            profile_w = min(360, max(300, w // 3))
        gap_above_bar = 6
        full_h = max(220, btn_y - gap_above_bar - margin)

        if not self.tools_drawer.isHidden():
            self.tools_drawer.setGeometry(margin, margin, build_w, full_h)
        if not self.settings_drawer.isHidden():
            settings_h = min(160, full_h)
            self.settings_drawer.setGeometry(
                margin, max(margin, btn_y - gap_above_bar - settings_h),
                settings_w, settings_h,
            )
        if not self.island_profile.isHidden():
            profile_top = below + 4
            profile_h = max(220, btn_y - gap_above_bar - profile_top)
            self.island_profile.setGeometry(
                margin, profile_top, profile_w, profile_h,
            )

        # Action log — bottom-right (~70% transparent frame)
        log_w = min(260, max(160, w // 3))
        log_h = min(160, max(90, h // 4))
        if not self.log_view.isHidden():
            self.log_view.setGeometry(
                w - margin - log_w, h - margin - log_h, log_w, log_h
            )

        # Guestbook — bottom center, between icon bar and log (when open)
        if not self.guestbook_frame.isHidden():
            gb_left = btn_x + (btn_w + 8 if btn_w else 0)

            gb_right = w - margin - (log_w if not self.log_view.isHidden() else 0) - 8

            gb_w = max(180, gb_right - gb_left)
            gb_h = min(130, max(96, h // 5))
            if gb_w < 160:
                gb_w = min(240, w - 2 * margin - btn_w - 8)
                gb_left = btn_x + (btn_w + 8 if btn_w else 0)
            self.guestbook_frame.setGeometry(
                gb_left, h - margin - gb_h, gb_w, gb_h
            )

        self._raise_overlays()


# Toolbar: (action key, display name, cost or None, shortcut digit/letter)
TOOL_SPECS: Tuple[Tuple[str, str, Optional[int], str], ...] = (
    ("farm", "建設農場", COST_FARM, "1"),
    ("factory", "建設工場", COST_FACTORY, "2"),
    ("remove", "移除建築", None, "3"),
    ("landfill", "填海造陸", COST_LANDFILL, "4"),
    ("level", "整地", COST_LEVEL, "5"),
    ("raise", "造山", COST_RAISE, "R"),
    ("quarry", "建設採掘場", COST_QUARRY, "Q"),
    ("excavate", "掘削／探油", COST_EXCAVATE, "X"),
    ("breakwater", "建設防波堤", COST_BREAKWATER, "W"),
    ("afforest", "植林", COST_AFFOREST, "6"),
    ("harvest", "伐採", COST_HARVEST if COST_HARVEST else None, "C"),
    ("missile", "發射飛彈", COST_MISSILE, "7"),
    ("wait", "觀望怪獸", None, "8"),
    ("defense", "建設防衛設施", COST_DEFENSE, "9"),
    ("missile_base", "建設飛彈基地", COST_MISSILE_BASE, "B"),
    ("decoy", "建設紙糊假設施", COST_DECOY, "Shift+B"),
    ("harbor", "建設港灣", COST_HARBOR, "H"),
    ("shipyard", "建設造船所", COST_SHIPYARD, "Y"),
    ("export", "貿易輸出", None, "E"),
    ("monument", "建設紀念碑", COST_MONUMENT, "M"),
    ("bank", "建設銀行", COST_BANK, "N"),
    ("supermarket", "建設超市", COST_SUPERMARKET, "S"),
    ("shrine", "建設神社", COST_SHRINE, "Z"),
    ("park", "建設公園", COST_PARK, "K"),
    ("airport", "建設空港", COST_AIRPORT, "I"),
    ("rocket_base", "建設ロケット基地", COST_ROCKET_BASE, "O"),
    ("rocket_launch", "發射火箭", COST_ROCKET_LAUNCH, "L"),
    ("hotel", "建設酒店", COST_HOTEL, "T"),
    ("casino", "建設賭場", COST_CASINO, "G"),
    ("university", "建設大學", COST_UNIVERSITY, "F"),
    ("research_lab", "建設研究所", COST_RESEARCH_LAB, "J"),
    ("attract", "誘致活動", COST_ATTRACT, "A"),
    ("deposit", "銀行存款", None, "D"),
    ("withdraw", "銀行提款", None, "U"),
    ("buy_food", "超市買糧", None, "P"),
    ("aquafarm", "建設養殖場", COST_AQUAFARM, "V"),
    ("amusement_park", "建設遊樂園", COST_AMUSEMENT_PARK, "Shift+V"),
    ("power_plant", "建設發電廠", COST_POWER_PLANT, "Shift+P"),
    ("undersea_base", "建設海底基地", COST_UNDERSEA_BASE, "Shift+S"),
    # Hard-locked catalog row: visible, never placeable (no shortcut).
    ("onsen_village", "溫泉村", 0, ""),
)


def tool_enabled(
    state: IslandState, kind: str, selected: Optional[Tuple[int, int]]
) -> Tuple[bool, str]:
    """Whether a toolbar action can run on the current selection.

    Returns (enabled, reason). Reason is empty when enabled; otherwise a short
    tip for the button tooltip (can't afford / wrong terrain / no selection).
    """
    # 溫泉村 stays locked until 溫泉開村.
    if state.placement_hard_locked(kind):
        return False, "鎖定：只能在溫泉山旁的平地自然出現"

    # 觀望：島上有怪獸即可（不必選格）.
    if kind == "wait":
        if not state.has_monster():
            return False, "島上沒有怪獸"
        return True, ""

    # 貿易輸出：有港灣或造船所即可（不必選格）.
    if kind == "export":
        if not state.can_trade_export():
            return False, "需要港灣或造船所"
        if state.food < FOOD_EXPORT_LOT:
            return False, f"糧食不足（一批需 {FOOD_EXPORT_LOT}）"
        return True, ""

    # 銀行存提：有銀行即可（不必選格）.
    if kind == "deposit":
        if not state.can_bank_transfer():
            return False, "需要銀行"
        if state.funds < BANK_TRANSFER_LOT:
            return False, f"流動資金不足（一批需 {BANK_TRANSFER_LOT}）"
        return True, ""
    if kind == "withdraw":
        if not state.can_bank_transfer():
            return False, "需要銀行"
        if state.bank_deposit < BANK_TRANSFER_LOT:
            return False, f"存款不足（一批需 {BANK_TRANSFER_LOT}）"
        return True, ""

    # 超市買糧：有超市即可（不必選格）.
    if kind == "buy_food":
        if not state.can_buy_food():
            return False, "需要超市"
        cost = food_buy_cost(1)
        if state.funds < cost:
            return False, f"資金不足（一批需 {cost}）"
        return True, ""

    # 誘致活動：不必選格；已安排則等下回合.
    if kind == "attract":
        if state.attract_pending:
            return False, "已安排誘致（請先推進回合）"
        if state.funds < COST_ATTRACT:
            return False, f"資金不足（需 {COST_ATTRACT}）"
        return True, ""

    # ロケット發射：不必選格；需基地；已在軌則鎖；大學可折扣.
    if kind == "rocket_launch":
        if not state.has_rocket_base():
            return False, "需要ロケット基地"
        if state.has_satellite():
            return False, "觀測衛星已在軌"
        launch_cost = state.rocket_launch_cost()
        if state.funds < launch_cost:
            return False, f"資金不足（需 {launch_cost}）"
        return True, ""

    if selected is None:
        return False, "請先選格"
    i, j = selected
    c = state.cell(i, j)

    if kind == "missile":
        has_monster = state.monster_at(i, j) is not None
        has_decoy = c.building == "decoy"
        if not has_monster and not has_decoy:
            return False, "此格沒有怪獸／紙糊"
        cost = state.missile_cost()
        if state.funds < cost:
            return False, f"資金不足（需 {cost}）"
        return True, ""

    if kind in PLACEABLE_BUILDINGS or state.achievement_unlocks(kind):
        unlocked, lock_reason = state.building_unlock_met(kind)
        if not unlocked:
            return False, lock_reason
        cost = int(BUILDINGS[kind]["cost"])
        if state.monster_at(i, j) is not None:
            return False, "此格有怪獸"
        # 防衛再建設＝自爆（定本）：已有防衛時改為自爆指令.
        if kind == "defense" and c.building == "defense":
            if state.funds < COST_DEFENSE:
                return False, f"資金不足（自爆需 {COST_DEFENSE}）"
            return True, ""
        if c.building is not None:
            return False, "此格已有建築"
        if kind in MOUNTAIN_ONLY_BUILDINGS:
            if c.terrain not in MOUNTAIN_FAMILY:
                return False, "採掘場須建在山上"
        elif kind in SHALLOW_ONLY_BUILDINGS:
            if c.terrain != "shallow":
                return False, "養殖場須建在淺灘"
        elif kind in SEA_ONLY_BUILDINGS:
            if c.terrain != "sea":
                return False, "海底基地須建在深海"
        elif c.terrain not in BUILDABLE:
            return False, "須在平地建設"
        if kind in COASTAL_BUILDINGS and not state._adjacent_to_sea(i, j):
            return False, "須臨海平地（鄰海／淺灘／油田）"
        if state.funds < cost:
            return False, f"資金不足（需 {cost}）"
        return True, ""

    if kind == "remove":
        if c.building is None:
            return False, "此格沒有建築"
        return True, ""

    if kind == "landfill":
        if not state.can_landfill(i, j):
            return False, "須鄰陸的海／淺灘"
        if state.funds < COST_LANDFILL:
            return False, f"資金不足（需 {COST_LANDFILL}）"
        return True, ""

    if kind == "level":
        if not state.can_level(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "此格無需整地"
        if state.funds < COST_LEVEL:
            return False, f"資金不足（需 {COST_LEVEL}）"
        return True, ""

    if kind == "raise":
        if not state.can_raise_mountain(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "須空的荒地或平地"
        if state.funds < COST_RAISE:
            return False, f"資金不足（需 {COST_RAISE}）"
        return True, ""

    if kind == "excavate":
        if not state.can_excavate(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "須空陸／淺灘／海"
        if state.funds < COST_EXCAVATE:
            return False, f"資金不足（需 {COST_EXCAVATE}）"
        return True, ""

    if kind == "afforest":
        if not state.can_afforest(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "須空的平地"
        if state.funds < COST_AFFOREST:
            return False, f"資金不足（需 {COST_AFFOREST}）"
        return True, ""

    if kind == "harvest":
        if not state.can_harvest(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "須為森林"
        return True, ""

    return False, "未知指令"


def _dp():
    """Late import so desktop_pet can finish loading before we pull chrome helpers."""
    import desktop_pet as dp

    return dp


class HakoniwaIslandDialog(QDialog):
    """Playable 箱庭島 v1 (optional NAS sync + local JSON fallback).

    Uses the same frameless / ornate-frame chrome as other mini-programs by
    calling desktop_pet helpers after the host module is fully initialized.
    """

    def __init__(self, config_manager=None, parent=None):
        dp = _dp()
        super().__init__(parent)
        self.cfg = config_manager
        self.remote: HakoniwaRemote | None = None
        self._online = False

        # Match FramelessCalcDialog shell.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._drag_grips = []

        self.setWindowTitle("箱庭島（未完成）／Hakoniwa (WIP)")
        self.setMinimumSize(720, 720)
        self.resize(900, 780)
        self.setStyleSheet(dp.CALC_DIALOG_STYLE + getattr(dp, "MINI_PROGRAM_STYLE", ""))

        self._save_path = self._resolve_save_path()
        self._status_seen_path = status_seen_path(self._save_path)
        # Optional user PNGs: Data/hakoniwa/user/ (beside save) then assets/user/.
        configure_user_art(self._save_path.parent.parent)
        ATLAS.invalidate_user_cache()
        loaded = load_island(self._save_path)
        self.state = loaded if loaded is not None else IslandState.new_game()
        self.selected = None
        # Open-island odometer roll: only when persisted turn snapshot advanced.
        self._pending_open_roll: Optional[Tuple[Dict[str, int], Dict[str, int]]] = None
        self._open_roll_armed = False
        seen = load_status_seen(self._status_seen_path)
        current = snapshot_from_state(self.state)
        if seen is not None and int(seen.get("turn", -1)) != int(current["turn"]):
            self._pending_open_roll = (seen, current)
        else:
            # Same turn (or first visit): show current; do not replay the roll.
            save_status_seen(self._status_seen_path, current)

        root = dp.install_ornate_calc_frame(self)
        root.setSpacing(4)
        root.addWidget(dp.make_draggable_title(self, "箱庭島（未完成）／Hakoniwa (WIP)"))

        # Map fills the body; all numeric/function UI is in-viewport HUD.
        # (No top instruction banner — controls live in the bottom icon bar.)
        self.map = HakoniwaMapWidget(self.state)
        self.map.cell_clicked.connect(self._on_cell_clicked)
        self.hud = HakoniwaMapHud(self.map)
        self.hud._persist_profile = self._cache_local
        self.hud._refresh_profile = self._refresh_ui
        self.stats = self.hud.stats
        self.sel_label = self.hud.sel_label
        self.log_view = self.hud.log_view
        self.guestbook_view = self.hud.guestbook_view
        root.addWidget(self.hud, stretch=1)

        # --- Build tools drawer (建築 icon): tree browse + hidden tool buttons ---
        self._tool_spec_by_key: Dict[str, Tuple[str, Optional[int], str]] = {
            key: (name, cost, digit) for key, name, cost, digit in TOOL_SPECS
        }
        self.tool_buttons: Dict[str, QPushButton] = {}
        # Hidden buttons keep shortcut / smoke enable-state API.
        self._hidden_tools = QWidget(self.hud.tools_drawer)
        self._hidden_tools.setVisible(False)
        hidden_lay = QVBoxLayout(self._hidden_tools)
        hidden_lay.setContentsMargins(0, 0, 0, 0)
        for key, name, cost, digit in TOOL_SPECS:
            if key in HARD_LOCKED_BUILDINGS:
                text = f"🔒 {name}（鎖定）"
            elif cost is None:
                text = f"{digit}. {name}"
            else:
                text = f"{digit}. {name}（{cost}）"
            btn = QPushButton(text)
            btn.setObjectName("calcAction")
            btn.setProperty("toolKey", key)
            btn.clicked.connect(lambda checked=False, k=key: self._do_action(k))
            btn.setVisible(False)
            hidden_lay.addWidget(btn)
            self.tool_buttons[key] = btn

        self._populate_build_tree()
        self.hud.build_place_btn.clicked.connect(self._on_build_place_clicked)

        # Server connection lives in the 設定 drawer (was under 工具／設定).
        settings_lay = self.hud.settings_layout
        settings_cap = QLabel("設定 · 伺服器連線")
        settings_cap.setObjectName("hakoniwaHudCaption")
        settings_lay.addWidget(settings_cap)

        self.server_url = QLineEdit()
        self.server_url.setObjectName("hakoniwaHudInput")
        self.server_url.setPlaceholderText("留空＝本機；例 http://192.168.1.10:8787")
        self.server_url.setText(self._load_server_url())
        settings_lay.addWidget(self.server_url)

        sync_row = QHBoxLayout()
        sync_row.setSpacing(4)
        connect_btn = QPushButton("連線")
        connect_btn.setObjectName("hakoniwaDrawerAction")
        connect_btn.clicked.connect(self._connect_server)
        sync_row.addWidget(connect_btn)
        local_btn = QPushButton("本機")
        local_btn.setObjectName("hakoniwaDrawerAction")
        local_btn.clicked.connect(self._use_local)
        sync_row.addWidget(local_btn)
        settings_lay.addLayout(sync_row)

        self.conn_status = QLabel()
        self.conn_status.setObjectName("hakoniwaHudCaption")
        self.conn_status.setWordWrap(True)
        settings_lay.addWidget(self.conn_status)

        # Guestbook form fields inside the translucent bottom overlay.
        gb_form = self.hud.guestbook_form
        name_cap = QLabel("名字")
        name_cap.setObjectName("hakoniwaHudCaption")
        gb_form.addWidget(name_cap)
        self.guest_name = QLineEdit()
        self.guest_name.setObjectName("hakoniwaHudInput")
        self.guest_name.setPlaceholderText("訪客名")
        self.guest_name.setMaxLength(MAX_GUEST_NAME)
        self.guest_name.setFixedWidth(90)
        gb_form.addWidget(self.guest_name)
        self.guest_text = QLineEdit()
        self.guest_text.setObjectName("hakoniwaHudInput")
        self.guest_text.setPlaceholderText("寫點什麼…")
        self.guest_text.setMaxLength(MAX_GUEST_TEXT)
        gb_form.addWidget(self.guest_text, stretch=1)
        post_btn = QPushButton("留言")
        post_btn.setObjectName("calcAction")
        post_btn.clicked.connect(self._post_guestbook)
        gb_form.addWidget(post_btn)
        refresh_gb = QPushButton("整理")
        refresh_gb.setObjectName("calcAction")
        refresh_gb.setToolTip("重新整理留言板")
        refresh_gb.clicked.connect(self._reload_guestbook)
        gb_form.addWidget(refresh_gb)

        self._install_shortcuts()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        # Auto-connect if URL already saved; otherwise stay local.
        if self.server_url.text().strip():
            self._connect_server(silent_ok=True)
        else:
            self._set_offline("本機模式（JSON 存檔）")
        self._refresh_ui()
        self.hud._layout_overlays()

    def _install_shortcuts(self) -> None:
        """Optional keyboard shortcuts for local play (tools / turn / view).

        Ignored while typing in guestbook / server URL fields.
        """
        for key, _name, _cost, digit in TOOL_SPECS:
            if not str(digit).strip():
                continue
            sc = QShortcut(QKeySequence(digit), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(lambda k=key: self._shortcut_tool(k))

        sc_turn = QShortcut(QKeySequence(Qt.Key.Key_T), self)
        sc_turn.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_turn.activated.connect(self._shortcut_next_turn)

        sc_save = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        sc_save.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_save.activated.connect(self._shortcut_save)

        sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        sc_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_esc.activated.connect(self._clear_selection)

        sc_reset = QShortcut(QKeySequence(Qt.Key.Key_0), self)
        sc_reset.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_reset.activated.connect(self._shortcut_reset_view)

        sc_zoom_in = QShortcut(QKeySequence(Qt.Key.Key_Plus), self)
        sc_zoom_in.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_zoom_in.activated.connect(lambda: self._shortcut_zoom(1.12))
        sc_zoom_eq = QShortcut(QKeySequence(Qt.Key.Key_Equal), self)
        sc_zoom_eq.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_zoom_eq.activated.connect(lambda: self._shortcut_zoom(1.12))
        sc_zoom_out = QShortcut(QKeySequence(Qt.Key.Key_Minus), self)
        sc_zoom_out.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_zoom_out.activated.connect(lambda: self._shortcut_zoom(1.0 / 1.12))

    def _typing_in_field(self) -> bool:
        w = self.focusWidget()
        return isinstance(w, (QLineEdit, QPlainTextEdit))

    def _shortcut_tool(self, kind: str) -> None:
        """Run tool from digit shortcut only if the button is currently enabled."""
        if self._typing_in_field():
            return
        btn = self.tool_buttons.get(kind)
        if btn is None or not btn.isEnabled():
            return
        self._do_action(kind)

    def _shortcut_next_turn(self) -> None:
        if self._typing_in_field():
            return
        self._next_turn()

    def _shortcut_save(self) -> None:
        if self._typing_in_field():
            return
        self._save()

    def _shortcut_reset_view(self) -> None:
        if self._typing_in_field():
            return
        self.map.reset_view()

    def _shortcut_zoom(self, factor: float) -> None:
        if self._typing_in_field():
            return
        self.map.zoom_by(factor)

    def _populate_build_tree(self) -> None:
        """Fill catalog categories with List Row Fill headers + Timeline children.

        Category rows always show number · name · (→ on hover) and thin
        separators above/below. Children start collapsed; expand plays
        Timeline Draw (~2.4s).
        """
        lay = self.hud.build_nav_layout
        # Clear previous widgets (keep trailing stretch).
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._tree_items: Dict[str, TimelineNodeData] = {}
        self._child_base_labels: Dict[str, str] = {}
        self._child_details: Dict[str, str] = {}
        self._category_rows: Dict[str, HakoniwaListRowFillItem] = {}
        self._category_panels: Dict[str, TimelineDrawPanel] = {}
        self._category_expanded: Dict[str, bool] = {}
        self._category_names: List[str] = []
        self._key_to_category: Dict[str, str] = {}

        cat_index = 0
        for cat_name, keys in build_tree_categories():
            child_specs: List[Tuple[str, str, str, str]] = []
            for key in keys:
                if key in settlement_keys_for_tree():
                    label = display_label(key)
                    digit = ""
                    cost = None
                elif key in self._tool_spec_by_key:
                    name, cost, digit = self._tool_spec_by_key[key]
                    label = display_label(key, name)
                else:
                    continue
                if cost is None:
                    detail = f"⌨{digit}" if digit else ""
                else:
                    detail = str(cost)
                child_specs.append((key, label, digit, detail))
            if not child_specs:
                continue
            cat_index += 1

            row = HakoniwaListRowFillItem(cat_index, cat_name, self.hud.build_nav_body)
            row.clicked.connect(
                lambda checked=False, n=cat_name: self._toggle_build_category(n)
            )
            lay.insertWidget(lay.count() - 1, row)
            self._category_rows[cat_name] = row
            self._category_names.append(cat_name)
            self._category_expanded[cat_name] = False

            panel = TimelineDrawPanel(self.hud.build_nav_body)
            nodes: List[TimelineNodeData] = []
            for key, label, digit, detail in child_specs:
                node = TimelineNodeData(key=key, title=label, detail=detail)
                nodes.append(node)
                self._tree_items[key] = node
                self._child_base_labels[key] = label
                self._child_details[key] = detail
                self._key_to_category[key] = cat_name
            panel.set_nodes(nodes)
            panel.nodeClicked.connect(self._on_build_child_clicked)
            panel.nodeActivated.connect(self._on_build_child_activate)
            panel.setVisible(False)  # children default collapsed
            lay.insertWidget(lay.count() - 1, panel)
            self._category_panels[cat_name] = panel

    def _toggle_build_category(self, cat_name: str) -> None:
        """Expand／collapse children; expand plays Timeline Draw."""
        panel = self._category_panels.get(cat_name)
        if panel is None:
            return
        nxt = not self._category_expanded.get(cat_name, False)
        self._category_expanded[cat_name] = nxt
        if nxt:
            panel.setVisible(True)
            panel.play_expand()
        else:
            panel.reset_collapsed()
            panel.setVisible(False)

    def is_category_expanded(self, cat_name: str) -> bool:
        return bool(self._category_expanded.get(cat_name, False))

    def _select_build_child(self, key: str) -> None:
        """Mark ``key`` selected in the nav and refresh the detail pane."""
        self.hud._build_tree_key = key
        for panel in self._category_panels.values():
            panel.set_selected_key(key)
        self._refresh_build_detail()

    def _on_build_child_clicked(self, key: str) -> None:
        self._select_build_child(key)

    def _on_build_child_activate(self, key: str) -> None:
        self._select_build_child(key)
        met, _ = unlock_met(self.state, key)
        if not met:
            return
        btn = self.tool_buttons.get(key)
        if btn is not None and btn.isEnabled():
            self._do_action(key)

    def _on_build_place_clicked(self) -> None:
        key = self.hud._build_tree_key
        if not key:
            return
        met, _ = unlock_met(self.state, key)
        if not met:
            return
        btn = self.tool_buttons.get(key)
        if btn is not None and btn.isEnabled():
            self._do_action(key)

    def _refresh_build_tree_locks(self) -> None:
        """Hard-lock child rows whose island unlock prerequisites are unmet."""
        lock = " 🔒"
        for key, node in getattr(self, "_tree_items", {}).items():
            met, reason = unlock_met(self.state, key)
            base = self._child_base_labels.get(key, display_label(key))
            title = base if met else base + lock
            node.title = title
            node.locked = not met
            cat = self._key_to_category.get(key)
            panel = self._category_panels.get(cat) if cat else None
            if panel is not None:
                panel.set_node_locked(key, not met, title)
                tip = base if met else (
                    f"{base}\n鎖定：{reason}" if reason else f"{base}\n鎖定"
                )
                panel.setToolTip(tip if key == (self.hud._build_tree_key or "") else panel.toolTip())

    def _refresh_build_detail(self) -> None:
        key = self.hud._build_tree_key
        title = self.hud.build_detail_title
        cost_lab = self.hud.build_detail_cost
        status_lab = self.hud.build_detail_status
        place_lab = self.hud.build_detail_place
        effects_lab = self.hud.build_detail_effects
        place_btn = self.hud.build_place_btn
        if not key:
            title.setText("選擇建築／指令")
            cost_lab.setText("")
            status_lab.setText("")
            place_lab.setText("")
            effects_lab.setText("")
            place_btn.setEnabled(False)
            place_btn.setText("放置")
            return

        tool_name = (
            self._tool_spec_by_key[key][0] if key in self._tool_spec_by_key else None
        )
        tool_cost = (
            self._tool_spec_by_key[key][1] if key in self._tool_spec_by_key else None
        )
        label = display_label(key, tool_name)
        title.setText(label)

        shown_cost = cost_for_kind(self.state, key, tool_cost)
        if shown_cost is None:
            cost_lab.setText("費用: 免費／依指令")
        elif shown_cost == 0 and (
            key in settlement_keys_for_tree()
            or self.state.placement_hard_locked(key)
        ):
            cost_lab.setText("費用: 0（非點選建造）")
        else:
            cost_lab.setText(f"資金: {shown_cost}")

        met, lock_reason = unlock_met(self.state, key)
        prereq = unlock_prereq(key)
        if self.state.placement_hard_locked(key):
            status_lab.setText(f"狀態: 鎖定 🔒\n前提: {lock_reason}")
        elif key in settlement_keys_for_tree():
            status_lab.setText("狀態: 瀏覽用（人口演進）\n前提: 不可點選建造")
        elif met:
            prereq_txt = "無" if prereq is None else display_label(prereq[0].split("|")[0])
            if prereq and "|" in prereq[0]:
                prereq_txt = " 或 ".join(
                    display_label(p) for p in prereq[0].split("|")
                )
            status_lab.setText(f"已解鎖\n前提: {prereq_txt}")
        else:
            status_lab.setText(f"未解鎖 🔒\n前提: {lock_reason}")

        place_lab.setText(f"配置條件: {placement_blurb(key)}")
        lines = effect_lines(key)
        effects_lab.setText("\n".join(f"· {ln}" for ln in lines) if lines else "")

        # Action label: 放置 for buildings, otherwise keep tool verb.
        if key in PLACEABLE_BUILDINGS or self.state.achievement_unlocks(key):
            place_btn.setText("放置")
        elif key in settlement_keys_for_tree() or key in HARD_LOCKED_BUILDINGS:
            place_btn.setText("不可建造")
        else:
            place_btn.setText("執行")

        btn = self.tool_buttons.get(key)
        can_run = bool(met and btn is not None and btn.isEnabled())
        place_btn.setEnabled(can_run)

    def _clear_selection(self) -> None:
        self.selected = None
        self.map.clear_selection()
        self._refresh_selection_label()
        self._refresh_toolbar()

    def _resolve_save_path(self) -> Path:
        if self.cfg is not None and getattr(self.cfg, "config_path", None):
            return default_save_path(Path(self.cfg.config_path).parent)
        return default_save_path(Path.cwd())

    def _load_server_url(self) -> str:
        if self.cfg is None:
            return ""
        return str(self.cfg.get("hakoniwa", "server_url") or "")

    def _load_api_key(self) -> str:
        if self.cfg is None:
            return ""
        return str(self.cfg.get("hakoniwa", "api_key") or "")

    def _persist_server_url(self) -> None:
        if self.cfg is None:
            return
        self.cfg.set(["hakoniwa", "server_url"], self.server_url.text().strip(), save=True)

    def _set_offline(self, reason: str) -> None:
        self.remote = None
        self._online = False
        self.conn_status.setText(reason)

    def _apply_island(self, state: IslandState) -> None:
        self.state = state
        self.map.set_state(self.state)

    def _cache_local(self) -> None:
        """Always keep a local JSON mirror so disconnect falls back cleanly."""
        try:
            save_island(self.state, self._save_path)
        except OSError:
            pass

    def _connect_server(self, silent_ok: bool = False) -> None:
        url = self.server_url.text().strip()
        self._persist_server_url()
        if not url:
            self._set_offline("本機模式（JSON 存檔）— 伺服器欄位為空")
            return
        client, island, err = try_connect(url, api_key=self._load_api_key())
        if err or client is None or island is None:
            self._set_offline(f"連線失敗，改用本機：{err or '未知錯誤'}")
            QMessageBox.warning(
                self,
                "箱庭島",
                f"無法連線伺服器，將繼續使用本機存檔。\n\n{err or ''}",
            )
            return
        self.remote = client
        self._online = True
        self._apply_island(island)
        self._cache_local()
        self.conn_status.setText(f"已連線：{client.base_url}")
        if not silent_ok:
            QMessageBox.information(self, "箱庭島", f"已同步島狀態\n{client.base_url}")
        self._refresh_ui()

    def _use_local(self) -> None:
        self._set_offline("本機模式（JSON 存檔）")
        loaded = load_island(self._save_path)
        if loaded is not None:
            self._apply_island(loaded)
        self._refresh_ui()

    def _format_guestbook(self, comments: List[GuestbookEntry]) -> str:
        if not comments:
            return "（尚無留言）"
        lines = []
        for c in comments:
            stamp = c.at.replace("T", " ").rstrip("Z")
            lines.append(f"[{stamp}] {c.name}：{c.text}")
        return "\n".join(lines)

    def _show_guestbook(self, comments: List[GuestbookEntry]) -> None:
        self.guestbook_view.setPlainText(self._format_guestbook(comments))
        bar = self.guestbook_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _reload_guestbook(self) -> None:
        if self._online and self.remote is not None:
            try:
                comments = self.remote.list_comments()
                self.state.comments = list(comments)
                self._cache_local()
                self._show_guestbook(comments)
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
        self._show_guestbook(self.state.list_comments())

    def _post_guestbook(self) -> None:
        name = self.guest_name.text()
        text = self.guest_text.text()
        if self._online and self.remote is not None:
            try:
                ok, err, comments = self.remote.post_comment(name, text)
                self.state.comments = list(comments)
                self._cache_local()
                self._show_guestbook(comments)
                if not ok:
                    QMessageBox.information(self, "箱庭島", err or "留言失敗")
                    return
                self.guest_text.clear()
                self._refresh_ui()
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)

        msg = self.state.add_comment(name, text)
        if msg != "ok":
            QMessageBox.information(self, "箱庭島", msg)
            return
        self.guest_text.clear()
        self._refresh_ui()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # Arm open-island odometer roll once the window is on screen.
        if self._pending_open_roll is not None and not self._open_roll_armed:
            self._open_roll_armed = True
            frm, to = self._pending_open_roll
            self._pending_open_roll = None
            monster_bit = self._monster_status_suffix()
            self.stats.set_values(frm, animate=False, suffix=monster_bit)
            # Persist *current* snapshot immediately so a same-turn re-open
            # does not replay the roll even if the animation is still running.
            save_status_seen(self._status_seen_path, to)
            QTimer.singleShot(
                40,
                lambda: self.stats.set_values(
                    to, animate=True, suffix=self._monster_status_suffix()
                ),
            )
            if hasattr(self, "hud"):
                self.hud._layout_overlays()

    def _monster_status_suffix(self) -> str:
        if not self.state.monsters:
            return ""
        m = self.state.monsters[0]
        return f" | 怪獸 {m.label()}({m.i},{m.j})"

    def _refresh_ui(self) -> None:
        s = self.state
        # Status overlay: funds / food / turn / land / pop / score / monster.
        # Server mode ([本機]/連線) lives in tools → settings, not here.
        # Order locked: 狀態 | 資金[odo] | 糧食 | 人口 | 回合 | 格數 | 分數.
        monster_bit = self._monster_status_suffix()
        current = snapshot_from_state(s)
        # While a pending open-roll is waiting for showEvent, park digits on the
        # previous snapshot so the roll is visible; otherwise update live.
        if self._pending_open_roll is not None:
            frm, _to = self._pending_open_roll
            self.stats.set_values(frm, animate=False, suffix=monster_bit)
        else:
            # Mid-session: short reel when visible; snap while hidden (tests).
            animate = self.isVisible()
            self.stats.set_values(current, animate=animate, suffix=monster_bit)
            save_status_seen(self._status_seen_path, current)
        self.log_view.setPlainText("\n".join(s.log[-30:]))
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.map.update()
        self._refresh_selection_label()
        self._refresh_toolbar()
        self._show_guestbook(s.list_comments())
        if hasattr(self, "hud"):
            self.hud.refresh_island_profile(s)
            self.hud._layout_overlays()

    def _refresh_toolbar(self) -> None:
        """Enable tools only when the selection can afford / accepts them."""
        for key, name, cost, digit in TOOL_SPECS:
            btn = self.tool_buttons[key]
            # 飛彈費用隨飛彈基地動態變化。
            shown_cost = self.state.missile_cost() if key == "missile" else cost
            if self.state.placement_hard_locked(key):
                label = f"🔒 {name}（鎖定）"
            elif shown_cost is None:
                label = f"{digit}. {name}"
            else:
                label = f"{digit}. {name}（{shown_cost}）"
            btn.setText(label)
            ok, reason = tool_enabled(self.state, key, self.selected)
            btn.setEnabled(ok)
            tip = f"{name}" + (
                f" · 費用 {shown_cost}" if shown_cost is not None else " · 免費"
            )
            if key == "missile" and self.state.has_missile_base():
                tip += "（飛彈／海底基地優惠）"
            if key == "onsen_village":
                tip += "\n鎖定：不可直接建設。溫泉山旁的平地才會自然出現（與村同族）"
            if reason:
                tip += f"\n不可用：{reason}"
            elif key == "wait" and self.state.has_monster():
                tip += "\n本回合不攻擊；下回合怪獸會行動"
            elif key == "defense":
                tip += "\n周圍 2 格減怪獸出現／踩踏；踩上自爆清怪"
                tip += "\n再點建設＝自爆清周圍怪獸（同額費用）"
            elif key == "missile_base":
                tip += "\n有基地時飛彈更便宜；觀光者眼中偽裝成森"
                tip += "\n解鎖前提：島上需有防衛設施"
            elif key == "undersea_base":
                tip += (
                    "\n深海色塊（不可淺灘／油田）：同飛彈基地優惠；"
                    "觀光者眼中為海"
                )
            elif key == "decoy":
                tip += "\n外觀像防衛、無實防、易毀；觀光者眼中顯示為防衛"
            elif key == "missile":
                tip += "\n可打怪獸；亦可拆毀紙糊假設施"

            elif key == "afforest":
                tip += "\n空平地→森（新林 100 本）"
            elif key == "harvest" and ok and self.selected is not None:
                hc = self.state.cell(*self.selected)
                trees = hc.trees if hc.trees > 0 else TREE_MIN
                tip += f"\n森→平地；{trees}本瞬售 +{timber_funds(trees)} 資金"
            elif key == "harbor":
                tip += "\n臨海平地→港灣色塊（可解鎖貿易輸出）"
            elif key == "shipyard":
                tip += "\n臨海平地→造船所色塊（可解鎖貿易輸出）"
                tip += "\n解鎖前提：島上需有港灣"
            elif key == "export":
                tip += (
                    f"\n糧食→資金：{FOOD_EXPORT_LOT} 噸≈"
                    f"{FUNDS_PER_FOOD_LOT} 資金（不推進回合）"
                )
                if ok:
                    tip += f"\n本批可得 +{food_export_funds(1)}；現有糧食 {self.state.food}"
            elif key == "monument":
                tip += "\n國威色塊：加島分數／安穩；抗怪獸踩踏；鄰格抑火災"
            elif key == "bank":
                tip += (
                    f"\n超流動上限 {FUNDS_SOFT_CAP} 時溢出進銀行緩衝；"
                    "無銀行則捨棄"
                )
            elif key == "supermarket":
                tip += (
                    f"\n可買糧：{FOOD_BUY_LOT} 噸≈{FUNDS_PER_FOOD_BUY} 資金"
                    "（略貴於貿易輸出）"
                )
            elif key == "shrine":
                tip += "\n信仰色塊：大幅加島分數；餵飽時安穩人口加成"
            elif key == "park":
                tip += "\n都市計畫色塊：加島分數／安穩；鄰格提高生村機率"
            elif key == "airport":
                tip += (
                    "\n交通色塊：加島分數；每回合觀光收入；"
                    "訪客留言小費；誘致 inbound 加成"
                )
            elif key == "rocket_base":
                tip += "\n宇宙色塊：加島分數；解鎖觀測衛星發射"
            elif key == "rocket_launch":
                launch_cost = self.state.rocket_launch_cost()
                tip += (
                    f"\n需ロケット基地：−{launch_cost}；"
                    "發射觀測衛星減震／海嘯／噴火（不推進回合）"
                )
                if self.state.has_university() and launch_cost < COST_ROCKET_LAUNCH:
                    tip += (
                        f"\n大學研究折扣：原價 {COST_ROCKET_LAUNCH}→{launch_cost}"
                    )
                if self.state.has_satellite():
                    tip += "\n衛星已在軌"
            elif key == "hotel":
                tip += (
                    "\n住宿觀光色塊：加島分數；每回合住宿觀光收入；"
                    "訪客留言小費（無空港時亦可）"
                )
            elif key == "casino":
                tip += (
                    "\n娛樂觀光色塊：加島分數；每回合娛樂觀光收入"
                    "（依人口加碼）"
                )
            elif key == "university":
                tip += (
                    "\n教育色塊：加島分數；有大學時觀測衛星發射較便宜"
                    "（研究／下一科技折扣）"
                )
            elif key == "research_lab":
                tip += (
                    "\n研究色塊：加島分數；輕量減震／海嘯／噴火"
                    "（可與觀測衛星疊乘）"
                )
            elif key == "attract":
                tip += (
                    f"\n定本誘致：−{COST_ATTRACT}；下回合餵飽時額外人口"
                    "（不推進回合）"
                )
                if self.state.has_airport():
                    tip += "\n有空港：誘致人口再加碼"
                if self.state.attract_pending:
                    tip += "\n已安排：請先推進回合"
            elif key == "deposit":
                tip += f"\n流動→銀行：一批 {BANK_TRANSFER_LOT}"
                if ok:
                    tip += f"\n現流動 {self.state.funds}／存 {self.state.bank_deposit}"
            elif key == "withdraw":
                tip += f"\n銀行→流動：一批 {BANK_TRANSFER_LOT}"
                if ok:
                    tip += f"\n現流動 {self.state.funds}／存 {self.state.bank_deposit}"
            elif key == "buy_food":
                tip += (
                    f"\n資金→糧食：{FOOD_BUY_LOT} 噸≈"
                    f"{FUNDS_PER_FOOD_BUY} 資金（不推進回合）"
                )
                if ok:
                    tip += (
                        f"\n本批 −{food_buy_cost(1)}；"
                        f"現資金 {self.state.funds}／糧食 {self.state.food}"
                    )
            elif key == "raise":
                tip += "\n空荒地／平地→山（可再建採掘場；噴火亦會生山）"
            elif key == "quarry":
                tip += "\n僅山上可建；勞動產資（農場優先後填採掘）"
            elif key == "excavate":
                tip += "\n陸→淺灘／淺灘→海／海→探油（機率發現海底油田）"
            elif key == "breakwater":
                tip += "\n臨海平地→防波堤色塊；鄰格減海嘯"
            elif self.selected is not None:
                tip += f"\n選格 {self.selected[0]},{self.selected[1]}"
            tip += f"\n快捷鍵 {digit}"
            btn.setToolTip(tip)
        self._refresh_build_tree_locks()
        self._refresh_build_detail()

    def _refresh_selection_label(self) -> None:
        if self.selected is None:
            if self.state.has_monster():
                m = self.state.monsters[0]
                self.sel_label.setText(
                    f"未選取格子\n島上有{m.label()}色塊於 ({m.i},{m.j})"
                )
            else:
                self.sel_label.setText("未選取格子")
            return
        i, j = self.selected
        c = self.state.cell(i, j)
        t = TERRAIN[c.terrain]["label"]
        b = BUILDINGS[c.building]["label"] if c.building else "（無）"
        m = self.state.monster_at(i, j)
        mline = f"\n怪獸：{m.label()}（色塊）" if m is not None else ""
        hints = []
        if m is not None:
            hints.append("可發射飛彈")
        if self.state.can_landfill(i, j):
            step = "海→淺灘" if c.terrain == "sea" else "淺灘→荒地"
            hints.append(f"可填海（{step}）")
        if self.state.can_level(i, j):
            hints.append("可整地")
        if self.state.can_raise_mountain(i, j):
            hints.append("可造山")
        if self.state.can_excavate(i, j):
            if c.terrain == "sea":
                hints.append("可掘削探油")
            else:
                hints.append("可掘削")
        if self.state.can_afforest(i, j):
            hints.append("可植林")
        if self.state.can_harvest(i, j):
            trees = c.trees if c.trees > 0 else TREE_MIN
            hints.append(f"可伐採（{trees}本→+{timber_funds(trees)}）")
        if self.state.can_place_building(i, j, "quarry"):
            hints.append("可建採掘場")
        if self.state.can_place_building(i, j, "harbor"):
            hints.append("可建港灣")
        if self.state.can_place_building(i, j, "shipyard"):
            hints.append("可建造船所")
        if self.state.can_place_building(i, j, "breakwater"):
            hints.append("可建防波堤")
        if self.state.can_place_building(i, j, "monument"):
            hints.append("可建紀念碑")
        if self.state.can_place_building(i, j, "bank"):
            hints.append("可建銀行")
        if self.state.can_place_building(i, j, "supermarket"):
            hints.append("可建超市")
        if self.state.can_place_building(i, j, "shrine"):
            hints.append("可建神社")
        if self.state.can_place_building(i, j, "park"):
            hints.append("可建公園")
        if self.state.can_place_building(i, j, "airport"):
            hints.append("可建空港")
        if self.state.can_place_building(i, j, "rocket_base"):
            hints.append("可建ロケット基地")
        if self.state.can_place_building(i, j, "hotel"):
            hints.append("可建酒店")
        if self.state.can_place_building(i, j, "casino"):
            hints.append("可建賭場")
        if self.state.can_place_building(i, j, "university"):
            hints.append("可建大學")
        if self.state.can_place_building(i, j, "research_lab"):
            hints.append("可建研究所")
        if self.state.can_place_building(i, j, "decoy"):
            hints.append("可建紙糊假設施")
        if c.building == "defense":
            hints.append("再建設防衛＝自爆")
        tree_line = ""
        if c.terrain == "forest":
            trees = c.trees if c.trees > 0 else TREE_MIN
            tree_line = f"\n林木：{trees} 本"
        extra = ("\n" + " · ".join(hints)) if hints else ""
        self.sel_label.setText(
            f"格子 ({i},{j})\n地形：{t}{tree_line}\n建築：{b}{mline}{extra}"
        )

    def _on_cell_clicked(self, i: int, j: int) -> None:
        self.selected = (i, j)
        self._refresh_selection_label()
        self._refresh_toolbar()

    def _require_selection(self):
        if self.selected is None:
            QMessageBox.information(self, "箱庭島", "請先在地圖上點選一格。")
            return None
        return self.selected

    def _drop_to_local_on_error(self, err: Exception) -> None:
        self._set_offline(f"連線中斷，改用本機：{err}")
        QMessageBox.warning(
            self,
            "箱庭島",
            f"伺服器操作失敗，已切回本機模式。\n\n{err}",
        )

    def _do_action(self, kind: str) -> None:
        # 觀望／貿易／銀行存提／超市買糧／誘致／火箭發射不需選格；其餘指令要點選格子。
        if self.state.placement_hard_locked(kind):
            label = BUILDINGS[kind]["label"]
            QMessageBox.information(
                self,
                "箱庭島",
                f"{label}不可直接建設（溫泉山旁的平地才會自然出現）",
            )
            return

        if kind in (
            "wait",
            "export",
            "deposit",
            "withdraw",
            "buy_food",
            "attract",
            "rocket_launch",
        ):
            i = j = 0
        else:
            sel = self._require_selection()
            if sel is None:
                return
            i, j = sel

        if self._online and self.remote is not None:
            try:
                if kind in PLACEABLE_BUILDINGS:
                    out = self.remote.place(i, j, kind)
                elif kind == "remove":
                    out = self.remote.remove(i, j)
                elif kind == "landfill":
                    out = self.remote.landfill(i, j)
                elif kind == "level":
                    out = self.remote.level(i, j)
                elif kind == "raise":
                    out = self.remote.raise_mountain(i, j)
                elif kind == "excavate":
                    out = self.remote.excavate(i, j)
                elif kind == "afforest":
                    out = self.remote.afforest(i, j)
                elif kind == "harvest":
                    out = self.remote.harvest(i, j)
                elif kind == "missile":
                    out = self.remote.missile(i, j)
                elif kind == "wait":
                    out = self.remote.wait_monster()
                elif kind == "export":
                    out = self.remote.export_food(1)
                elif kind == "deposit":
                    out = self.remote.deposit_funds(BANK_TRANSFER_LOT)
                elif kind == "withdraw":
                    out = self.remote.withdraw_funds(BANK_TRANSFER_LOT)
                elif kind == "buy_food":
                    out = self.remote.buy_food(1)
                elif kind == "attract":
                    out = self.remote.attract_population()
                elif kind == "rocket_launch":
                    out = self.remote.launch_rocket()
                else:
                    QMessageBox.information(self, "箱庭島", "未知指令")
                    return
                self._apply_island(out.island)
                self._cache_local()
                if not out.ok:
                    QMessageBox.information(self, "箱庭島", out.error or "操作失敗")
                self._refresh_ui()
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
                # Fall through to local action below.

        if kind in PLACEABLE_BUILDINGS or self.state.achievement_unlocks(kind):
            msg = self.state.place_building(i, j, kind)
        elif kind == "remove":
            msg = self.state.remove_building(i, j)
        elif kind == "landfill":
            msg = self.state.landfill(i, j)
        elif kind == "level":
            msg = self.state.level_land(i, j)
        elif kind == "raise":
            msg = self.state.raise_mountain(i, j)
        elif kind == "excavate":
            msg = self.state.excavate(i, j)
        elif kind == "afforest":
            msg = self.state.afforest(i, j)
        elif kind == "harvest":
            msg = self.state.harvest(i, j)
        elif kind == "missile":
            msg = self.state.fire_missile(i, j)
        elif kind == "wait":
            msg = self.state.wait_monster()
        elif kind == "export":
            msg = self.state.export_food(1)
        elif kind == "deposit":
            msg = self.state.deposit_funds(BANK_TRANSFER_LOT)
        elif kind == "withdraw":
            msg = self.state.withdraw_funds(BANK_TRANSFER_LOT)
        elif kind == "buy_food":
            msg = self.state.buy_food(1)
        elif kind == "attract":
            msg = self.state.attract_population()
        elif kind == "rocket_launch":
            msg = self.state.launch_rocket()
        else:
            msg = "未知指令"
        if msg != "ok":
            QMessageBox.information(self, "箱庭島", msg)
        self._refresh_ui()

    def _next_turn(self) -> None:
        if self._online and self.remote is not None:
            try:
                out = self.remote.next_turn()
                self._apply_island(out.island)
                self._cache_local()
                self._refresh_ui()
                QMessageBox.information(
                    self, "回合結果", "\n".join(out.notes or ["（無）"])
                )
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)

        notes = self.state.next_turn()
        self._refresh_ui()
        QMessageBox.information(self, "回合結果", "\n".join(notes))

    def _save(self) -> None:
        path = save_island(self.state, self._save_path)
        if self._online and self.remote is not None:
            try:
                self._apply_island(self.remote.put_island(self.state))
                self.state._log(f"已同步至伺服器並本機：{path}")
                self._refresh_ui()
                QMessageBox.information(
                    self, "箱庭島", f"已同步伺服器，並存本機\n{path}"
                )
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
        self.state._log(f"已存檔：{path}")
        self._refresh_ui()
        QMessageBox.information(self, "箱庭島", f"已存檔到\n{path}")

    def _new_island(self) -> None:
        reply = QMessageBox.question(
            self,
            "新島",
            "重置為新的中央 7 格島？（未存檔進度會丟失）",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._online and self.remote is not None:
            try:
                self._apply_island(self.remote.reset())
                self._cache_local()
                self.selected = None
                self._refresh_ui()
                return
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
        self.state = IslandState.new_game()
        self.map.set_state(self.state)
        self.selected = None
        self._refresh_ui()

    def _tourism_catalog(self) -> List[Dict[str, Any]]:
        """Online: server list. Offline: home snapshot + seeded demos."""
        if self._online and self.remote is not None:
            try:
                return self.remote.list_islands()
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
        rows = [island_summary(self.state)]
        for demo in local_demo_islands():
            if demo.island_id == self.state.island_id:
                continue
            rows.append(island_summary(demo))
        return rows

    def _load_tourism_island(self, island_id: str) -> Optional[IslandState]:
        if self._online and self.remote is not None:
            try:
                return self.remote.get_island_by_id(island_id)
            except HakoniwaRemoteError as e:
                self._drop_to_local_on_error(e)
        if island_id == self.state.island_id or island_id == "home":
            # Snapshot of the player's current island (read-only view).
            return IslandState.from_dict(self.state.to_dict())
        for demo in local_demo_islands():
            if demo.island_id == island_id:
                return demo
        return None

    def _open_tourism(self) -> None:
        catalog = self._tourism_catalog()
        if not catalog:
            QMessageBox.information(self, "觀光", "目前沒有可觀光的島。")
            return
        picker = TourismListDialog(catalog, parent=self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        island_id = picker.selected_id
        if not island_id:
            return
        island = self._load_tourism_island(island_id)
        if island is None:
            QMessageBox.warning(self, "觀光", f"找不到島：{island_id}")
            return
        visitor = TourismIslandDialog(
            island,
            remote=self.remote if self._online else None,
            parent=self,
        )
        visitor.exec()
        # If we visited home online, refresh guestbook in case we posted there.
        if island_id in (self.state.island_id, "home"):
            self._reload_guestbook()
            self._refresh_ui()


class TourismListDialog(QDialog):
    """Pick an island from the 諸島 list (server or local demos)."""

    def __init__(self, islands: List[Dict[str, Any]], parent=None):
        dp = _dp()
        super().__init__(parent)
        self.selected_id: Optional[str] = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._drag_grips = []
        self.setWindowTitle("觀光 — 諸島列表")
        self.setMinimumSize(420, 360)
        self.resize(480, 420)
        self.setStyleSheet(dp.CALC_DIALOG_STYLE + getattr(dp, "MINI_PROGRAM_STYLE", ""))

        root = dp.install_ornate_calc_frame(self)
        root.setSpacing(6)
        root.addWidget(dp.make_draggable_title(self, "觀光 — 諸島列表"))

        hint = QLabel("選擇一座島以唯讀瀏覽地圖；留言板仍可使用。")
        hint.setObjectName("calcResult")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.list = QListWidget()
        for row in islands:
            iid = str(row.get("id") or "")
            name = str(row.get("name") or iid or "（未命名）")
            pop = row.get("population", "?")
            land = row.get("land", "?")
            turn = row.get("turn", "?")
            label = f"{name}  ·  人口 {pop}  ·  陸地 {land}  ·  回合 {turn}"
            if iid == "home":
                label += "  （本島）"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, iid)
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(self._accept_item)
        root.addWidget(self.list, stretch=1)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        go = QPushButton("觀光")
        go.setObjectName("calcAction")
        go.clicked.connect(self._accept_current)
        row.addWidget(go)
        root.addLayout(row)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if self.selected_id:
            self.accept()

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, "觀光", "請先選一座島。")
            return
        self._accept_item(item)


class TourismIslandDialog(QDialog):
    """Read-only 箱庭斜視 map of another (or home) island; guestbook still works."""

    def __init__(
        self,
        island: IslandState,
        remote: Optional[HakoniwaRemote] = None,
        parent=None,
    ):
        dp = _dp()
        super().__init__(parent)
        self.state = island
        self.remote = remote
        self.selected = None
        self._island_id = island.island_id or "home"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._drag_grips = []

        title = f"觀光 — {island.name}"
        self.setWindowTitle(title)
        self.setMinimumSize(720, 640)
        self.resize(880, 720)
        self.setStyleSheet(dp.CALC_DIALOG_STYLE + getattr(dp, "MINI_PROGRAM_STYLE", ""))

        root = dp.install_ornate_calc_frame(self)
        root.setSpacing(4)
        root.addWidget(dp.make_draggable_title(self, title))

        hint = QLabel(
            "箱庭斜視 · 觀光模式（唯讀地圖）· 色塊佔位　"
            "滾輪縮放 · 中／右鍵平移　"
            "可瀏覽格子與留言；建設／地形／回合已鎖定　"
            "飛彈基地偽裝成森、紙糊假設施顯示為防衛"
        )
        hint.setObjectName("calcResult")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.map = HakoniwaMapWidget(self.state, tourist_mode=True)
        self.map.cell_clicked.connect(self._on_cell_clicked)
        self.hud = HakoniwaMapHud(self.map)
        self.stats = self.hud.stats
        self.sel_label = self.hud.sel_label
        self.guestbook_view = self.hud.guestbook_view
        # Tourism: hide 建築 icon／drawer; guestbook opens via 留言 icon.
        self.hud.set_tourism_chrome()
        self.hud.refresh_island_profile(island)
        mode = "連線" if remote is not None else "本機示範"
        self.stats.setText(
            f"[{mode}觀光] {island.name}（{self._island_id}） | "
            f"資金 {island.funds} | 糧食 {island.food} | 人口 {island.population} | "
            f"回合 {island.turn} | 格數 {island.land_count()} | "
            f"分數 {island.island_score()}"
        )
        self.hud.log_view.setPlainText("觀光模式：建設與地形指令已鎖定。")
        root.addWidget(self.hud, stretch=1)

        gb_form = self.hud.guestbook_form
        name_cap = QLabel("名字")
        name_cap.setObjectName("hakoniwaHudCaption")
        gb_form.addWidget(name_cap)
        self.guest_name = QLineEdit()
        self.guest_name.setObjectName("hakoniwaHudInput")
        self.guest_name.setPlaceholderText("訪客名")
        self.guest_name.setMaxLength(MAX_GUEST_NAME)
        self.guest_name.setFixedWidth(90)
        gb_form.addWidget(self.guest_name)
        self.guest_text = QLineEdit()
        self.guest_text.setObjectName("hakoniwaHudInput")
        self.guest_text.setPlaceholderText("寫點什麼…")
        self.guest_text.setMaxLength(MAX_GUEST_TEXT)
        gb_form.addWidget(self.guest_text, stretch=1)
        post_btn = QPushButton("留言")
        post_btn.setObjectName("calcAction")
        post_btn.clicked.connect(self._post_guestbook)
        gb_form.addWidget(post_btn)
        refresh_gb = QPushButton("整理")
        refresh_gb.setObjectName("calcAction")
        refresh_gb.clicked.connect(self._reload_guestbook)
        gb_form.addWidget(refresh_gb)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("返回")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self._show_guestbook(self.state.list_comments())
        self.hud._layout_overlays()

    def _format_guestbook(self, comments: List[GuestbookEntry]) -> str:
        if not comments:
            return "（尚無留言）"
        lines = []
        for c in comments:
            stamp = c.at.replace("T", " ").rstrip("Z")
            lines.append(f"[{stamp}] {c.name}：{c.text}")
        return "\n".join(lines)

    def _show_guestbook(self, comments: List[GuestbookEntry]) -> None:
        self.guestbook_view.setPlainText(self._format_guestbook(comments))
        bar = self.guestbook_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _reload_guestbook(self) -> None:
        if self.remote is not None:
            try:
                comments = self.remote.list_island_comments(self._island_id)
                self.state.comments = list(comments)
                self._show_guestbook(comments)
                return
            except HakoniwaRemoteError as e:
                QMessageBox.warning(self, "觀光", f"無法重新整理留言：{e}")
        self._show_guestbook(self.state.list_comments())

    def _post_guestbook(self) -> None:
        name = self.guest_name.text()
        text = self.guest_text.text()
        if self.remote is not None:
            try:
                ok, err, comments = self.remote.post_island_comment(
                    self._island_id, name, text
                )
                self.state.comments = list(comments)
                self._show_guestbook(comments)
                if not ok:
                    QMessageBox.information(self, "觀光", err or "留言失敗")
                    return
                self.guest_text.clear()
                return
            except HakoniwaRemoteError as e:
                QMessageBox.warning(self, "觀光", f"留言失敗：{e}")
                return
        msg = self.state.add_comment(name, text)
        if msg != "ok":
            QMessageBox.information(self, "觀光", msg)
            return
        self.guest_text.clear()
        self._show_guestbook(self.state.list_comments())

    def _on_cell_clicked(self, i: int, j: int) -> None:
        self.selected = (i, j)
        terrain_key, building_key = self.state.tourist_appearance(i, j)
        t = TERRAIN[terrain_key]["label"]
        b = BUILDINGS[building_key]["label"] if building_key else "（無）"
        self.sel_label.setText(f"格子 ({i},{j})\n地形：{t}\n建築：{b}\n（觀光唯讀）")
        self.map.select(i, j)
