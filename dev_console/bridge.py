"""Bridge: hakoniwa screenshots, Alignment(2), ImageEditor save, chat router."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HAKONIWA_TESTDATA = REPO_ROOT / "hakoniwa" / "testdata"
ALIGN_TESTDATA = REPO_ROOT / "testdata"
DATA_DIR = REPO_ROOT / "Data" / "dev_console"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
LATEST_PNG = DATA_DIR / "latest.png"
LATEST_JSON = DATA_DIR / "latest.json"
REQUEST_MD = DATA_DIR / "request.md"
OBLIQUE_JSON = HAKONIWA_TESTDATA / "oblique_projection.json"
DEFAULT_PRESET_LABEL = "hakoniwa/ui_overlay_map_hud.png"

Message = Dict[str, str]
History = List[Message]
ChatResult = Tuple[History, str, Any, Dict[str, Any]]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def ensure_messages(history: Optional[Sequence[Any]]) -> History:
    """Normalize chat history to Gradio messages dicts. Never fall back to tuples."""
    if not history:
        return []
    out: History = []
    for item in history:
        if isinstance(item, dict) and "role" in item and "content" in item:
            out.append({"role": str(item["role"]), "content": str(item["content"])})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            # Convert legacy pairs into messages; do not keep tuple form.
            user, assistant = item[0], item[1]
            if user is not None and str(user) != "":
                out.append({"role": "user", "content": str(user)})
            if assistant is not None and str(assistant) != "":
                out.append({"role": "assistant", "content": str(assistant)})
        else:
            raise TypeError(
                f"chat history entries must be messages dicts {{role, content}}; got {type(item)!r}"
            )
    return out


def append_turn(history: Optional[Sequence[Any]], user: str, assistant: str) -> History:
    hist = ensure_messages(history)
    hist.append({"role": "user", "content": user})
    hist.append({"role": "assistant", "content": assistant})
    return hist


def display_path(path: Path, base: Path = REPO_ROOT) -> str:
    path = Path(path).resolve()
    base = Path(base).resolve()
    try:
        if path.is_relative_to(base):
            return str(path.relative_to(base)).replace("\\", "/")
    except AttributeError:
        # Python < 3.9 fallback (should not hit on supported runtimes).
        try:
            return str(path.relative_to(base)).replace("\\", "/")
        except ValueError:
            pass
    except ValueError:
        pass
    return str(path)


def _preset_label(path: Path) -> str:
    """Label like hakoniwa/ui_overlay_map_hud.png for hakoniwa/testdata shots."""
    try:
        if path.is_relative_to(HAKONIWA_TESTDATA):
            return f"hakoniwa/{path.name}"
    except ValueError:
        pass
    try:
        if path.is_relative_to(REPO_ROOT):
            return display_path(path)
    except ValueError:
        pass
    return path.name


def list_screenshot_presets() -> List[str]:
    if not HAKONIWA_TESTDATA.is_dir():
        return []
    files = sorted(
        p
        for p in HAKONIWA_TESTDATA.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )
    return [_preset_label(p) for p in files]


def resolve_preset(label: str) -> Path:
    label = (label or "").strip().replace("\\", "/")
    if not label:
        raise FileNotFoundError("empty preset label")
    # hakoniwa/<name> → hakoniwa/testdata/<name>
    if label.startswith("hakoniwa/") and label.count("/") == 1:
        candidate = HAKONIWA_TESTDATA / label.split("/", 1)[1]
        if candidate.is_file():
            return candidate
    direct = REPO_ROOT / label
    if direct.is_file():
        return direct
    bare = HAKONIWA_TESTDATA / Path(label).name
    if bare.is_file():
        return bare
    raise FileNotFoundError(label)


def default_preset_label() -> Optional[str]:
    presets = list_screenshot_presets()
    if DEFAULT_PRESET_LABEL in presets:
        return DEFAULT_PRESET_LABEL
    return presets[0] if presets else None


def load_oblique_projection() -> Dict[str, Any]:
    if not OBLIQUE_JSON.is_file():
        raise FileNotFoundError(display_path(OBLIQUE_JSON))
    data = json.loads(OBLIQUE_JSON.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("oblique_projection.json must be an object")
    return data


def default_workbook() -> Path:
    preferred = ALIGN_TESTDATA / "alignment2_sample.xlsx"
    if preferred.is_file():
        return preferred
    for name in (
        "alignment_sample.xlsx",
        "alignment_batch_design.xlsx",
    ):
        p = ALIGN_TESTDATA / name
        if p.is_file():
            return p
    raise FileNotFoundError("no Alignment(2) sample workbook under testdata/")


def run_alignment2(
    workbook: Union[str, Path, None] = None, *, step: float = 1.0
) -> Dict[str, Any]:
    import alignment2

    path = Path(workbook) if workbook else default_workbook()
    if not path.is_file():
        raise FileNotFoundError(display_path(path))
    result = alignment2.parse_alignment2_workbook(path, step=float(step))
    result = dict(result)
    meta = dict(result.get("meta") or {})
    meta["workbook"] = display_path(path)
    meta["step"] = float(step)
    result["meta"] = meta
    return result


def alignment_plot(result: Dict[str, Any]):
    """Build a matplotlib Figure for the live pane (E/N centreline)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = result.get("points") or []
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    if points:
        e = [p[1] for p in points]
        n = [p[2] for p in points]
        ax.plot(e, n, "-", color="#1f6feb", linewidth=1.6, label="centreline")
        ax.scatter([e[0]], [n[0]], c="#2da44e", s=36, zorder=3, label="start")
        ax.scatter([e[-1]], [n[-1]], c="#cf222e", s=36, zorder=3, label="end")
        ax.set_aspect("equal", adjustable="datalim")
        ax.legend(loc="best", fontsize=8)
    else:
        ax.text(0.5, 0.5, "no points", ha="center", va="center", transform=ax.transAxes)
    meta = result.get("meta") or {}
    ax.set_title(
        f"Alignment(2)  step={meta.get('step', '?')}  n={meta.get('count', 0)}"
    )
    ax.set_xlabel("E")
    ax.set_ylabel("N")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _pil_from_editor(editor_value: Any):
    """Extract a PIL image from Gradio ImageEditor value / path / PIL."""
    from PIL import Image

    if editor_value is None:
        return None
    if isinstance(editor_value, Image.Image):
        return editor_value.convert("RGBA")
    if isinstance(editor_value, (str, Path)):
        p = Path(editor_value)
        if p.is_file():
            return Image.open(p).convert("RGBA")
        return None
    if isinstance(editor_value, dict):
        for key in ("composite", "background", "image"):
            val = editor_value.get(key)
            if val is None:
                continue
            img = _pil_from_editor(val)
            if img is not None:
                return img
        layers = editor_value.get("layers") or []
        for layer in layers:
            img = _pil_from_editor(layer)
            if img is not None:
                return img
    return None


