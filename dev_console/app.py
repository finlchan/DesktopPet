"""Gradio three-pane developer console — chat | ImageEditor | live plot+JSON."""

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
    DEFAULT_PRESET_LABEL,
    display_path,
    ensure_messages,
    help_text,
)


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
            "三欄：聊天指令｜可繪製截圖｜Alignment(2)／投影即時面板"
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
                    placeholder="/help 或輸入中文校正備註…",
                    lines=2,
                )
                workbook = gr.Textbox(
                    label="Alignment(2) workbook",
                    value=wb_default,
                    placeholder="testdata/alignment2_sample.xlsx",
                )
                with gr.Row():
                    send = gr.Button("Send", variant="primary")
                    sync_btn = gr.Button("Sync to Agent", variant="secondary")
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
                    height=480,
                )
                load_btn = gr.Button("Load preset")
            with gr.Column(scale=1):
                plot = gr.Plot(label="Live Alignment(2) / preview")
                live_json = gr.JSON(label="Live JSON", value={"kind": "ready"})

        gr.Markdown(f"```\n{help_text()}\n```")

        def on_send(message, history, editor_value, workbook_path):
            history = ensure_messages(history)
            wb = workbook_path.strip() if workbook_path else None
            if wb:
                p = Path(wb)
                if not p.is_file():
                    cand = REPO_ROOT / wb
                    if cand.is_file():
                        wb = str(cand)
            new_hist, cleared, fig, payload = bridge.handle_chat(
                message, history, editor_value, workbook=wb
            )
            return new_hist, cleared, fig, payload

        def on_load_preset(label):
            if not label:
                return None, {"kind": "preset", "error": "no preset selected"}
            value = bridge.load_preset_editor(label)
            return value, {"kind": "preset", "preset": label}

        def on_sync(editor_value, history, message):
            history = ensure_messages(history)
            note = (message or "").strip()
            meta = bridge.save_annotation(
                editor_value,
                note=note,
                request=note or "Sync from Dev Console",
            )
            packet = bridge.read_sync_request()
            reply = (
                f"Synced for agent pickup → {meta.get('latest_png')} "
                f"+ {meta.get('request_md')}"
            )
            new_hist = history + [
                {"role": "user", "content": note or "[Sync to Agent]"},
                {"role": "assistant", "content": reply},
            ]
            payload = {"kind": "sync_packet", **meta, "packet": packet}
            return new_hist, "", None, payload

        send.click(
            on_send,
            inputs=[msg, chatbot, editor, workbook],
            outputs=[chatbot, msg, plot, live_json],
        )
        msg.submit(
            on_send,
            inputs=[msg, chatbot, editor, workbook],
            outputs=[chatbot, msg, plot, live_json],
        )
        sync_btn.click(
            on_sync,
            inputs=[editor, chatbot, msg],
            outputs=[chatbot, msg, plot, live_json],
        )
        load_btn.click(on_load_preset, inputs=[preset], outputs=[editor, live_json])
        preset.change(on_load_preset, inputs=[preset], outputs=[editor, live_json])

    return demo


def main(argv: Optional[List[str]] = None) -> int:
    _ = argv
    demo = _build_ui()
    share = os.environ.get("GRADIO_SHARE", "").strip() in ("1", "true", "True", "yes")
    demo.launch(
        server_name="127.0.0.1",
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        share=share,
        inbrowser=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
