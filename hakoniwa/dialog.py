"""箱庭島 window — FramelessCalcDialog chrome + map + turn / terrain actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
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
from .save import default_save_path, load_island, save_island
from .view import HakoniwaMapWidget


def _dp():
    """Late import so desktop_pet can finish loading before we pull chrome helpers."""
    import desktop_pet as dp

    return dp


class HakoniwaIslandDialog(QDialog):
    """Playable 箱庭島 v1 deepen (local mock state + JSON save).

    Uses the same frameless / ornate-frame chrome as other mini-programs by
    calling desktop_pet helpers after the host module is fully initialized.
    """

    def __init__(self, config_manager=None, parent=None):
        dp = _dp()
        super().__init__(parent)
        self.cfg = config_manager

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
        self.setMinimumSize(720, 560)
        self.resize(860, 640)
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
        online_note = QLabel("之後需連線；目前為本機暫存")
        online_note.setObjectName("calcResult")
        close_row.addWidget(online_note)
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self._refresh_ui()

    def _resolve_save_path(self) -> Path:
        if self.cfg is not None and getattr(self.cfg, "config_path", None):
            return default_save_path(Path(self.cfg.config_path).parent)
        return default_save_path(Path.cwd())

    def _refresh_ui(self) -> None:
        s = self.state
        self.stats.setText(
            f"資金 {s.funds}　糧食 {s.food}　人口 {s.population}　"
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

    def _do_action(self, kind: str) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        i, j = sel
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
        notes = self.state.next_turn()
        self._refresh_ui()
        QMessageBox.information(self, "回合結果", "\n".join(notes))

    def _save(self) -> None:
        path = save_island(self.state, self._save_path)
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
        self.state = IslandState.new_game()
        self.map.set_state(self.state)
        self.selected = None
        self._refresh_ui()