def editor_value_for_path(path: Path) -> Dict[str, Any]:
    """ImageEditor-compatible value from a file path."""
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    return {"background": img, "layers": [], "composite": img.copy()}


def save_composite(
    editor_value: Any,
    *,
    note: str = "",
    stem: Optional[str] = None,
) -> Dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    img = _pil_from_editor(editor_value)
    if img is None:
        # Fall back to default preset so /save and smoke tests still work headless.
        label = default_preset_label()
        if label:
            img = _pil_from_editor(resolve_preset(label))
    if img is None:
        raise ValueError("no image to save (editor empty and no preset)")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = stem or f"markup_{ts}"
    png_path = DATA_DIR / f"{base}.png"
    img.save(png_path)

    meta = {
        "saved_at": ts,
        "image": display_path(png_path),
        "note": (note or "").strip(),
        "size": list(img.size),
    }
    json_path = DATA_DIR / f"{base}.json"
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def save_annotation(
    editor_value: Any = None,
    *,
    note: str = "",
    request: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist markup for agent pickup.

    Writes:
      - Data/dev_console/annotations/<ts>.png (+ .json sidecar)
      - Data/dev_console/latest.png
      - Data/dev_console/latest.json
      - Data/dev_console/request.md
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    img = _pil_from_editor(editor_value)
    if img is None:
        label = default_preset_label()
        if label:
            img = _pil_from_editor(resolve_preset(label))
    if img is None:
        raise ValueError("no image to annotate (editor empty and no preset)")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    note_text = (note or "").strip()
    request_text = (request or note_text or "Sync from Dev Console").strip()

    ann_png = ANNOTATIONS_DIR / f"{ts}.png"
    img.save(ann_png)
    img.save(LATEST_PNG)

    meta: Dict[str, Any] = {
        "saved_at": ts,
        "kind": "sync_packet",
        "note": note_text,
        "request": request_text,
        "image": display_path(LATEST_PNG),
        "annotation": display_path(ann_png),
        "latest_png": display_path(LATEST_PNG),
        "latest_json": display_path(LATEST_JSON),
        "request_md": display_path(REQUEST_MD),
        "size": list(img.size),
    }
    if extra:
        meta["extra"] = extra

    ann_json = ANNOTATIONS_DIR / f"{ts}.json"
    ann_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Dev Console sync request",
        "",
        f"- saved_at: `{ts}`",
        f"- image: `{display_path(LATEST_PNG)}`",
        f"- annotation: `{display_path(ann_png)}`",
    ]
    if note_text:
        md_lines.append(f"- note: {note_text}")
    md_lines.extend(["", "## Request", "", request_text, ""])
    REQUEST_MD.write_text("\n".join(md_lines), encoding="utf-8")
    return meta


