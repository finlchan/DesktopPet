# DesktopPet 開發者主控台（Dev Console）

可選的 Gradio 三欄工具，方便對照箱庭截圖、標記畫面，並即時檢視 Alignment(2)／投影參數。

## 安裝與啟動

```bash
pip install -r requirements.txt
python -m dev_console.app
# optional public link:
GRADIO_SHARE=1 python -m dev_console.app
```

瀏覽器開啟 `http://127.0.0.1:7860`。

也可：`python -m dev_console`

## 三欄說明

1. **聊天（左）** — 指令與校正備註；歷史一律為 `{role, content}` 訊息格式。**Sync to Agent** 寫入 `Data/dev_console/latest.png`、`latest.json`、`request.md` 供 agent 讀取。
2. **截圖編輯（中）** — Gradio `ImageEditor`：載入箱庭 testdata 截圖、塗鴉標記、合成存檔至 `Data/dev_console/`（含 `annotations/`）。
3. **即時面板（右）** — Alignment(2) 平面圖（matplotlib）＋ JSON（投影／對齊 meta／備註／sync_packet）。

## 聊天指令

| 指令 | 作用 |
|------|------|
| `/help` | 顯示說明 |
| `/align [step]` | 以目前工作簿跑 Alignment(2)（預設 step=1） |
| `/hakoniwa` 或 `/proj` | 載入 `hakoniwa/testdata/oblique_projection.json` |
| `/shots` | 列出可用截圖預設（箱庭 testdata） |
| `/save [note]` | 將 ImageEditor 合成圖存到 `Data/dev_console/` |
| **Sync to Agent** | `save_annotation` → `annotations/*` + `latest.png` / `latest.json` / `request.md` |
| （純中文文字） | 視為校正備註：寫入 note 並刷新標記預覽 JSON |

## 預設截圖

若存在，預設載入 `hakoniwa/ui_overlay_map_hud.png`（對應 `hakoniwa/testdata/ui_overlay_map_hud.png`）。

## 無頭測試

```bash
python -m dev_console.smoke_test
```

通過時會印出：`All smoke checks passed.`
