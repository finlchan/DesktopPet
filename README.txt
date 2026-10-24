Desktop Pet
==================

Version: 261024.01
Published: 2026-10-24

A floating shortcut menu and document record gadget on the Windows desktop.

Features
--------
1. Displays a small icon on the desktop (custom image or auto-rotating image set).
2. Click the icon to open a semi-transparent menu.
3. The top of the menu shows "Folder shortcuts" for opening local folders (with search/filter).
4. Below that, "File / URL shortcuts"; click ">>" to open the submenu (search/filter; files and web links).
5. The middle section shows "Document record"; click the ">>" button to open the submenu and browse/search files.
6. Drag files, folders, or URLs onto the pet to add shortcuts (prompt for name/description).
7. The bottom has a "Settings" button to edit all configurations.
8. Window level can be set to Normal, Always on top, or Always on bottom.
9. Optional "Start with Windows" login autostart (Windows only).
10. Remembers pet position across monitors and resolution changes.

Quick Usage
--------
- Left-click the pet: open menu
- Drag the pet: move position
- Double-click the pet: open settings
- Right-click the pet: open menu
- Drag-and-drop a file/folder/URL onto the pet: add a shortcut
- Right-click a file item: edit Time / Comment / Publisher / Version

Settings
--------
1. Pet Image: choose a single image or an image folder for automatic rotation.
2. Folder shortcuts: set "Item name", "Folder path", and "Description" (list has search/filter).
3. File shortcuts: set Type (File or URL), "Item name", path/URL, and "Description" (list has search/filter).
4. Document record: set the "Title" and one or more "Data storage folders"
   (click Add to add additional folders);
   the app will automatically list all files in those folders.
5. System: set window level (Normal / Always on top / Always on bottom);
   enable/disable "Start with Windows" (registry Run key; Windows only).

What's new in 261024.01 (2026-10-24)
--------
1. Search/filter for Document record lists, File/URL shortcuts submenu, folder shortcuts in the menu, and Settings lists.
2. Start with Windows: System tab option (HKCU Run key); hidden/disabled gracefully on non-Windows.
3. Drag-and-drop files/folders/URLs onto the pet to add shortcuts (name/description prompt).
4. URL shortcuts: file_shortcuts entries support optional "type": "file"|"url"; Settings Type selector; open in default browser.
5. Multi-monitor position memory: saves screen name + relative position; restores/clamps on startup and screen changes.

What's new in 261023.01 (2026-10-23)
--------
1. File shortcuts: Settings tab + pet menu section (header + >> submenu, like Document record).
2. Document record Settings: 「新增」 button label changed to English "Add".
3. Config adds "file_shortcuts" (existing "shortcuts" folder list unchanged).

What's new in 261022.01 (2026-10-22)
--------
1. Document record: multiple storage folders, with Add in Settings to add more.
2. Document list shows filename and comment.
3. Hover state on options (slightly darker).
4. build.bat fixed for Windows cmd; shareable output goes to upload\.
5. Packaging ignores personal config / save / pics (blank template only).

Download
--------
A ready-to-run build is on GitHub Releases. You do not need to build the EXE.

https://github.com/finlchan/DesktopPet/releases

Download these files and keep them in the same folder:

- DesktopPet.exe
- config.json
- How to use.jpg

Then start DesktopPet.exe.

Build EXE
--------
Only needed if you want to build from source.
Double-click build.bat to generate the shareable folder upload\
(DesktopPet.exe, blank packaging config.json, How to use.jpg).
Do not copy your personal config.json, save data, or pet pictures into uploads.

Notes
--------
- config.json is created automatically on first run if it is missing.
- Keep DesktopPet.exe and config.json in the same folder.
- Contact: chanpofaihk@gmail.com
- Support me via PayPal: scan the QR code below. 


--------------------------------------------------------------------------------

版本：261024.01
發布日期：2026-10-24

一款位於 Windows 桌面上的浮動快捷選單與文檔記錄小工具。

功能特點


