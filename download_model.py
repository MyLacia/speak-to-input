# -*- coding: utf-8 -*-
"""
自动下载 FunASR Paraformer 模型
使用 ModelScope 自动下载
"""
import sys


def download_model():
    """下载 Paraformer 模型"""
    print("=" * 50)
    print("下载 FunASR Paraformer-zh 模型")
    print("=" * 50)
    print()
    print("模型: paraformer-zh (中文语音识别专用)")
    print("大小: 约 220MB")
    print("预计时间: 3-10 分钟（取决于网络速度）")
    print()

    try:
        from funasr import AutoModel

        print("正在下载并加载模型...")
        print()

        # This will auto-download the model from ModelScope on first run
        model = AutoModel(model="paraformer-zh", device="cpu")

        print()
        print("=" * 50)
        print("下载完成！")
        print("=" * 50)
        print()
        print("现在可以运行应用了:")
        print("  双击 run_cli.bat 或运行 python run_cli.py")

        return True

    except ImportError:
        print("[错误] 缺少 funasr 库")
        print("请先运行: venv_py39\\Scripts\\python.exe -m pip install funasr")
        return False
    except Exception as e:
        print(f"[错误] 下载失败: {e}")
        print()
        print("可以尝试手动安装:")
        print("  1. pip install funasr modelscope")
        print("  2. 重新运行此脚本")
        return False


if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)
