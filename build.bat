@echo off
chcp 65001 >nul
REM ---------------------------------------------------------------------------
REM Release / 「上載版」 packaging rules (do not relax):
REM - NEVER copy the working-tree config.json (may contain personal paths/data).
REM - NEVER copy Data/, save folders, or personal pet/picture files.
REM - Only ship: built EXE + packaging\config.json (blank template) + app assets
REM   (How to use.jpg, and assets already bundled into the EXE via --add-data).
REM ---------------------------------------------------------------------------
echo Building DesktopPet...

if not exist "packaging\config.json" (
    echo ERROR: packaging\config.json missing. Refusing to build without blank template.
    pause
    exit /b 1
)

REM Bundle only the blank template config into the EXE — never root config.json.
py -m PyInstaller --noconfirm --onefile --windowed --icon "logo.ico" --add-data "packaging\config.json;." --add-data "paypal_qr.jpg;." --add-data "logo.ico;." --add-data "logo.png;." --add-data "README.txt;." --name "DesktopPet" desktop_pet.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

REM Rebuild 「上載版」 from scratch so leftover personal files cannot linger.
if exist "上載版" rmdir /s /q "上載版"
mkdir "上載版"

copy /Y "dist\DesktopPet.exe" "上載版\DesktopPet.exe" >nul
REM Blank template only — do NOT use .\config.json from the working tree.
copy /Y "packaging\config.json" "上載版\config.json" >nul
if exist "How to use.jpg" copy /Y "How to use.jpg" "上載版\How to use.jpg" >nul

rmdir /s /q build
rmdir /s /q dist
del /q DesktopPet.spec 2>nul

echo.
echo Done. Share this folder: 上載版
echo (config.json is the blank packaging template — not your personal config.)
pause
