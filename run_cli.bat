@echo off
chcp 65001 >/dev/null
cd /d "%~dp0"
python run_cli.py
pause
