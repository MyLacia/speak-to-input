@echo off
chcp 65001 >nul
echo ========================================
echo  Speak to Input - 一键安装
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] 检查 Python 版本...
python --version

echo.
echo [2/5] 创建虚拟环境...
if exist venv_py39 (
    echo 虚拟环境已存在，跳过创建
) else (
    python -m venv venv_py39
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo 虚拟环境创建成功
)

echo.
echo [3/5] 安装 PyTorch CPU 版本...
venv_py39\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo [警告] PyTorch 安装失败，尝试继续...
)

echo.
echo [4/5] 安装依赖包...
venv_py39\Scripts\python.exe -m pip install --upgrade pip
venv_py39\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)
echo 依赖安装完成

echo.
echo [5/5] 下载 Paraformer 模型...
echo 注意: 首次下载需要时间（约3-10分钟）
echo.
venv_py39\Scripts\python.exe download_model.py
if errorlevel 1 (
    echo [警告] 模型下载可能失败，可以稍后手动运行 download_model.py
)

echo.
echo ========================================
echo  安装完成！
echo ========================================
echo.
echo 运行方式:
echo   1. 双击 run_cli.bat
echo   2. 或命令行: venv_py39\Scripts\python.exe run_cli.py
echo.
pause
