@echo off
chcp 65001 >nul
echo Building DesktopPet single-file EXE...
py -m PyInstaller --noconfirm --onefile --windowed --icon "logo.ico" --add-data "packaging\config.json;." --add-data "paypal_qr.jpg;." --add-data "logo.ico;." --add-data "logo.png;." --add-data "README.txt;." --name "DesktopPet" desktop_pet.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)
echo.
echo Copying a blank portable folder...
if not exist "DesktopPet_Portable" mkdir "DesktopPet_Portable"
copy /Y "dist\DesktopPet.exe" "DesktopPet_Portable\DesktopPet.exe" >nul
copy /Y "packaging\config.json" "DesktopPet_Portable\config.json" >nul
if exist "How to use.jpg" copy /Y "How to use.jpg" "DesktopPet_Portable\How to use.jpg" >nul
echo.
echo Done.
echo   dist\DesktopPet.exe
echo   DesktopPet_Portable\  (blank config, no personal paths)
pause
