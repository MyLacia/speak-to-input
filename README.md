# Speak to Input - 实时语音转文本输入

> 本地语音识别，实时文字输入。基于 faster-whisper，无需网络连接。

**注意：持续检测模式（说"嘿"触发）目前存在 bug，暂时无法修复，请不要使用。请使用鼠标长按模式。**

---

## 使用方法

### 启动程序

双击 `run_cli.bat` 或在命令行运行：

```bash
python run_cli.py                     # 默认鼠标模式
python run_cli.py --mode continuous   # 持续模式
```

### 两种监听模式

#### 鼠标模式（默认）
- **在输入框中长按鼠标左键** - 开始说话
- **松开鼠标左键** - 识别并发送文本

> **智能光标检测**: 只有在有输入光标的位置（如文本框、搜索框等）才会触发，避免误操作。

#### 持续模式
- 说 **"嘿"** - 触发录音（支持模糊匹配：诶、哎、咳、黑、喂、哈等）
- 停顿 **0.5 秒** - 开始录音
- 静音 **2 秒** - 自动结束并发送

> **提示**: 使用滑动窗口检测技术，确保不会漏掉跨越音频块边界的语音。

### 快捷键

| 按键 | 功能 |
|------|------|
| **鼠标左键 (长按)** | 开始录音（鼠标模式） |
| **鼠标左键 (松开)** | 停止录音并发送（鼠标模式） |
| **c** | 切换监听模式（仅在命令行窗口有效） |
| **q** | 退出程序 |

### 使用演示

```
1. 启动程序后，打开记事本/微信/浏览器
2. 点击输入框，长按鼠标左键（鼠标模式）或 说"嘿"（持续模式）
3. 说话："你好世界"
4. 松开鼠标（鼠标模式）或 等待自动发送（持续模式）
5. 文字自动输入！
```

---

## 快速开始（Windows）

### 第一次使用：

```
1. 双击运行 install.bat
2. 等待自动安装和下载模型（约5-10分钟）
3. 双击运行 run_cli.bat
4. 打开记事本，在输入框长按鼠标左键说话
```

### 手动安装：

```bash
# 1. 克隆项目
git clone https://github.com/MyLacia/speak-to-input.git
cd speak-to-input

# 2. 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. (可选) 安装 OpenCC 用于繁简转换
pip install opencc

# 4. 运行
python run_cli.py
```

---

## 功能特点

- **两种监听模式**: 鼠标长按触发 / 关键词持续监听
- **智能光标检测**: 只有在有输入光标的位置才会触发录音，避免误操作
- **实时语音识别**: 使用 faster-whisper 本地模型，无需网络连接
- **智能关键词检测**:
  - 滑动窗口检测（50% 重叠），防止漏检跨边界的语音
  - 模糊匹配支持（嘿、诶、哎、咳、黑、喂、哈等）
  - 0.6秒快速响应检测
- **中文识别**: 默认中文语言，支持中英文混合
- **简体中文输出**: 自动将繁体转换为简体（需安装 opencc）
- **剪贴板输入**: 通过剪贴板 + Ctrl+V 实现稳定的中文输入
- **CPU 优化**: 自动检测 CPU 指令集，选择最佳计算类型
- **命令行界面**: 简洁高效，避免 GUI 兼容性问题
- **调试日志**: 详细的日志输出，方便排查问题

---

## 系统要求

- **操作系统**: Windows 10/11 (64位)
- **Python**: 3.8 或更高版本（推荐 3.9+）
- **内存**: 至少 4GB RAM
- **网络**: 首次运行需要下载模型

---

## 模型说明

| 模型 | 大小 | 下载时间 | 识别精度 | 推荐场景 |
|------|------|----------|----------|----------|
| tiny | ~50MB | ~1分钟 | 一般 | 快速测试 |
| base | ~140MB | ~3分钟 | 良好 | 日常使用 |
| small | ~460MB | ~10分钟 | 很好 | 精准识别（默认） |

*下载时间基于国内镜像，实际速度取决于网络*

当前默认使用 `small` 模型，可在 `config.yaml` 中切换。

---

## 配置文件

创建 `config.yaml` 文件（可选，首次运行会自动创建默认配置）：

```yaml
# 语音识别配置
transcriber:
  model_size: small      # 模型: tiny/base/small/medium/large
  language: zh           # 语言: zh=中文, en=英文
  compute_type: auto     # 计算类型: auto=自动检测
  beam_size: 5           # 搜索宽度
  num_workers: 1

# 音频配置
audio:
  sample_rate: 16000     # 采样率
  channels: 1            # 声道数
  chunk_duration: 0.5    # 音频块时长（秒）
  device_index: null     # 麦克风设备（留空使用默认）
  silence_threshold: 0.002  # 静音能量阈值

# 键盘配置
keyboard:
  method: clipboard      # 输入方式: clipboard=剪贴板
  paste_delay: 0.1       # 粘贴后延迟（秒）

# 快捷键配置
hotkey:
  toggle: <ctrl>+<shift>+<r>  # 开始/停止识别
  pause: <ctrl>+<shift>+<p>   # 暂停/恢复
  clear: <ctrl>+<shift>+<c>   # 清除当前文本

# 语音活动检测
vad:
  enabled: true
  threshold: 0.5               # 语音概率阈值
  min_silence_duration_ms: 800 # 静音判定时长
  speech_pad_ms: 400           # 语音前后填充

# 持续模式配置
continuous:
  enabled: false
  trigger_word: "嘿"     # 触发关键词
  pause_threshold: 0.5   # 触发后停顿时间（秒）
  timeout_duration: 2.0  # 静音超时时间（秒）
  min_capture_duration: 0.3
  buffer_duration: 5.0   # 预缓冲时长（秒）
```

