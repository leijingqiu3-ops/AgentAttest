@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo  Cohen kappa, round 2
echo.
python scripts\compute_kappa.py --sheet reports\labeling_sheet_labeled_round2.csv
echo.
pause
