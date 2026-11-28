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
    from map_bubbles.water_ripple import (
        SEA_SURFACE_OPACITY,
        WaterRippleSim,
        load_sea_surface,
    )

    sea = load_sea_surface()
    assert sea is not None and not sea.isNull(), "map_bubbles/assets/sea-surface.jpg must ship"
    assert abs(SEA_SURFACE_OPACITY - 0.60) < 1e-9

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


def test_rename_refreshes_label() -> None:
    """Topic rename must update on-bubble text even when radius is unchanged."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import BubbleItem

    data = make_bubble(x=0, y=0, r=52, topic="BUBBLE2")
    item = BubbleItem(
        data["id"],
        topic=data["topic"],
        path=data["path"],
        url=data["url"],
        radius=data["r"],
    )
    assert item._label.text() == "BUBBLE2"
    # Same radius as before — the old set_radius early-return skipped the label.
    item.set_fields("Renamed topic", "", "https://example.com", radius=52.0)
    assert item.topic == "Renamed topic"
    assert item._label.text() == "Renamed topic"
    assert item.to_dict()["topic"] == "Renamed topic"
    del app


def test_fill_opacity_and_pan_chrome() -> None:
    """Bubble fill ~60%; text full opacity; no scrollbars; MAP gold shell."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.dialog import MapDialog, MapGoldShell
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import (
        BUBBLE_FILL,
        BUBBLE_FILL_ALPHA,
        BUBBLE_TEXT,
        MapScene,
        MapView,
    )

    assert BUBBLE_FILL_ALPHA == int(round(255 * 0.60))
    assert BUBBLE_FILL.alpha() == BUBBLE_FILL_ALPHA
    assert BUBBLE_TEXT.alpha() == 255

    scene = MapScene()
    view = MapView(scene)
    assert (
        view.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert (
        view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    bubble = scene.add_bubble_from_dict(make_bubble(x=0, y=0, topic="Alpha"))
    assert bubble._label.opacity() == 1.0
    assert bubble._fill_color().alpha() == BUBBLE_FILL_ALPHA

    cfg = {"map_bubbles": {"bubbles": [], "edges": []}}
    dlg = MapDialog(cfg)
    assert isinstance(dlg._gold, MapGoldShell)
    assert dlg.view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # Title + toolbar live as overlays on the sea body (same gold frame).
    assert dlg._top.parent() is dlg._body
    assert dlg.view.parent() is dlg._body
    assert dlg._gold._grip_tl is not None
    assert dlg._gold._grip_br is not None
    assert dlg._gold._move_grip is not None
    from map_bubbles.dialog import MAP_MOVE_ICON_NAME, _load_window_move_pixmap
    from map_bubbles.water_ripple import _assets_root

    icon_path = _assets_root() / MAP_MOVE_ICON_NAME
    assert icon_path.is_file(), f"missing MAP move icon: {icon_path}"
    pix = _load_window_move_pixmap(20)
    assert not pix.isNull()
    assert not dlg._gold._move_grip.icon().isNull()
    dlg.resize(700, 500)
    dlg.show()
    app.processEvents()
    # Top-right placement inside the gold frame.
    mg = dlg._gold._move_grip
    assert mg.x() > dlg._gold.width() // 2
    assert mg.y() < 40
    dlg.hide()
    # Open path/URL toolbar button removed — double-click / Enter open instead.
    assert not hasattr(dlg, "btn_activate")
    assert dlg.btn_edit is not None
    assert dlg.btn_delete is not None
    dlg.close()
    del app


def test_double_click_requests_activate() -> None:
    """Left double-click on a bubble emits request_activate (open path/URL)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import MapScene

    scene = MapScene()
    bubble = scene.add_bubble_from_dict(
        make_bubble(x=0, y=0, topic="ClickMe", url="https://example.com")
    )
    activated: list = []
    edited: list = []
    scene.request_activate.connect(lambda b: activated.append(b))
    scene.request_edit.connect(lambda b: edited.append(b))

    class _FakeDbl:
        def scenePos(self):
            return QPointF(0, 0)

        def button(self):
            return Qt.MouseButton.LeftButton

        def accept(self):
            return None

    scene.mouseDoubleClickEvent(_FakeDbl())
    assert activated == [bubble], activated
    assert edited == []
    del app


def main() -> int:
    test_blank_packaging_template()
    test_save_roundtrip()
    test_scene_qt()
    test_edit_dialog_size_field()
    test_water_ripple()
    test_rename_refreshes_label()
    test_fill_opacity_and_pan_chrome()
    test_double_click_requests_activate()
    print("map_bubbles smoke_test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
