# DesktopPet Sync Board

Static three-pane sync UI for DesktopPet: write校正指示, mark up a screenshot on canvas, then Sync a localStorage packet (JSON + preview data URL) for agent pickup.

## Panes

1. **指示** — chat history + textarea; helpers `/help`, `/hakoniwa`, `/align`
2. **繪圖修正** — canvas with stroke tools over preset screenshots (`sample-hud.jpg`, `sample-logo.png`)
3. **即時同步** — Sync button, annotated preview, live JSON packet, download link

## Start

From this folder:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
# or: npm start
```

Open `http://127.0.0.1:8765/`.

No build step and no Node runtime required — plain HTML/CSS/JS served statically.
