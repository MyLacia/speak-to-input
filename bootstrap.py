# -*- coding: utf-8 -*-
"""
Bootstrap script for Speak to Input.
Auto-detects missing dependencies and installs them before launching the app.
Runs with system Python (stdlib only) — no venv required yet.
"""

import os
import sys
import subprocess
from pathlib import Path

# --- Configuration ---
ROOT_DIR = Path(__file__).parent.resolve()
VENV_DIR = ROOT_DIR / "venv_py39"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"
REQUIREMENTS = ROOT_DIR / "requirements.txt"

# PyTorch CPU-only index (avoids downloading 2GB+ CUDA packages)
TORCH_INDEX_URL = "https://download.pytorch.org/whl/cpu"


def run(cmd, **kwargs):
    """Run a subprocess and stream output to console."""
    print(f"  > {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=str(ROOT_DIR), **kwargs)


def can_import(module_name):
    """Check if a module is importable in the venv Python."""
    result = subprocess.run(
        [str(VENV_PYTHON), "-c", f"import {module_name}"],
        capture_output=True,
    )
    return result.returncode == 0


def ensure_venv():
    """Create virtual environment if it doesn't exist."""
    if VENV_PYTHON.exists():
        print("[OK] 虚拟环境已存在")
        return True

    print("\n" + "=" * 55)
    print("  首次运行：正在创建虚拟环境...")
    print("=" * 55)

    # Determine which Python to use
    python_exe = sys.executable

    result = run([python_exe, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        print(f"[ERROR] 创建虚拟环境失败 (exit code {result.returncode})")
        return False

    if not VENV_PYTHON.exists():
        print("[ERROR] 虚拟环境创建完成但找不到 python.exe")
        return False

    # Upgrade pip to avoid old-pip issues
    print("  升级 pip...")
    run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])

    print("[OK] 虚拟环境创建完成")
    return True


def ensure_torch():
    """Install PyTorch CPU version if not present."""
    if can_import("torch"):
        print("[OK] PyTorch 已安装")
        return True

    print("\n--- 安装 PyTorch (CPU) ---")
    result = run([
        str(VENV_PIP), "install",
        "torch", "torchaudio",
        "--index-url", TORCH_INDEX_URL,
    ])
    if result.returncode != 0:
        print("[ERROR] PyTorch 安装失败")
        return False

    print("[OK] PyTorch 安装完成")
    return True


def ensure_deps():
    """Install remaining dependencies from requirements.txt."""
    if can_import("funasr"):
        print("[OK] FunASR 及依赖已安装")
        return True

    print("\n--- 安装应用依赖 ---")

    # Try bulk install first
    if REQUIREMENTS.exists():
        result = run([
            str(VENV_PIP), "install",
            "-r", str(REQUIREMENTS),
        ])
        if result.returncode == 0 and can_import("funasr"):
            print("[OK] 依赖安装完成")
            return True

    # Fallback: install packages one by one
    print("  批量安装失败，尝试逐个安装...")
    packages = [
        "modelscope>=1.9.0",
        "funasr>=1.0.0",
        "sounddevice>=0.4.6",
        "pynput>=1.7.6",
        "numpy>=1.24.0",
        "pyyaml>=6.0",
        "pyperclip>=1.8.2",
        "opencc>=1.1.6",
    ]

    failed = []
    for pkg in packages:
        print(f"  安装 {pkg}...")
        result = run([str(VENV_PIP), "install", pkg])
        if result.returncode != 0:
            failed.append(pkg)

    if failed:
        print(f"[WARN] 以下包安装失败: {', '.join(failed)}")

    # Verify funasr specifically — the most critical dependency
    if not can_import("funasr"):
        print("[ERROR] FunASR 安装失败，尝试 --no-deps 方式...")
        result = run([
            str(VENV_PIP), "install",
            "funasr", "--no-deps",
        ])
        if result.returncode != 0:
            print("[ERROR] FunASR 安装最终失败")
            return False

    print("[OK] 依赖安装完成")
    return True


def launch_app():
    """Replace current process with run_cli.py using venv Python."""
    print("\n" + "=" * 55)
    print("  启动 Speak to Input...")
    print("=" * 55 + "\n")

    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(ROOT_DIR / "run_cli.py")])


def main():
    print("Speak to Input - 环境检查")
    print()

    if not ensure_venv():
        print("\n环境准备失败，请检查错误信息。")
        input("按回车键退出...")
        sys.exit(1)

    if not ensure_torch():
        print("\nPyTorch 安装失败，请检查网络连接。")
        input("按回车键退出...")
        sys.exit(1)

    if not ensure_deps():
        print("\n依赖安装失败，请检查错误信息。")
        input("按回车键退出...")
        sys.exit(1)

    launch_app()


if __name__ == "__main__":
    main()
