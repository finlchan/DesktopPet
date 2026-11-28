# MAP water backdrop assets

| File | Notes |
|------|--------|
| `sea-surface.jpg` | User-provided ocean photo for the MAP sea backdrop. Drawn at **60% opacity** over a steel-blue underlay; water-ripple refraction samples this layer. Bundled with the EXE via `map_bubbles/assets` — do not hardcode local Downloads paths. |
| `window-move.png` | Clean 4-way arrow glyph (white fill, dark outline, transparent backdrop) for the top-right MAP **window-move grip**. Bundled with the EXE via the same `--add-data map_bubbles/assets` path. |

Used as the refracted MAP water layer (`WaterRippleSim`). Bubble rings and labels are drawn above this layer and are not warped. The move grip sits on the gold chrome (not warped).
