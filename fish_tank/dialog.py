"""Transparent Fish Tank window — glass click-through, edge grips, Social Icon Fill toolbar.

Phase 1: local playable tank only. Phase 2 hooks live in ``remote_stubs``.
Primary chrome: bottom-left circular Social Icon Fill buttons (not a top text strip).
"""

from __future__ import annotations

import sys
import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .model import TankState
from .save import default_save_path, load_tank, save_tank
from .social_toolbar import SocialIconToolbar
from .species import SPECIES
from .sprites import warm_cache
from .view import TankView, capture_card_pixmap
from . import remote_stubs
from . import world as world_sim

# Edge grip thickness (always-on 「 」 style handles).
GRIP = 10
# Slim top status chip only (primary toolbar is bottom-left Social Icon Fill).
STATUS_CHIP_H = 28

TANK_STYLE = """
QDialog#FishTankDialog {
    background: transparent;
}
QLabel#fishTankStatusChip {
    color: #c8dce8;
    font-size: 11px;
    padding: 4px 10px;
    background-color: rgba(24, 36, 48, 180);
    border: 1px solid rgba(140, 180, 200, 120);
    border-radius: 10px;
}
QPushButton#fishTankBtn {
    background-color: rgba(50, 78, 100, 220);
    color: #f0f6fa;
    border: 1px solid rgba(140, 180, 200, 180);
    border-radius: 3px;
    padding: 3px 8px;
    font-size: 12px;
}
QPushButton#fishTankBtn:hover {
    background-color: rgba(70, 110, 140, 230);
}
QPushButton#fishTankBtn:checked {
    background-color: rgba(120, 90, 40, 230);
}
QFrame#fishTankGrip {
    background-color: rgba(210, 230, 240, 90);
}
QDialog#CaptureCardDialog {
    background-color: rgba(20, 32, 44, 235);
}
"""


