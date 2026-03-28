@echo off
chcp 65001 >nul
cd /d "%~dp0"
python bootstrap.py
if %ERRORLEVEL% NEQ 0 (
    if exist .bootstrap_done del .bootstrap_done
    echo.
    echo 程序异常退出 (错误码: %ERRORLEVEL%)
    echo 下次启动将重新检查环境。
)
pause
