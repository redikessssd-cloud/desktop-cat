@echo off
chcp 65001 >nul
setlocal enableextensions enabledelayedexpansion
title Desktop Cat - установка
cd /d "%~dp0"

set "REPO=https://raw.githubusercontent.com/redikessssd-cloud/desktop-cat/main"
set "DEST=%LOCALAPPDATA%\DesktopCat"
set "FILES=cat.py cat.png cat_stretch.png cat_scratch.png cat_play.png cat_stand.png cat_walk.png cat_walkf.png cat_sleep.png cat_type.png"

echo ============================================
echo    Установка Desktop Cat
echo ============================================
echo.

REM --- 1. ищем Python ---
set "PYEXE="
for /f "delims=" %%P in ('where python 2^>nul') do (
    set "PYEXE=%%P"
    goto :gotpy
)
:gotpy
if "%PYEXE%"=="" (
    echo [!] Python не найден.
    echo     Скачай Python 3 с https://www.python.org/downloads/
    echo     ВАЖНО: при установке поставь галочку "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
for %%I in ("%PYEXE%") do set "PYDIR=%%~dpI"
set "PYW=%PYDIR%pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
echo [1/4] Python найден: %PYEXE%

REM --- 2. зависимости ---
echo [2/4] Ставлю библиотеки (pillow, pynput)...
python -m pip install --user --upgrade pip >nul 2>&1
python -m pip install --user pillow pynput
if errorlevel 1 (
    echo [!] Не удалось поставить зависимости. Проверь интернет и попробуй снова.
    pause
    exit /b 1
)

REM --- 3. качаем котика ---
echo [3/4] Качаю котика в "%DEST%"...
if not exist "%DEST%" mkdir "%DEST%"
for %%F in (%FILES%) do (
    echo      - %%F
    curl -L -s -o "%DEST%\%%F" "%REPO%/%%F"
    if errorlevel 1 powershell -NoProfile -Command "Invoke-WebRequest -Uri '%REPO%/%%F' -OutFile '%DEST%\%%F'" >nul 2>&1
)
if not exist "%DEST%\cat.py" (
    echo [!] Не удалось скачать cat.py. Проверь интернет.
    pause
    exit /b 1
)

REM --- 4. автозапуск + ярлык ---
echo [4/4] Добавляю в автозапуск Windows...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%STARTUP%\DesktopCat.lnk'); $s.TargetPath='%PYW%'; $s.Arguments='\"%DEST%\cat.py\"'; $s.WorkingDirectory='%DEST%'; $s.Save()" >nul 2>&1
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%DEST%\Запустить котика.lnk'); $s.TargetPath='%PYW%'; $s.Arguments='\"%DEST%\cat.py\"'; $s.WorkingDirectory='%DEST%'; $s.Save()" >nul 2>&1

echo.
echo [OK] Готово! Котик установлен и будет запускаться при входе в Windows.
echo      Запускаю сейчас...
start "" "%PYW%" "%DEST%\cat.py"
echo.
echo  Чтобы удалить - запусти uninstall.bat
pause
exit /b 0
