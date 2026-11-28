"""Blank-safe status marquee persistence (config.json key ``status_marquee``)."""

from __future__ import annotations

from typing import Any, Dict

# Theme-locked color presets (steel-blue / gold — match DesktopPet tokens).
COLOR_PRESETS: Dict[str, Dict[str, str]] = {
    "steel": {
        "label": "Steel blue／鋼藍",
        "band_a": "#3d5a80",
        "band_b": "#2a4a6e",
        "text": "#e8f2f8",
    },
    "gold": {
        "label": "Gold／金",
        "band_a": "#c9a84c",
        "band_b": "#7a5e18",
        "text": "#1e2832",
    },
    "slate": {
        "label": "Slate／石板",
        "band_a": "#283a4e",
        "band_b": "#1c2837",
        "text": "#f5e6c8",
    },
}

# Display modes: single-monitor fill vs bands spanning the virtual desktop.
DISPLAY_MODE_SINGLE = "single"
DISPLAY_MODE_DUAL_SPAN = "dual_span"
DISPLAY_MODE_LABELS: Dict[str, str] = {
    DISPLAY_MODE_SINGLE: "單一全視窗化／Single fullscreen",
    DISPLAY_MODE_DUAL_SPAN: "雙顯視屏貫穿／Span dual monitors",
}
DEFAULT_DISPLAY_MODE = DISPLAY_MODE_SINGLE

DEFAULT_TEXT = "休息中..."
DEFAULT_COLOR_KEY = "steel"
DEFAULT_WIDTH = 440
DEFAULT_HEIGHT = 200

# Scroll speed 1..10 → cycle duration (ms). 5 ≈ previous ~8s playful cycle.
DEFAULT_SCROLL_SPEED = 5
MIN_SCROLL_SPEED = 1
MAX_SCROLL_SPEED = 10
# Band thickness in px.
DEFAULT_BAND_SIZE = 56
MIN_BAND_SIZE = 28
MAX_BAND_SIZE = 120

# Packaging / DEFAULT_CONFIG shape: empty dual-band fields only (no personal text).
BLANK_STATUS_MARQUEE = {
    "text1": "",
    "text2": "",
    "color_key": "",
    "display_mode": "",
    "scroll_speed": None,
    "band_size": None,
    "pos_x": None,
    "pos_y": None,
    "width": None,
    "height": None,
}


def blank_status_marquee_config() -> Dict[str, Any]:
    """Shippable empty fields only (no personal status text)."""
    return dict(BLANK_STATUS_MARQUEE)


def normalize_color_key(raw: Any) -> str:
    key = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if key in COLOR_PRESETS:
        return key
    return DEFAULT_COLOR_KEY


def normalize_display_mode(raw: Any) -> str:
    key = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if key in (DISPLAY_MODE_SINGLE, DISPLAY_MODE_DUAL_SPAN):
        return key
    return DEFAULT_DISPLAY_MODE


def _as_text(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value or "")
    return value.strip()


def _opt_int(raw: Any):
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    n = _opt_int(value)
    if n is None:
        return default
    return max(lo, min(hi, n))


def cycle_ms_for_speed(speed: Any) -> int:
    """Map scroll_speed 1..10 to one full text-cycle duration in ms.

    Speed 1 ≈ 16s (slow); 5 ≈ 8s (default); 10 ≈ 3.2s (fast).
    """
    s = _clamp_int(speed, MIN_SCROLL_SPEED, MAX_SCROLL_SPEED, DEFAULT_SCROLL_SPEED)
    # Linear map: ms = 18000 - 2000 * s  → 1→16000, 5→8000, 10→2000 (floor).
    return max(2000, 18000 - 2000 * s)


