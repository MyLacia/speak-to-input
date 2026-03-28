@echo off
chcp 65001 >nul
cd /d "%~dp0"
venv_py39\Scripts\python.exe run_cli.py
pause
