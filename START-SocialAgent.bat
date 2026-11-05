@echo off
REM Double-click to start SocialAgent from the USB drive (Windows 10/11).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 pause
