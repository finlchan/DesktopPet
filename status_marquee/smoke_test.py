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
    assert sm["pos_x"] is None
    assert sm["pos_y"] is None
    # No personal status shipped in the blank template.
    assert "fish_tank" not in data


def test_save_roundtrip() -> None:
    from status_marquee.save import (
        COLOR_PRESETS,
        effective_color_key,
        effective_text,
        load_settings,
        save_settings,
    )

    cfg = {"status_marquee": {"text1": "", "text2": "", "color_key": ""}}
    save_settings(
        cfg,
        {
            "text1": "休息中",
            "text2": "會議中",
            "color_key": "gold",
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
    assert "text" not in loaded
    assert effective_text({"text1": "", "text2": "x"}, band=1) == "休息中..."
    assert effective_text({"text1": "a", "text2": ""}, band=2) == "休息中..."
    assert effective_color_key({"color_key": ""}) == "steel"
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
    from status_marquee.dialog import DiagonalBandsCanvas

    cfg = {
        "status_marquee": {
            "text1": "休息中...",
            "text2": "會議中...",
            "color_key": "steel",
            "pos_x": None,
            "pos_y": None,
            "width": 400,
            "height": 180,
        }
    }
    dlg = StatusMarqueeDialog(cfg, None)
    assert dlg.windowTitle()
    canvas = dlg.canvas
    assert isinstance(canvas, DiagonalBandsCanvas)
    assert canvas._text1 == "休息中..."
    assert canvas._text2 == "會議中..."
    canvas.set_status("帶一測試", "帶二測試", "gold")
    assert canvas._text1 == "帶一測試"
    assert canvas._text2 == "帶二測試"
    canvas._phase = 0.25
    # Force a paint without showing on a real display.
    pix = canvas.grab()
    assert pix.width() > 0 and pix.height() > 0

    # Settings dialog exposes two text fields.
    from status_marquee.dialog import StatusMarqueeSettingsDialog

    settings = StatusMarqueeSettingsDialog(dlg)
    assert settings.text1_edit is not None
    assert settings.text2_edit is not None
    settings.close()

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
