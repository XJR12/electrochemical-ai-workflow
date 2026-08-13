@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run-electrochem.ps1" -Task "LSV+Tafel"
pause
