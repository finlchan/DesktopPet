Desktop Pet
==================

Version: 261031.01
Published: 2026-10-31

A floating shortcut menu and document record gadget on the Windows desktop.

Note: from version 261027.01 this README is English-only. Earlier releases
shipped a bilingual (English + Traditional Chinese) README; the Chinese half
was dropped when the app UI was fully translated to English.

Features
--------
1. Displays a small icon on the desktop (custom image or auto-rotating image set).
2. Click the icon to open a semi-transparent menu.
3. The top of the menu shows "Folder shortcuts" for opening local folders (with search/filter).
4. Below that, "File / URL shortcuts"; click ">>" to open the submenu (search/filter; files and web links).
5. The middle section shows "Document record"; click the ">>" button to open the submenu and browse/search files.
   The Document record submenu header has an "Open folder" button to open storage folder(s) in the file manager.
6. Below Document record, "Mini programs"; click ">>" for Text records and Calculations
   (Level calc / Slope calc / Free station), plus Pomodoro, Translate, and 箱庭島
   (richer island sim: textured oblique map HUD, forest/harbor/monuments/mountain/
   quarry/breakwater/oil, bank/shop/shrine/park, optional user PNG art overlay).
7. Drag files, folders, or URLs onto the pet to add shortcuts (prompt for name/description).
8. The bottom has a "Settings" button to edit all configurations.
9. Window level can be set to Normal, Always on top, or Always on bottom.
10. Optional "Start with Windows" login autostart (Windows only).
11. Remembers pet position across monitors and resolution changes.

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
5. Text records: add/edit/delete text records (Title + Body); list has search/filter.
6. System: set window level (Normal / Always on top / Always on bottom);
   enable/disable "Start with Windows" (registry Run key; Windows only).

Free Station calculator
--------
Mini programs → Calculations → Free station resects the standing station from
2–4 known backsight stations, mirroring the "Free Station" sheet of the
Free_Station_FAI.xls / .xlsm survey spreadsheet:

