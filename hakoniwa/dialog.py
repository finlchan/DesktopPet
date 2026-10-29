"""箱庭島 window — FramelessCalcDialog chrome + map + turn / terrain / guestbook / 觀光.

Local-play UX: named toolbar with costs + disable rules, status bar,
pan/zoom map (via HakoniwaMapWidget), optional keyboard shortcuts.

Numeric / function chrome lives as **overlays inside the map viewport**
(status, tile info, action log, tools drawer, guestbook) — not as outside
columns or strips. Action log + guestbook frames are ~70% transparent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QResizeEvent
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
    QVBoxLayout,
    QWidget,
)

from .demos import island_summary, local_demo_islands
from .model import (
    BUILDABLE,
    BUILDINGS,
    COST_AFFOREST,
    COST_DEFENSE,
    COST_FACTORY,
    COST_FARM,
    COST_LANDFILL,
    COST_LEVEL,
    COST_MISSILE,
    COST_MISSILE_BASE,
    GuestbookEntry,
    MAX_GUEST_NAME,
    MAX_GUEST_TEXT,
    PLACEABLE_BUILDINGS,
    TERRAIN,
    IslandState,
)
from .remote import HakoniwaRemote, HakoniwaRemoteError, try_connect
from .save import default_save_path, load_island, save_island
from .view import HakoniwaMapWidget

# Overlay frames (action log / guestbook): 70% transparent ≈ 30% opaque.
_OVERLAY_BG = "rgba(12, 28, 18, 77)"
_OVERLAY_BORDER = "rgba(150, 200, 150, 130)"

# In-map HUD styles (status / tile / log / guestbook / tools).
HAKONIWA_HUD_STYLE = f"""
QLabel#hakoniwaHudStatus {{
    background-color: rgba(18, 42, 26, 210);
    color: #e4f5e4;
    border: 1px solid rgba(90, 150, 90, 200);
    border-radius: 3px;
    padding: 3px 10px;
    /* Single-line status strip — do not wrap stats. */
}}
QLabel#hakoniwaHudTile {{
    background-color: rgba(16, 40, 28, 170);
    color: #d0ecd0;
    border: 1px solid rgba(70, 170, 100, 170);
    border-radius: 3px;
    padding: 4px 8px;
}}
QPlainTextEdit#hakoniwaHudLog,
QPlainTextEdit#hakoniwaHudGuestbook {{
    background-color: {_OVERLAY_BG};
    color: #e8f5e8;
    border: 1px solid {_OVERLAY_BORDER};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: #3d5a80;
}}
QFrame#hakoniwaHudGuestbookFrame {{
    background-color: {_OVERLAY_BG};
    border: 1px solid {_OVERLAY_BORDER};
    border-radius: 4px;
}}
QFrame#hakoniwaToolsDrawer {{
    background-color: rgba(24, 36, 28, 230);
    border: 1px solid rgba(180, 120, 50, 200);
    border-radius: 4px;
}}
QPushButton#hakoniwaToolsBtn {{
    background-color: rgba(176, 96, 36, 230);
    color: #fff8f0;
    border: 1px solid rgba(220, 140, 60, 230);
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
}}
QPushButton#hakoniwaToolsBtn:hover {{
    background-color: rgba(200, 120, 48, 240);
}}
QPushButton#hakoniwaToolsBtn:checked {{
    background-color: rgba(140, 72, 24, 240);
}}
QLabel#hakoniwaHudCaption {{
    color: #c8e0c8;
    background: transparent;
    border: none;
    padding: 0;
}}
QLineEdit#hakoniwaHudInput {{
    background-color: rgba(30, 40, 30, 180);
    color: #f0f0f0;
    border: 1px solid rgba(120, 160, 120, 160);
    border-radius: 3px;
    padding: 2px 4px;
}}
"""


class HakoniwaMapHud(QWidget):
    """Hosts the map and positions HUD overlays inside the map viewport.

    Layout (user-locked annotation):
      - status bar → top center
      - tile info → top-left (below status)
      - tools button → bottom-left (opens tools/settings drawer)
      - guestbook → bottom center (~70% transparent)
      - action log → bottom-right (~70% transparent)
    """

    def __init__(self, map_widget: HakoniwaMapWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet(HAKONIWA_HUD_STYLE)
        self.map = map_widget
        self.map.setParent(self)
        self.map.lower()

        self.stats = QLabel(self)
        self.stats.setObjectName("hakoniwaHudStatus")
        # User-locked: status HUD is one horizontal line (no wrap).
        self.stats.setWordWrap(False)
        self.stats.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.stats.setTextFormat(Qt.TextFormat.PlainText)

        self.sel_label = QLabel("未選取格子", self)
        self.sel_label.setObjectName("hakoniwaHudTile")
        self.sel_label.setWordWrap(True)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setObjectName("hakoniwaHudLog")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("行動日誌")

        self.tools_btn = QPushButton("工具／設定", self)
        self.tools_btn.setObjectName("hakoniwaToolsBtn")
        self.tools_btn.setCheckable(True)
        self.tools_btn.setToolTip("開啟建設工具與伺服器設定")
        self.tools_btn.toggled.connect(self._on_tools_toggled)

        self.tools_drawer = QFrame(self)
        self.tools_drawer.setObjectName("hakoniwaToolsDrawer")
        self.tools_drawer.setVisible(False)
        drawer_outer = QVBoxLayout(self.tools_drawer)
        drawer_outer.setContentsMargins(6, 6, 6, 6)
        drawer_outer.setSpacing(4)
        drawer_scroll = QScrollArea()
        drawer_scroll.setWidgetResizable(True)
        drawer_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        drawer_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.tools_body = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_body)
        self.tools_layout.setContentsMargins(2, 2, 2, 2)
        self.tools_layout.setSpacing(4)
        drawer_scroll.setWidget(self.tools_body)
        drawer_outer.addWidget(drawer_scroll, stretch=1)
        # Settings (server connection) pinned under the scrollable tool list.
        self.settings_body = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_body)
        self.settings_layout.setContentsMargins(2, 4, 2, 2)
        self.settings_layout.setSpacing(4)
        drawer_outer.addWidget(self.settings_body)

        # Guestbook cluster (view + form) in one translucent frame.
        self.guestbook_frame = QFrame(self)
        self.guestbook_frame.setObjectName("hakoniwaHudGuestbookFrame")
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

        self.setMinimumSize(480, 480)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    def _on_tools_toggled(self, checked: bool) -> None:
        self.tools_drawer.setVisible(checked)
        self._layout_overlays()
        if checked:
            self.tools_drawer.raise_()
            self.tools_btn.raise_()

    def toggle_tools(self) -> None:
        self.tools_btn.toggle()

    def close_tools(self) -> None:
        if self.tools_btn.isChecked():
            self.tools_btn.setChecked(False)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_overlays()

    def eventFilter(self, watched, event):  # noqa: N802
        # Keep overlays above the map if something re-raises the map.
        if watched is self.map and event.type() == QEvent.Type.Show:
            self._raise_overlays()
        return super().eventFilter(watched, event)

    def _raise_overlays(self) -> None:
        for w in (
            self.stats,
            self.sel_label,
            self.log_view,
            self.guestbook_frame,
            self.tools_drawer,
            self.tools_btn,
        ):
            if w.isVisible():
                w.raise_()

    def _layout_overlays(self) -> None:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        self.map.setGeometry(0, 0, w, h)
        self.map.lower()

        margin = 8
        # Status — top center, single horizontal line (no wrap / multi-line).
        fm = self.stats.fontMetrics()
        text = self.stats.text() or ""
        text_w = fm.horizontalAdvance(text) + 24
        status_h = max(fm.height() + 10, 26)
        status_w = min(max(text_w, 200), w - 2 * margin)
        self.stats.setGeometry((w - status_w) // 2, margin, status_w, status_h)

        # Tile info — top-left below status
        self.sel_label.adjustSize()
        tile_w = min(220, max(140, w // 4))
        tile_h = max(self.sel_label.sizeHint().height() + 8, 56)
        self.sel_label.setGeometry(
            margin, margin + status_h + 6, tile_w, tile_h
        )

        # Tools button — bottom-left (hidden in tourism / read-only)
        btn_x = margin
        if self.tools_btn.isVisible():
            self.tools_btn.adjustSize()
            btn_w = max(self.tools_btn.sizeHint().width() + 8, 100)
            btn_h = max(self.tools_btn.sizeHint().height(), 28)
            btn_y = h - margin - btn_h
            self.tools_btn.setGeometry(btn_x, btn_y, btn_w, btn_h)
        else:
            btn_w = 0
            btn_h = 0
            btn_y = h - margin

        # Tools drawer — above the button, left side
        drawer_w = min(280, max(200, w // 3))
        drawer_h = min(h - 2 * margin - btn_h - 8, max(220, int(h * 0.62)))
        if self.tools_drawer.isVisible():
            self.tools_drawer.setGeometry(
                margin,
                max(margin, btn_y - 6 - drawer_h),
                drawer_w,
                drawer_h,
            )

        # Action log — bottom-right (~70% transparent frame)
        log_w = min(260, max(160, w // 3))
        log_h = min(160, max(90, h // 4))
        self.log_view.setGeometry(
            w - margin - log_w, h - margin - log_h, log_w, log_h
        )

        # Guestbook — bottom center, between tools and log
        gb_left = btn_x + (btn_w + 8 if btn_w else 0)
        gb_right = w - margin - log_w - 8
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
    ("afforest", "植林", COST_AFFOREST, "6"),
    ("missile", "發射飛彈", COST_MISSILE, "7"),
    ("wait", "觀望怪獸", None, "8"),
    ("defense", "建設防衛設施", COST_DEFENSE, "9"),
    ("missile_base", "建設飛彈基地", COST_MISSILE_BASE, "B"),
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

    if selected is None:
        return False, "請先選格"
    i, j = selected
    c = state.cell(i, j)

    if kind == "missile":
        if state.monster_at(i, j) is None:
            return False, "此格沒有怪獸"
        cost = state.missile_cost()
        if state.funds < cost:
            return False, f"資金不足（需 {cost}）"
        return True, ""

    if kind in PLACEABLE_BUILDINGS:
        cost = int(BUILDINGS[kind]["cost"])
        if state.monster_at(i, j) is not None:
            return False, "此格有怪獸"
        if c.terrain not in BUILDABLE:
            return False, "須在平地建設"
        if c.building is not None:
            return False, "此格已有建築"
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

    if kind == "afforest":
        if not state.can_afforest(i, j):
            if state.monster_at(i, j) is not None:
                return False, "此格有怪獸"
            return False, "須空的平地"
        if state.funds < COST_AFFOREST:
            return False, f"資金不足（需 {COST_AFFOREST}）"
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

        self.setWindowTitle("箱庭島")
        self.setMinimumSize(720, 720)
        self.resize(900, 780)
        self.setStyleSheet(dp.CALC_DIALOG_STYLE + getattr(dp, "MINI_PROGRAM_STYLE", ""))

        self._save_path = self._resolve_save_path()
        loaded = load_island(self._save_path)
        self.state = loaded if loaded is not None else IslandState.new_game()
        self.selected = None

        root = dp.install_ornate_calc_frame(self)
        root.setSpacing(4)
        root.addWidget(dp.make_draggable_title(self, "箱庭島"))

        hint = QLabel(
            "箱庭斜視 · 點選格子 → 左下「工具／設定」建設／地形／飛彈 · 下回合結算　"
            "（色塊佔位）· 滾輪縮放 · 中／右鍵平移　"
            "快捷鍵：1–9／B 工具 · T 下回合 · S 存檔 · Esc 取消選取 · 0 重置視圖"
        )
        hint.setObjectName("calcResult")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Map fills the body; all numeric/function UI is in-viewport HUD.
        self.map = HakoniwaMapWidget(self.state)
        self.map.cell_clicked.connect(self._on_cell_clicked)
        self.hud = HakoniwaMapHud(self.map)
        self.stats = self.hud.stats
        self.sel_label = self.hud.sel_label
        self.log_view = self.hud.log_view
        self.guestbook_view = self.hud.guestbook_view
        root.addWidget(self.hud, stretch=1)

        # --- Tools / settings drawer (orange button) ---
        tools_lay = self.hud.tools_layout
        tools_cap = QLabel("工具")
        tools_cap.setObjectName("hakoniwaHudCaption")
        tools_lay.addWidget(tools_cap)

        self.tool_buttons: Dict[str, QPushButton] = {}
        for key, name, cost, digit in TOOL_SPECS:
            if cost is None:
                text = f"{digit}. {name}"
            else:
                text = f"{digit}. {name}（{cost}）"
            btn = QPushButton(text)
            btn.setObjectName("calcAction")
            btn.setProperty("toolKey", key)
            btn.clicked.connect(lambda checked=False, k=key: self._do_action(k))
            tools_lay.addWidget(btn)
            self.tool_buttons[key] = btn

        tools_lay.addSpacing(4)

        self.turn_btn = QPushButton("T. 下回合")
        self.turn_btn.setObjectName("calcAction")
        self.turn_btn.setToolTip("結算本回合產糧／產資（快捷鍵 T）")
        self.turn_btn.clicked.connect(self._next_turn)
        tools_lay.addWidget(self.turn_btn)

        tour_btn = QPushButton("觀光")
        tour_btn.setObjectName("calcAction")
        tour_btn.setToolTip("瀏覽諸島地圖（唯讀）；留言板仍可用")
        tour_btn.clicked.connect(self._open_tourism)
        tools_lay.addWidget(tour_btn)

        save_btn = QPushButton("S. 存檔")
        save_btn.setObjectName("calcAction")
        save_btn.setToolTip("寫入本機 JSON（快捷鍵 S）")
        save_btn.clicked.connect(self._save)
        tools_lay.addWidget(save_btn)

        new_btn = QPushButton("新島（重置）")
        new_btn.setObjectName("calcAction")
        new_btn.clicked.connect(self._new_island)
        tools_lay.addWidget(new_btn)

        reset_view_btn = QPushButton("0. 重置視圖")
        reset_view_btn.setObjectName("calcAction")
        reset_view_btn.setToolTip("縮放／平移回到預設（快捷鍵 0）")
        reset_view_btn.clicked.connect(self.map.reset_view)
        tools_lay.addWidget(reset_view_btn)
        tools_lay.addStretch(1)

        # Server connection lives in settings (was top chrome + status [本機]).
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
        connect_btn.setObjectName("calcAction")
        connect_btn.clicked.connect(self._connect_server)
        sync_row.addWidget(connect_btn)
        local_btn = QPushButton("本機")
        local_btn.setObjectName("calcAction")
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

    def _refresh_ui(self) -> None:
        s = self.state
        # Status overlay: funds / food / turn / land / pop / monster.
        # Server mode ([本機]/連線) lives in tools → settings, not here.
        monster_bit = ""
        if s.monsters:
            m = s.monsters[0]
            monster_bit = f" | 怪獸 {m.label()}({m.i},{m.j})"
        # One line only — compact separators so the strip stays single-row.
        self.stats.setText(
            f"狀態 | 資金 {s.funds} | 糧食 {s.food} | "
            f"回合 {s.turn} | 陸地 {s.land_count()} 格 | "
            f"人口 {s.population}{monster_bit}"
        )
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
                tip += "（飛彈基地優惠）"
            if reason:
                tip += f"\n不可用：{reason}"
            elif key == "wait" and self.state.has_monster():
                tip += "\n本回合不攻擊；下回合怪獸會行動"
            elif key == "defense":
                tip += "\n周圍 2 格減怪獸出現／踩踏；踩上自爆清怪"
            elif key == "missile_base":
                tip += "\n有基地時飛彈更便宜"
            elif self.selected is not None:
                tip += f"\n選格 {self.selected[0]},{self.selected[1]}"
            tip += f"\n快捷鍵 {digit}"
            btn.setToolTip(tip)

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
        if self.state.can_afforest(i, j):
            hints.append("可植林")
        extra = ("\n" + " · ".join(hints)) if hints else ""
        self.sel_label.setText(f"格子 ({i},{j})\n地形：{t}\n建築：{b}{mline}{extra}")

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
        # 觀望不需選格；其餘指令要點選格子。
        if kind == "wait":
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
                elif kind == "afforest":
                    out = self.remote.afforest(i, j)
                elif kind == "missile":
                    out = self.remote.missile(i, j)
                elif kind == "wait":
                    out = self.remote.wait_monster()
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
        elif kind == "afforest":
            msg = self.state.afforest(i, j)
        elif kind == "missile":
            msg = self.state.fire_missile(i, j)
        elif kind == "wait":
            msg = self.state.wait_monster()
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
            "可瀏覽格子與留言；建設／地形／回合已鎖定"
        )
        hint.setObjectName("calcResult")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.map = HakoniwaMapWidget(self.state)
        self.map.cell_clicked.connect(self._on_cell_clicked)
        self.hud = HakoniwaMapHud(self.map)
        self.stats = self.hud.stats
        self.sel_label = self.hud.sel_label
        self.guestbook_view = self.hud.guestbook_view
        # Tourism: no build toolbar; hide tools chrome; log shows read-only note.
        self.hud.tools_btn.hide()
        self.hud.tools_drawer.hide()
        mode = "連線" if remote is not None else "本機示範"
        self.stats.setText(
            f"[{mode}觀光] {island.name}（{self._island_id}） | "
            f"資金 {island.funds} | 糧食 {island.food} | 人口 {island.population} | "
            f"回合 {island.turn} | 陸地 {island.land_count()} 格"
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
        c = self.state.cell(i, j)
        t = TERRAIN[c.terrain]["label"]
        b = BUILDINGS[c.building]["label"] if c.building else "（無）"
        self.sel_label.setText(f"格子 ({i},{j})\n地形：{t}\n建築：{b}\n（觀光唯讀）")
        self.map.select(i, j)
