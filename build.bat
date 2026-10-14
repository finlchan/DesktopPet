@echo off
chcp 65001 >nul
echo Building DesktopPet...
py -m PyInstaller --noconfirm --onefile --windowed --icon "logo.ico" --add-data "packaging\config.json;." --add-data "paypal_qr.jpg;." --add-data "logo.ico;." --add-data "logo.png;." --add-data "README.txt;." --name "DesktopPet" desktop_pet.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

if not exist "上載版" mkdir "上載版"
copy /Y "dist\DesktopPet.exe" "上載版\DesktopPet.exe" >nul
copy /Y "packaging\config.json" "上載版\config.json" >nul
if exist "How to use.jpg" copy /Y "How to use.jpg" "上載版\How to use.jpg" >nul

rmdir /s /q build
rmdir /s /q dist
del /q DesktopPet.spec

echo.
echo Done. Share this folder: 上載版
pause
