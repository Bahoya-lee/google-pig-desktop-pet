# -*- coding: utf-8 -*-
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root "dist\谷歌猪桌宠.exe"

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host ""
    Write-Host "找不到 dist\谷歌猪桌宠.exe，请先运行“打包exe.bat”。" -ForegroundColor Yellow
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $desktop) {
    $desktop = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Desktop"
}
$link = Join-Path $desktop "谷歌猪桌宠.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = Split-Path $exe
$shortcut.IconLocation = $exe + ",0"
$shortcut.Description = "谷歌猪桌宠"
$shortcut.Save()

Write-Host ""
Write-Host "已创建桌面快捷方式：" -ForegroundColor Green
Write-Host $link

