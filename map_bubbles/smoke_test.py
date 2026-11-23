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
    a = make_bubble(x=10, y=20, r=64, topic="A", path="/tmp/a")
    b = make_bubble(x=100, y=40, r=40, topic="B", url="https://example.com")
    save_map(cfg, [a, b], [{"a": a["id"], "b": b["id"]}])
    bubbles, edges = load_map(cfg)
    assert len(bubbles) == 2
    assert len(edges) == 1
    assert edges[0]["a"] < edges[0]["b"] or edges[0]["a"] != edges[0]["b"]
    by_id = {b["id"]: b for b in bubbles}
    assert by_id[a["id"]]["r"] == 64.0
    assert by_id[b["id"]]["r"] == 40.0


def test_blank_packaging_template() -> None:
    path = ROOT / "packaging" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "map_bubbles" in data
    assert data["map_bubbles"]["bubbles"] == []
    assert data["map_bubbles"]["edges"] == []
    # Blank template stays empty — no sample size / personal paths.
    assert list(data["map_bubbles"].keys()) == ["bubbles", "edges"]


def test_scene_qt() -> None:
    import math

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import MapScene

    scene = MapScene()
    a = scene.add_bubble_from_dict(make_bubble(x=0, y=0, r=50, topic="Hub"))
    b = scene.add_bubble_from_dict(make_bubble(x=200, y=0, r=40, topic="Leaf"))
    edge = scene.add_edge_between(a, b)
    assert edge is not None
    assert len(scene.bubbles()) == 2
    assert len(scene.edges()) == 1
    # Edges stop at the outer rim, not centers
    line = edge.line()
    assert abs(line.x1() - 50.0) < 0.05, line
    assert abs(line.y1() - 0.0) < 0.05
    assert abs(line.x2() - 160.0) < 0.05, line  # 200 - 40
    assert abs(line.y2() - 0.0) < 0.05

    a.setPos(30, 10)
    edge.refresh()
    line = edge.line()
    c1x, c1y = 30.0, 10.0
    c2x, c2y = 200.0, 0.0
    dx, dy = c2x - c1x, c2y - c1y
    dist = math.hypot(dx, dy)
    ux, uy = dx / dist, dy / dist
    expect_x1 = c1x + ux * a.radius
    expect_y1 = c1y + uy * a.radius
    assert abs(line.x1() - expect_x1) < 0.05
    assert abs(line.y1() - expect_y1) < 0.05

    # Per-bubble size update refreshes rim endpoints
    a.set_radius(70)
    assert a.radius == 70.0
    edge.refresh()
    line = edge.line()
    dist = math.hypot(c2x - c1x, c2y - c1y)
    ux, uy = (c2x - c1x) / dist, (c2y - c1y) / dist
    assert abs(line.x1() - (c1x + ux * 70)) < 0.05

    scene.remove_bubble(a)
    assert len(scene.bubbles()) == 1
    assert len(scene.edges()) == 0
    del app


def test_edit_dialog_size_field() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.dialog import BubbleEditDialog
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import BubbleItem

    data = make_bubble(x=0, y=0, r=48, topic="Sized")
    item = BubbleItem(
        data["id"],
        topic=data["topic"],
        path=data["path"],
        url=data["url"],
        radius=data["r"],
    )
    dlg = BubbleEditDialog(item)
    assert abs(dlg.size_spin.value() - 48.0) < 0.01
    dlg.size_spin.setValue(80)
    topic, path, url, radius = dlg.values()
    assert topic == "Sized"
    assert radius == 80.0
    dlg.close()
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
    test_edit_dialog_size_field()
    test_water_ripple()
    print("map_bubbles smoke_test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
