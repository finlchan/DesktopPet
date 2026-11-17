"""Bridge: screenshots, Alignment(2), annotation sync packets, chat router."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HAKONIWA_TESTDATA = REPO_ROOT / "hakoniwa" / "testdata"
FISH_TANK_SIDE = REPO_ROOT / "fish_tank" / "assets" / "side"
LOGO_PNG = REPO_ROOT / "logo.png"
ALIGN_TESTDATA = REPO_ROOT / "testdata"
SESSION_ROOT = REPO_ROOT / "Data" / "dev_console"
ANNOTATIONS_DIR = SESSION_ROOT / "annotations"
OBLIQUE_JSON = HAKONIWA_TESTDATA / "oblique_projection.json"
DEFAULT_PRESET_LABEL = "hakoniwa/ui_overlay_map_hud.png"

Message = Dict[str, str]
History = List[Message]
ChatResult = Tuple[History, str, Any, Any, Dict[str, Any]]

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
        try:
            return str(path.relative_to(base)).replace("\\", "/")
        except ValueError:
            pass
    except ValueError:
        pass
    return str(path)


def _preset_label(path: Path) -> str:
    path = Path(path)
    try:
        if path.is_relative_to(HAKONIWA_TESTDATA):
            return f"hakoniwa/{path.name}"
    except ValueError:
        pass
    try:
        if path.is_relative_to(FISH_TANK_SIDE):
            return f"fish_tank/side/{path.name}"
    except ValueError:
        pass
    if path.resolve() == LOGO_PNG.resolve():
        return "logo.png"
    try:
        if path.is_relative_to(REPO_ROOT):
            return display_path(path)
    except ValueError:
        pass
    return path.name


def list_screenshot_presets() -> List[str]:
    labels: List[str] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            return
        label = _preset_label(path)
        if label not in seen:
            seen.add(label)
            labels.append(label)

    if HAKONIWA_TESTDATA.is_dir():
        for p in sorted(HAKONIWA_TESTDATA.iterdir()):
            _add(p)
    if FISH_TANK_SIDE.is_dir():
        for p in sorted(FISH_TANK_SIDE.iterdir()):
            _add(p)
    _add(LOGO_PNG)
    return labels


def resolve_preset(label: str) -> Path:
    label = (label or "").strip().replace("\\", "/")
    if not label:
        raise FileNotFoundError("empty preset label")
    if label.startswith("hakoniwa/") and label.count("/") == 1:
        candidate = HAKONIWA_TESTDATA / label.split("/", 1)[1]
        if candidate.is_file():
            return candidate
    if label.startswith("fish_tank/side/"):
        candidate = FISH_TANK_SIDE / Path(label).name
        if candidate.is_file():
            return candidate
    if label in ("logo.png", "logo"):
        if LOGO_PNG.is_file():
            return LOGO_PNG
    direct = REPO_ROOT / label
    if direct.is_file():
        return direct
    bare = HAKONIWA_TESTDATA / Path(label).name
    if bare.is_file():
        return bare
    side = FISH_TANK_SIDE / Path(label).name
    if side.is_file():
        return side
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
    for name in ("alignment_sample.xlsx", "alignment_batch_design.xlsx"):
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


def plot_alignment(result: Dict[str, Any]):
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


# Back-compat alias used by older callers.
alignment_plot = plot_alignment


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


def make_demo_markup(base_image: Any = None):
    """Draw a red frame + crosshair overlay for sample / demo markup."""
    from PIL import Image, ImageDraw

    img = _pil_from_editor(base_image)
    if img is None:
        label = default_preset_label()
        if label:
            img = _pil_from_editor(resolve_preset(label))
    if img is None:
        img = Image.new("RGBA", (640, 360), (40, 44, 52, 255))
    else:
        img = img.copy()

    draw = ImageDraw.Draw(img)
    w, h = img.size
    margin = max(8, min(w, h) // 40)
    # Red frame
    for i in range(3):
        draw.rectangle(
            [margin + i, margin + i, w - 1 - margin - i, h - 1 - margin - i],
            outline=(220, 38, 38, 255),
        )
    # Crosshair at centre
    cx, cy = w // 2, h // 2
    arm = max(16, min(w, h) // 12)
    draw.line([(cx - arm, cy), (cx + arm, cy)], fill=(220, 38, 38, 255), width=2)
    draw.line([(cx, cy - arm), (cx, cy + arm)], fill=(220, 38, 38, 255), width=2)
    r = max(4, arm // 6)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(220, 38, 38, 255), width=2)
    return img


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_request_md(meta: Dict[str, Any]) -> Path:
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Agent sync request",
        "",
        f"- saved_at: `{meta.get('saved_at', '')}`",
        f"- prefix: `{meta.get('prefix', '')}`",
        f"- note: {meta.get('note') or '(none)'}",
        f"- annotation_png: `{meta.get('annotation_png', '')}`",
        f"- annotation_json: `{meta.get('annotation_json', '')}`",
        f"- latest_png: `{meta.get('latest_png', 'Data/dev_console/latest.png')}`",
        f"- latest_json: `{meta.get('latest_json', 'Data/dev_console/latest.json')}`",
        f"- size: `{meta.get('size')}`",
        "",
        "Read `latest.png` + `latest.json` (and this file) from `Data/dev_console/`.",
        "",
    ]
    path = SESSION_ROOT / "request.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_annotation(
    editor_value: Any = None,
    *,
    note: str = "",
    prefix: str = "anno",
) -> Dict[str, Any]:
    """Save annotation PNG/JSON under annotations/ and refresh latest.* + request.md."""
    from PIL import Image

    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    img = _pil_from_editor(editor_value)
    if img is None:
        label = default_preset_label()
        if label:
            img = _pil_from_editor(resolve_preset(label))
    if img is None:
        img = Image.new("RGBA", (64, 48), (30, 144, 255, 255))

    stamp = _utc_stamp()
    safe_prefix = (prefix or "anno").strip().replace(" ", "_") or "anno"
    stem = f"{safe_prefix}_{stamp}"
    anno_png = ANNOTATIONS_DIR / f"{stem}.png"
    anno_json = ANNOTATIONS_DIR / f"{stem}.json"
    latest_png = SESSION_ROOT / "latest.png"
    latest_json = SESSION_ROOT / "latest.json"

    img.save(anno_png)
    img.save(latest_png)

    meta: Dict[str, Any] = {
        "ok": True,
        "saved_at": stamp,
        "prefix": safe_prefix,
        "note": (note or "").strip(),
        "size": list(img.size),
        "annotation_png": display_path(anno_png),
        "annotation_json": display_path(anno_json),
        "latest_png": display_path(latest_png),
        "latest_json": display_path(latest_json),
        "session_root": display_path(SESSION_ROOT),
    }
    payload = json.dumps(meta, ensure_ascii=False, indent=2)
    anno_json.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    request_md = _write_request_md(meta)
    meta["request_md"] = display_path(request_md)
    # Keep latest.json in sync with request_md path.
    latest_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    anno_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def read_sync_request() -> Dict[str, Any]:
    """Return the latest agent-sync packet pointers."""
    latest_png = SESSION_ROOT / "latest.png"
    latest_json = SESSION_ROOT / "latest.json"
    request_md = SESSION_ROOT / "request.md"
    meta: Dict[str, Any] = {}
    if latest_json.is_file():
        try:
            loaded = json.loads(latest_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except json.JSONDecodeError:
            meta = {"error": "latest.json is not valid JSON"}
    md_text = request_md.read_text(encoding="utf-8") if request_md.is_file() else ""
    ok = bool(latest_png.is_file() and latest_json.is_file() and request_md.is_file())
    return {
        "ok": ok,
        "meta": meta,
        "request_md": md_text,
        "latest_png": display_path(latest_png) if latest_png.is_file() else None,
    }


def help_text() -> str:
    return (
        "DesktopPet Dev Console 指令：\n"
        "/help — 說明\n"
        "/align | /align2 [step] — Alignment(2)（預設 step=1）\n"
        "/hakoniwa | /proj — 箱庭 oblique_projection.json\n"
        "/shots — 列出截圖預設\n"
        "/save [note] — 儲存標記並同步 latest.png / request.md\n"
        "一般文字 — 視為校正備註並寫入 sync packet"
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
    payload["kind"] = kind
    fig = None
    if plot_result is not None:
        fig = plot_alignment(plot_result)
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
        self.last_preview = None

    def presets(self) -> List[str]:
        return list_screenshot_presets()

    def default_preset(self) -> Optional[str]:
        return default_preset_label()

    def load_preset_editor(self, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        label = label or self.default_preset()
        if not label:
            return None
        return editor_value_for_path(resolve_preset(label))

    def load_demo_editor(self, label: Optional[str] = None) -> Dict[str, Any]:
        base = None
        try:
            base = self.load_preset_editor(label)
        except FileNotFoundError:
            base = None
        marked = make_demo_markup(base)
        return {"background": marked, "layers": [], "composite": marked.copy()}

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
            preview = self.last_preview
            return hist, "", preview, fig, payload

        wb = Path(workbook) if workbook else self.workbook
        if workbook:
            self.workbook = Path(workbook)

        lower = text.lower()
        plot_result = None
        preview = self.last_preview
        reply: str
        kind: str
        data: Dict[str, Any]

        if lower in ("/help", "help", "?"):
            reply = help_text()
            kind = "help"
            data = {"help": True}
        elif lower.startswith("/align2") or lower.startswith("/align"):
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
            lines = ["可用截圖預設："] + [
                f"- {p}" + ("  (default)" if p == default else "") for p in presets
            ]
            reply = "\n".join(lines) if presets else "（無截圖預設）"
            kind = "shots"
            data = {"presets": presets, "default": default}
        elif lower.startswith("/save"):
            note = text[len("/save") :].strip()
            meta = save_annotation(editor_value, note=note, prefix="save")
            preview = _pil_from_editor(editor_value) or self.last_preview
            if latest := SESSION_ROOT / "latest.png":
                if latest.is_file():
                    from PIL import Image

                    preview = Image.open(latest).convert("RGBA")
            reply = f"已同步給 Agent → {meta['latest_png']}" + (
                f" — note: {note}" if note else ""
            )
            kind = "save"
            data = meta
        elif text.startswith("/"):
            reply = f"未知指令：{text}\n\n{help_text()}"
            kind = "unknown"
            data = {"command": text}
        else:
            # Bare text = correction note + save sync packet.
            meta = save_annotation(editor_value, note=text, prefix="note")
            if (SESSION_ROOT / "latest.png").is_file():
                from PIL import Image

                preview = Image.open(SESSION_ROOT / "latest.png").convert("RGBA")
            reply = (
                f"已記錄校正備註並同步 sync packet → {meta.get('latest_png')} "
                f"(request.md / latest.json)"
            )
            kind = "note"
            data = meta

        fig, payload = live_payload(kind=kind, data=data, plot_result=plot_result)
        self.last_live = payload
        if preview is not None:
            self.last_preview = preview
        new_hist = append_turn(hist, text, reply)
        return new_hist, "", preview, fig, payload


# Module-level singleton for simple smoke / app wiring.
BRIDGE = DevBridge()
