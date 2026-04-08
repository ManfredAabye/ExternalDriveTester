@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "APP_NAME=ExternalDriveTester"
set "SCRIPT=ExternalDriveTester.py"
set "ICON_PNG=icon.png"
set "ICON_ICO=icon.ico"

if not exist "%SCRIPT%" (
	echo [FEHLER] Datei "%SCRIPT%" wurde nicht gefunden.
	pause
	exit /b 1
)

if not exist "window.png" (
	echo [WARNUNG] window.png nicht gefunden. Fenstersymbol in der EXE kann fehlen.
)

if not exist "titel.png" (
	echo [WARNUNG] titel.png nicht gefunden. Titelbild im Programm kann fehlen.
)

echo [INFO] Pruefe PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
	echo [INFO] PyInstaller ist nicht installiert. Installiere...
	python -m pip install --upgrade pip pyinstaller
	if errorlevel 1 (
		echo [FEHLER] PyInstaller konnte nicht installiert werden.
		pause
		exit /b 1
	)
)

echo [INFO] Alte Build-Ordner werden entfernt...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

if exist "%ICON_ICO%" del /q "%ICON_ICO%"

if exist "%ICON_PNG%" (
	echo [INFO] Erzeuge %ICON_ICO% aus %ICON_PNG% ...
	python -c "from PIL import Image; Image.open(r'%ICON_PNG%').save(r'%ICON_ICO%', format='ICO')" >nul 2>&1
	if errorlevel 1 (
		echo [WARNUNG] icon.png konnte nicht in icon.ico umgewandelt werden. Versuche Installation von Pillow...
		python -m pip install pillow >nul 2>&1
		python -c "from PIL import Image; Image.open(r'%ICON_PNG%').save(r'%ICON_ICO%', format='ICO')" >nul 2>&1
	)
)

echo [INFO] Erstelle Einzeldatei-EXE...
set "ICON_ARG="
if exist "%ICON_ICO%" set "ICON_ARG=--icon %ICON_ICO%"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%APP_NAME%" ^
	%ICON_ARG% ^
	--add-data "icon.ico;." ^
	--add-data "window.png;." ^
	--add-data "titel.png;." ^
	--add-data "ExternalDriveTesterTR.png;." ^
	--add-data "ExternalDriveTester1.png;." ^
  --collect-all ttkbootstrap ^
  "%SCRIPT%"

if errorlevel 1 (
	echo [FEHLER] Build fehlgeschlagen.
	pause
	exit /b 1
)

echo.
echo [OK] Build erfolgreich.
echo [OK] EXE: "%~dp0dist\%APP_NAME%.exe"

if exist "%ICON_ICO%" copy /y "%ICON_ICO%" "dist\%ICON_ICO%" >nul
if exist "window.png" copy /y "window.png" "dist\window.png" >nul
if exist "titel.png" copy /y "titel.png" "dist\titel.png" >nul
if exist "ExternalDriveTesterTR.png" copy /y "ExternalDriveTesterTR.png" "dist\ExternalDriveTesterTR.png" >nul
if exist "ExternalDriveTester1.png" copy /y "ExternalDriveTester1.png" "dist\ExternalDriveTester1.png" >nul
if exist "i18n.json" copy /y "i18n.json" "dist\i18n.json" >nul
echo [OK] Zusatzdateien nach dist kopiert (falls vorhanden).
echo.
pause
exit /b 0

