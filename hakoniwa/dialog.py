"""箱庭島 window — FramelessCalcDialog chrome + map + turn / terrain actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .model import (
    BUILDINGS,
    COST_AFFOREST,
    COST_FACTORY,
    COST_FARM,
    COST_LANDFILL,
    COST_LEVEL,
    TERRAIN,
    IslandState,
)
from .remote import HakoniwaRemote, HakoniwaRemoteError, try_connect
from .save import default_save_path, load_island, save_island
from .view import HakoniwaMapWidget


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
        self.setMinimumSize(720, 600)
        self.resize(880, 680)
        self.setStyleSheet(dp.CALC_DIALOG_STYLE + getattr(dp, "MINI_PROGRAM_STYLE", ""))

        self._save_path = self._resolve_save_path()
        loaded = load_island(self._save_path)
        self.state = loaded if loaded is not None else IslandState.new_game()
        self.selected = None

        root = dp.install_ornate_calc_frame(self)
        root.setSpacing(6)
        root.addWidget(dp.make_draggable_title(self, "箱庭島"))

        hint = QLabel(
            "箱庭斜視 · 點選格子 → 建設／地形指令 · 下回合結算　"
            "（貼圖稍後替換；目前為色塊佔位）"
        )
        hint.setObjectName("calcResult")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Optional NAS server URL (empty = local JSON only).
        sync_row = QHBoxLayout()
        sync_row.setSpacing(6)
        url_cap = QLabel("伺服器")
        url_cap.setObjectName("calcFieldCaption")
        sync_row.addWidget(url_cap)
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("留空＝本機；例 http://192.168.1.10:8787")
        self.server_url.setText(self._load_server_url())
        self.server_url.setMinimumWidth(280)
        sync_row.addWidget(self.server_url, stretch=1)
        connect_btn = QPushButton("連線")
        connect_btn.setObjectName("calcAction")
        connect_btn.clicked.connect(self._connect_server)
        sync_row.addWidget(connect_btn)
        local_btn = QPushButton("本機")
        local_btn.setObjectName("calcAction")
        local_btn.clicked.connect(self._use_local)
        sync_row.addWidget(local_btn)
        root.addLayout(sync_row)

        self.conn_status = QLabel()
        self.conn_status.setObjectName("calcResult")
        self.conn_status.setWordWrap(True)
        root.addWidget(self.conn_status)

        self.stats = QLabel()
        self.stats.setObjectName("calcSectionTitle")
        root.addWidget(self.stats)

        body = QHBoxLayout()
        body.setSpacing(8)

        self.map = HakoniwaMapWidget(self.state)
        self.map.cell_clicked.connect(self._on_cell_clicked)
        body.addWidget(self.map, stretch=1)

        side = QVBoxLayout()
        side.setSpacing(4)

        self.sel_label = QLabel("未選取格子")
        self.sel_label.setObjectName("calcResult")
        self.sel_label.setWordWrap(True)
        side.addWidget(self.sel_label)

        for key, text in (
            ("farm", f"建設農場（{COST_FARM}）"),
            ("factory", f"建設工場（{COST_FACTORY}）"),
            ("remove", "移除建築"),
            ("landfill", f"填海造陸（{COST_LANDFILL}）"),
            ("level", f"整地（{COST_LEVEL}）"),
            ("afforest", f"植林（{COST_AFFOREST}）"),
        ):
            btn = QPushButton(text)
            btn.setObjectName("calcAction")
            btn.clicked.connect(lambda checked=False, k=key: self._do_action(k))
            side.addWidget(btn)

        side.addSpacing(6)

        turn_btn = QPushButton("下回合")
        turn_btn.setObjectName("calcAction")
        turn_btn.clicked.connect(self._next_turn)
        side.addWidget(turn_btn)

        save_btn = QPushButton("存檔")
        save_btn.setObjectName("calcAction")
        save_btn.clicked.connect(self._save)
        side.addWidget(save_btn)

        new_btn = QPushButton("新島（重置）")
        new_btn.setObjectName("calcAction")
        new_btn.clicked.connect(self._new_island)
        side.addWidget(new_btn)

        side.addSpacing(4)
        log_cap = QLabel("日誌")
        log_cap.setObjectName("calcFieldCaption")
        side.addWidget(log_cap)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumWidth(260)
        self.log_view.setMinimumHeight(160)
        side.addWidget(self.log_view, stretch=1)

        side_wrap = QWidget()
        side_wrap.setLayout(side)
        side_wrap.setFixedWidth(270)
        body.addWidget(side_wrap)

        root.addLayout(body, stretch=1)

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

    def _refresh_ui(self) -> None:
        s = self.state
        mode = "連線" if self._online else "本機"
        self.stats.setText(
            f"[{mode}] 資金 {s.funds}　糧食 {s.food}　人口 {s.population}　"
            f"回合 {s.turn}　陸地 {s.land_count()} 格"
        )
        self.log_view.setPlainText("\n".join(s.log[-30:]))
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.map.update()
        self._refresh_selection_label()

    def _refresh_selection_label(self) -> None:
        if self.selected is None:
            self.sel_label.setText("未選取格子")
            return
        i, j = self.selected
        c = self.state.cell(i, j)
        t = TERRAIN[c.terrain]["label"]
        b = BUILDINGS[c.building]["label"] if c.building else "（無）"
        hints = []
        if self.state.can_landfill(i, j):
            step = "海→淺灘" if c.terrain == "sea" else "淺灘→荒地"
            hints.append(f"可填海（{step}）")
        if self.state.can_level(i, j):
            hints.append("可整地")
        if self.state.can_afforest(i, j):
            hints.append("可植林")
        extra = ("\n" + " · ".join(hints)) if hints else ""
        self.sel_label.setText(f"格子 ({i},{j})\n地形：{t}\n建築：{b}{extra}")

    def _on_cell_clicked(self, i: int, j: int) -> None:
        self.selected = (i, j)
        self._refresh_selection_label()

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
        sel = self._require_selection()
        if sel is None:
            return
        i, j = sel

        if self._online and self.remote is not None:
            try:
                if kind == "farm":
                    out = self.remote.place(i, j, "farm")
                elif kind == "factory":
                    out = self.remote.place(i, j, "factory")
                elif kind == "remove":
                    out = self.remote.remove(i, j)
                elif kind == "landfill":
                    out = self.remote.landfill(i, j)
                elif kind == "level":
                    out = self.remote.level(i, j)
                elif kind == "afforest":
                    out = self.remote.afforest(i, j)
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

        if kind == "farm":
            msg = self.state.place_building(i, j, "farm")
        elif kind == "factory":
            msg = self.state.place_building(i, j, "factory")
        elif kind == "remove":
            msg = self.state.remove_building(i, j)
        elif kind == "landfill":
            msg = self.state.landfill(i, j)
        elif kind == "level":
            msg = self.state.level_land(i, j)
        elif kind == "afforest":
            msg = self.state.afforest(i, j)
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
