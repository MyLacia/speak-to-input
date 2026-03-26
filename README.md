# Speak to Input - 实时语音转文本输入桌面应用

一个 Windows 桌面应用，能够实时捕获麦克风输入，使用本地 Whisper 模型进行语音识别，并将识别结果模拟键盘输入发送到任意应用程序中。

## 效果演示

```
1. 打开记事本/微信/浏览器等任意应用
2. 按住 ALT 键
3. 说话："你好世界"
4. 松开 ALT 键
5. 文字自动输入到应用中
```

## 功能特点

- **实时语音识别**: 使用 faster-whisper 本地模型，无需网络连接
- **ALT 键触发**: 按住 ALT 键开始说话，松开自动发送
- **中文识别**: 默认中文语言，支持中英文混合
- **剪贴板输入**: 通过剪贴板 + Ctrl+V 实现稳定的中文输入
- **CPU 优化**: 自动检测 CPU 指令集，选择最佳计算类型
- **命令行模式**: 简洁的命令行界面，避免 GUI 冲突

## 使用方法（三步即可）

### 步骤 1：克隆项目

```bash
git clone https://github.com/MyLacia/speak-to-input.git
cd speak-to-input
```

### 步骤 2：安装依赖并下载模型

```bash
# 创建 Python 3.9 虚拟环境
python -m venv venv_py39

# 激活虚拟环境
venv_py39\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 下载模型（选择以下任一方式）
```

**下载模型方式：**

1. **手动下载（推荐）**：
   - 访问 https://hf-mirror.com/Systran/faster-whisper-small/tree/main
   - 下载 `model.bin` 文件
   - 创建文件夹 `models/small/`，放入 `model.bin`

2. **Python 脚本下载**：
   ```python
   import os
   os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
   from huggingface_hub import snapshot_download
   snapshot_download("Systran/faster-whisper-small", local_dir="models/small")
   ```

### 步骤 3：运行应用

**双击运行：**
```
run_cli.bat
```

**命令行运行：**
```bash
venv_py39\Scripts\python.exe cli_app.py
```

### 开始使用

1. 看到提示后，打开记事本或任何你想输入文字的应用
2. **按住 ALT 键** 开始说话
3. **松开 ALT 键** 自动发送文字

## 配置说明

创建 `config.yaml` 文件（如果不存在）：

```yaml
# 转录器配置
transcriber:
  model_size: small      # 模型: tiny/base/small/medium/large
  language: zh           # 语言: zh=中文, en=英文, null=自动检测
  compute_type: auto     # 计算类型: auto=自动选择

# 音频配置
audio:
  sample_rate: 16000     # 采样率
  device_index: null     # 麦克风设备索引（留空使用默认）

# 键盘配置
keyboard:
  method: clipboard      # 输入方式: clipboard=剪贴板
```

## 模型对比

| 模型 | 大小 | 延迟 | CPU占用 | 内存占用 | 精度 |
|------|------|------|---------|----------|------|
| tiny | ~50MB | <1s | ~15% | ~500MB | 一般 |
| base | ~140MB | <2s | ~25% | ~700MB | 良好 |
| small | ~460MB | <3s | ~35% | ~1GB | 很好 |

*以上数据基于 Intel CPU, 无 GPU*

## 系统要求

- **操作系统**: Windows 10/11 (64位)
- **Python**: 3.9+ (推荐 3.9)
- **内存**: 至少 4GB RAM
- **麦克风**: 系统默认麦克风

## 项目结构

```
speak_to_input/
├── cli_app.py              # 命令行版本入口
├── run_cli.bat             # 快速启动脚本
├── main.py                 # 原始GUI入口（已弃用）
├── run_dev.bat             # 开发模式启动
├── requirements.txt        # 依赖列表
├── config.yaml             # 配置文件
├── src/                    # 源代码
│   ├── audio_capture.py   # 音频捕获
│   ├── vad_detector.py    # 语音检测
│   ├── transcriber.py     # 语音识别引擎
│   ├── keyboard_emulator.py # 键盘模拟
│   └── config.py          # 配置管理
├── models/                 # Whisper 模型
│   ├── base/              # base 模型
│   └── small/             # small 模型
└── venv_py39/             # Python 3.9 虚拟环境
```

## 故障排除

### 1. 模型加载失败

**原因**: CTranslate2 C++ 库与 Python 版本不兼容

**解决方法**:
- 使用 Python 3.9（不要使用 3.14+）
- 确保 `compute_type: auto` 配置正确

### 2. 麦克风无法使用

- 检查系统麦克风权限
- 确认其他应用可以正常使用麦克风
- 在 `config.yaml` 中设置 `device_index`

### 3. 识别不准确

- 切换到更大的模型 (small/medium)
- 确保麦克风清晰，环境安静
- 靠近麦克风说话

## 常见问题

**Q: 为什么使用命令行版本？**
A: PyQt5 GUI 与 CTranslate2 C++ 库存在兼容性问题，命令行版本更稳定。

**Q: 如何切换回 GUI 版本？**
A: 运行 `python main.py`，但可能遇到模型加载崩溃问题。

**Q: 支持其他语言吗？**
A: 支持所有 Whisper 支持的语言，修改 `config.yaml` 中的 `language` 配置。

## 依赖项

```
faster-whisper >= 1.0.0
ctranslate2 >= 4.0.0
sounddevice >= 0.5.0
pynput >= 1.8.0
PyYAML >= 6.0
numpy >= 1.24.0
```

## 更新日志

### v2.0.0 (当前)
- ✅ 重构为命令行版本，修复 C++ 库冲突
- ✅ 添加 Python 3.9 虚拟环境支持
- ✅ 添加 compute_type 自动降级 (int8 -> float32)
- ✅ 修复批处理文件编码问题
- ✅ 简化项目结构，移除 GUI 依赖

### v1.2.0
- ✅ 修复模型加载崩溃问题
- ✅ 添加诊断工具

### v1.0.0
- ✅ 初始版本
- ✅ ALT 键触发语音输入
- ✅ faster-whisper 本地模型

## 许可证

MIT License
