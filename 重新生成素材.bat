@echo off
chcp 936 >nul
cd /d "%~dp0"
title 重新生成谷歌猪桌宠素材

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [错误] 没有检测到 Python。
  echo.
  pause
  exit /b 1
)

python "tools\prepare_assets.py" --source "D:\Downloads\谷歌猪"
echo.
if errorlevel 1 (
  echo   素材生成失败，请检查图片目录和 Pillow 是否已安装。
) else (
  echo   素材已重新生成。
)
pause
exit /b %errorlevel%

