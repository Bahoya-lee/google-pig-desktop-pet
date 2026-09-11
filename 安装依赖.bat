@echo off
chcp 936 >nul
cd /d "%~dp0"
title 安装谷歌猪桌宠依赖

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [错误] 没有检测到 Python。
  echo   请先安装 Python 3.9 以上版本，并勾选 Add Python to PATH。
  echo.
  pause
  exit /b 1
)

python -m pip install -r "requirements.txt"
echo.
if errorlevel 1 (
  echo   依赖安装失败，请检查网络后重试。
) else (
  echo   依赖安装完成。
)
pause
exit /b %errorlevel%