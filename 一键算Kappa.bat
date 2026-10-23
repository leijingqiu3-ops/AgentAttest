@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Computing Cohen's kappa...
echo.
python scripts\compute_kappa.py
echo.
pause
