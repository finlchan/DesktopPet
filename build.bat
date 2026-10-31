@echo off
REM ---------------------------------------------------------------------------
REM Release / upload packaging rules - do not relax:
REM - NEVER copy the working-tree config.json (may contain personal paths/data).
REM - NEVER copy Data/, save folders, or personal pet/picture files.
REM - Only ship: built EXE + packaging\config.json blank template + app assets
REM   How-to-use.pdf / How-to-use.png, plus assets already bundled into the EXE via --add-data.
REM Output folder is ASCII "upload" so cmd.exe parses this script reliably.
REM ---------------------------------------------------------------------------
echo Building DesktopPet...

if not exist "packaging\config.json" (
    echo ERROR: packaging\config.json missing. Refusing to build without blank template.
    pause
    exit /b 1
)

REM Prefer Windows Python launcher, then python / python3 on PATH.
set "PY_CMD="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
    python3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python3"
)
if not defined PY_CMD (
    echo ERROR: Python not found. Install from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then reopen this terminal.
    pause
    exit /b 1
)
echo Using: %PY_CMD%

REM Bundle only the blank template config into the EXE - never root config.json.
REM hakoniwa/ + fish_tank/ are lazy-imported from Mini programs; openpyxl/xlrd for Free Station IMPORT.
REM hakoniwa/assets (terrain tops + ocean backdrop) must ship with the EXE.
%PY_CMD% -m PyInstaller --noconfirm --onefile --windowed --icon "logo.ico" --add-data "packaging\config.json;." --add-data "paypal_qr.jpg;." --add-data "logo.ico;." --add-data "logo.png;." --add-data "README.txt;." --add-data "hakoniwa\assets;hakoniwa/assets" --hidden-import hakoniwa --hidden-import hakoniwa.dialog --hidden-import hakoniwa.view --hidden-import hakoniwa.model --hidden-import hakoniwa.grid --hidden-import hakoniwa.tiles --hidden-import hakoniwa.user_art --hidden-import hakoniwa.save --hidden-import hakoniwa.remote --collect-submodules hakoniwa --hidden-import fish_tank --hidden-import fish_tank.dialog --hidden-import fish_tank.view --hidden-import fish_tank.model --hidden-import fish_tank.sprites --hidden-import fish_tank.species --hidden-import fish_tank.save --hidden-import fish_tank.world --hidden-import fish_tank.remote_stubs --hidden-import fish_tank.social_toolbar --collect-submodules fish_tank --hidden-import openpyxl --hidden-import xlrd --collect-submodules openpyxl --name "DesktopPet" desktop_pet.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM Rebuild upload folder from scratch so leftover personal files cannot linger.
if exist "upload" rmdir /s /q "upload"
mkdir "upload"

copy /Y "dist\DesktopPet.exe" "upload\DesktopPet.exe" >nul
if errorlevel 1 (
    echo ERROR: could not copy DesktopPet.exe into upload.
    pause
    exit /b 1
)

REM Blank template only - do NOT use .\config.json from the working tree.
copy /Y "packaging\config.json" "upload\config.json" >nul
if exist "How-to-use.pdf" copy /Y "How-to-use.pdf" "upload\How-to-use.pdf" >nul
if exist "How-to-use.png" copy /Y "How-to-use.png" "upload\How-to-use.png" >nul

rmdir /s /q build
rmdir /s /q dist
del /q DesktopPet.spec 2>nul

echo.
echo Done. Share this folder: upload
echo config.json there is the blank packaging template - not your personal config.
pause
