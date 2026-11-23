"""Headless smoke test for MAP bubbles (no GUI show required for save/normalize)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Allow running from repo root: python -m map_bubbles.smoke_test
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_save_roundtrip() -> None:
    from map_bubbles.save import load_map, make_bubble, save_map

    cfg = {"map_bubbles": {"bubbles": [], "edges": []}}
    a = make_bubble(x=10, y=20, topic="A", path="/tmp/a")
    b = make_bubble(x=100, y=40, topic="B", url="https://example.com")
    save_map(cfg, [a, b], [{"a": a["id"], "b": b["id"]}])
    bubbles, edges = load_map(cfg)
    assert len(bubbles) == 2
    assert len(edges) == 1
    assert edges[0]["a"] < edges[0]["b"] or edges[0]["a"] != edges[0]["b"]


def test_blank_packaging_template() -> None:
    path = ROOT / "packaging" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "map_bubbles" in data
    assert data["map_bubbles"]["bubbles"] == []
    assert data["map_bubbles"]["edges"] == []


def test_scene_qt() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import MapScene

    scene = MapScene()
    a = scene.add_bubble_from_dict(make_bubble(x=0, y=0, topic="Hub"))
    b = scene.add_bubble_from_dict(make_bubble(x=120, y=40, topic="Leaf"))
    edge = scene.add_edge_between(a, b)
    assert edge is not None
    assert len(scene.bubbles()) == 2
    assert len(scene.edges()) == 1
    a.setPos(30, 10)
    # Edge should track
    line = edge.line()
    assert abs(line.x1() - 30) < 0.01
    scene.remove_bubble(a)
    assert len(scene.bubbles()) == 1
    assert len(scene.edges()) == 0
    del app


def test_water_ripple() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import MapScene, MapView
    from map_bubbles.water_ripple import WaterRippleSim, load_sea_surface

    sea = load_sea_surface()
    assert sea is not None and not sea.isNull(), "map_bubbles/assets/sea-surface.png must ship"

    sim = WaterRippleSim()
    bw, bh = sim.ensure_size(400, 300)
    assert bw >= 8 and bh >= 8
    sim.disturb(bw / 2, bh / 2, radius=3, strength=200)
    assert sim.active
    sim.step()
    frame = sim.render_upscaled(400, 300)
    assert not frame.isNull()
    assert frame.width() == 400 and frame.height() == 300

    scene = MapScene()
    view = MapView(scene)
    view.resize(400, 300)
    view.show()
    bubble = scene.add_bubble_from_dict(make_bubble(x=0, y=0, topic="Ripple"))
    # Labels stay visible on the live item (not stamped into the refracted sea).
    assert bubble._label.opacity() > 0.5
    view._splash_at_view(80, 90, 4.0, 300.0)
    view._on_ripple_tick()
    assert view._cached_frame is not None and not view._cached_frame.isNull()
    view.hide()
    del app


def main() -> int:
    test_blank_packaging_template()
    test_save_roundtrip()
    test_scene_qt()
    test_water_ripple()
    print("map_bubbles smoke_test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
