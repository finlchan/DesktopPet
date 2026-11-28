# MAP water backdrop assets

| File | Notes |
|------|--------|
| `sea-surface.jpg` | User-provided ocean photo (**1376×768** source). Drawn at **60% opacity** over a steel-blue underlay with **cover-fit** (KeepAspectRatioByExpanding + center) into the viewport — the file is **not** permanently downsampled. Soft edge fade (vignette) is applied at draw time on all four outer edges. Water-ripple refraction samples this cover-fitted layer. Bundled with the EXE via `map_bubbles/assets` — do not hardcode local Downloads paths. |
| `window-move.png` | Clean 4-way arrow glyph (white fill, dark outline, transparent backdrop) for the top-right MAP **window-move grip**. Bundled with the EXE via the same `--add-data map_bubbles/assets` path. |

Used as the refracted MAP water layer (`WaterRippleSim`). Bubble rings and labels are drawn above this layer and are not warped. The move grip sits on the gold chrome (not warped).

## Display notes

Earlier builds looked cropped/low-res because the ripple pipeline **scaled the photo into the low-res sim buffer with IgnoreAspectRatio**, then upscaled that buffer to the window. The asset on disk was already the full user photo; the fix is cover-fit display from the original plus viewport-sized sampling (physics stays low-res).
