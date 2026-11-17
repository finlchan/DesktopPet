"""Gradio three-pane developer console — chat | ImageEditor+Sync | live preview."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from .bridge import (
    BRIDGE,
    SESSION_ROOT,
    display_path,
    ensure_messages,
    help_text,
    plot_alignment,
    read_sync_request,
    run_alignment2,
    save_annotation,
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def _resolve_workbook(workbook_path: Optional[str]) -> Optional[str]:
    if not workbook_path:
        return None
    wb = workbook_path.strip()
    if not wb:
        return None
    p = Path(wb)
    if p.is_file():
        return str(p)
    cand = REPO_ROOT / wb
    if cand.is_file():
        return str(cand)
    return wb


def _build_ui():
    import gradio as gr

    bridge = BRIDGE
    presets = bridge.presets()
    default = bridge.default_preset()
    initial_editor = bridge.load_preset_editor(default) if default else None
    wb_default = display_path(bridge.workbook) if bridge.workbook.is_file() else ""

    with gr.Blocks(title="DesktopPet Dev Console") as demo:
        gr.Markdown(
            "# DesktopPet Dev Console\n"
            "三欄：聊天｜可繪製截圖 + **同步給 Agent**｜即時預覽 / Alignment(2)\n\n"
            f"Sync packet 目錄：`{display_path(SESSION_ROOT)}` "
            "（`latest.png` / `latest.json` / `request.md`）"
        )
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(
                    label="Chat",
                    type="messages",
                    height=420,
                    value=[],
                )
                msg = gr.Textbox(
                    label="Message",
                    placeholder="/help 或輸入校正備註…",
                    lines=2,
                )
                workbook = gr.Textbox(
                    label="Alignment(2) workbook",
                    value=wb_default,
                    placeholder="testdata/alignment2_sample.xlsx",
                )
                with gr.Row():
                    send = gr.Button("送出")
                    clear = gr.Button("清除對話")
            with gr.Column(scale=1):
                preset = gr.Dropdown(
                    label="Screenshot preset",
                    choices=presets,
                    value=default if default in presets else None,
                    interactive=True,
                )
                editor = gr.ImageEditor(
                    label="Screenshot editor",
                    value=initial_editor,
                    type="pil",
                    height=420,
                )
                with gr.Row():
                    load_btn = gr.Button("載入樣本")
                    push_btn = gr.Button("推到右側預覽")
                sync_btn = gr.Button("同步給 Agent", variant="primary")
            with gr.Column(scale=1):
                live_image = gr.Image(label="Live preview", type="pil", height=240)
                plot = gr.Plot(label="Alignment(2) E/N")
                live_json = gr.JSON(label="Live JSON", value={"kind": "ready"})
                align_btn = gr.Button("立刻運算 Alignment(2)")

        gr.Markdown(f"```\n{help_text()}\n```")

        def on_send(message, history, editor_value, workbook_path):
            history = ensure_messages(history)
            wb = _resolve_workbook(workbook_path)
            new_hist, cleared, preview, fig, payload = bridge.handle_chat(
                message, history, editor_value, workbook=wb
            )
            # Guarantee messages dicts even when starting from empty history.
            new_hist = ensure_messages(new_hist)
            return new_hist, cleared, preview, fig, payload

        def on_clear():
            return [], ""

        def on_load_sample(label):
            value = bridge.load_demo_editor(label)
            return value, {"kind": "sample", "preset": label}

        def on_push_preview(editor_value):
            from .bridge import _pil_from_editor

            img = _pil_from_editor(editor_value)
            if img is None:
                return None, {"kind": "preview", "error": "editor empty"}
            bridge.last_preview = img
            return img, {"kind": "preview", "size": list(img.size)}

        def on_sync_to_agent(editor_value, note_text=""):
            note = (note_text or "").strip()
            meta = save_annotation(editor_value, note=note, prefix="sync")
            packet = read_sync_request()
            from PIL import Image

            preview = None
            latest = SESSION_ROOT / "latest.png"
            if latest.is_file():
                preview = Image.open(latest).convert("RGBA")
                bridge.last_preview = preview
            payload = {
                "kind": "sync",
                "meta": meta,
                "sync_packet": {
                    "ok": packet.get("ok"),
                    "latest_png": packet.get("latest_png"),
                    "request_md_len": len(packet.get("request_md") or ""),
                },
            }
            bridge.last_live = payload
            return preview, payload

        def on_align_now(workbook_path):
            wb = _resolve_workbook(workbook_path)
            result = run_alignment2(wb, step=1.0)
            bridge.last_align = result
            fig = plot_alignment(result)
            payload = {
                "kind": "align",
                "meta": result.get("meta"),
                "points_count": len(result.get("points") or []),
            }
            bridge.last_live = payload
            return fig, payload

        send.click(
            on_send,
            inputs=[msg, chatbot, editor, workbook],
            outputs=[chatbot, msg, live_image, plot, live_json],
        )
        msg.submit(
            on_send,
            inputs=[msg, chatbot, editor, workbook],
            outputs=[chatbot, msg, live_image, plot, live_json],
        )
        clear.click(on_clear, inputs=[], outputs=[chatbot, msg])
        load_btn.click(on_load_sample, inputs=[preset], outputs=[editor, live_json])
        push_btn.click(on_push_preview, inputs=[editor], outputs=[live_image, live_json])
        sync_btn.click(
            on_sync_to_agent,
            inputs=[editor, msg],
            outputs=[live_image, live_json],
        )
        align_btn.click(on_align_now, inputs=[workbook], outputs=[plot, live_json])
        preset.change(
            lambda label: (
                bridge.load_preset_editor(label),
                {"kind": "preset", "preset": label},
            ),
            inputs=[preset],
            outputs=[editor, live_json],
        )

    return demo


def main(argv: Optional[List[str]] = None) -> int:
    _ = argv
    demo = _build_ui()
    share = _env_bool("GRADIO_SHARE", False)
    server_name = os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1") or "127.0.0.1"
    server_port = _env_int("GRADIO_SERVER_PORT", 7860)
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        inbrowser=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
