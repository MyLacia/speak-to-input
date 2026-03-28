# Speak to Input - 实时语音转文本输入

> 本地语音识别，实时文字输入。基于 FunASR Paraformer（阿里达摩院中文语音模型），无需网络连接。

---

## 快速开始（Windows）

```
1. 克隆项目: git clone https://github.com/MyLacia/speak-to-input.git
2. 双击运行 run_cli.bat
3. 首次运行自动安装依赖 + 下载模型（约5-10分钟）
4. 打开记事本，在输入框长按鼠标左键说话
```

> 首次运行后，后续启动直接进入应用，不再重复安装。

### 手动安装

```bash
git clone https://github.com/MyLacia/speak-to-input.git
cd speak-to-input
python -m venv venv_py39
venv_py39\Scripts\activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python run_cli.py
```

### 项目大小

| 项目 | 大小 |
|------|------|
| 源代码 | < 1 MB |
| 虚拟环境 (venv_py39/) | ~1.2 GB |
| Paraformer-zh 模型 (自动下载至用户缓存) | ~944 MB |

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

## 功能特点

- **两种监听模式**: 鼠标长按触发 / 关键词持续监听
- **一键启动**: 首次双击 run_cli.bat 自动创建虚拟环境、安装依赖、下载模型
- **智能光标检测**: 只有在有输入光标的位置才会触发录音，避免误操作
- **中文精准识别**: 使用 FunASR Paraformer-zh 中文专用模型，同音词区分更精确
- **自动标点**: 使用 ct-punc 标点模型，根据语音停顿自动添加逗号
- **简体中文输出**: 自动将繁体转换为简体（需安装 opencc）
- **剪贴板输入**: 通过剪贴板 + Ctrl+V 实现稳定的中文输入

---

## 系统要求

- **操作系统**: Windows 10/11 (64位)
- **Python**: 3.8 或更高版本
- **内存**: 至少 4GB RAM
- **网络**: 首次运行需要下载模型（~944 MB）

---

## 项目结构

```
speak-to-input/
├── run_cli.bat           # 启动脚本（自动安装依赖）
├── bootstrap.py          # 依赖自检与安装脚本
├── run_cli.py            # CLI 主程序
├── requirements.txt      # 依赖列表
├── config.yaml           # 配置文件（可选）
├── src/                  # 源代码
│   ├── config.py         # 配置管理
│   ├── transcriber.py    # 语音识别引擎（FunASR Paraformer）
│   ├── audio_capture.py  # 音频捕获
│   ├── vad_detector.py   # 语音活动检测
│   └── keyboard_emulator.py  # 键盘/鼠标模拟
└── logs/                 # 日志目录（自动创建）
```

---

## 配置文件

`config.yaml`（可选，首次运行会自动创建默认配置）：

```yaml
transcriber:
  model_size: paraformer-zh  # 模型名称
  language: zh               # 语言
  beam_size: 5               # 搜索宽度
  device: null               # 设备: null=自动, cpu, cuda:0

audio:
  sample_rate: 16000
  channels: 1
  chunk_duration: 0.5
  device_index: null         # 麦克风设备（留空使用默认）
  silence_threshold: 0.002

keyboard:
  method: clipboard          # 输入方式: clipboard
  paste_delay: 0.1

continuous:
  trigger_word: "嘿"
  pause_threshold: 0.5
  timeout_duration: 2.0
```

---

## 故障排除

### 麦克风无法使用

- 检查系统麦克风权限
- 可在 `config.yaml` 中指定设备索引：`audio.device_index: 1`

### 中文无法输入

- 确保使用 "clipboard" 输入方式（默认）
- 检查目标应用是否支持 Ctrl+V 粘贴

### 鼠标模式在哪些地方会触发？

只有在当前焦点窗口有可编辑光标（工字形 IBeam 光标）时才会触发：
- 记事本、文本编辑器
- 浏览器的搜索框、输入框
- 微信、QQ等聊天软件的输入框

### 依赖安装失败

- 删除项目根目录下的 `.bootstrap_done` 文件，重新双击 `run_cli.bat`
- 或手动删除 `venv_py39/` 目录后重试

---

## 许可证

MIT License
