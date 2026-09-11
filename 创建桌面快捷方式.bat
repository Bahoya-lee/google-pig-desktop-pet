@echo off
chcp 936 >nul
cd /d "%~dp0"
title 创建谷歌猪桌面快捷方式

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0创建桌面快捷方式.ps1"
echo.
pause
exit /b %errorlevel%