---

## 故障排除

### 1. 找不到 Python

```bash
# 检查 Python 是否安装
python --version

# 如果未安装，下载: https://www.python.org/downloads/
# 安装时勾选 "Add Python to PATH"
```

### 2. 识别到虚假文本（如"字幕by索兰娅"）

**原因**：这是Whisper模型的**幻觉输出**（Hallucination）现象。在静音或噪声环境下，模型会输出训练数据中的常见文本模式。

**已内置的解决方案**：
- 程序已自动过滤已知的幻觉文本
- 只有在有真实声音（能量超过阈值）时才进行识别
- 置信度过滤：低置信度的输出会被忽略

**如果问题仍然存在**：
1. 确保麦克风正常工作，对着麦克风说话测试
2. 提高说话音量，确保音频能量超过阈值
3. 减少背景噪音
4. 在 `config.yaml` 中调整 `silence_threshold`（默认0.002）

### 3. 模型下载失败

- 使用国内镜像，脚本已自动配置
- 如果仍然失败，手动下载：
  - 访问 https://hf-mirror.com/Systran/faster-whisper-small
  - 下载模型文件到 `models/small/` 目录

### 4. 麦克风无法使用

- 检查系统麦克风权限
- 确认其他应用可以正常使用麦克风
- 可在 `config.yaml` 中指定设备索引：

```yaml
audio:
  device_index: 1  # 修改为你的麦克风设备索引
```

### 5. 中文无法输入

- 确保使用 "clipboard" 输入方式（默认）
- 检查目标应用是否支持 Ctrl+V 粘贴

### 6. 程序启动时崩溃

- 这是 CTranslate2 C++ 库的兼容性问题
- 程序已内置 compute_type 自动降级机制（int8 → float32）
- 尝试更新 faster-whisper 到最新版本

### 7. 持续模式关键词检测不灵敏

- **确保发音清晰**: 清楚地说 "嘿" (hēi)
- **查看日志文件**: 检查 `logs/cli.log` 查看 Whisper 实际识别的内容
- **调整触发词**: 如果识别不准确，可以在 `config.yaml` 中修改 `trigger_word`
- **提高麦克风音量**: 确保麦克风有足够的增益
- **减少环境噪音**: 背景噪音可能影响识别准确度

**日志示例**:
```
INFO - Checking for '嘿' in: '你好'
INFO - Checking for '嘿' in: '嘿'
INFO - Trigger word '嘿' detected
INFO - Pause detected after trigger, starting capture
```

---

## 项目结构

```
speak-to-input/
├── install.bat           # 一键安装脚本
├── install_opencc.bat    # OpenCC 繁简转换安装脚本
├── run_cli.bat           # 启动脚本
├── run_cli.py            # CLI 主程序
├── download_model.py     # 模型下载脚本
├── requirements.txt      # 依赖列表
├── config.yaml           # 配置文件
├── src/                  # 源代码
│   ├── config.py         # 配置管理
│   ├── transcriber.py    # 语音识别引擎
│   ├── audio_capture.py  # 音频捕获
│   ├── vad_detector.py   # 语音活动检测
│   └── keyboard_emulator.py  # 键盘/鼠标模拟
├── models/               # 模型目录（自动下载）
│   └── small/            # Whisper small 模型
└── logs/                 # 日志目录（自动创建）
```

---

## 依赖项

```
faster-whisper >= 1.0.0
sounddevice >= 0.4.6
pynput >= 1.7.6
PyYAML >= 6.0
numpy >= 1.24.0
pyperclip >= 1.8.2
huggingface-hub >= 0.17.0
opencc >= 1.1.6           # 繁简转换（可选）
```

---

## 常见问题

**Q: 为什么使用命令行版本？**
A: PyQt5 GUI 与 CTranslate2 C++ 库存在兼容性问题，命令行版本更稳定。

**Q: 支持其他语言吗？**
A: 支持，修改 `config.yaml` 中的 `language` 配置。

**Q: 可以使用 GPU 加速吗？**
A: 可以，安装 CUDA 版本的 faster-whisper 并在配置中设置 `device: cuda`。

**Q: 持续模式中的触发词可以修改吗？**
A: 可以，在 `config.yaml` 中修改 `continuous.trigger_word` 配置。

**Q: 为什么说"嘿"有时检测不到？**
A:
- 语音识别可能不准确，系统已支持模糊匹配（诶、哎、咳、黑、喂、哈等）
- 如果发音不清晰，可以查看 `logs/cli.log` 了解实际识别结果
- 系统使用滑动窗口检测，不会漏掉跨越音频块边界的语音

**Q: 如何查看关键词检测是否正常工作？**
A: 查看 `logs/cli.log` 文件，会显示每次检测的转录结果：
- `Checking for '嘿' in: 'xxx'` - 显示正在检测的内容
- `Trigger word '嘿' detected` - 表示检测成功

**Q: 鼠标模式在哪些地方会触发？**
A: 只有在当前焦点窗口有可编辑光标时才会触发，包括：
- 记事本、文本编辑器
- 浏览器的搜索框、输入框
- 微信、QQ等聊天软件的输入框
- 任何显示工字形（IBeam）光标的地方

---

## 许可证

MIT License
