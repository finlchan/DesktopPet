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

DEFAULT_TEXT = "休息中..."
DEFAULT_COLOR_KEY = "steel"
DEFAULT_WIDTH = 440
DEFAULT_HEIGHT = 200

# Packaging / DEFAULT_CONFIG shape: empty dual-band fields only (no personal text).
BLANK_STATUS_MARQUEE = {
    "text1": "",
    "text2": "",
    "color_key": "",
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


def _as_text(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value or "")
    return value.strip()


def normalize_settings(raw: Any) -> Dict[str, Any]:
    """Normalize config; migrate legacy single ``text`` → ``text1``/``text2``.

    Prefer dual fields when either ``text1`` or ``text2`` is present.
    If only legacy ``text`` exists, copy it onto both bands.
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

    def _opt_int(key: str):
        val = raw.get(key)
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _opt_size(key: str, default: int, lo: int, hi: int):
        val = _opt_int(key)
        if val is None:
            return None
        return max(lo, min(hi, val))

    return {
        "text1": text1,
        "text2": text2,
        "color_key": color_key,
        "pos_x": _opt_int("pos_x"),
        "pos_y": _opt_int("pos_y"),
        "width": _opt_size("width", DEFAULT_WIDTH, 280, 900),
        "height": _opt_size("height", DEFAULT_HEIGHT, 140, 500),
    }


def effective_text(settings: Dict[str, Any], band: int = 1) -> str:
    """Display text for band 1 or 2; blank → default placeholder."""
    key = "text1" if band != 2 else "text2"
    text = (settings.get(key) or "").strip()
    return text or DEFAULT_TEXT


def effective_color_key(settings: Dict[str, Any]) -> str:
    return normalize_color_key(settings.get("color_key") or DEFAULT_COLOR_KEY)


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
