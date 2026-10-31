"""Smoke checks for Transparent Fish Tank Phase 1 (no GUI required).

Run: python -m fish_tank.smoke_test
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])

    from . import remote_stubs
    from .model import TankState, WORLD_H, WORLD_W
    from .save import load_tank, save_tank
    from .species import FISH_KEYS, PLANT_KEY, SPECIES
    from .sprites import (
        SWIM_H,
        SWIM_W,
        oblique_swim_metrics,
        side_pixmap,
        swim_pixmap,
        warm_cache,
    )
    from . import world as world_sim

    assert len(FISH_KEYS) == 5, FISH_KEYS
    assert PLANT_KEY in SPECIES and SPECIES[PLANT_KEY].is_plant
    # Market alias form for 塘虱.
    assert "（" in SPECIES["catfish"].display_market_zh() or "(" in SPECIES["catfish"].display_market_zh()

    warm_cache()
    for key in FISH_KEYS:
        pix = swim_pixmap(key, False, True)
        assert not pix.isNull() and pix.width() == SWIM_W and pix.height() == SWIM_H
        side = side_pixmap(key, True)
        assert not side.isNull()
        # Side card must differ from swim canvas (side profile vs oblique).
        assert side.width() != SWIM_W or side.height() != SWIM_H

    # Oblique invariant: bilateral mass above+below midline (pectorals), not a
    # thin side-profile strip. Rejects the closed-PR eye-level swim mistake.
    m = oblique_swim_metrics("grouper")
    assert m["opaque"] > 80, m
    assert m["y_span"] >= 16, m
    assert m["upper_band"] >= 8 and m["lower_band"] >= 8, m
    _ = app  # keep app alive for pixmap lifetime

    st = TankState.new_tank()
    assert len(st.active_fish()) >= 5
    st.feed()
    assert st.food_pellets
    st.decorate()
    assert any(d.species_key == PLANT_KEY for d in st.decor)

    target = st.active_fish()[0]
    caught = st.catch_fish(target.id)
    assert caught is not None and caught.owned
    assert st.name_fish(caught.id, "小青")
    assert caught.custom_name == "小青"
    # Scientific name only required on capture card data.
    assert caught.scientific()

    # Away stub path: force leave.
    target2 = next(f for f in st.active_fish() if not f.owned)
    target2.away = True
    target2.away_until = 0
    logs = world_sim.tick(st, 0.05)
    assert isinstance(logs, list)

    # Zoom changes visible range only (helpers).
    z0 = st.visible_size()
    st.zoom = 0.5
    z1 = st.visible_size()
    assert z1[0] > z0[0] and z1[1] > z0[1]

    # Settlement / immediate API stubs are no-ops / local echoes.
    st.flush_settlement_stub()
    echo = remote_stubs.upload_catch_immediate({"id": "x"})
    assert echo.get("local") is True
    assert remote_stubs.trade_immediate({}).get("ok") is False
    assert remote_stubs.gift_immediate({}).get("ok") is False
    assert remote_stubs.drop_to_public_sea_immediate("x").get("ok") is False
    assert remote_stubs.SETTLEMENT_INTERVAL_SEC == 30 * 60

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "tank.json"
        save_tank(st, path)
        loaded = load_tank(path)
        assert loaded is not None
        assert any(f.owned for f in loaded.fish)

    # World bounds sanity.
    assert WORLD_W > 0 and WORLD_H > 0
    print("fish_tank smoke_test: OK (oblique swim invariant passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
