# 箱庭島 (`hakoniwa/`)

Desktop Pet mini-program: local 箱庭斜視 map + simplified island loop.

## 箱庭斜視 (mandatory view)

Official player view is **~45° down-looking oblique with depth foreshortening**,
not a flat top-down square grid rotated 45°.

| | |
|---|---|
| Projection | Logical 1:1 diamond tops → screen `H = W · sin(45°)` (`grid.OBLIQUE_Y_SCALE`) |
| Lattice | v9 diagonal-strip stagger, 20×20, same-layer sea/dirt/grass |
| Terrain | Flat top PNGs in `assets/tiles/` (dirt／grass／sea；森＝草面＋綠洗); ocean backdrop optional |
| Forest | 植林 50→森(100本)；每回合+100本(上限20000)；伐採免費瞬售 100本≈5資金 |
| Harbor | 港灣 800／造船所 500（臨海平地色塊）；有其一可貿易輸出 100噸≈5資金 |
| Forbidden | Orthographic-only / pure `rotate(45°)` (equal diamond W/H on screen) |
| No | Under-tile thickness / skirts |

Constants and helpers live in `grid.py` (`oblique_projection_params()`,
`cell_screen_size()`, `diamond_vertices()`).

## In-map HUD overlays

All numeric / function chrome sits **inside the map viewport** (`HakoniwaMapHud`):

| Overlay | Position | Notes |
|---|---|---|
| Status | Top center | **Single line**; order 狀態→資金→糧食→人口→回合→格數; no connection mode |
| Tile info | Top-left | Below status |
| Action log | Bottom-right | ~70% transparent frame |
| Guestbook | Bottom center | ~70% transparent frame |
| Tools / settings | Bottom-left button → drawer | Build toolbar + server connection |

No permanent right-side build column. Server URL / 本機·連線 live under tools → settings.

## Checklist after any map/view change

1. Open the island map (or render the offscreen preview).
2. Confirm foreshortening: cell diamonds are **wider than tall** (H/W ≈ 0.707).
3. If the map looks like flat diamonds with H/W ≈ 1 (rotated squares), **fix immediately**.
4. Run `python -m hakoniwa.smoke_test` — must pass `test_oblique_foreshortening_invariant`.
5. Keep v9 stagger, 20×20, same-layer tops, no under-tile skirts.
6. Confirm HUD overlays still sit on the map (not outside columns).
7. Confirm dirt／grass／sea cells show real textures (not solid color fills).

CI/local smoke fails if the projection regresses to orthographic-only.