def read_sync_request() -> Dict[str, Any]:
    """Read the latest agent pickup packet from Data/dev_console/."""
    packet: Dict[str, Any] = {
        "kind": "sync_packet",
        "latest_png": display_path(LATEST_PNG) if LATEST_PNG.is_file() else None,
        "latest_json": display_path(LATEST_JSON) if LATEST_JSON.is_file() else None,
        "request_md": display_path(REQUEST_MD) if REQUEST_MD.is_file() else None,
        "exists": {
            "png": LATEST_PNG.is_file(),
            "json": LATEST_JSON.is_file(),
            "md": REQUEST_MD.is_file(),
        },
    }
    if LATEST_JSON.is_file():
        try:
            packet["meta"] = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            packet["meta_error"] = str(exc)
    if REQUEST_MD.is_file():
        packet["request"] = REQUEST_MD.read_text(encoding="utf-8")
    return packet


def help_text() -> str:
    return (
        "DesktopPet Dev Console 指令：\n"
        "/help — 說明\n"
        "/align [step] — Alignment(2)（預設 step=1）\n"
        "/hakoniwa | /proj — 箱庭 oblique_projection.json\n"
        "/shots — 列出截圖預設\n"
        "/save [note] — 儲存 ImageEditor 合成圖到 Data/dev_console/\n"
        "Sync to Agent — 寫入 latest.png / latest.json / request.md 供 agent 讀取\n"
        "純中文文字 — 視為校正備註並寫入預覽 JSON"
    )


