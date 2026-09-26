@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Stop %*
if errorlevel 1 (pause) else (ping -n 3 127.0.0.1 >nul)
