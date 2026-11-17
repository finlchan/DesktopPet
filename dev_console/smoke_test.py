"""Headless checks for the Gradio developer console bridge (no server required).

Run: python -m dev_console.smoke_test
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from PIL import Image

    from .bridge import (
        DEFAULT_PRESET_LABEL,
        DevBridge,
        DATA_DIR,
        OBLIQUE_JSON,
        append_turn,
        display_path,
        ensure_messages,
        load_oblique_projection,
        list_screenshot_presets,
        resolve_preset,
        run_alignment2,
        save_composite,
    )

    # --- presets ---
    presets = list_screenshot_presets()
    assert presets, "expected hakoniwa testdata screenshots"
    assert any("ui_overlay_map_hud" in p for p in presets), presets
    bridge = DevBridge()
    default = bridge.default_preset()
    assert default == DEFAULT_PRESET_LABEL or DEFAULT_PRESET_LABEL in presets
    if DEFAULT_PRESET_LABEL in presets:
        assert default == DEFAULT_PRESET_LABEL
        path = resolve_preset(DEFAULT_PRESET_LABEL)
        assert path.is_file(), path
        editor = bridge.load_preset_editor(DEFAULT_PRESET_LABEL)
        assert editor is not None and editor.get("background") is not None

    # --- oblique json y_scale=0.65 ---
    assert OBLIQUE_JSON.is_file(), OBLIQUE_JSON
    proj = load_oblique_projection()
    assert abs(float(proj["y_scale"]) - 0.65) < 1e-9, proj
    hist, _cleared, _fig, payload = bridge.handle_chat("/proj", [])
    assert payload.get("kind") == "proj"
    assert abs(float(payload["oblique"]["y_scale"]) - 0.65) < 1e-9
    assert all(isinstance(m, dict) and "role" in m for m in hist), hist

    # --- empty history must stay messages (never tuples) ---
    empty = ensure_messages(None)
    assert empty == []
    empty2 = ensure_messages([])
    assert empty2 == []
    turned = append_turn([], "hi", "there")
    assert turned == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "there"},
    ]

    # --- align ---
    result = run_alignment2(step=5.0)
    meta = result["meta"]
    assert meta["count"] >= 2, meta
    assert meta["step"] == 5.0
    # Path display uses Path.is_relative_to semantics
    wb_disp = meta["workbook"]
    assert not wb_disp.startswith("/") or "testdata" in wb_disp
    assert "alignment" in wb_disp.lower() or "testdata" in wb_disp
    hist2, _, fig, payload2 = bridge.handle_chat("/align 10", [])
    assert payload2.get("kind") == "align"
    assert payload2["meta"]["step"] == 10.0
    assert fig is not None
    assert all(isinstance(m, dict) for m in hist2)

    # --- save ---
    img = Image.new("RGBA", (64, 48), (30, 144, 255, 255))
    editor_val = {"background": img, "layers": [], "composite": img.copy()}
    with tempfile.TemporaryDirectory() as tmp:
        # save_composite writes under Data/dev_console (gitignored); still assert files.
        meta_save = save_composite(editor_val, note="smoke")
        saved = REPO_ROOT / meta_save["image"]
        if not saved.is_file():
            # display_path may be relative
            saved = Path(meta_save["image"])
            if not saved.is_file():
                saved = DATA_DIR / Path(meta_save["image"]).name
        assert saved.is_file(), meta_save
        assert meta_save["note"] == "smoke"

    hist3, _, _, payload3 = bridge.handle_chat("/save smoke-note", [], editor_val)
    assert payload3.get("kind") == "save"
    assert "smoke-note" in (payload3.get("note") or "")
    assert all(isinstance(m, dict) for m in hist3)

    # --- chat: help / shots / Chinese correction ---
    hist4, _, _, payload4 = bridge.handle_chat("/help", [])
    assert payload4.get("kind") == "help"
    assert "/align" in hist4[-1]["content"]

    hist5, _, _, payload5 = bridge.handle_chat("/shots", [])
    assert payload5.get("kind") == "shots"
    assert DEFAULT_PRESET_LABEL in (payload5.get("presets") or []) or any(
        "ui_overlay" in p for p in (payload5.get("presets") or [])
    )

    hist6, _, _, payload6 = bridge.handle_chat("道路偏左需修正", [], editor_val)
    assert payload6.get("kind") == "correction"
    assert payload6.get("note") == "道路偏左需修正"
    assert all(isinstance(m, dict) and set(m) >= {"role", "content"} for m in hist6)

    # relative path helper
    rel = display_path(OBLIQUE_JSON)
    assert rel == "hakoniwa/testdata/oblique_projection.json", rel
    assert OBLIQUE_JSON.resolve().is_relative_to(REPO_ROOT.resolve())

    # keep a tiny JSON proof next to Data for local debugging (gitignored Data/)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "smoke_ok.json").write_text(
        json.dumps({"ok": True, "y_scale": proj["y_scale"]}, indent=2),
        encoding="utf-8",
    )

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
