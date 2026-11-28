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
    assert sm["text"] == ""
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

    cfg = {"status_marquee": {"text": "", "color_key": ""}}
    save_settings(
        cfg,
        {
            "text": "會議中",
            "color_key": "gold",
            "pos_x": 10,
            "pos_y": 20,
            "width": 400,
            "height": 180,
        },
    )
    loaded = load_settings(cfg)
    assert loaded["text"] == "會議中"
    assert loaded["color_key"] == "gold"
    assert effective_text({"text": ""}) == "休息中..."
    assert effective_color_key({"color_key": ""}) == "steel"
    assert "gold" in COLOR_PRESETS
    assert "steel" in COLOR_PRESETS
    assert "slate" in COLOR_PRESETS


def test_fish_tank_removed_from_repo() -> None:
    assert not (ROOT / "fish_tank").exists(), "fish_tank package must be deleted"
    readme = (ROOT / "README.txt").read_text(encoding="utf-8")
    assert "透明魚缸" not in readme
    assert "Fish Tank" not in readme
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
            "text": "休息中...",
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
    canvas.set_status("測試", "gold")
    canvas._phase = 0.25
    # Force a paint without showing on a real display.
    pix = canvas.grab()
    assert pix.width() > 0 and pix.height() > 0
    dlg.close()
    del dlg
    # Keep app alive for other Qt tests in-process.
    assert app is not None


def main() -> int:
    tests = [
        test_blank_packaging_template,
        test_save_roundtrip,
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
