@echo off
REM One-time setup: installs llama.cpp, a portable Python on the drive, and downloads the Qwen2.5-7B model.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\setup-windows.ps1" %*
pause
