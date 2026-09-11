@echo off
chcp 936 >nul
cd /d "%~dp0"
title 谷歌猪桌宠

where pythonw >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo.
    echo   [错误] 没有检测到 Python。
    echo   请先安装 Python 3.9 以上版本，并勾选 Add Python to PATH。
    echo.
    pause
    exit /b 1
  )
  python -c "import PySide6" >nul 2>nul
  if errorlevel 1 (
    start "" "安装依赖.bat"
    exit /b 0
  )
  start "" python "app_qt.py"
) else (
  python -c "import PySide6" >nul 2>nul
  if errorlevel 1 (
    start "" "安装依赖.bat"
    exit /b 0
  )
  start "" pythonw "app_qt.py"
)
exit /b 0