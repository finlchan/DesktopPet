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
        MAX_SIM_H,
        MAX_SIM_W,
        SEA_DISPLAY_DIVISOR,
        SEA_SURFACE_OPACITY,
        WaterRippleSim,
        apply_edge_fade,
        cover_fit_rect,
        load_sea_surface,
        paint_cover_sea,
        sea_paint_size,
    )
    from PySide6.QtGui import QImage
    import time

    sea = load_sea_surface()
    assert sea is not None and not sea.isNull(), "map_bubbles/assets/sea-surface.jpg must ship"
    # Original bundled photo stays high-res on disk (display buffer is lowered).
    assert sea.width() >= 1280 and sea.height() >= 720, (sea.width(), sea.height())
    assert abs(SEA_SURFACE_OPACITY - 0.80) < 1e-9
    assert SEA_DISPLAY_DIVISOR == 2
    paint_w, paint_h = sea_paint_size(1920, 1080, sea.width(), sea.height())
    assert paint_w <= sea.width() // 2 and paint_h <= sea.height() // 2, (paint_w, paint_h)
    assert paint_w < 1920 and paint_h < 1080
    # Default MAP window (760×560) is taller than half the photo, so it drops too.
    def_w, def_h = sea_paint_size(760, 560, sea.width(), sea.height())
    assert def_h <= sea.height() // 2 and def_w * def_h < 760 * 560, (def_w, def_h)

    # Cover-fit (not IgnoreAspectRatio stretch) for a wide viewport.
    scale, ox, oy, _ = cover_fit_rect(sea.width(), sea.height(), 800, 400)
    assert scale == max(800 / sea.width(), 400 / sea.height())
    assert ox >= 0 and oy >= 0

    sim = WaterRippleSim()
    bw, bh = sim.ensure_size(400, 300)
    assert bw >= 8 and bh >= 8
    # Quiet frame is the cover-fit sea at the viewport (lowered when the window exceeds half the photo).
    quiet = sim.render_upscaled(400, 300)
    assert not quiet.isNull()
    assert quiet.width() == 400 and quiet.height() == 300

    sim.disturb(bw / 2, bh / 2, radius=3, strength=200)
    assert sim.active
    sim.step()
    frame = sim.render_upscaled(400, 300)
    assert not frame.isNull()
    assert frame.width() == 400 and frame.height() == 300
    # Calm corner stays the unshifted sea; refraction only slides cells that have a gradient.
    assert quiet.pixel(6, 6) == frame.pixel(6, 6)

    # A large window must still simulate on the small buffer, not the viewport.
    big = WaterRippleSim()
    bw_big, bh_big = big.ensure_size(1920, 1080)
    assert bw_big <= MAX_SIM_W and bh_big <= MAX_SIM_H, (bw_big, bh_big)
    assert bw_big * bh_big <= MAX_SIM_W * MAX_SIM_H
    quiet_big = big.render_upscaled(1920, 1080)
    assert quiet_big.width() == 1920 and quiet_big.height() == 1080
    big.disturb(bw_big / 2, bh_big / 2, radius=4, strength=420)
    assert big.active
    big.step()
    t0 = time.perf_counter()
    active_big = big.render_upscaled(1920, 1080)
    refract_s = time.perf_counter() - t0
    # The old full-window / 640-class Python warp was ~200ms+. Block blits stay well under.
    assert refract_s < 0.15, refract_s
    assert active_big.width() == 1920 and active_big.height() == 1080
    assert quiet_big.pixel(16, 16) == active_big.pixel(16, 16)
    cx, cy = 960, 540
    changed = any(
        quiet_big.pixel(cx + dx, cy + dy) != active_big.pixel(cx + dx, cy + dy)
        for dy in range(-48, 49, 8)
        for dx in range(-48, 49, 8)
    )
    assert changed, "center splash should refract a visible ripple in the sea"

    # Edge fade helper is safe on a blank buffer.
    blank = QImage(64, 48, QImage.Format.Format_RGB32)
    paint_cover_sea(blank, sea)
    apply_edge_fade(blank)
    assert not blank.isNull()

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


def test_disconnect_clears_links() -> None:
    """Disconnect removes edges of the selected bubble; bubble stays."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from map_bubbles.save import make_bubble
    from map_bubbles.scene import MapScene

    scene = MapScene()
    a = scene.add_bubble_from_dict(make_bubble(x=0, y=0, topic="A"))
    b = scene.add_bubble_from_dict(make_bubble(x=120, y=0, topic="B"))
    c = scene.add_bubble_from_dict(make_bubble(x=60, y=80, topic="C"))
    scene.add_edge_between(a, b)
    scene.add_edge_between(a, c)
    assert len(scene.edges()) == 2
    n = scene.disconnect_bubble(a)
    assert n == 2
    assert len(scene.edges()) == 0
    assert len(scene.bubbles()) == 3
    assert a in scene.bubbles() or a.bubble_id in {x.bubble_id for x in scene.bubbles()}
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
    # Toolbar is to the RIGHT of the MAP title (same horizontal row).
    from PySide6.QtWidgets import QLabel

    title = dlg._top.findChild(QLabel, "mapTitle")
    assert title is not None
    assert dlg.btn_add.y() == title.y() or abs(dlg.btn_add.y() - title.y()) <= 6
    assert dlg.btn_add.x() > title.x() + title.width() - 2
    dlg.hide()
    # Open path/URL toolbar button removed — double-click / Enter open instead.
    assert not hasattr(dlg, "btn_activate")
    assert dlg.btn_edit is not None
    assert dlg.btn_delete is not None
    assert dlg.btn_disconnect is not None
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
    test_disconnect_clears_links()
    test_rename_refreshes_label()
    test_fill_opacity_and_pan_chrome()
    test_double_click_requests_activate()
    print("map_bubbles smoke_test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