def normalize_settings(raw: Any) -> Dict[str, Any]:
    """Normalize config; migrate legacy single ``text`` → ``text1``/``text2``.

    Prefer dual fields when either ``text1`` or ``text2`` is present.
    If only legacy ``text`` exists, copy it onto both bands.
    Blank ``display_mode`` / ``scroll_speed`` / ``band_size`` stay empty in
    the saved payload sense for packaging, but load_settings callers get
    effective defaults via helpers.
    """
    if not isinstance(raw, dict):
        raw = {}

    legacy = _as_text(raw.get("text", ""))
    has_text1 = "text1" in raw
    has_text2 = "text2" in raw

    if has_text1 or has_text2:
        text1 = _as_text(raw.get("text1", "")) if has_text1 else legacy
        text2 = _as_text(raw.get("text2", "")) if has_text2 else legacy
    else:
        # Pure legacy single-string config (v261128.03): both bands get it.
        text1 = legacy
        text2 = legacy

    color_key_raw = raw.get("color_key", "")
    if isinstance(color_key_raw, str) and color_key_raw.strip():
        color_key = normalize_color_key(color_key_raw)
    else:
        color_key = ""

    display_raw = raw.get("display_mode", "")
    if isinstance(display_raw, str) and display_raw.strip():
        display_mode = normalize_display_mode(display_raw)
    else:
        display_mode = ""

    # Persist None when blank/unset so packaging stays empty-safe.
    scroll_raw = raw.get("scroll_speed", None)
    if scroll_raw is None or scroll_raw == "":
        scroll_speed = None
    else:
        scroll_speed = _clamp_int(
            scroll_raw, MIN_SCROLL_SPEED, MAX_SCROLL_SPEED, DEFAULT_SCROLL_SPEED
        )

    band_raw = raw.get("band_size", None)
    if band_raw is None or band_raw == "":
        band_size = None
    else:
        band_size = _clamp_int(
            band_raw, MIN_BAND_SIZE, MAX_BAND_SIZE, DEFAULT_BAND_SIZE
        )

    def _opt_size(key: str, lo: int, hi: int):
        val = _opt_int(raw.get(key))
        if val is None:
            return None
        return max(lo, min(hi, val))

    return {
        "text1": text1,
        "text2": text2,
        "color_key": color_key,
        "display_mode": display_mode,
        "scroll_speed": scroll_speed,
        "band_size": band_size,
        "pos_x": _opt_int(raw.get("pos_x")),
        "pos_y": _opt_int(raw.get("pos_y")),
        "width": _opt_size("width", 280, 900),
        "height": _opt_size("height", 140, 500),
    }


def effective_text(settings: Dict[str, Any], band: int = 1) -> str:
    """Display text for band 1 or 2; blank → default placeholder."""
    key = "text1" if band != 2 else "text2"
    text = (settings.get(key) or "").strip()
    return text or DEFAULT_TEXT


def effective_color_key(settings: Dict[str, Any]) -> str:
    return normalize_color_key(settings.get("color_key") or DEFAULT_COLOR_KEY)


def effective_display_mode(settings: Dict[str, Any]) -> str:
    return normalize_display_mode(settings.get("display_mode") or DEFAULT_DISPLAY_MODE)


def effective_scroll_speed(settings: Dict[str, Any]) -> int:
    return _clamp_int(
        settings.get("scroll_speed"),
        MIN_SCROLL_SPEED,
        MAX_SCROLL_SPEED,
        DEFAULT_SCROLL_SPEED,
    )


def effective_band_size(settings: Dict[str, Any]) -> int:
    return _clamp_int(
        settings.get("band_size"),
        MIN_BAND_SIZE,
        MAX_BAND_SIZE,
        DEFAULT_BAND_SIZE,
    )


def load_settings(cfg) -> Dict[str, Any]:
    raw = None
    if hasattr(cfg, "get"):
        raw = cfg.get("status_marquee")
    elif isinstance(cfg, dict):
        raw = cfg.get("status_marquee")
    return normalize_settings(raw)


def save_settings(cfg, settings: Dict[str, Any]) -> None:
    payload = normalize_settings(settings)
    if hasattr(cfg, "set"):
        cfg.set(["status_marquee"], payload, save=True)
    elif isinstance(cfg, dict):
        cfg["status_marquee"] = payload