- Per backsight: name, Easting, Northing, reduced level (optional), observed
  mean bearing (DD.MMSS, e.g. 330.140182 = 330°14'01.8"), vertical (zenith)
  angle, slope distance and prism/spot height (face-left / face-right).
- IMPORT (left of Calculate) loads standing station, instrument height, BS
  names/coords, and face observations from a Free Station sheet
  (.xlsm / .xlsx / .xls). Annotated layout: standing D12, HI H12, BS1–3
  Name/E/N/RL from D/E/F/G13–15, BS4 from D/E/F/G17, faces C25–F32.
  Measurement cells are filled only for BS rows whose Name is non-empty after
  import; empty Excel cells (and template placeholders such as "BS name" /
  "DD.MMSS" / "Distance") clear to blank. Runtime deps: openpyxl + xlrd
  (bundled in the Windows EXE via PyInstaller --hidden-import /
  --collect-submodules).
- Every ordered From→To pair is solved by the sine rule exactly as the sheet's
  FreeStation / FreeStation_Mirror VBA functions; the sheet's branch rule is
  kept (preliminary branch unless its distance check exceeds 0.05 m, then the
  mirror branch when valid).
- Output: station Easting/Northing, reduced level, and the distance-check
  residual ΔHD per accepted pair, plus an Average (mean E / N / RL) of those
  pair results. Copy button copies the result block.

What's new in 261031.01 (2026-10-31)
--------
1. Free Station IMPORT: annotated-layout BS1–3 Name now maps from D13 / D14 /
   D15 (E/N/RL from E/F/G on the same rows); BS4 Name stays D17; standing D12,
   Inst. ht H12, and face obs C25–F32 unchanged. Empty cells and template
   placeholders ("BS name" / "DD.MMSS" / "Distance") clear to blank.

What's new in 261030.01 (2026-10-30)
--------
1. 箱庭島: oblique diamond projection fix (stable map geometry).
2. Map HUD / terrain textures (tile tops + ocean backdrop bundled in EXE).
3. Forest: plant and harvest gameplay.
4. Harbor / shipyard trade loop.
5. Monuments and score tracking.
6. Mountain / quarry production.
7. Breakwater, oil, and tsunami mitigation.
8. Bank, supermarket, and shrine buildings.
9. City park and induction mechanics.
10. Optional user PNG art overlay on the island map.
11. Windows CI PyInstaller aligned with build.bat: hakoniwa/assets --add-data
    plus hidden-imports for hakoniwa.tiles and hakoniwa.user_art.

What's new in 261029.01 (2026-10-29)
--------
1. Free Station: IMPORT button (left of Calculate) reads the Free Station
   sheet from .xlsm / .xlsx / .xls into standing station, instrument height,
   and BS1–BS4 name / E / N / RL / face observations. Face measurement cells
   are filled only when that BS Name is non-empty after import.
2. Free Station green results: Average line (mean E, N, RL of accepted pair
   solutions) after the per-pair coordinate lines.
3. requirements.txt / PyInstaller / Windows CI: openpyxl + xlrd for Excel
   import (lazy import at runtime; collected explicitly for the EXE), plus
   hakoniwa hidden-imports for the Mini programs 箱庭島 entry.
4. 箱庭島 (Hakoniwa Island) is available under Mini programs → 箱庭島
   (already on main via earlier merges; included in this combined release EXE).

What's new in 261027.02 (2026-10-27)
--------
1. Free Station dialog: 4 backsight rows (was 3), each with face-left (F1) and
   face-right (F2) observations averaged exactly like the sheet's "Mean B/S"
   formulas (bearing: mean of F1 and F2+180°; vertical angle:
   (360−F1−F2)/2+F1; slope distance / spot height: plain average).
2. Per-pair review table like the Excel: From / To, Preliminary E/N,
   Mirror E/N, chosen Easting/Northing, Reduced Lv., Distance Check, with
   per-pair "Reject both" and "Use mirror angle" checkboxes; the summary
   respects the choices.
3. "<< 1 / 2 >>" pager: page 2 stores backsight records (Name, Easting,
   Northing, RL) in config as "free_station_stations" (backward compatible);
   typing a stored name on page 1 auto-fills that row's E/N/RL (still editable).

What's new in 261027.01 (2026-10-27)
--------
1. Mini programs → Calculations → Free Station: resection calculator porting the
   Free_Station_FAI.xls sheet math (sine rule with mirror branch and distance
   check; DD.MMSS angles; zenith-angle verticals). Ornate frame style matching
   the other calculation dialogs.
2. Whole user interface translated to English (menus, dialogs, buttons,
   tooltips, tray notifications, message boxes). Config keys are unchanged.
3. README is now English-only.

What's new in 261026.08 (2026-10-27)
--------
1. Mini-program panel fills painted via QPainter ARGB (not QSS rgba). QSS rgba under
   WA_TranslucentBackground was dropping alpha so 60% vs 80% looked identical.
   Window center ~70% opaque, gray panel ~80% opaque.

What's new in 261026.07 (2026-10-27)
--------
1. Mini-program opacity tuning: window center ~70% opaque, gray content panel ~80% opaque
   (ornate frame ring stays solid).

What's new in 261026.06 (2026-10-27)
--------
1. Mini-program translucency fix: ornate outer/mid layers paint border rings only
   (transparent center). Previously a full-rect frame fill sat under the gray panel
   and blocked see-through. Content panel stays ~60% opaque against the desktop.

What's new in 261026.05 (2026-10-27)
--------
1. Mini-program dialogs: window drag is limited to the ornate frame border band only
   (gilt/wood margin). Title row and inner content no longer move the window.
2. Gray content panel opacity set to ~60% opaque (ornate frame stays solid).

What's new in 261026.04 (2026-10-26)
--------
1. All mini-program dialogs (平水計算, 坡度運算, 番茄鐘, 翻譯): frameless + ornate frame +
   ~70% opaque panels; reliable drag on the picture-frame border and the title row.
   (These tools are now named Level calc, Slope calc, Pomodoro, Translate.)
2. 番茄鐘 / 翻譯 now match the calc dialogs (no OS title bar, translucent content fill).

What's new in 261026.03 (2026-10-26)
--------
1. 小程式 → 番茄鐘 (Pomodoro): countdown timer with 25/5/15 minute presets and custom minutes
   (1–600), Start / Pause / Reset, progress bar, gentle tray notification + beep when done.
   Last used duration is remembered in config (running state is not saved).
2. 小程式 → 翻譯 (Translate): text translation with source auto-detect, target languages
   EN / 繁體中文 / 简体中文 / 日本語 / 한국어 / Français / Deutsch / Español, Translate button
   plus auto-translate after typing pauses, copy button. Uses Google Translate's public web
   endpoint (no API key); failures show a friendly inline message; recent translations are
   cached in memory only (user text is never written to disk or logs).
3. 平水計算 / 坡度運算: frameless windows (no OS title bar); ornate frame is the chrome.
4. Dialogs are ~70% opaque (半透明); drag by frame/title/empty areas; Close still available.

What's new in 261026.01 (2026-10-26)
--------
1. 平水計算 / 坡度運算 dialogs: ornate gilt/wood picture-frame border.
2. Removed +/− stepper buttons; compact keyboard-editable decimal inputs (validate on calculate).
3. Removed explanatory help paragraphs under titles; kept section titles, field labels, and radio labels.
4. Shrunk input boxes and primary action buttons (計算平水 / 計算坡度 / 計算高程).

What's new in 261024.03 (2026-10-24)
--------
1. Pet menu: new top-level "小程式" section with >> submenu.
2. Text records moved under 小程式 (English label; config key still "text_records"); Settings tab renamed to "Text records".
3. 小程式 → 運算 → 平水計算: linear interpolate level at target distance
   (level = high − (high−low)×(target/full); extrapolation allowed with note).
4. 小程式 → 運算 → 坡度運算: three tools — 兩點高差求坡度, 坡度推算高程, 坡度單位互相運算
   (Fall %, 1 in X, angle DMS / DD.MMSS).

What's new in 261024.02 (2026-10-24)
--------
1. Document record submenu: "Open folder" button in the header opens the storage folder(s) in the OS file manager
   (one folder opens directly; multiple folders show a picker menu).
2. Text records: pet-menu section with >> submenu of article titles; click a title to read the body.
3. Settings tab "Text records" to add/edit/delete/reorder text records; config key "text_records": [{title, body}, …]
   (backward compatible — older configs omit the key).

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
- config.json   (blank template from the release — do NOT use a personal config)
- How-to-use.pdf   (user guide; How-to-use.png is a one-page summary)
  (supersedes the old "How to use.jpg")

Then start DesktopPet.exe.

Build EXE
--------
Only needed if you want to build from source.
Double-click build.bat to generate the shareable folder upload\
(DesktopPet.exe, blank packaging config.json, How-to-use.pdf, How-to-use.png).
Do not copy your personal config.json, save data, or pet pictures into uploads.

Notes
--------
- config.json is created automatically on first run if it is missing.
- Keep DesktopPet.exe and config.json in the same folder.
- Contact: chanpofaihk@gmail.com
- Support me via PayPal: scan the QR code below. 

