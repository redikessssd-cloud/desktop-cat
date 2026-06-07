@echo off
chcp 65001 >nul
setlocal enableextensions
title Desktop Cat - удаление

set "DEST=%LOCALAPPDATA%\DesktopCat"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo Останавливаю котика...
taskkill /f /im pythonw.exe >nul 2>&1

echo Убираю из автозапуска...
del /q "%STARTUP%\DesktopCat.lnk" >nul 2>&1

echo Удаляю файлы из "%DEST%"...
rmdir /s /q "%DEST%" >nul 2>&1

echo.
echo [OK] Котик удалён.
pause
exit /b 0
