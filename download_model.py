# -*- coding: utf-8 -*-
"""
自动下载 Whisper 模型
使用国内镜像加速下载
"""
import os
import sys
from pathlib import Path

# 设置使用国内镜像
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

def download_model():
    """下载 Whisper 模型"""
    print("=" * 50)
    print("下载 Whisper 模型（使用国内镜像）")
    print("=" * 50)
    print()
    print("镜像源: https://hf-mirror.com")
    print()

    # 读取配置获取模型大小
    model_size = "base"  # 默认使用 base 模型
    config_file = Path(__file__).parent / "config.yaml"

    if config_file.exists():
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if config and 'transcriber' in config:
                    model_size = config['transcriber'].get('model_size', 'base')
        except:
            pass

    print(f"将下载模型: {model_size}")
    print()

    # 模型信息
    models_info = {
        'tiny': {'repo': 'Systran/faster-whisper-tiny', 'size': '~50MB'},
        'base': {'repo': 'Systran/faster-whisper-base', 'size': '~140MB'},
        'small': {'repo': 'Systran/faster-whisper-small', 'size': '~460MB'},
        'medium': {'repo': 'Systran/faster-whisper-medium', 'size': '~1.5GB'},
        'large': {'repo': 'Systran/faster-whisper-large-v3', 'size': '~3GB'},
    }

    info = models_info.get(model_size, models_info['base'])
    print(f"模型大小: {info['size']}")
    print(f"预计时间: 3-10 分钟（取决于网络速度）")
    print()

    try:
        from huggingface_hub import snapshot_download

        models_dir = Path(__file__).parent / "models"
        models_dir.mkdir(exist_ok=True)

        print(f"正在从 {info['repo']} 下载...")
        print()

        snapshot_download(
            repo_id=info['repo'],
            local_dir=models_dir / model_size,
            local_dir_use_symlinks=False
        )

        print()
        print("=" * 50)
        print("下载完成！")
        print("=" * 50)
        print(f"模型保存在: {models_dir / model_size}")

        # 显示文件大小
        model_path = models_dir / model_size
        if model_path.exists():
            total_size = sum(f.stat().st_size for f in model_path.rglob('*') if f.is_file())
            print(f"实际大小: {total_size / (1024**2):.0f} MB")

        print()
        print("现在可以运行应用了:")
        print("  双击 run_cli.bat 或运行 python run_cli.py")

        return True

    except ImportError:
        print("[错误] 缺少 huggingface-hub 库")
        print("请先运行: venv_py39\\Scripts\\python.exe -m pip install huggingface-hub")
        return False
    except Exception as e:
        print(f"[错误] 下载失败: {e}")
        print()
        print("可以尝试手动下载:")
        print(f"  1. 访问 https://hf-mirror.com/{info['repo']}")
        print(f"  2. 下载所有文件到 models/{model_size}/ 目录")
        return False

if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)
