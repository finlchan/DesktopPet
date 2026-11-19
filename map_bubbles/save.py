"""Blank-safe MAP persistence helpers (config.json key ``map_bubbles``)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Tuple


BLANK_MAP = {
    "bubbles": [],
    "edges": [],
}


def blank_map_config() -> Dict[str, Any]:
    """Return a shippable empty map (no personal paths/URLs)."""
    return {
        "bubbles": [],
        "edges": [],
    }


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_bubble(raw: Any) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    bid = raw.get("id")
    if not isinstance(bid, str) or not bid.strip():
        bid = _new_id()
    else:
        bid = bid.strip()

    def _str(key: str) -> str:
        val = raw.get(key, "")
        if not isinstance(val, str):
            val = str(val or "")
        return val.strip()

    try:
        x = float(raw.get("x", 0))
        y = float(raw.get("y", 0))
    except (TypeError, ValueError):
        x, y = 0.0, 0.0
    try:
        r = float(raw.get("r", 52))
    except (TypeError, ValueError):
        r = 52.0
    r = max(36.0, min(r, 120.0))

    topic = _str("topic")
    path = _str("path")
    url = _str("url")
    # Keep empty bubbles so the user can fill them in; do not drop on load.
    return {
        "id": bid,
        "x": x,
        "y": y,
        "r": r,
        "topic": topic,
        "path": path,
        "url": url,
    }


def normalize_edge(raw: Any, known_ids: set[str]) -> Dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    a = raw.get("a")
    b = raw.get("b")
    if not isinstance(a, str) or not isinstance(b, str):
        return None
    a, b = a.strip(), b.strip()
    if not a or not b or a == b:
        return None
    if a not in known_ids or b not in known_ids:
        return None
    # Canonical undirected key
    if a > b:
        a, b = b, a
    return {"a": a, "b": b}


def load_map(cfg) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Read bubbles + edges from ConfigManager (or dict-like)."""
    raw = None
    if hasattr(cfg, "get"):
        raw = cfg.get("map_bubbles")
    elif isinstance(cfg, dict):
        raw = cfg.get("map_bubbles")
    if not isinstance(raw, dict):
        raw = {}

    bubbles: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw.get("bubbles") or []:
        b = normalize_bubble(item)
        if b is None or b["id"] in seen:
            continue
        seen.add(b["id"])
        bubbles.append(b)

    edges: List[Dict[str, str]] = []
    edge_keys: set[Tuple[str, str]] = set()
    for item in raw.get("edges") or []:
        e = normalize_edge(item, seen)
        if e is None:
            continue
        key = (e["a"], e["b"])
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append(e)
    return bubbles, edges


def save_map(cfg, bubbles: List[Dict[str, Any]], edges: List[Dict[str, str]]) -> None:
    """Write map into config under map_bubbles (blank-safe shape)."""
    payload = {
        "bubbles": [normalize_bubble(b) for b in bubbles if normalize_bubble(b)],
        "edges": [],
    }
    known = {b["id"] for b in payload["bubbles"]}
    edge_keys: set[Tuple[str, str]] = set()
    cleaned_edges: List[Dict[str, str]] = []
    for item in edges:
        e = normalize_edge(item, known)
        if e is None:
            continue
        key = (e["a"], e["b"])
        if key in edge_keys:
            continue
        edge_keys.add(key)
        cleaned_edges.append(e)
    payload["edges"] = cleaned_edges

    if hasattr(cfg, "set"):
        cfg.set(["map_bubbles"], payload, save=True)
    elif isinstance(cfg, dict):
        cfg["map_bubbles"] = payload


def make_bubble(
    *,
    x: float = 0.0,
    y: float = 0.0,
    r: float = 52.0,
    topic: str = "",
    path: str = "",
    url: str = "",
    bubble_id: str | None = None,
) -> Dict[str, Any]:
    return {
        "id": bubble_id or _new_id(),
        "x": float(x),
        "y": float(y),
        "r": float(r),
        "topic": (topic or "").strip(),
        "path": (path or "").strip(),
        "url": (url or "").strip(),
    }
