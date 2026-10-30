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
| User art | Optional PNGs in `Data/hakoniwa/user/` or `assets/user/` replace building／monster color blocks and optionally terrain (see below); missing → color blocks / bundled tops |
| Forest | 植林 50→森(100本)；每回合+100本(上限20000)；伐採免費瞬售 100本≈5資金 |
| Mountain | 造山 100／噴火→山；整地山→荒地；採掘場 300（僅山上色塊）產資 |
| Labor | 回合勞動：農場優先，再工場、採掘場；產能依就業比例 |
| Harbor | 港灣 800／造船所 500（臨海平地色塊）；有其一可貿易輸出 100噸≈5資金 |
| Breakwater | 防波堤 200（臨海平地色塊）；鄰格減海嘯；自身不被海嘯摧毀 |
| Oilfield | 掘削 200：陸→淺灘／淺灘→海／海→探油；油田被動產資；機率枯竭→海 |
| Monument | 紀念碑 9999（平地色塊）；加島分數／安穩；抗怪獸踩踏；鄰格抑火災如森 |
| Bank | 銀行 500（平地色塊）；流動資金上限 9999；溢出進存款緩衝；可手動存提 |
| Supermarket | 超市 300（平地色塊）；資金買糧 100噸≈8資金（略貴於貿易輸出） |
| Shrine | 神社 800（平地色塊）；大幅加島分數；餵飽時安穩人口加成 |
| Park | 公園 250（平地色塊）；島分數／安穩；鄰格提高生村機率 |
| Airport | 空港 1500（平地色塊；目錄費用原 `?`，本機採箱庭2啟發估算）；島分數／觀光收入／留言小費／誘致加成 |
| Rocket | ロケット基地 2000（平地色塊；目錄／變體常 `?`，近究想衛星建設 2000）；發射觀測衛星 800（Ex 啟發；需基地；減震／海嘯／噴火） |
| Hotel | 酒店 600（平地色塊；目錄民宿／度假村費用 `?` → 介於公園與神社）；島分數／住宿觀光收入／留言小費 |
| Casino | 賭場 1100（平地色塊；目錄賭場／遊樂園費用 `?` → 介於神社與空港）；島分數／娛樂觀光收入（依人口加碼） |
| Attract | 誘致活動 1000（定本；不耗回合）；下回合餵飽時額外人口；有空港再加 inbound |
| Forbidden | Orthographic-only / pure `rotate(45°)` (equal diamond W/H on screen) |
| No | Under-tile thickness / skirts |

Constants and helpers live in `grid.py` (`oblique_projection_params()`,
`cell_screen_size()`, `diamond_vertices()`).

## In-map HUD overlays

All numeric / function chrome sits **inside the map viewport** (`HakoniwaMapHud`):

| Overlay | Position | Notes |
|---|---|---|
| Status | Top center | **Single line**; order 狀態→資金→糧食→人口→回合→格數→分數; no connection mode |
| Tile info | Top-left | Below status |
| Action log | Bottom-right | ~70% transparent frame |
| Guestbook | Bottom center | ~70% transparent frame |
| Tools / settings | Bottom-left button → drawer | Build toolbar + server connection |

No permanent right-side build column. Server URL / 本機·連線 live under tools → settings.

## User-provided art (optional)

Buildings／monsters ship as **color blocks** until you drop PNGs. Sea／dirt／grass
already have bundled tops; user files override them when present. **Do not commit
player PNGs** — `Data/` is gitignored; `assets/user/*.png` is also ignored.

| Search root (first hit wins) | When |
|---|---|
| `{config}/Data/hakoniwa/user/` | Preferred — beside `Data/hakoniwa_island.json` |
| `hakoniwa/assets/user/` | Package-local drop folder |

Expected filenames (exact; loader is case-sensitive on Linux):

| Category | Filenames |
|---|---|
| Terrain | `sea.png` `shallow.png` `oilfield.png` `dirt.png` `grass.png` `forest.png` `mountain.png` `village.png` `town.png` `city.png` |
| Backdrop | `ocean-background.png` |
| Buildings | `farm.png` `factory.png` `quarry.png` `defense.png` `missile_base.png` `harbor.png` `shipyard.png` `breakwater.png` `monument.png` `bank.png` `supermarket.png` `shrine.png` `park.png` `airport.png` `rocket_base.png` `hotel.png` `casino.png` |
| Monsters | `inora.png` |

Fallback when a file is absent: buildings／monsters → solid color; terrain → bundled
`assets/tiles/{sea,dirt,grass}-01.png` (or color if that is missing too). Hook:
`hakoniwa.user_art` + `TileAtlas` / map paint in `view.py`.

## Checklist after any map/view change

1. Open the island map (or render the offscreen preview).
2. Confirm foreshortening: cell diamonds are **wider than tall** (H/W ≈ 0.707).
3. If the map looks like flat diamonds with H/W ≈ 1 (rotated squares), **fix immediately**.
4. Run `python -m hakoniwa.smoke_test` — must pass `test_oblique_foreshortening_invariant`.
5. Keep v9 stagger, 20×20, same-layer tops, no under-tile skirts.
6. Confirm HUD overlays still sit on the map (not outside columns).
7. Confirm dirt／grass／sea cells show real textures (not solid color fills).
8. Without user PNGs, buildings／monsters stay color blocks; with drops, those keys swap.

CI/local smoke fails if the projection regresses to orthographic-only.
