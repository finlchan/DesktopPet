# Transparent Fish Tank（透明魚缸）

Phase 1 local mini-program under Desktop Pet → Mini programs → **透明魚缸／Fish Tank** (below 箱庭島).

## Camera (locked)

- **Swim view:** high slightly oblique / isometric; **8-direction** RTS pre-rendered pixel sheets (no realtime 3D).
- **Capture／圖鑑:** side profile OK; scientific name only here.

Closed PR #48 used wrong eye-level swim silhouettes — do **not** treat it as reference.

## Phase 1 (this package)

- Full-window translucent glass; Windows click-through on the glass; always-on edge grips `「 」` + bottom-left **Social Icon Fill** circular toolbar (comic line icons, hover fill-rise ~0.45s).
- Zoom/pan change **visible world range only**; swim sprites stay fixed pixel size.
- Five fish + one plant: **RTS isometric pre-rendered pixel** 8-dir swim sheets under `assets/swim/`; rare = palette remap; side cards under `assets/side/`.
- Free swim; fish may leave the local view (away stub — no public server).
- Feed / decorate / name / catch (local ownership). Capture／圖鑑 shows health, fullness, age, rarity + scientific name; market aliases as `主名 (別名)`.
- Saves under `Data/fish_tank/tank.json` (gitignored via `Data/`).

## Phase 2 stubs

See `remote_stubs.py`: 30‑minute settlement flush, immediate catch/trade/gift/drop APIs — no-op or local echo only. **Do not** ship a public fish-tank server in Phase 1.

## Smoke

```bash
python -m fish_tank.smoke_test
```
