# MAP water backdrop assets

| File | Notes |
|------|--------|
| `sea-surface.jpg` | User-provided ocean photo (**1376×768** on disk; the file is not rewritten). Cover-fit (KeepAspectRatioByExpanding + center) into a buffer **at most half the photo (≤688×384)**, smooth-scaled to the window, drawn at **80% opacity** over a steel-blue underlay. Soft edge fade (vignette) is applied at draw time on all four outer edges. Water-ripple refraction slides blocks of this layer. Bundled with the EXE via `map_bubbles/assets` — do not hardcode local Downloads paths. |
| `window-move.png` | Clean 4-way arrow glyph (white fill, dark outline, transparent backdrop) for the top-right MAP **window-move grip**. Bundled with the EXE via the same `--add-data map_bubbles/assets` path. |

Used as the refracted MAP water layer (`WaterRippleSim`). Bubble rings and labels are drawn above this layer and are not warped. The move grip sits on the gold chrome (not warped).

## Display notes

The photo on disk stays 1376×768. The window shows it from the half-resolution paint buffer above (so a large MAP is softer than a 1:1 cover-fit) at 80% opacity. Ripple rings are a block refraction of that image; physics stays on the ≤220×160 height field.
