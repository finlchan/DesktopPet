Desktop Pet
==================

Version: 261114.01
Published: 2026-11-14

A floating shortcut menu and document record gadget on the Windows desktop.

Note: from version 261027.01 this README is English-only. Earlier releases
shipped a bilingual (English + Traditional Chinese) README; the Chinese half
was dropped when the app UI was fully translated to English. Feature names
below keep the bilingual UI labels where the menus show them.

Features
--------
1. Pet — small desktop icon (custom image or rotating set); click toggles
   Folder Shortcuts; drag to move; drop files/folders/URLs to add shortcuts;
   Heartbeat Zoom on click.
2. Folder Shortcuts フォルダー ショートカット — local folders with search/
   filter; Float Drift title; List Row Fill hover.
3. File/URL Shortcuts 指定傳送 — file or URL items with search/filter;
   Jitter Settle title motion.
4. Document Record 文檔紀錄 — browse/search files in one or more storage
   folders; Crumble Down title; Open folder; per-file Time / Comment /
   Publisher / Version.
5. Mini Programs 副程式 — Text records; Calculations; Pomodoro; Translate;
   箱庭島（未完成）／Hakoniwa (WIP); 透明魚缸（未完成）／Fish Tank (WIP).
   Panel ambient: Particle Network.
6. Calculations — Level calc, Slope calc, Free station (resection IMPORT +
   pair Prelim/Mirror/Reject/Use mirror; BS4 left blank for manual entry),
   Alignment(1) (point-list interpolate + 大量運算 batch), Alignment(2)
   (OSCH design densify, interval, OSCH2_AOut Excel with LEVEL columns).
7. Pomodoro — Now / Target / Countdown, duration presets and End-at mode.
8. Translate — auto-detect source; EN / 繁中 / 简中 / 日本語 / 한국어 /
   Français / Deutsch / Español (public web endpoint; no API key).
9. 箱庭島／Hakoniwa (WIP) and 透明魚缸／Fish Tank (WIP) — entries kept and
   marked unfinished.
10. Settings — pet image, shortcuts, document folders, text records, window
    level (Normal / Always on top / Always on bottom), Start with Windows.
11. Remembers pet position across monitors and resolution changes.
12. Dev Console (optional) — Gradio three-pane tool under dev_console/:
    chat + drawable screenshot editor + live Alignment(2) / annotation pane.
    Run: pip install -r requirements.txt && python -m dev_console.app
    See: dev_console/README.md

Quick Usage
--------
- Left-click / right-click the pet: toggle Folder Shortcuts (open ↔ close)
- Drag the pet: move position
- Double-click the pet: open settings
- Drag-and-drop a file/folder/URL onto the pet: add a shortcut
- Right-click a Document Record file item: edit Time / Comment / Publisher /
  Version

Latest updates (5)
--------
261114.01 (2026-11-14)
1. Free Station IMPORT: BS4 stays blank for manual entry (no longer maps
   Computed Bearing / stray cells into BS4).

261106.06 (2026-11-07)
1. Free Station: soft-fail asin/acos domain errors; keep From/To pair rows
   with Prelim / Mirror / Dist. check and Reject both / Use mirror.

261106.05 (2026-11-06)
1. Alignment(1) 大量運算: right-hand Output is chainage, signed plan offset,
   and diff level (not chainage-only).

261106.04 (2026-11-06)
1. Alignment(2) Output Excel: CHAINAGE / E / N / LEVEL plus LHS/RHS E·N·Lv
   columns from vertical + crossfall.

261106.03 (2026-11-06)
1. Alignment(1) section 3 大量運算: Import batch / Compute / Output for the
   dual Input→Output workbook.

Older release notes are on GitHub Releases.

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
- Packaging uses blank packaging/config.json only (no personal data).
- Contact: chanpofaihk@gmail.com
- Support me via PayPal: scan the QR code below.
