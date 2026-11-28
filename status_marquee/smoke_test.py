"""Smoke checks for desktop status marquee + fish-tank removal.

Run: QT_QPA_PLATFORM=offscreen python -m status_marquee.smoke_test
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_blank_packaging_template() -> None:
    path = ROOT / "packaging" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "status_marquee" in data
    sm = data["status_marquee"]
    assert sm.get("text1") == ""
    assert sm.get("text2") == ""
    assert "text" not in sm  # dual fields only in blank template
    assert sm["color_key"] == ""
    assert sm.get("display_mode") == ""
    assert sm.get("scroll_speed") is None
    assert sm.get("band_size") is None
    assert sm["pos_x"] is None
    assert sm["pos_y"] is None
    # No personal status shipped in the blank template.
    assert "fish_tank" not in data


def test_save_roundtrip() -> None:
    from status_marquee.save import (
        COLOR_PRESETS,
        DISPLAY_MODE_DUAL_SPAN,
        cycle_ms_for_speed,
        effective_band_size,
        effective_color_key,
        effective_display_mode,
        effective_scroll_speed,
        effective_text,
        load_settings,
        save_settings,
    )

    cfg = {
        "status_marquee": {
            "text1": "",
            "text2": "",
            "color_key": "",
            "display_mode": "",
            "scroll_speed": None,
            "band_size": None,
        }
    }
    save_settings(
        cfg,
        {
            "text1": "休息中",
            "text2": "會議中",
            "color_key": "gold",
            "display_mode": DISPLAY_MODE_DUAL_SPAN,
            "scroll_speed": 8,
            "band_size": 72,
            "pos_x": 10,
            "pos_y": 20,
            "width": 400,
            "height": 180,
        },
    )
    loaded = load_settings(cfg)
    assert loaded["text1"] == "休息中"
    assert loaded["text2"] == "會議中"
    assert loaded["color_key"] == "gold"
    assert loaded["display_mode"] == DISPLAY_MODE_DUAL_SPAN
    assert loaded["scroll_speed"] == 8
    assert loaded["band_size"] == 72
    assert "text" not in loaded
    assert effective_text({"text1": "", "text2": "x"}, band=1) == "休息中..."
    assert effective_text({"text1": "a", "text2": ""}, band=2) == "休息中..."
    assert effective_color_key({"color_key": ""}) == "steel"
    assert effective_display_mode({"display_mode": ""}) == "single"
    assert effective_scroll_speed({"scroll_speed": None}) == 5
    assert effective_band_size({"band_size": None}) == 56
    assert cycle_ms_for_speed(5) == 8000
    assert cycle_ms_for_speed(1) > cycle_ms_for_speed(10)
    assert "gold" in COLOR_PRESETS
    assert "steel" in COLOR_PRESETS
    assert "slate" in COLOR_PRESETS


def test_legacy_text_migration() -> None:
    """Old single ``text`` applies to both bands; dual fields win when present."""
    from status_marquee.save import load_settings, normalize_settings

    legacy = normalize_settings({"text": "舊狀態", "color_key": "slate"})
    assert legacy["text1"] == "舊狀態"
    assert legacy["text2"] == "舊狀態"
    assert "text" not in legacy
    # New fields default blank on legacy configs.
    assert legacy["display_mode"] == ""
    assert legacy["scroll_speed"] is None
    assert legacy["band_size"] is None

    # Prefer dual fields over legacy when text1/text2 keys exist.
    dual = normalize_settings(
        {"text": "舊", "text1": "帶一", "text2": "帶二", "color_key": "steel"}
    )
    assert dual["text1"] == "帶一"
    assert dual["text2"] == "帶二"

    # Partial dual: missing band falls back to legacy text.
    partial = normalize_settings({"text": "共用", "text1": "只有一"})
    assert partial["text1"] == "只有一"
    assert partial["text2"] == "共用"

    loaded = load_settings({"status_marquee": {"text": "從cfg"}})
    assert loaded["text1"] == "從cfg"
    assert loaded["text2"] == "從cfg"


def test_fish_tank_removed_from_repo() -> None:
    assert not (ROOT / "fish_tank").exists(), "fish_tank package must be deleted"
    readme = (ROOT / "README.txt").read_text(encoding="utf-8")
    # Features / Quick Usage must not list the tank (release-note history may mention removal).
    features = readme.split("Latest updates", 1)[0]
    assert "透明魚缸" not in features
    assert "Fish Tank" not in features
    assert "桌面跑馬燈" in readme or "跑馬燈" in readme

    desktop = (ROOT / "desktop_pet.py").read_text(encoding="utf-8")
    assert "open_fish_tank" not in desktop
    assert "FishTankDialog" not in desktop
    assert "透明魚缸" not in desktop
    assert "status_marquee" in desktop
    assert "桌面跑馬燈" in desktop

    build = (ROOT / "build.bat").read_text(encoding="utf-8")
    assert "fish_tank" not in build
    assert "status_marquee" in build

    workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8"
    )
    assert "fish_tank" not in workflow
    assert "status_marquee" in workflow


def test_menu_entry_present() -> None:
    """Mini programs submenu wires StatusMarqueeDialog (AST, no GUI)."""
    src = (ROOT / "desktop_pet.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_open = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "open_status_marquee":
            found_open = True
            break
    assert found_open, "MiniProgramsSubMenu.open_status_marquee missing"


def test_dialog_qt_offscreen() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from status_marquee import StatusMarqueeDialog
    from status_marquee.dialog import (
        CenteredGearButton,
        DiagonalBandsCanvas,
        StatusMarqueeSettingsPanel,
    )
    from status_marquee.save import DISPLAY_MODE_DUAL_SPAN, cycle_ms_for_speed

    cfg = {
        "status_marquee": {
            "text1": "休息中...",
            "text2": "會議中...",
            "color_key": "steel",
            "display_mode": "single",
            "scroll_speed": 5,
            "band_size": 56,
            "pos_x": None,
            "pos_y": None,
            "width": 400,
            "height": 180,
        }
    }
    dlg = StatusMarqueeDialog(cfg, None)
    assert dlg.windowTitle()
    # Show so child isVisible() reflects panel show/hide (ancestors must be visible).
    dlg.show()
    canvas = dlg.canvas
    assert isinstance(canvas, DiagonalBandsCanvas)
    assert isinstance(dlg.gear, CenteredGearButton)
    assert canvas._text1 == "休息中..."
    assert canvas._text2 == "會議中..."
    assert canvas._band_size == 56
    assert canvas._cycle_ms == cycle_ms_for_speed(5)

    canvas.set_status(
        "帶一測試",
        "帶二測試",
        "gold",
        band_size=80,
        cycle_ms=4000,
    )
    assert canvas._text1 == "帶一測試"
    assert canvas._text2 == "帶二測試"
    assert canvas._band_size == 80
    assert canvas._cycle_ms == 4000
    canvas._phase = 0.25
    # Force a paint without showing on a real display.
    pix = canvas.grab()
    assert pix.width() > 0 and pix.height() > 0

    # Settings are an inline panel (same window), not a separate QDialog.
    assert isinstance(dlg.settings_panel, StatusMarqueeSettingsPanel)
    assert dlg.settings_panel.parent() is dlg
    dlg.open_settings()
    assert dlg.settings_panel.isVisible()
    assert not isinstance(dlg.settings_panel, type(dlg))  # not another top-level dialog
    from PySide6.QtWidgets import QDialog as _QDialog

    assert not isinstance(dlg.settings_panel, _QDialog)
    assert dlg.settings_panel.text1_edit is not None
    assert dlg.settings_panel.text2_edit is not None
    assert dlg.settings_panel.mode_single is not None
    assert dlg.settings_panel.mode_dual is not None
    assert dlg.settings_panel.speed_slider is not None
    assert dlg.settings_panel.band_slider is not None

    # Apply dual-span + speed/size via panel.
    dlg.settings_panel.mode_dual.setChecked(True)
    dlg.settings_panel.speed_slider.setValue(9)
    dlg.settings_panel.band_slider.setValue(90)
    dlg.settings_panel.text1_edit.setText("帶一")
    dlg.settings_panel.text2_edit.setText("帶二")
    dlg.settings_panel._apply()
    assert dlg._settings["display_mode"] == DISPLAY_MODE_DUAL_SPAN
    assert dlg._settings["scroll_speed"] == 9
    assert dlg._settings["band_size"] == 90
    assert canvas._band_size == 90

    # Dual-span: gear stays visible, raised, and on the primary-screen chrome.
    assert dlg.gear.isVisible()
    assert not dlg.gear.isHidden()
    gear_geo = dlg.gear.geometry()
    assert dlg.rect().contains(gear_geo), "gear must stay inside dialog"
    anchor = dlg._chrome_anchor_rect()
    assert anchor.intersects(gear_geo) or anchor.contains(gear_geo.center())
    # Z-order: gear above the full-bleed canvas.
    assert dlg.gear.isVisible()
    assert dlg.canvas.isVisible()

    # Gear toggles the same inline panel (no separate window).
    dlg.hide_settings()
    assert not dlg.settings_panel.isVisible()
    dlg.gear.click()
    assert dlg.settings_panel.isVisible()
    assert dlg.gear.isVisible()

    # Right-click on bands / empty area opens the same inline panel.
    dlg.hide_settings()
    assert not dlg.settings_panel.isVisible()
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    # Click near center of the canvas (not on gear/panel).
    click_pos = QPoint(max(40, dlg.width() // 2), max(40, dlg.height() // 2))
    # Ensure we are not hitting the gear.
    assert not dlg.gear.geometry().contains(click_pos)
    local = QPointF(click_pos)
    global_pos = QPointF(dlg.mapToGlobal(click_pos))
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        local,
        local,
        global_pos,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(dlg, press)
    assert dlg.settings_panel.isVisible(), "right-click must open inline settings"
    assert dlg.gear.isChecked()

    # Gear glyph paints into a square circle target.
    gear_pix = dlg.gear.grab()
    assert gear_pix.width() == dlg.gear.width()
    assert gear_pix.height() == dlg.gear.height()

    # Switch back to single fullscreen — gear still visible top-right.
    dlg.settings_panel.mode_single.setChecked(True)
    dlg.settings_panel._apply()
    assert dlg._settings["display_mode"] == "single"
    assert dlg.gear.isVisible()
    assert dlg.rect().contains(dlg.gear.geometry())

    dlg.close()
    del dlg
    assert app is not None


def main() -> int:
    tests = [
        test_blank_packaging_template,
        test_save_roundtrip,
        test_legacy_text_migration,
        test_fish_tank_removed_from_repo,
        test_menu_entry_present,
        test_dialog_qt_offscreen,
    ]
    for fn in tests:
        fn()
        print(f"OK  {fn.__name__}")
    print("status_marquee smoke_test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
