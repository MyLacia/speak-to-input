"""
语音转文字输入 - 命令行版本
避免 PyQt5 与 C++ 库冲突
"""

import sys
import logging
import time
import threading
import numpy as np
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from transcriber import Transcriber
from audio_capture import AudioCapture
from keyboard_emulator import KeyboardEmulator
from config import get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CLIApp:
    """语音转文字输入 - 命令行版本"""

    def __init__(self):
        self.config = get_config()
        self.running = False
        self.recording = False

        # 组件
        self.transcriber = None
        self.audio_capture = None
        self.keyboard = None

        # 录音线程
        self.record_thread = None

    def start(self):
        """启动应用"""
        logger.info("=" * 50)
        logger.info("语音转文字输入 - 命令行模式")
        logger.info("=" * 50)

        try:
            # 加载模型
            logger.info("正在加载 Whisper 模型...")
            self.transcriber = Transcriber(
                config=self.config.transcriber,
                timeout=120
            )
            self.transcriber.load_model()
            logger.info("模型加载成功！")

            # 初始化音频捕获
            logger.info("正在初始化音频捕获...")
            self.audio_capture = AudioCapture(config=self.config.audio)
            self.audio_capture.start()
            logger.info(f"音频捕获已启动 (采样率: {self.config.audio.sample_rate}Hz)")

            # 初始化键盘模拟器
            self.keyboard = KeyboardEmulator(config=self.config.keyboard)

            # 设置转录回调
            self.transcriber.on_transcription = self._on_transcription

            # 启动转录器
            self.transcriber.start()

            self.running = True
            logger.info("")
            logger.info("=" * 50)
            logger.info("准备就绪！")
            logger.info("=" * 50)
            logger.info("按住 ALT 键说话，松开自动发送文字")
            logger.info("按 Ctrl+C 退出")
            logger.info("")

            # 主循环 - 监听 ALT 键
            self._main_loop()

        except KeyboardInterrupt:
            logger.info("\n正在退出...")
        except Exception as e:
            logger.error(f"错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()

    def _main_loop(self):
        """主循环 - 监听 ALT 键"""
        from pynput import keyboard

        alt_pressed = False

        def on_press(key):
            nonlocal alt_pressed
            if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                if not alt_pressed:
                    alt_pressed = True
                    self._start_recording()

        def on_release(key):
            nonlocal alt_pressed
            if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                if alt_pressed:
                    alt_pressed = False
                    self._stop_recording()

        # 启动键盘监听器
        listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release
        )
        listener.start()

        # 保持运行
        while self.running:
            time.sleep(0.1)

        listener.stop()

    def _start_recording(self):
        """开始录音"""
        if self.recording:
            return

        self.recording = True
        logger.info("🎤 正在录音... (松开 ALT 键停止)")

        # 在后台线程中开始录音
        self.record_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.record_thread.start()

    def _record_audio(self):
        """在后台线程中录音"""
        self.audio_capture.start_recording()
        # 在录音标志为 True 时持续录音
        while self.recording:
            time.sleep(0.1)

    def _stop_recording(self):
        """停止录音并转录"""
        if not self.recording:
            return

        self.recording = False

        # 等待录音线程结束
        if self.record_thread:
            self.record_thread.join(timeout=1)

        # 获取录制的音频
        audio = self.audio_capture.stop_recording()

        if audio is not None and len(audio) > 0:
            duration = len(audio) / self.config.audio.sample_rate
            logger.info(f"正在处理 {duration:.1f} 秒的音频...")

            # 转录
            result = self.transcriber.transcribe(audio)
            if result and result.text:
                text = result.text.strip()
                if text:
                    logger.info(f"识别结果: {text}")

                    # 通过键盘发送
                    try:
                        self.keyboard.send_text(text)
                        logger.info("✓ 文字已发送！")
                    except Exception as e:
                        logger.error(f"发送文字失败: {e}")
            else:
                logger.info("未检测到语音")
        else:
            logger.warning("没有捕获到音频")

    def _on_transcription(self, result):
        """处理转录结果（异步模式）"""
        pass  # 命令行版本使用同步模式

    def stop(self):
        """停止应用"""
        self.running = False
        self.recording = False

        if self.audio_capture:
            self.audio_capture.stop()

        if self.transcriber:
            self.transcriber.stop()

        logger.info("已停止。")


if __name__ == "__main__":
    app = CLIApp()
    app.start()
