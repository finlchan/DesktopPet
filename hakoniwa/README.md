# 箱庭島 (`hakoniwa/`)

Desktop Pet mini-program: local 箱庭斜視 map + simplified island loop.

## 箱庭斜視 (mandatory view)

Official player view is **箱庭斜視 with depth foreshortening H/W ≈ 0.65**,
not a flat top-down square grid rotated 45°.

| | |
|---|---|
| Projection | Logical 1:1 diamond tops → screen `H = W · 0.65` (`grid.OBLIQUE_Y_SCALE`) |
| Lattice | v9 diagonal-strip stagger, 20×20, same-layer 海／淺灘／mud／grass |
| Terrain | Flat top PNGs in `assets/tiles/` (dirt／grass／shallow／sea／oilfield／crater；森＝草面＋綠洗); 淺灘＝原海面貼圖、海＝同圖加深藍；油田＝海面＋油膜、彈坑＝荒地＋圓坑（皆無色洗、菱形 clip）; ocean backdrop optional |
| User art | Optional PNGs in `Data/hakoniwa/user/` or `assets/user/` replace building／monster color blocks and optionally terrain (see below); missing → color blocks / bundled tops |
| Building art | User PNGs align by **alpha content AABB** (ignore canvas padding): content left↔right = diamond W↔E (full cell `W`); content bottom = S tip; top may rise above N; **no** diamond clip. Flat art（防波堤 etc.）included. Terrain tops stay diamond-clipped. `mountain.png` uses this same unclipped placement on top of the mountain ground tile (not a diamond fill). `tall=True` marks portrait-friendly keys |
| Cell size | `DEFAULT_CELL=120`; wheel zoom `MIN_CELL…MAX_CELL` (12…256); `OBLIQUE_Y_SCALE=0.65` |
| Forest | 植林 50→森(100本)；每回合+100本(上限20000)；伐採免費瞬售 100本≈5資金 |
| Mountain | 造山 100／噴火→山；整地山→荒地；地面仍是山格（泥面＋色洗），可見高度是 `sprites/mountain.png`（建築放置、不裁切）；採掘場 300（僅山上，含溫泉山）產資 |
| Onsen mountain | 普通山每回合 2% 異變為溫泉山（`onsen_mountain`）；地面仍是山格，高度是 `sprites/onsen_mountain.png`（同一套不裁切放置）；分數與採掘場視同山 |
| Onsen village | 溫泉村（`onsen_village`）是建築、費用 0、不可直接建設，目錄列硬鎖。平地鄰溫泉山時以生村機率出現；分數與鄰格生村視同村。貼圖走建築路徑（`sprites/onsen_village.png`） |
| Labor | 回合勞動：農場優先，再工場、採掘場；產能依就業比例 |
| Harbor | 港灣 800／造船所 500（臨海平地色塊）；有其一可貿易輸出 100噸≈5資金 |
| Breakwater | 防波堤 200（臨海平地色塊）；鄰格減海嘯；自身不被海嘯摧毀 |
| Oilfield | 掘削 200：陸→淺灘／淺灘→海／海→探油；油田被動產資；機率枯竭→海；地面為 `oilfield-01.png`（海面油膜） |
| Crater | 飛彈落空於空的荒地／平地→彈坑（`crater-01.png`）；防衛範圍內落空不留坑；整地→平地。森／山／溫泉山與海域不改。村／町／都市是建築，所在平地仍會變彈坑 |
| Monument | 紀念碑 9999（平地色塊）；加島分數／安穩；抗怪獸踩踏；鄰格抑火災如森 |
| Bank | 銀行 500（平地色塊）；流動資金上限 9999；溢出進存款緩衝；可手動存提 |
| Supermarket | 超市 300（平地色塊）；資金買糧 100噸≈8資金（略貴於貿易輸出） |
| Shrine | 神社 800（平地色塊）；大幅加島分數；餵飽時安穩人口加成 |
| Park | 公園 250（平地色塊）；島分數／安穩；鄰格提高生村機率 |
| Airport | 空港 1500（平地色塊；目錄費用原 `?`，本機採箱庭2啟發估算）；島分數／觀光收入／留言小費／誘致加成 |
| Rocket | ロケット基地 2000（平地色塊；目錄／變體常 `?`，近究想衛星建設 2000）；發射觀測衛星 800（Ex 啟發；需基地；減震／海嘯／噴火） |
| Hotel | 酒店 600（平地色塊；目錄民宿／度假村費用 `?` → 介於公園與神社）；島分數／住宿觀光收入／留言小費 |
| Casino | 賭場 1100（平地色塊；目錄賭場／遊樂園費用 `?` → 介於神社與空港）；島分數／娛樂觀光收入（依人口加碼） |
| University | 大學 700（平地色塊；目錄費用 `?` → 介於酒店與神社）；島分數／觀測衛星發射折扣（研究／下一科技 stub；800→600） |
| Research lab | 研究所 950（平地色塊；目錄費用 `?` → 介於神社與賭場）；島分數／輕量減震／海嘯／噴火（可與衛星疊乘） |
| Aquafarm | 養殖場 300（**淺灘**色塊；目錄「淺灘產糧」變體）；被動產糧 30／回合（無勞動） |
| Amusement park | 遊樂園 1300（平地色塊；目錄費用 `?` → 介於賭場與空港）；島分數／安穩＋5／觀光收入（依人口加碼，高於賭場） |
| Power plant | 發電廠 650（平地色塊；SE 電力 stub）；被動產資 15／回合；有電時工場產出 ×1.2 |