def live_payload(
    *,
    kind: str,
    data: Optional[Dict[str, Any]] = None,
    plot_result: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    payload: Dict[str, Any] = {}
    if data:
        payload.update(data)
    # Router kind wins over any nested payload keys (e.g. correction_note).
    payload["kind"] = kind
    fig = None
    if plot_result is not None:
        fig = alignment_plot(plot_result)
        # Keep JSON lean: meta + short sample, not full aout.
        payload["alignment_meta"] = plot_result.get("meta")
        pts = plot_result.get("points") or []
        payload["points_sample"] = [
            {"ch": p[0], "e": p[1], "n": p[2], "lv": p[3]} for p in pts[:5]
        ]
        payload["points_count"] = len(pts)
    return fig, payload


class DevBridge:
    """Stateful helper shared by the Gradio UI and smoke_test."""

    def __init__(self) -> None:
        try:
            self.workbook: Path = default_workbook()
        except FileNotFoundError:
            self.workbook = ALIGN_TESTDATA / "alignment2_sample.xlsx"
        self.last_align: Optional[Dict[str, Any]] = None
        self.last_live: Dict[str, Any] = {"kind": "ready"}

    def presets(self) -> List[str]:
        return list_screenshot_presets()

    def default_preset(self) -> Optional[str]:
        return default_preset_label()

    def load_preset_editor(self, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        label = label or self.default_preset()
        if not label:
            return None
        return editor_value_for_path(resolve_preset(label))

    def save_annotation(
        self,
        editor_value: Any = None,
        *,
        note: str = "",
        request: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = save_annotation(
            editor_value, note=note, request=request, extra=extra
        )
        self.last_live = {"kind": "sync_packet", **meta}
        return meta

    def read_sync_request(self) -> Dict[str, Any]:
        return read_sync_request()

    def handle_chat(
        self,
        message: str,
        history: Optional[Sequence[Any]] = None,
        editor_value: Any = None,
        workbook: Union[str, Path, None] = None,
    ) -> ChatResult:
        text = (message or "").strip()
        hist = ensure_messages(history)
        if not text:
            fig, payload = live_payload(kind="idle", data=self.last_live)
            return hist, "", fig, payload

        wb = Path(workbook) if workbook else self.workbook
        if workbook:
            self.workbook = Path(workbook)

        lower = text.lower()
        plot_result = None
        reply: str
        kind: str
        data: Dict[str, Any]

        if lower in ("/help", "help", "?"):
            reply = help_text()
            kind = "help"
            data = {"help": True}
        elif lower.startswith("/align"):
            parts = text.split()
            step = 1.0
            if len(parts) >= 2:
                step = float(parts[1])
            result = run_alignment2(wb, step=step)
            self.last_align = result
            plot_result = result
            meta = result.get("meta") or {}
            reply = (
                f"Alignment(2) OK — workbook={meta.get('workbook')} "
                f"step={meta.get('step')} points={meta.get('count')} "
                f"aout={meta.get('aout_count')}"
            )
            kind = "align"
            data = {"meta": meta}
        elif lower in ("/hakoniwa", "/proj", "/projection"):
            proj = load_oblique_projection()
            reply = (
                f"oblique_projection.json — y_scale={proj.get('y_scale')} "
                f"kind={proj.get('kind')} elevation_deg={proj.get('elevation_deg')}"
            )
            kind = "proj"
            data = {"oblique": proj, "path": display_path(OBLIQUE_JSON)}
        elif lower in ("/shots", "/presets"):
            presets = self.presets()
            default = self.default_preset()
            lines = ["可用截圖預設："] + [f"- {p}" + ("  (default)" if p == default else "") for p in presets]
            reply = "\n".join(lines) if presets else "（無截圖預設）"
            kind = "shots"
            data = {"presets": presets, "default": default}
        elif lower.startswith("/save"):
            note = text[len("/save") :].strip()
            meta = save_composite(editor_value, note=note)
            reply = f"已儲存 {meta['image']}" + (f" — note: {note}" if note else "")
            kind = "save"
            data = meta
        elif text.startswith("/"):
            reply = f"未知指令：{text}\n\n{help_text()}"
            kind = "unknown"
            data = {"command": text}
        elif _CJK_RE.search(text):
            meta = save_composite(editor_value, note=text, stem=None)
            # Also write a dedicated correction note sidecar for markup preview.
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            note_path = DATA_DIR / f"correction_{ts}.json"
            preview = {
                "kind": "correction_note",
                "note": text,
                "saved_at": ts,
                "markup_image": meta.get("image"),
                "markup_meta": meta,
            }
            note_path.write_text(
                json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            reply = f"已記錄校正備註，並儲存標記預覽 → {display_path(note_path)}"
            kind = "correction"
            data = preview
        else:
            reply = (
                "請使用指令（/help）或以中文輸入校正備註。\n\n" + help_text()
            )
            kind = "hint"
            data = {"echo": text}

        fig, payload = live_payload(kind=kind, data=data, plot_result=plot_result)
        self.last_live = payload
        new_hist = append_turn(hist, text, reply)
        return new_hist, "", fig, payload


# Module-level singleton for simple smoke / app wiring.
BRIDGE = DevBridge()
