# Fish tank art assets

Offline / pre-rendered pixel sheets (plan items 5, 7, 24).

- `swim/<species>.png` — horizontal strip of **8** frames: N, NE, E, SE, S, SW, W, NW (48×40 each).
- `side/<species>.png` — capture／圖鑑 side profile.
- `plant/waterweed.png` — decor plant.

Regenerate (dev only):

```bash
python -m fish_tank.tools.gen_rts_sheets
```

In-game: Qt blit by heading bucket; rare = palette remap. **No realtime 3D.**

## 青衣 HD

`swim/grouper.png` is **96×80** per facing (HD pixel). Regenerate with `python -m fish_tank.tools.gen_grouper_hd`.