| Undersea base | 海底基地 8000（**深海**色塊；定本同飛彈基地）；飛彈優惠；觀光偽裝成海；陸上飛彈基地觀光偽裝成森 |
| Decoy | 紙糊假設施 1（平地色塊；定本ハリボテ）；外觀像防衛、無實防、易毀；觀光顯示為防衛 |
| Camouflage | 觀光偽裝：飛彈基地→森；海底基地→海；紙糊→防衛（島主畫面仍見真貌）；防衛再建設＝自爆清周圍怪 |

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

| Alert marquee | Under status | 警報走馬燈; 通知→警報 on **and** alerts queued |
| Tile info | Top-left | Below status／marquee; 通知→方格資訊 (open by default) |
| Action log | Bottom-right | ~70% transparent; 通知→歷史記錄框 |
| Guestbook | Bottom center | ~70% transparent; **closed by default**; open via 留言 icon |
| Icon bar | Bottom-left | 通知／建築／資訊／留言／設定 — hover micro-animations |
| Build drawer | Full height, left | 建築 icon → **tree browse** (formal categories) + right detail／放置; unmet unlock prereqs hard-locked (🔒); no building thumbnails in the tree |
| Island profile | Above icon bar | 資訊 icon → 本島基本資料 (player／created／name／turn／size…) |
| Settings drawer | Above icon bar | 設定 icon → server connection |

「通知」opens a small menu: 歷史記錄框／警報／方格資訊（independent）. 「資訊」shows island profile — not the tile box.

No permanent right-side build column. Server URL / 本機·連線 live under 設定.

## User-provided art (optional)

Buildings／monsters ship as **color blocks** until you drop PNGs. 海／淺灘／dirt／grass
already have bundled tops (`sea-01` deeper blue, `shallow-01` original cyan sea art);
user files override them when present. **Do not commit player PNGs** — `Data/` is
gitignored; `assets/user/*.png` is also ignored.

| Search root (first hit wins) | When |
|---|---|
| `{config}/Data/hakoniwa/user/` | Preferred — beside `Data/hakoniwa_island.json` |
| `hakoniwa/assets/user/` | Package-local drop folder |

Expected filenames (exact; loader is case-sensitive on Linux). Building sprites
scale to full cell width (W↔E tips) with the bottom on the S tip; portrait art
(e.g. `quarry.png` with a big mountain) may extend above the N tip unclipped.
`tall=True` keys（`quarry.png` `monument.png` `rocket_base.png`）are the usual
portrait subjects.

`mountain.png` is a 2.5D sprite, not a diamond fill. The cell stays mountain
terrain (bundled dirt top + wash) so quarry and score rules still see a
mountain tile; the PNG supplies the visible height. It uses the building
placement above (alpha AABB, left=W, right=E, bottom=S, may exceed N, no
diamond clip). Shipped at `hakoniwa/assets/sprites/mountain.png`; a user drop
of the same name replaces that sprite only. `onsen_mountain.png` uses that
same placement on 溫泉山. `onsen_village.png` is building art (user drop or
`assets/sprites/onsen_village.png`), not a terrain top. `village.png`,
`town.png`, and `city.png` are building art too (EW+S, not a diamond top).
`forest.png` and `oilfield.png` stay flat terrain tops. `crater.png` is the
optional override for the missile pit.

| Category | Filenames |
|---|---|
| Terrain | `sea.png` `shallow.png` `oilfield.png` `dirt.png` `crater.png` `grass.png` `forest.png` `mountain.png` `onsen_mountain.png` |
| Backdrop | `ocean-background.png` |

| Buildings | `farm.png` `factory.png` `quarry.png` `village.png` `town.png` `city.png` `defense.png` `missile_base.png` `undersea_base.png` `decoy.png` `harbor.png` `shipyard.png` `breakwater.png` `monument.png` `bank.png` `supermarket.png` `shrine.png` `park.png` `airport.png` `rocket_base.png` `hotel.png` `casino.png` `university.png` `research_lab.png` `aquafarm.png` `amusement_park.png` `power_plant.png` `onsen_village.png` |

| Monsters | `inora.png` |

Fallback when a file is absent: buildings／monsters → solid color; terrain → bundled
`assets/tiles/{sea,shallow,dirt,grass,oilfield,crater}-01.png` (or color if that is missing too). Hook:
`hakoniwa.user_art` + `TileAtlas` / map paint in `view.py`.

## Checklist after any map/view change

1. Open the island map (or render the offscreen preview).
2. Confirm foreshortening: cell diamonds are **wider than tall** (H/W ≈ 0.65).
3. If the map looks like flat diamonds with H/W ≈ 1 (rotated squares), **fix immediately**.
4. Run `python -m hakoniwa.smoke_test` — must pass `test_oblique_foreshortening_invariant`.
5. Keep v9 stagger, 20×20, same-layer tops, no under-tile skirts.
6. Confirm HUD overlays still sit on the map (not outside columns).
7. Confirm dirt／grass／海／淺灘 cells show real textures (deep blue vs cyan shallow).
8. Without user PNGs, buildings／monsters stay color blocks; with drops, those keys swap.
9. Building user art spans W↔E tips, sits on the S tip, and may exceed the N tip (no diamond clip on sprites). Mountain and 溫泉山 cells draw their sprites the same way, above the mountain ground tile. 溫泉村 uses the building path, not a terrain top.

CI/local smoke fails if the projection regresses to orthographic-only.
