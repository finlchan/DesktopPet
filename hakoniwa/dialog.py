"""箱庭島 window — FramelessCalcDialog chrome + map + turn / terrain / guestbook / 觀光.

Local-play UX: named toolbar with costs + disable rules, status bar,
pan/zoom map (via HakoniwaMapWidget), optional keyboard shortcuts.

Numeric / function chrome lives as **overlays inside the map viewport**
(status, tile info, action log, icon bar → drawers, guestbook) — not as
outside columns or strips. Guestbook is closed by default (留言 icon).
Action log + guestbook frames are ~70% transparent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
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

from .demos import island_summary, local_demo_islands
from .model import (
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
/* Tools／settings drawers: same deep-teal glass + cyan as icon bar. */
QFrame#hakoniwaToolsDrawer,
QFrame#hakoniwaSettingsDrawer {{
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
QLineEdit#hakoniwaHudInput {{
    background-color: rgba(14, 28, 32, 180);
    color: {_HUD_TEXT};
    border: 1px solid {_DRAWER_BORDER};
    border-radius: 3px;
    padding: 2px 4px;
}}
/* Building tree — text only; orange select like icon-bar active. */
QTreeWidget#hakoniwaBuildTree {{
    background: transparent;
    color: {_HUD_TEXT};
    border: none;
    outline: none;
    font-size: 10pt;
    show-decoration-selected: 1;
}}
QTreeWidget#hakoniwaBuildTree::item {{
    padding: 3px 6px;
    border-radius: 2px;
}}
QTreeWidget#hakoniwaBuildTree::item:selected {{
    background-color: {_ACCENT_BG};
    color: #fff8f0;
}}
QTreeWidget#hakoniwaBuildTree::item:hover:!selected {{
    background-color: rgba(28, 52, 56, 180);
}}
QTreeWidget#hakoniwaBuildTree::item:disabled {{
    color: rgba(140, 170, 168, 140);
}}
QTreeWidget#hakoniwaBuildTree::branch {{
    background: transparent;
    border-image: none;
}}
QTreeWidget#hakoniwaBuildTree::branch:has-children:!has-siblings:closed,
QTreeWidget#hakoniwaBuildTree::branch:closed:has-children:has-siblings {{
    border-image: none;
    image: none;
}}
QTreeWidget#hakoniwaBuildTree::branch:open:has-children:!has-siblings,
QTreeWidget#hakoniwaBuildTree::branch:open:has-children:has-siblings {{
    border-image: none;
    image: none;
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


class HakoniwaMapHud(QWidget):
    """Hosts the map and positions HUD overlays inside the map viewport.

    Layout (user-locked annotation):
      - status bar → top center

      - alert marquee → under status (警報走馬燈; via 通知; hidden without alerts)
      - tile info → top-left (below status／marquee; 資訊 or 通知 chrome)
      - icon bar → bottom-left (通知／建築／資訊／留言／設定)
      - guestbook → bottom center (~70% transparent; **closed by default**)
      - action log → bottom-right (~70% transparent; 通知 chrome)
      - tools / settings drawers → above icon bar when open

    「通知」toggles status chrome in sync: 格資訊 + 行動日誌 + 警報走馬燈.

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

        # Content browse/build: left text tree + right detail (no thumbnails).
        browse_row = QHBoxLayout()
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.setSpacing(6)

        self.build_tree = QTreeWidget()
        self.build_tree.setObjectName("hakoniwaBuildTree")
        self.build_tree.setHeaderHidden(True)
        self.build_tree.setRootIsDecorated(True)
        self.build_tree.setAnimated(True)
        self.build_tree.setIndentation(14)
        self.build_tree.setUniformRowHeights(True)
        self.build_tree.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        browse_row.addWidget(self.build_tree, stretch=2)

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

        # Session utilities under the browse pane (下回合／存檔…).
        drawer_scroll = QScrollArea()
        drawer_scroll.setWidgetResizable(True)
        drawer_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        drawer_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        drawer_scroll.setMaximumHeight(48)
        self.tools_body = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_body)
        self.tools_layout.setContentsMargins(2, 2, 2, 2)
        self.tools_layout.setSpacing(2)
        drawer_scroll.setWidget(self.tools_body)
        drawer_outer.addWidget(drawer_scroll, stretch=0)

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


        # Status chrome (格資訊 + 日誌 + 走馬燈) starts on — panels as today.
        self._status_chrome_on = True

        # Wire icons after drawers exist (setChecked emits and may layout).
        self.icon_bar.iconToggled.connect(self._on_icon_toggled)
        # 通知 = chrome master (checked). 資訊 = tile panel (checked). Drawers closed.
        notify_btn = self.icon_bar.button("notify")
        if notify_btn is not None:
            notify_btn.setToolTip("通知：格資訊／日誌／警報走馬燈")
            notify_btn.setChecked(True)

        info_btn = self.icon_bar.button("info")
        if info_btn is not None:
            info_btn.setChecked(True)

        self.setMinimumSize(480, 480)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )


    def _apply_status_chrome(self) -> None:
        """Show/hide 格資訊 + 日誌 + 走馬燈 together from ``_status_chrome_on``."""
        on = self._status_chrome_on
        self.log_view.setVisible(on)
        # Tile info follows chrome; 資訊 icon stays in sync when chrome flips.
        info_btn = self.icon_bar.button("info")
        if on:
            if info_btn is not None and not info_btn.isChecked():
                info_btn.setChecked(True)
            else:
                self.sel_label.setVisible(True)
        else:
            self.sel_label.setVisible(False)
            if info_btn is not None and info_btn.isChecked():
                # Block re-entry into notify via info toggled handler.
                info_btn.blockSignals(True)
                info_btn.setChecked(False)
                info_btn.blockSignals(False)
        # Marquee only when chrome on AND alerts are queued.
        self._sync_marquee_visibility()

    def _sync_marquee_visibility(self) -> None:
        show = self._status_chrome_on and self.alert_marquee.has_alerts()
        self.alert_marquee.setVisible(show)

    def set_alerts(self, texts) -> None:
        """Replace alert marquee lines; visibility follows 通知 chrome."""
        self.alert_marquee.set_alerts(texts)
        self._sync_marquee_visibility()
        self._layout_overlays()

    def set_sample_alerts(self) -> None:
        self.alert_marquee.set_sample_alerts()
        self._sync_marquee_visibility()
        self._layout_overlays()

    def _on_icon_toggled(self, kind: str, checked: bool) -> None:
        """Wire icon checks to panels; build／guestbook／settings exclusive."""
        # 通知 is a chrome toggle, not a drawer — keep it out of exclusive set
        # so tools／guestbook／settings can stay open while chrome is on.
        exclusive = ("build", "guestbook", "settings")
        if kind in exclusive and checked:
            for other in exclusive:
                if other != kind:
                    btn = self.icon_bar.button(other)
                    if btn is not None and btn.isChecked():
                        btn.setChecked(False)

        if kind == "notify":
            self._status_chrome_on = checked
            self._apply_status_chrome()
        elif kind == "build":
            self.tools_drawer.setVisible(checked)
        elif kind == "info":
            # Fine-grained tile panel; ignored while chrome is off.
            if self._status_chrome_on:
                self.sel_label.setVisible(checked)
            elif checked:
                # Turning info on while chrome off also re-enables chrome.
                self._status_chrome_on = True
                notify_btn = self.icon_bar.button("notify")
                if notify_btn is not None and not notify_btn.isChecked():
                    notify_btn.blockSignals(True)
                    notify_btn.setChecked(True)
                    notify_btn.blockSignals(False)
                self._apply_status_chrome()
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

        """Close build / guestbook / settings drawers (chrome／info stay)."""
        for kind in ("build", "guestbook", "settings"):

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
        # settings stays compact above the icon bar.
        build_w = min(460, max(320, w // 2))
        settings_w = min(280, max(200, w // 3))
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
)


def tool_enabled(
    state: IslandState, kind: str, selected: Optional[Tuple[int, int]]
) -> Tuple[bool, str]:
    """Whether a toolbar action can run on the current selection.

    Returns (enabled, reason). Reason is empty when enabled; otherwise a short
    tip for the button tooltip (can't afford / wrong terrain / no selection).
    """
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

    if kind in PLACEABLE_BUILDINGS:
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
            if c.terrain != "mountain":
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
            if cost is None:
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
        self.hud.build_tree.itemSelectionChanged.connect(self._on_build_tree_sel)
        self.hud.build_tree.itemDoubleClicked.connect(self._on_build_tree_activate)
        self.hud.build_place_btn.clicked.connect(self._on_build_place_clicked)

        tools_lay = self.hud.tools_layout
        # Compact horizontal chip row (teal glass) — avoids calcAction gray stack.
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)

        self.turn_btn = QPushButton("T. 下回合")
        self.turn_btn.setObjectName("hakoniwaDrawerAction")
        self.turn_btn.setToolTip("結算本回合產糧／產資（快捷鍵 T）")
        self.turn_btn.clicked.connect(self._next_turn)
        footer.addWidget(self.turn_btn)

        tour_btn = QPushButton("觀光")
        tour_btn.setObjectName("hakoniwaDrawerAction")
        tour_btn.setToolTip("瀏覽諸島地圖（唯讀）；留言板仍可用")
        tour_btn.clicked.connect(self._open_tourism)
        footer.addWidget(tour_btn)

        save_btn = QPushButton("S. 存檔")
        save_btn.setObjectName("hakoniwaDrawerAction")
        save_btn.setToolTip("寫入本機 JSON（快捷鍵 S）")
        save_btn.clicked.connect(self._save)
        footer.addWidget(save_btn)

        new_btn = QPushButton("新島")
        new_btn.setObjectName("hakoniwaDrawerAction")
        new_btn.setToolTip("新島（重置）")
        new_btn.clicked.connect(self._new_island)
        footer.addWidget(new_btn)

        reset_view_btn = QPushButton("0. 視圖")
        reset_view_btn.setObjectName("hakoniwaDrawerAction")
        reset_view_btn.setToolTip("縮放／平移回到預設（快捷鍵 0）")
        reset_view_btn.clicked.connect(self.map.reset_view)
        footer.addWidget(reset_view_btn)
        footer.addStretch(1)
        tools_lay.addLayout(footer)
        tools_lay.addStretch(1)

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
        """Fill the formal catalog category tree (text rows, no thumbnails)."""
        tree = self.hud.build_tree
        tree.clear()
        self._tree_items: Dict[str, QTreeWidgetItem] = {}
        for cat_name, keys in build_tree_categories():
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            cat_item.setData(0, Qt.ItemDataRole.UserRole, None)
            for key in keys:
                # Settlements (if buildings) + all TOOL_SPECS keys in categories.
                if key in settlement_keys_for_tree():
                    label = display_label(key)
                    digit = ""
                    name = label
                elif key in self._tool_spec_by_key:
                    name, _cost, digit = self._tool_spec_by_key[key]
                    label = display_label(key, name)
                else:
                    continue
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.ItemDataRole.UserRole, key)
                child.setToolTip(0, f"{label}" + (f" · 快捷鍵 {digit}" if digit else ""))
                cat_item.addChild(child)
                self._tree_items[key] = child
            if cat_item.childCount() > 0:
                tree.addTopLevelItem(cat_item)
                cat_item.setExpanded(True)

    def _on_build_tree_sel(self) -> None:
        items = self.hud.build_tree.selectedItems()
        key = None
        if items:
            key = items[0].data(0, Qt.ItemDataRole.UserRole)
        self.hud._build_tree_key = key if isinstance(key, str) else None
        self._refresh_build_detail()

    def _on_build_tree_activate(self, item: QTreeWidgetItem, _column: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(key, str):
            return
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
        """Hard-lock tree rows whose island unlock prerequisites are unmet."""
        lock = " 🔒"
        for key, item in getattr(self, "_tree_items", {}).items():
            met, reason = unlock_met(self.state, key)
            base = display_label(
                key,
                self._tool_spec_by_key[key][0]
                if key in self._tool_spec_by_key
                else None,
            )
            # Keep Enabled so rows stay browsable for detail; Place / double-click
            # stay hard-blocked via unlock_met (prefs 前置不滿足不可點).
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            if met:
                item.setText(0, base)
                item.setForeground(0, QBrush())
                item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
                item.setToolTip(0, base)
            else:
                item.setText(0, base + lock)
                item.setForeground(0, QBrush(QColor(140, 170, 168, 160)))
                item.setData(0, Qt.ItemDataRole.UserRole + 1, True)
                tip = f"{base}\n鎖定：{reason}" if reason else f"{base}\n鎖定"
                item.setToolTip(0, tip)

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
        elif shown_cost == 0 and key in settlement_keys_for_tree():
            cost_lab.setText("費用: 0（非點選建造）")
        else:
            cost_lab.setText(f"資金: {shown_cost}")

        met, lock_reason = unlock_met(self.state, key)
        prereq = unlock_prereq(key)
        if key in settlement_keys_for_tree():
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
        if key in PLACEABLE_BUILDINGS:
            place_btn.setText("放置")
        elif key in settlement_keys_for_tree():
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
            self.hud._layout_overlays()

    def _refresh_toolbar(self) -> None:
        """Enable tools only when the selection can afford / accepts them."""
        for key, name, cost, digit in TOOL_SPECS:
            btn = self.tool_buttons[key]
            # 飛彈費用隨飛彈基地動態變化。
            shown_cost = self.state.missile_cost() if key == "missile" else cost
            if shown_cost is None:
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

        if kind in PLACEABLE_BUILDINGS:
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
