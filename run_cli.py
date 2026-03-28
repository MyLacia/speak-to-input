# -*- coding: utf-8 -*-
"""
Speak to Input - CLI Version
Speech-to-text application with mouse long-press or continuous listening mode.
Press 'c' to toggle between mouse and continuous modes.
"""

import sys
import logging
import faulthandler
import threading
import time
import argparse
import numpy as np
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Enable crash handler for C++ extensions
faulthandler.enable()

# Add src to path for imports
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "cli.log", encoding="utf-8"),
    ]
)

logger = logging.getLogger(__name__)


class CLIApplication:
    """Main CLI application"""

    def __init__(self):
        self.mode = "mouse"  # mouse (left-button long-press) or continuous
        self.is_running = False
        self.audio_capture = None
        self.transcriber = None
        self.vad = None
        self.keyboard_emulator = None
        self.key_listener = None  # For keyboard shortcuts (c/q keys)
        self.mouse_listener = None  # For mouse long-press trigger
        self.model_loaded = False
        self._recording_active = False
        self._processing_lock = threading.Lock()  # Prevent concurrent processing
        self._executor = ThreadPoolExecutor(max_workers=1)  # Background thread for processing

    def _print_header(self):
        """Print application header"""
        print("\n" + "=" * 55)
        print("  Speak to Input - CLI Version")
        print("=" * 55)

    def _get_mode_text(self):
        """Get mode display text"""
        if self.mode == "mouse":
            return "鼠标模式 (在输入框长按左键说话)"
        else:
            return "持续模式 (说'嘿'触发)"

    def _print_status(self, message=""):
        """Print current status"""
        mode_text = self._get_mode_text()
        if message:
            print(f"\r{message}", end="", flush=True)
        else:
            print(f"\r[模式: {mode_text}] - 按'c'切换 | 按'q'退出", end="", flush=True)

    def _print_instructions(self):
        """Print usage instructions"""
        print()
        if self.mode == "mouse":
            print("使用方法:")
            print("  - 在有输入光标的地方，长按鼠标左键开始说话")
            print("  - 松开鼠标左键识别并发送文本")
            print("  - 提示: 只有在可输入的位置才会触发")
        else:
            print("使用方法:")
            print("  - 说 '嘿' 触发录音")
            print("  - 停顿 0.5 秒后开始录音")
            print("  - 静音 2 秒后自动结束并发送")

    def switch_mode(self):
        """Switch between mouse and continuous modes"""
        old_mode = self.mode
        self.mode = "continuous" if self.mode == "mouse" else "mouse"

        logger.info(f"Mode switched: {old_mode} -> {self.mode}")
        print(f"\n>>> 模式已切换到: {self._get_mode_text()}")

        # Reinitialize VAD if service is running
        if self.is_running:
            self._reinitialize_vad()

        self._print_status()

    def _reinitialize_vad(self):
        """Reinitialize VAD after mode switch"""
        from vad_detector import ManualVAD, ContinuousVAD
        from config import get_config
        from keyboard_emulator import get_mouse_listener

        config = get_config()

        # Reset audio callback
        if self.audio_capture:
            self.audio_capture.on_audio_chunk = None

        # Stop mouse listener if running
        if self.mouse_listener and self.mouse_listener.is_running:
            logger.info("Stopping mouse listener")
            self.mouse_listener.on_long_press = None
            self.mouse_listener.on_release = None
            # Don't stop the listener, just clear callbacks to avoid conflicts

        # Create new VAD
        if self.mode == "mouse":
            self.vad = ManualVAD()
            self.audio_capture.on_audio_chunk = self._on_audio_chunk_mouse
            logger.info("Switched to mouse mode VAD")
        else:
            self.vad = ContinuousVAD(
                sample_rate=config.audio.sample_rate,
                transcriber=self.transcriber
            )
            self.vad.transcriber = self.transcriber
            self.audio_capture.on_audio_chunk = self._on_audio_chunk_continuous
            logger.info("Switched to continuous mode VAD")

    def _on_audio_chunk_mouse(self, chunk):
        """Handle audio chunk for mouse mode"""
        if self.vad and self._recording_active:
            self.vad.add_audio(chunk.data)

    def _on_audio_chunk_continuous(self, chunk):
        """Handle audio chunk for continuous mode"""
        if self.vad:
            audio = self.vad.process_audio(chunk.data)
            if audio is not None and len(audio) > 0:
                # Process in background to avoid blocking audio thread
                self._process_audio_async(audio)
            # Add debug log occasionally (1% of the time to avoid spam)
            elif random.random() < 0.01:
                logger.info(f"Audio chunk processed, VAD state: {self.vad.get_state()}")

    def _process_audio(self, audio):
        """Process captured audio (blocking - call from background thread)"""
        if self.transcriber is None:
            return

        self._print_status("正在识别...")

        try:
            result = self.transcriber.transcribe(audio)
            if result and result.text:
                text = self.transcriber.post_process(result.text)

                # In continuous mode, strip trigger word from the beginning
                if self.mode == "continuous":
                    text = self._strip_trigger_word(text)

                if not text:
                    print(f"\n>>> 触发词后无有效语音")
                else:
                    print(f"\n>>> 识别: {text}")
                    # Send text if keyboard emulator available
                    if self.keyboard_emulator:
                        self._print_status("正在发送...")
                        time.sleep(0.5)  # Give user time to switch to target app
                        success = self.keyboard_emulator.send_text(text)
                        if success:
                            print(f"\n>>> 已发送 ({len(text)} 字符)")
                        else:
                            print(f"\n>>> 发送失败")
            else:
                print(f"\n>>> 未识别到语音")
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            print(f"\n>>> 识别错误: {e}")

        self._print_status()

    def _strip_trigger_word(self, text: str) -> str:
        """Remove trigger word (and its fuzzy matches) from the beginning of text."""
        if not text:
            return text

        # Same fuzzy match list used by ContinuousVAD._do_trigger_check
        trigger_variants = ['嘿', '诶', '哎', '咳', '黑', '喂', '哈', '和', '赫', '合']
        import re

        for variant in trigger_variants:
            # Match variant at the start, followed by optional punctuation/whitespace
            pattern = rf'^{re.escape(variant)}[\s,，。.！!？?、]*'
            new_text = re.sub(pattern, '', text)
            if new_text != text:
                logger.info(f"Stripped trigger word '{variant}' from output")
                return new_text

        return text

    def _process_audio_async(self, audio):
        """Process captured audio in background thread (non-blocking)"""
        if self._processing_lock.locked():
            logger.debug("Already processing audio, skipping")
            return

        def process():
            with self._processing_lock:
                self._process_audio(audio)

        # Submit to thread pool for non-blocking execution
        self._executor.submit(process)

    def _on_mouse_long_press(self):
        """Handle mouse long-press"""
        if self.mode != "mouse":
            return

        self._recording_active = True
        if self.vad:
            self.vad.start()
            self._print_status("正在录音... (松开鼠标发送)")

    def _on_mouse_release(self):
        """Handle mouse release"""
        if self.mode != "mouse":
            return

        self._recording_active = False
        if self.vad:
            audio = self.vad.stop()
            if audio is not None and len(audio) > 0:
                # Process in background to avoid blocking mouse
                self._process_audio_async(audio)
            else:
                self._print_status()

    def _load_model(self):
        """Load the ASR model"""
        from config import get_config
        from transcriber import Transcriber

        config = get_config()

        print("正在加载模型...")

        def progress_callback(stage, percent):
            if stage == "complete":
                print(f"  加载完成 ({percent}%)")
            elif stage != "complete":
                print(f"  {stage}: {percent}%")

        try:
            self.transcriber = Transcriber(
                config=config.transcriber,
                progress_callback=progress_callback,
                timeout=120
            )
            self.transcriber.load_model()
            self.transcriber.start()
            self.model_loaded = True
            print("模型加载完成!\n")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            print(f"模型加载失败: {e}\n")
            return False

    def _start_services(self):
        """Start all services"""
        from config import get_config
        from audio_capture import get_audio_capture
        from keyboard_emulator import get_emulator, get_listener, get_mouse_listener
        from vad_detector import ManualVAD, ContinuousVAD

        config = get_config()

        # Initialize audio capture
        try:
            print("初始化音频捕获...")
            self.audio_capture = get_audio_capture()
            self.audio_capture.start()
        except Exception as e:
            print(f"音频捕获初始化失败: {e}")
            return False

        # Initialize keyboard emulator
        try:
            print("初始化键盘模拟器...")
            self.keyboard_emulator = get_emulator()
        except Exception as e:
            print(f"键盘模拟器初始化失败: {e}")
            return False

        # Initialize VAD based on mode
        try:
            print(f"初始化VAD (模式: {self.mode})...")
            if self.mode == "mouse":
                self.vad = ManualVAD()
                self.audio_capture.on_audio_chunk = self._on_audio_chunk_mouse

                # Setup mouse listener for long-press trigger
                self.mouse_listener = get_mouse_listener(long_press_delay=0.2)
                self.mouse_listener.on_long_press = self._on_mouse_long_press
                self.mouse_listener.on_release = self._on_mouse_release
                self.mouse_listener.start()

                # Setup keyboard listener for shortcuts (c/q keys)
                self.key_listener = get_listener()
                self.key_listener.register_hotkey('c', self.switch_mode)
                self.key_listener.start()
            else:
                self.vad = ContinuousVAD(
                    sample_rate=config.audio.sample_rate,
                    transcriber=self.transcriber
                )
                self.vad.transcriber = self.transcriber
                self.audio_capture.on_audio_chunk = self._on_audio_chunk_continuous

                # Setup keyboard listener for shortcuts (c/q keys)
                self.key_listener = get_listener()
                self.key_listener.register_hotkey('c', self.switch_mode)
                self.key_listener.start()

        except Exception as e:
            print(f"VAD初始化失败: {e}")
            return False

        self.is_running = True
        print("服务启动完成!\n")
        return True

    def _stop_services(self):
        """Stop all services"""
        if self.audio_capture:
            self.audio_capture.stop()
        if self.transcriber:
            self.transcriber.stop()
        if self.key_listener:
            self.key_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.vad:
            self.vad.reset()

        self.is_running = False

    def run(self):
        """Run the CLI application"""
        self._print_header()
        self._print_instructions()

        # Load model
        if not self._load_model():
            input("\n按回车键退出...")
            return 1

        # Start services
        if not self._start_services():
            input("\n按回车键退出...")
            return 1

        print("=" * 55)
        print("服务运行中!")
        print("=" * 55)

        self._print_status()

        # Main loop - wait for 'q' to quit or 'c' to switch mode
        try:
            import msvcrt
            while self.is_running:
                # Check for key press
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    if key == 'q':
                        break
                    elif key == 'c':
                        self.switch_mode()

                # Continuous mode timeout check
                if self.mode == "continuous" and self.vad:
                    if self.vad.get_state() == "CAPTURING":
                        # Use last_speech_time (only set on non-silent audio)
                        # Falls back to start_time if no speech detected yet
                        check_time = self.vad.last_speech_time or self.vad.start_time
                        if check_time:
                            time_since = time.time() - check_time
                            timeout = self.vad.config.timeout_duration
                            if time_since > timeout:
                                # Trigger completion with silence
                                silence = np.zeros(int(0.1 * 16000), dtype=np.float32)
                                audio = self.vad.process_audio(silence)
                                if audio is not None and len(audio) > 0:
                                    self._process_audio_async(audio)

                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\n\n收到中断信号")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            print(f"\n错误: {e}")

        self._stop_services()
        print("\n程序已退出")
        return 0


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Speak to Input CLI - 语音输入命令行版本"
    )
    parser.add_argument(
        '--mode',
        choices=['mouse', 'continuous'],
        default='mouse',
        help='初始模式: mouse (鼠标长按) 或 continuous (说"嘿")'
    )
    args = parser.parse_args()

    app = CLIApplication()
    app.mode = args.mode

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