桌面小圖示：在桌面上顯示一個小圖示（可自訂單張圖片或設定圖片資料夾自動輪播）。
半透明選單：點擊圖示即可開啟半透明快捷選單。
資料夾快捷方式：選單頂部顯示「資料夾快捷方式」，並可搜尋／篩選。
檔案／網址快捷方式：其下顯示「檔案／網址快捷方式」，點擊「>>」開啟子選單（可搜尋；支援檔案與網址）。
文檔記錄：選單中部顯示「文檔記錄」，點擊「>>」按鈕可開啟子選單並瀏覽／搜尋檔案。
拖放新增：可將檔案、資料夾或網址拖放到寵物上以新增快捷方式（會提示輸入名稱與描述）。
設定選項：選單底部設有「設定」按鈕，可編輯所有配置參數。
視窗層級：視窗層級可設定為「一般 (Normal)」、「置頂 (Always on top)」或「置底 (Always on bottom)」。
開機啟動：可於系統設定啟用「隨 Windows 啟動」（僅 Windows）。
多螢幕位置記憶：記住寵物在各螢幕上的位置，並在啟動或螢幕變更時還原／限制在可見範圍內。

快速上手
左鍵點擊：開啟選單
拖曳：移動位置
雙擊：開啟設定
右鍵點擊：開啟選單
拖放檔案／資料夾／網址到寵物：新增快捷方式
右鍵點擊檔案項目：編輯時間 / 備註 / 發布者 / 版本 (Time / Comment / Publisher / Version)

設定說明
圖片 (Pet Image)：可選擇單張圖片，或指定圖片資料夾進行自動輪播。
資料夾快捷方式 (Folder shortcuts)：可設定「項目名稱 (Item name)」、「資料夾路徑 (Folder path)」及「描述 (Description)」（列表可搜尋／篩選）。
檔案快捷方式 (File shortcuts)：可設定類型 (File / URL)、「項目名稱」、路徑或網址及「描述」（列表可搜尋／篩選）。
文檔記錄 (Document record)：設定「標題 (Title)」與一個或多個「資料儲存資料夾 (Data storage folders)」（按「Add」可加入更多資料夾）；應用程式將自動列出這些資料夾內的所有檔案。
系統設定 (System)：設定視窗層級（一般 / 置頂 / 置底）；可啟用／停用「隨 Windows 啟動」（登錄檔 Run 機碼；僅 Windows）。

261024.01 更新內容（2026-10-24）
1. 搜尋／篩選：文檔記錄列表、檔案／網址子選單、資料夾快捷方式選單，以及設定列表。
2. 隨 Windows 啟動：系統分頁選項（HKCU Run 機碼）；非 Windows 上停用／隱藏。
3. 拖放新增：將檔案／資料夾／網址拖到寵物即可新增快捷方式（名稱／描述提示）。
4. 網址快捷方式：file_shortcuts 支援可選 "type": "file"|"url"；設定中可選類型；以預設瀏覽器開啟。
5. 多螢幕位置記憶：儲存螢幕名稱與相對位置；啟動及螢幕變更時還原並限制在可見範圍。

261023.01 更新內容（2026-10-23）
1. 新增檔案快捷方式：設定分頁與選單標題列＋「>>」子選單（與文檔記錄相同交互）。
2. 文檔記錄設定中「新增」按鈕改為英文「Add」。
3. 設定檔新增 "file_shortcuts"（既有 "shortcuts" 資料夾清單維持不變）。

261022.01 更新內容（2026-10-22）
1. 文檔記錄：支援多個儲存資料夾，設定中可按 Add 加入更多資料夾。
2. 列表同時顯示檔名與備註 (comment)。
3. 選項加入滑鼠懸停狀態（略為變深）。
4. 修正 build.bat 在 Windows cmd 下執行；輸出資料夾為 upload\。
5. 包裝流程忽略個人 config / 存檔 / 圖片（僅附空白模板）。

下載說明
GitHub Releases 已提供免安裝、可直接執行的版本，您無需自行編譯 EXE 檔案：
https://github.com/finlchan/DesktopPet/releases
請下載以下檔案並保持放在同一資料夾中：
DesktopPet.exe
config.json
How to use.jpg
完成後即可啟動 DesktopPet.exe 使用。

編譯 EXE 檔案
僅在您希望從原始碼自行建置時才需要操作。
雙擊執行 build.bat，即可在 upload\ 資料夾產生可分享內容
（DesktopPet.exe、空白包裝用 config.json、How to use.jpg）。
請勿把個人 config.json、存檔或寵物圖片放入上載內容。
注意事項
若初次執行時缺少 config.json，系統將自動建立該檔案。
請務必將 DesktopPet.exe 與 config.json 保持在同一資料夾下。

聯絡方式：chanpofaihk@gmail.com