def _set_windows_click_through(widget: QWidget, enable: bool) -> None:
    """Toggle WS_EX_TRANSPARENT so glass clicks reach the desktop (Windows)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if enable:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


class EdgeGrips(QWidget):
    """Always-on edge / corner resize grips drawn as soft 「 」 brackets."""

    def __init__(self, host: "FishTankDialog"):
        super().__init__(host)
        self.host = host
        self.setObjectName("fishTankGrip")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._mode: Optional[str] = None
        self._origin = QPoint()
        self._geo = QRect()

    def hit_mode(self, pos: QPoint) -> Optional[str]:
        r = self.rect()
        x, y = pos.x(), pos.y()
        left, right = x <= GRIP, x >= r.width() - GRIP
        top, bottom = y <= GRIP, y >= r.height() - GRIP
        # Corners / edges always grip; Social Icon toolbar is bottom-left (mask keeps
        # center transparent so toolbar receives clicks).
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if bottom:
            return "b"
        if top:
            # Top edge only outside toolbar horizontal span is still a grip
            # for move; use full top as move/drag.
            return "move"
        return None

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = p.pen()
        pen.setColor(QColor(220, 235, 245, 160))
        pen.setWidth(2)
        p.setPen(pen)
        w, h = self.width(), self.height()
        L = 18
        # 「 top-left
        p.drawLine(2, GRIP + L, 2, 2)
        p.drawLine(2, 2, GRIP + L, 2)
        # 」 top-right
        p.drawLine(w - 3, 2, w - 3, GRIP + L)
        p.drawLine(w - 3, 2, w - GRIP - L, 2)
        # bottom-left
        p.drawLine(2, h - 3, 2, h - GRIP - L)
        p.drawLine(2, h - 3, GRIP + L, h - 3)
        # bottom-right
        p.drawLine(w - 3, h - 3, w - 3, h - GRIP - L)
        p.drawLine(w - 3, h - 3, w - GRIP - L, h - 3)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        mode = self.hit_mode(event.position().toPoint())
        if mode is None:
            event.ignore()
            return
        self._mode = mode
        self._origin = event.globalPosition().toPoint()
        self._geo = self.host.geometry()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode is None:
            mode = self.hit_mode(event.position().toPoint())
            cursors = {
                "tl": Qt.CursorShape.SizeFDiagCursor,
                "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor,
                "bl": Qt.CursorShape.SizeBDiagCursor,
                "l": Qt.CursorShape.SizeHorCursor,
                "r": Qt.CursorShape.SizeHorCursor,
                "b": Qt.CursorShape.SizeVerCursor,
                "move": Qt.CursorShape.SizeAllCursor,
            }
            self.setCursor(cursors.get(mode, Qt.CursorShape.ArrowCursor))
            event.ignore()
            return
        delta = event.globalPosition().toPoint() - self._origin
        g = QRect(self._geo)
        m = self._mode
        if m == "move":
            g.translate(delta)
        else:
            if "l" in m:
                g.setLeft(g.left() + delta.x())
            if "r" in m:
                g.setRight(g.right() + delta.x())
            if "t" in m:
                g.setTop(g.top() + delta.y())
            if "b" in m:
                g.setBottom(g.bottom() + delta.y())
            if g.width() < 320:
                g.setWidth(320)
            if g.height() < 240:
                g.setHeight(240)
        self.host.setGeometry(g)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._mode = None
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Zoom via wheel on grips (visible-range only).
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.1 if delta > 0 else 1 / 1.1
        # Anchor at viewport center.
        self.host.tank_view.zoom_at(
            factor, self.host.tank_view.width() / 2, self.host.tank_view.height() / 2
        )
        event.accept()


class CaptureCardDialog(QDialog):
    """View-2 capture / 圖鑑 card: side art + status + scientific name."""

    def __init__(self, fish, parent=None):
        super().__init__(parent)
        self.setObjectName("CaptureCardDialog")
        self.setWindowTitle("圖鑑／Capture")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setStyleSheet(TANK_STYLE)
        sp = SPECIES[fish.species_key]
        lay = QVBoxLayout(self)
        title = QLabel(sp.display_market_bilingual())
        title.setStyleSheet("color:#f0f6fa; font-size:14px; font-weight:bold;")
        lay.addWidget(title)
        sci = QLabel(f"學名／Scientific: {sp.scientific}")
        sci.setStyleSheet("color:#b8d0e0; font-style:italic;")
        lay.addWidget(sci)
        art = QLabel()
        art.setPixmap(capture_card_pixmap(fish.species_key, fish.rare))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(art)
        name_line = fish.custom_name or "（未命名／unnamed）"
        stats = QLabel(
            "\n".join(
                [
                    f"名稱／Name: {name_line}",
                    f"狀態／Status:",
                    f"  健康／Health: {fish.health:.0%}",
                    f"  飽食／Fullness: {fish.fullness:.0%}",
                    f"  年齡／Age: {fish.age_days:.1f} d",
                    f"  稀有度／Rarity: {fish.rarity_label()}",
                    f"  擁有／Owned: {'是／yes' if fish.owned else '否／no'}",
                ]
            )
        )
        stats.setStyleSheet("color:#e4eef6;")
        lay.addWidget(stats)
        close_btn = QPushButton("關閉／Close")
        close_btn.setObjectName("fishTankBtn")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)
        self.resize(320, 420)


class FishTankDialog(QDialog):
    """Full-window translucent tank with glass click-through + grips + toolbar."""

    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setObjectName("FishTankDialog")
        self.setWindowTitle("透明魚缸／Transparent Fish Tank")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(TANK_STYLE)
        self.setMinimumSize(480, 320)
        self.resize(900, 560)

        warm_cache()
        self._save_path = default_save_path()
        loaded = load_tank(self._save_path)
        self.state = loaded if loaded is not None else TankState.new_tank()

        # Stack: glass view fills; grips overlay; Social Icon Fill toolbar bottom-left.
        self.tank_view = TankView(self.state, self)
        self.tank_view.fish_clicked.connect(self._on_fish_clicked)

        self.grips = EdgeGrips(self)
        self.grips.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )

        # Slim top status chip (title + live stats) — no text button strip.
        self.status_chip = QLabel("透明魚缸／Fish Tank", self)
        self.status_chip.setObjectName("fishTankStatusChip")
        self.status_chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.toolbar = SocialIconToolbar(self)
        self.toolbar.bind(
            feed=self._feed,
            decorate=self._decorate,
            name=self._name,
            catch_toggle=self._toggle_catch,
            dex=self._open_dex,
            view=self._reset_view,
            close=self.close,
        )
        self.btn_catch = self.toolbar.catch_button()

        self._catch_mode = False
        self._click_through = True
        self._last_tick = time.monotonic()
        self._log_flash = ""

        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(50)
        self._sim_timer.timeout.connect(self._on_tick)
        self._sim_timer.start()

        # Periodically re-apply click-through based on cursor over chrome.
        self._hit_timer = QTimer(self)
        self._hit_timer.setInterval(80)
        self._hit_timer.timeout.connect(self._update_click_through)
        self._hit_timer.start()

        # Phase 2 settlement cadence stub (local flush only).
        self._settle_timer = QTimer(self)
        self._settle_timer.setInterval(remote_stubs.SETTLEMENT_INTERVAL_SEC * 1000)
        self._settle_timer.timeout.connect(self._on_settlement_stub)
        self._settle_timer.start()

        self._layout_children()
        self._refresh_status()

    # --- layout ---------------------------------------------------------

    def _layout_children(self) -> None:
        r = self.rect()
        self.tank_view.setGeometry(r)
        self.grips.setGeometry(r)
        # Slim status chip — top-left, clear of edge grips.
        self.status_chip.adjustSize()
        chip_w = max(160, self.status_chip.sizeHint().width() + 8)
        self.status_chip.setGeometry(
            GRIP + 8, GRIP + 6, min(chip_w, r.width() - 2 * GRIP - 16), STATUS_CHIP_H
        )
        # Primary toolbar: bottom-left Social Icon Fill row (compact).
        self.toolbar.adjustSize()
        th = self.toolbar.sizeHint()
        tw = min(th.width(), r.width() - GRIP - 16)
        tb_h = th.height()
        self.toolbar.setGeometry(GRIP + 6, r.height() - GRIP - tb_h - 6, tw, tb_h)
        self.status_chip.raise_()
        self.toolbar.raise_()
        self.grips.raise_()
        # Let grips receive edge hits but pass center to view/toolbar via
        # a mask: grips only opaque on the GRIP band.
        self._update_grip_mask()

    def _update_grip_mask(self) -> None:
        from PySide6.QtGui import QRegion

        r = self.grips.rect()
        region = QRegion(0, 0, r.width(), GRIP)  # top
        region = region.united(QRegion(0, r.height() - GRIP, r.width(), GRIP))
        region = region.united(QRegion(0, 0, GRIP, r.height()))
        region = region.united(QRegion(r.width() - GRIP, 0, GRIP, r.height()))
        self.grips.setMask(region)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_children()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._layout_children()
        # Start with click-through enabled (glass).
        _set_windows_click_through(self, True)
        self._click_through = True

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            save_tank(self.state, self._save_path)
        except OSError:
            pass
        _set_windows_click_through(self, False)
        super().closeEvent(event)

    # --- click-through --------------------------------------------------

    def _chrome_contains_global(self, gpos: QPoint) -> bool:
        local = self.mapFromGlobal(gpos)
        # Bottom-left Social Icon Fill toolbar?
        if self.toolbar.geometry().contains(local):
            return True
        # Slim status chip (non-interactive but still chrome for pass-through).
        if self.status_chip.geometry().contains(local):
            return True
        # Grip band?
        r = self.rect()
        if (
            local.x() <= GRIP
            or local.x() >= r.width() - GRIP
            or local.y() <= GRIP
            or local.y() >= r.height() - GRIP
        ):
            return True
        # Catch / interact mode: whole window interactive.
        if self._catch_mode:
            return True
        return False

    def _update_click_through(self) -> None:
        over_chrome = self._chrome_contains_global(QCursor.pos())
        want_through = not over_chrome
        if want_through != self._click_through:
            _set_windows_click_through(self, want_through)
            self._click_through = want_through

    # --- simulation -----------------------------------------------------

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last_tick)
        self._last_tick = now
        logs = world_sim.tick(self.state, dt)
        if logs:
            self._log_flash = logs[-1]
        self.tank_view.update()
        self._refresh_status()

    def _on_settlement_stub(self) -> None:
        # Phase 1: flush care deltas into no-op settlement hook.
        self.state.flush_settlement_stub()
        self._log_flash = "結算暫存／Settlement stub flushed (local)"

    def _refresh_status(self) -> None:
        n = len(self.state.active_fish())
        owned = len(self.state.owned_fish())
        away = sum(1 for f in self.state.fish if f.away)
        z = self.state.zoom
        msg = f"魚／Fish {n}  擁有／Owned {owned}  外出／Away {away}  縮放／Zoom {z:.2f}"
        if self._log_flash:
            msg = f"{msg}  ·  {self._log_flash}"
        self.status_chip.setText(f"透明魚缸／Fish Tank  ·  {msg}")
        self.toolbar.set_status(msg)

    # --- toolbar actions ------------------------------------------------

    def _feed(self) -> None:
        self.state.feed()
        self._log_flash = "已餵食／Fed"
        try:
            save_tank(self.state, self._save_path)
        except OSError:
            pass

    def _decorate(self) -> None:
        self.state.decorate()
        self._log_flash = "已佈景／Decorated (水蘊草／Waterweed)"
        try:
            save_tank(self.state, self._save_path)
        except OSError:
            pass

    def _name(self) -> None:
        owned = self.state.owned_fish()
        if not owned:
            QMessageBox.information(
                self,
                "命名／Name",
                "尚未擁有魚隻。先捕捉／No owned fish — catch one first.",
            )
            return
        labels = [
            f"{f.custom_name or f.market_label()} [{f.id}]"
            for f in owned
        ]
        item, ok = QInputDialog.getItem(
            self,
            "命名／Name",
            "選擇魚隻／Choose fish:",
            labels,
            0,
            False,
        )
        if not ok:
            return
        idx = labels.index(item)
        fish = owned[idx]
        new_name, ok2 = QInputDialog.getText(
            self,
            "命名／Name",
            f"新名稱／New name ({fish.market_label()}):",
            text=fish.custom_name,
        )
        if ok2:
            self.state.name_fish(fish.id, new_name)
            self._log_flash = f"已命名／Named: {new_name}"
            try:
                save_tank(self.state, self._save_path)
            except OSError:
                pass

    def _toggle_catch(self, checked: bool = False) -> None:
        # Social Icon catch button toggles itself before emitting clicked.
        self._catch_mode = self.btn_catch.isChecked()
        self.tank_view.set_interact_mode(self._catch_mode)
        if self._catch_mode:
            self._log_flash = "捕捉模式／Catch mode — click a fish"
            # Ensure window receives clicks.
            _set_windows_click_through(self, False)
            self._click_through = False
        else:
            self._log_flash = "結束捕捉／Catch mode off"
        self._refresh_status()

    def _on_fish_clicked(self, fish_id: str) -> None:
        if not self._catch_mode:
            return
        fish = next((f for f in self.state.fish if f.id == fish_id), None)
        if fish is None:
            return
        if fish.owned:
            CaptureCardDialog(fish, self).exec()
            return
        caught = self.state.catch_fish(fish_id)
        if caught:
            self._log_flash = f"已捕捉／Caught: {caught.market_label()}"
            try:
                save_tank(self.state, self._save_path)
            except OSError:
                pass
            CaptureCardDialog(caught, self).exec()
        self.btn_catch.setChecked(False)
        self._toggle_catch(False)

    def _open_dex(self) -> None:
        """圖鑑: list owned fish; show view-2 card with scientific name."""
        owned = self.state.owned_fish()
        if not owned:
            # Still allow browsing species templates via a wild fish if any.
            active = self.state.active_fish()
            if not active:
                QMessageBox.information(
                    self, "圖鑑／Dex", "魚缸內沒有魚／No fish in tank."
                )
                return
            QMessageBox.information(
                self,
                "圖鑑／Dex",
                "圖鑑顯示已捕捉魚隻的學名與狀態。\n"
                "Dex shows scientific name + status for caught fish.\n"
                "請先捕捉／Catch a fish first.",
            )
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("圖鑑／Dex")
        dlg.setStyleSheet(TANK_STYLE)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("已捕捉／Owned — 選取查看卡片／select for card"))
        lst = QListWidget()
        for f in owned:
            sp = SPECIES[f.species_key]
            text = f"{f.custom_name + ' · ' if f.custom_name else ''}{sp.display_market_zh()} — {sp.scientific}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            lst.addItem(item)
        lay.addWidget(lst)

        def _open():
            items = lst.selectedItems()
            if not items:
                return
            fid = items[0].data(Qt.ItemDataRole.UserRole)
            fish = next(f for f in owned if f.id == fid)
            CaptureCardDialog(fish, dlg).exec()

        lst.itemDoubleClicked.connect(lambda _i: _open())
        row = QHBoxLayout()
        open_btn = QPushButton("查看／Open")
        open_btn.setObjectName("fishTankBtn")
        open_btn.clicked.connect(_open)
        close_btn = QPushButton("關閉／Close")
        close_btn.setObjectName("fishTankBtn")
        close_btn.clicked.connect(dlg.accept)
        row.addWidget(open_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)
        dlg.resize(420, 320)
        dlg.exec()

    def _reset_view(self) -> None:
        from .model import VIEW_H, VIEW_W, WORLD_H, WORLD_W

        self.state.zoom = 1.0
        self.state.cam_x = (WORLD_W - VIEW_W) * 0.5
        self.state.cam_y = (WORLD_H - VIEW_H) * 0.5
        self.tank_view.update()
        self._log_flash = "視圖已重置／View reset"
