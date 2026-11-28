Desktop Pet
==================

Version: 261128.09
Published: 2026-11-28

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
5. MAP — interconnected bubbles (topic / local path / website); Social Icon
   Fill button to the right of Document Record; water-ripple backdrop
   (cursor path / click / idle drops; bubbles refract under water);
   drag / connect / edit / open path or URL; saved in config map_bubbles
   (blank in packaging).
6. Mini Programs 副程式 — Text records; Calculations; Pomodoro; Translate;
   箱庭島（未完成）／Hakoniwa (WIP); 桌面跑馬燈／視窗跑馬燈 (status marquee).
   Panel ambient: Particle Network.
7. Calculations — Level calc, Slope calc, Free station (resection IMPORT +
   pair Prelim/Mirror/Reject/Use mirror; BS4 left blank for manual entry),
   Alignment(1) (point-list interpolate + 大量運算 batch), Alignment(2)
   (OSCH design densify, interval, OSCH2_AOut Excel with LEVEL columns).
8. Pomodoro — Now / Target / Countdown, duration presets and End-at mode.
9. Translate — auto-detect source; EN / 繁中 / 简中 / 日本語 / 한국어 /
   Français / Deutsch / Español (public web endpoint; no API key).
10. 箱庭島／Hakoniwa (WIP) — entry kept and marked unfinished.
    桌面跑馬燈／視窗跑馬燈 — always-on-top Diagonal Text Bands status window
    (inline gear settings: text1/text2, theme, single/dual-span display,
    scroll speed, band size; blank-safe status_marquee).
11. Settings — pet image, shortcuts, document folders, text records, window
    level (Normal / Always on top / Always on bottom), Start with Windows.
12. Remembers pet position across monitors and resolution changes.

Quick Usage
--------
- Left-click / right-click the pet: toggle Folder Shortcuts (open ↔ close)
- Drag the pet: move position
- Double-click the pet: open settings
- Drag-and-drop a file/folder/URL onto the pet: add a shortcut
- Right-click a Document Record file item: edit Time / Comment / Publisher /
  Version
- Home toolbar MAP (right of Document Record): open bubble map; Add / Connect /
  Edit / Open path-URL / Delete; drag to reposition (no float physics yet)

Latest updates (5)
--------
261128.09 (2026-11-28)
1. MAP: ripples are the earlier refractive blocks again (not the blurred
   ≤220×160 overlay). Sea backdrop is painted at most half the photo
   (≤688×384) at 80% opacity. Wave physics stays ≤220×160; frames are
   cell blits, not the slow full-window warp.

261128.08 (2026-11-28)
1. MAP: cover-fit sea stays sharp. Ripples composite from a small buffer
   (≤220×160) so pan and bubbles stay smooth (the viewport-sized wave pass
   was the lag, not the sea photo).

261128.07 (2026-11-28)
1. MAP: cover-fit high-res sea backdrop (no stretch downsample), soft edge
   fade; toolbar sits right of the MAP title; Disconnect clears selected
   bubble links.

261128.06 (2026-11-28)
1. Status marquee: gear stays on primary top-right in 雙顯視屏貫穿;
   right-click bands / empty area opens the same inline settings panel.

261128.05 (2026-11-28)
1. Status marquee: centered gear; inline settings on the bands window;
   display modes 單一全視窗化 / 雙顯視屏貫穿; 文字移動速度; 斜線帶的大小.

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
