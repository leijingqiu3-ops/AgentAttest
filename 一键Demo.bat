@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ==========================================
echo   Agent Audit Demo
echo   Press Enter at each pause to continue.
echo  ==========================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo.ps1"
echo.
echo Done. You can stop recording now.
pause
