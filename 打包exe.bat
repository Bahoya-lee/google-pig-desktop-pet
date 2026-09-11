@echo off
chcp 936 >nul
cd /d "%~dp0"
title 打包谷歌猪桌宠 exe

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [错误] 没有检测到 Python。
  echo.
  pause
  exit /b 1
)

python -c "import PyInstaller, PySide6" >nul 2>nul
if errorlevel 1 (
  echo   正在安装打包依赖...
  python -m pip install --disable-pip-version-check pyinstaller PySide6
  if errorlevel 1 (
    echo   依赖安装失败。
    pause
    exit /b 1
  )
)

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "谷歌猪桌宠" ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  --distpath dist ^
  --workpath build ^
  --specpath . ^
  app_qt.py

if errorlevel 1 (
  echo.
  echo   exe 打包失败，请查看上方错误。
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0创建桌面快捷方式.ps1"
echo.
echo   打包完成：
echo   %~dp0dist\谷歌猪桌宠.exe
pause
exit /b 0