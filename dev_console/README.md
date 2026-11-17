# DesktopPet 開發者主控台（Dev Console）

可選的 Gradio 三欄工具：聊天指令、可繪製截圖編輯，以及 Alignment(2)／標記即時預覽。  
按 **同步給 Agent** 會把目前畫面寫入 sync packet，供本機 Agent 讀取。

## 安裝與啟動

```bash
pip install -r requirements.txt
python -m dev_console.app
```

瀏覽器開啟 `http://127.0.0.1:7860`（可用環境變數覆寫，見下方）。

也可：`python -m dev_console`

### 環境變數

| 變數 | 說明 | 預設 |
|------|------|------|
| `GRADIO_SHARE` | 設為 `1` / `true` 時開啟 Gradio public share link | off |
| `GRADIO_SERVER_NAME` | bind address | `127.0.0.1` |
| `GRADIO_SERVER_PORT` | port | `7860` |

例：

```bash
GRADIO_SHARE=1 GRADIO_SERVER_PORT=7861 python -m dev_console.app
```

## 三欄說明

1. **聊天（左）** — 指令與校正備註；歷史一律為 `{role, content}` 訊息格式。按鈕：送出、清除對話。
2. **截圖編輯（中）** — Gradio `ImageEditor`。按鈕：載入樣本、推到右側預覽、**同步給 Agent**（primary）。
3. **即時面板（右）** — live Image + Alignment(2) matplotlib（E/N）+ JSON。按鈕：立刻運算 Alignment(2)。

## Agent sync packet

按 **同步給 Agent**（或聊天 `/save`／輸入校正備註）會寫入 `Data/dev_console/`：

| 檔案 | 用途 |
|------|------|
| `annotations/<prefix>_<stamp>.png` + `.json` | 歷次標記封存 |
| `latest.png` | 最新合成圖（給 Agent 讀） |
| `latest.json` | 最新 meta（note、size、路徑） |
| `request.md` | 給 Agent 的簡短請求說明 |

`read_sync_request()` 回傳 `{ok, meta, request_md, latest_png}`。

## 聊天指令

| 指令 | 作用 |
|------|------|
| `/help` | 顯示說明 |
| `/align [step]` 或 `/align2 [step]` | 跑 Alignment(2)（預設 step=1） |
| `/hakoniwa` 或 `/proj` | 載入 `hakoniwa/testdata/oblique_projection.json` |
| `/shots` | 列出截圖預設（箱庭 testdata + fish_tank/side + logo） |
| `/save [note]` | 儲存標記並更新 sync packet |
| （一般文字） | 校正備註：寫入 note 並更新 sync packet |

## 預設截圖

若存在，預設載入 `hakoniwa/ui_overlay_map_hud.png`（對應 `hakoniwa/testdata/ui_overlay_map_hud.png`）。

## 無頭測試

```bash
python -m dev_console.smoke_test
```

通過時會印出各項檢查（含 `sync_packet`）並以：`All smoke checks passed.` 結束。
