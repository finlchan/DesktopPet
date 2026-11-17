"""Headless checks for the Gradio developer console bridge (no server required).

Run: python -m dev_console.smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ok(name: str) -> None:
    print(f"  {name}: ok")


def main() -> int:
    from PIL import Image

    from .bridge import (
        DEFAULT_PRESET_LABEL,
        DevBridge,
        OBLIQUE_JSON,
        SESSION_ROOT,
        append_turn,
        display_path,
        ensure_messages,
        list_screenshot_presets,
        load_oblique_projection,
        make_demo_markup,
        plot_alignment,
        read_sync_request,
        resolve_preset,
        run_alignment2,
        save_annotation,
    )

    print("Running dev_console smoke checks…")

    # --- presets ---
    presets = list_screenshot_presets()
    assert presets, "expected screenshot presets"
    assert any("ui_overlay_map_hud" in p for p in presets), presets
    assert any(p.startswith("fish_tank/side/") for p in presets), presets
    assert "logo.png" in presets, presets
    _ok("presets")

    # --- hud load ---
    bridge = DevBridge()
    default = bridge.default_preset()
    assert default == DEFAULT_PRESET_LABEL or DEFAULT_PRESET_LABEL in presets
    if DEFAULT_PRESET_LABEL in presets:
        assert default == DEFAULT_PRESET_LABEL
        path = resolve_preset(DEFAULT_PRESET_LABEL)
        assert path.is_file(), path
        editor = bridge.load_preset_editor(DEFAULT_PRESET_LABEL)
        assert editor is not None and editor.get("background") is not None
    demo = make_demo_markup(bridge.load_preset_editor(default) if default else None)
    assert demo.size[0] > 0 and demo.size[1] > 0
    _ok("hud")

    # --- oblique json y_scale=0.65 ---
    assert OBLIQUE_JSON.is_file(), OBLIQUE_JSON
    proj = load_oblique_projection()
    assert abs(float(proj["y_scale"]) - 0.65) < 1e-9, proj
    hist, _cleared, _preview, _fig, payload = bridge.handle_chat("/proj", [])
    assert payload.get("kind") == "proj"
    assert abs(float(payload["oblique"]["y_scale"]) - 0.65) < 1e-9
    assert all(isinstance(m, dict) and "role" in m for m in hist), hist
    _ok("oblique")

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
    _ok("messages")

    # --- align ---
    result = run_alignment2(step=5.0)
    meta = result["meta"]
    assert meta["count"] >= 2, meta
    assert meta["step"] == 5.0
    wb_disp = meta["workbook"]
    assert "alignment" in wb_disp.lower() or "testdata" in wb_disp
    fig = plot_alignment(result)
    assert fig is not None
    hist2, _, _, fig2, payload2 = bridge.handle_chat("/align 10", [])
    assert payload2.get("kind") == "align"
    assert payload2["meta"]["step"] == 10.0
    assert fig2 is not None
    hist2b, _, _, _, payload2b = bridge.handle_chat("/align2 2", [])
    assert payload2b.get("kind") == "align"
    assert payload2b["meta"]["step"] == 2.0
    assert all(isinstance(m, dict) for m in hist2)
    assert all(isinstance(m, dict) for m in hist2b)
    _ok("align")

    # --- save_annotation ---
    img = Image.new("RGBA", (64, 48), (30, 144, 255, 255))
    editor_val = {"background": img, "layers": [], "composite": img.copy()}
    meta_save = save_annotation(editor_val, note="smoke", prefix="smoke")
    assert meta_save.get("ok") is True
    anno = REPO_ROOT / meta_save["annotation_png"]
    assert anno.is_file(), meta_save
    assert (SESSION_ROOT / "latest.png").is_file()
    assert (SESSION_ROOT / "latest.json").is_file()
    assert (SESSION_ROOT / "request.md").is_file()
    assert meta_save["note"] == "smoke"
    _ok("save_annotation")

    # --- sync_packet ---
    packet = read_sync_request()
    assert packet.get("ok") is True, packet
    assert packet.get("latest_png"), packet
    assert "Agent sync request" in (packet.get("request_md") or "")
    assert isinstance(packet.get("meta"), dict)
    assert (packet["meta"] or {}).get("note") == "smoke"
    _ok("sync_packet")

    # --- chat: help / align / note ---
    hist4, _, _, _, payload4 = bridge.handle_chat("/help", [])
    assert payload4.get("kind") == "help"
    assert "/align" in hist4[-1]["content"]

    hist5, _, _, _, payload5 = bridge.handle_chat("/align 1", [])
    assert payload5.get("kind") == "align"

    hist6, _, preview6, _, payload6 = bridge.handle_chat(
        "道路偏左需修正", [], editor_val
    )
    assert payload6.get("kind") == "note"
    assert payload6.get("note") == "道路偏左需修正"
    assert all(isinstance(m, dict) and set(m) >= {"role", "content"} for m in hist6)
    assert (SESSION_ROOT / "latest.png").is_file()
    _ok("chat")

    # relative path helper
    rel = display_path(OBLIQUE_JSON)
    assert rel == "hakoniwa/testdata/oblique_projection.json", rel

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
