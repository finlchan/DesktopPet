# 箱庭島 NAS server (v1)

FastAPI + Docker for single-player island state on a LAN / NAS.

Auth is a stub: leave `HAKONIWA_API_KEY` empty for open LAN, or set it and send `X-API-Key`.

## Endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | Liveness (no auth) |
| GET | `/api/v1/island` | Full island JSON |
| PUT | `/api/v1/island` | Replace island |
| POST | `/api/v1/island/reset` | New central-7 island |
| POST | `/api/v1/island/place` | `{i,j,kind}` farm/factory |
| POST | `/api/v1/island/remove` | `{i,j}` |
| POST | `/api/v1/island/turn` | Advance turn |
| POST | `/api/v1/island/landfill` | `{i,j}` |
| POST | `/api/v1/island/level` | `{i,j}` |
| POST | `/api/v1/island/afforest` | `{i,j}` |
| GET | `/api/v1/island/comments` | Visitor guestbook list |
| POST | `/api/v1/island/comments` | `{name,text}` leave a message |

Gameplay rules match the Desktop Pet `hakoniwa` package (色塊佔位 · 箱庭斜視 client).

## Run on NAS

```bash
cd hakoniwa_server
docker compose up -d --build
# → http://<nas-ip>:8787/health
```

Data persists in the `hakoniwa-data` volume (`/data/island.json`).

## Dev (no Docker)

```bash
pip install -r hakoniwa_server/requirements.txt
HAKONIWA_DATA_DIR=./Data/hakoniwa_server python -m hakoniwa_server
```
