@echo off
chcp 65001 >nul
cd /d "%~dp0"
python bootstrap.py
if %ERRORLEVEL% NEQ 0 (
    if exist .bootstrap_done del .bootstrap_done
    echo.
    echo Error exit code: %ERRORLEVEL%
    echo Will re-check environment on next launch.
)
pause
