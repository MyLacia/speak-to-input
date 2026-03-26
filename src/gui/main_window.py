"""
Main application window for the speech-to-text application.
"""

import logging
import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton, QGroupBox,
    QSystemTrayIcon, QMenu, QAction, QStatusBar,
    QMessageBox, QApplication, QProgressDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt5.QtGui import QIcon, QFont, QTextCursor, QPixmap, QPainter, QColor

from config import get_config
from gui.settings import SettingsDialog


logger = logging.getLogger(__name__)


# Language translations
TRANSLATIONS = {
    "en": {
        "app_title": "Speak to Input",
        "ready": "Ready - Hold ALT to speak",
        "running": "Running - Hold ALT to speak",
        "listening": "Listening... (Release ALT to send)",
        "processing": "Processing...",
        "stopped": "Stopped",
        "start": "Start",
        "stop": "Stop",
        "settings": "Settings",
        "instructions": "<b>Instructions:</b><br>"
                       "• Hold <b>ALT</b> key to start speaking<br>"
                       "• Release <b>ALT</b> to transcribe and send text<br>"
                       "• Click text below to edit before sending",
        "current_text": "Current Text",
        "text_placeholder": "Transcribed text will appear here...",
        "send_text": "Send Text",
        "clear": "Clear",
        "statistics": "Statistics",
        "model": "Model",
        "transcriptions": "Transcriptions",
        "sent": "Sent! Hold ALT to speak again",
        "switch_app": "Switch to target app... (pasting in 1s)",
        "loading_model": "Loading Whisper model, please wait...",
        "loading_detect": "Detecting device...",
        "loading_local": "Loading local model...",
        "loading_download": "Downloading model (first time only)...",
        "loading_init": "Initializing model...",
        "loading_timeout": "Loading timed out. Please check your connection or try CPU mode.",
        "loading_error_device": "Failed to detect device.",
        "loading_error_import": "Required library not found.",
        "loading_failed": "Failed to load model",
        "tray_show": "Show",
        "tray_hide": "Hide",
        "tray_quit": "Quit",
        "tray_settings": "Settings",
        "service_running": "Service running",
        "service_stopped": "Service stopped",
        "error_start": "Failed to start service",
        "error_transcriber": "Transcriber failed",
        "error_audio": "Audio capture failed",
        "error_keyboard": "Keyboard listener failed",
    },
    "zh": {
        "app_title": "语音输入",
        "ready": "就绪 - 按住 ALT 键说话",
        "running": "运行中 - 按住 ALT 键说话",
        "listening": "正在听... (松开 ALT 发送)",
        "processing": "处理中...",
        "stopped": "已停止",
        "start": "启动",
        "stop": "停止",
        "settings": "设置",
        "instructions": "<b>使用说明:</b><br>"
                       "• 按住 <b>ALT</b> 键开始说话<br>"
                       "• 松开 <b>ALT</b> 键识别并发送文本<br>"
                       "• 点击下方文本可编辑后再发送",
        "current_text": "当前文本",
        "text_placeholder": "识别的文字将显示在这里...",
        "send_text": "发送文本",
        "clear": "清空",
        "statistics": "统计信息",
        "model": "模型",
        "transcriptions": "识别次数",
        "sent": "已发送! 按住 ALT 再次说话",
        "switch_app": "切换到目标应用... (1秒后粘贴)",
        "loading_model": "正在加载 Whisper 模型，请稍候...",
        "loading_detect": "正在检测设备...",
        "loading_local": "正在加载本地模型...",
        "loading_download": "正在下载模型 (仅首次)...",
        "loading_init": "正在初始化模型...",
        "loading_timeout": "加载超时。请检查网络连接或尝试 CPU 模式。",
        "loading_error_device": "设备检测失败。",
        "loading_error_import": "缺少必需的库。",
        "loading_failed": "模型加载失败",
        "tray_show": "显示",
        "tray_hide": "隐藏",
        "tray_quit": "退出",
        "tray_settings": "设置",
        "service_running": "服务运行中",
        "service_stopped": "服务已停止",
        "error_start": "启动服务失败",
        "error_transcriber": "转录器启动失败",
        "error_audio": "音频捕获初始化失败",
        "error_keyboard": "键盘监听器初始化失败",
    }
}


def t(key: str, lang: str = "zh") -> str:
    """Get translation for a key"""
    return TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["en"].get(key, key))


class StatusIndicator(QWidget):
    """Custom status indicator widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.status = "idle"  # idle, listening, processing

    def set_status(self, status: str):
        """Set status and update appearance"""
        self.status = status
        self.update()

    def paintEvent(self, event):
        """Paint the status indicator"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Colors
        colors = {
            "idle": "#888888",
            "listening": "#4CAF50",
            "processing": "#2196F3",
            "error": "#F44336",
        }
        color = colors.get(self.status, "#888888")

        # Draw circle with proper color
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 16, 16)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = get_config()

        # Language (default to Chinese)
        self.language = getattr(self.config, 'language', 'zh')

        # Components
        self.audio_capture = None
        self.transcriber = None
        self.vad_detector = None
        self.keyboard_emulator = None
        self.key_listener = None

        # State
        self.is_running = False
        self.is_listening = False
        self.current_text = ""
        self.model_loaded = False
        self.manual_vad = None

        self._setup_ui()
        self._setup_tray()
        self._setup_status_timer()

    def _setup_ui(self):
        """Setup the main UI"""
        self.setWindowTitle(t("app_title", self.language))
        self.setMinimumSize(500, 400)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Status bar
        status_layout = QHBoxLayout()
        self.status_indicator = StatusIndicator()
        status_layout.addWidget(self.status_indicator)
        self.status_label = QLabel(t("ready", self.language))
        self.status_label.setFont(QFont("", 10))
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        # Status button
        self.toggle_button = QPushButton(t("start", self.language))
        self.toggle_button.clicked.connect(self._toggle_service)
        self.toggle_button.setMinimumWidth(80)
        status_layout.addWidget(self.toggle_button)

        layout.addLayout(status_layout)

        # Instructions
        instructions = QLabel(t("instructions", self.language))
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Current text display
        text_group = QGroupBox(t("current_text", self.language))
        text_layout = QVBoxLayout(text_group)

        self.text_display = QTextEdit()
        self.text_display.setPlaceholderText(t("text_placeholder", self.language))
        self.text_display.setMinimumHeight(150)
        self.text_display.textChanged.connect(self._on_text_changed)
        text_layout.addWidget(self.text_display)

        # Text control buttons
        control_layout = QHBoxLayout()

        self.send_button = QPushButton(t("send_text", self.language))
        self.send_button.clicked.connect(self._send_text)
        self.send_button.setEnabled(False)
        control_layout.addWidget(self.send_button)

        self.clear_button = QPushButton(t("clear", self.language))
        self.clear_button.clicked.connect(self._clear_text)
        control_layout.addWidget(self.clear_button)

        text_layout.addLayout(control_layout)
        layout.addWidget(text_group)

        # Statistics
        stats_group = QGroupBox(t("statistics", self.language))
        stats_layout = QHBoxLayout(stats_group)

        self.model_label = QLabel(f"{t('model', self.language)}: base")
        stats_layout.addWidget(self.model_label)

        self.stats_label = QLabel(f"{t('transcriptions', self.language)}: 0")
        stats_layout.addWidget(self.stats_label)

        stats_layout.addStretch()

        layout.addWidget(stats_group)

        # Settings button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.settings_button = QPushButton(t("settings", self.language))
        self.settings_button.clicked.connect(self._open_settings)
        button_layout.addWidget(self.settings_button)

        layout.addLayout(button_layout)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage(t("ready", self.language))

    def _setup_tray(self):
        """Setup system tray icon"""
        # Create a simple icon with proper error handling
        try:
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(Qt.blue)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(4, 4, 24, 24)
            # Ensure painter is properly ended
            painter.end()

            icon = QIcon(pixmap)

            self.tray_icon = QSystemTrayIcon(icon, self)
            self.tray_icon.setToolTip(t("app_title", self.language))
        except Exception as e:
            logger.warning(f"Failed to create tray icon: {e}")
            # Create tray icon without custom icon
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setToolTip(t("app_title", self.language))

        # Tray menu
        menu = QMenu()
        menu.addAction(QAction(t("tray_show", self.language), self, triggered=self.show))
        menu.addAction(QAction(t("tray_hide", self.language), self, triggered=self.hide))
        menu.addSeparator()
        menu.addAction(QAction(t("tray_settings", self.language), self, triggered=self._open_settings))
        menu.addSeparator()
        menu.addAction(QAction(t("tray_quit", self.language), self, triggered=self._quit))

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _setup_status_timer(self):
        """Setup timer for status updates"""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(100)  # Update every 100ms

    def _toggle_service(self):
        """Toggle the service on/off"""
        if self.is_running:
            self._stop_service()
        else:
            self._start_service_async()

    def _start_service_async(self):
        """Start all services synchronously (to avoid C++ crash issues)"""
        # Show loading dialog
        self._loading_dialog = QProgressDialog(
            t("loading_model", self.language),
            "",
            0, 100,
            self
        )
        self._loading_dialog.setWindowModality(Qt.WindowModal)
        self._loading_dialog.setCancelButton(None)
        self._loading_dialog.setAutoClose(False)
        self._loading_dialog.setWindowTitle(t("app_title", self.language))
        self._loading_dialog.show()

        # Disable button during loading
        self.toggle_button.setEnabled(False)

        # Process events to show dialog
        QApplication.processEvents()

        # Load model synchronously in main thread
        try:
            from transcriber import Transcriber

            self._loading_dialog.setLabelText(t("loading_detect", self.language))
            self._loading_dialog.setValue(20)
            QApplication.processEvents()

            self._transcriber = Transcriber(
                config=self.config.transcriber,
                progress_callback=self._on_loading_progress,
                timeout=120
            )

            self._loading_dialog.setLabelText(t("loading_local", self.language))
            self._loading_dialog.setValue(40)
            QApplication.processEvents()

            # This is where crash might happen - load model
            self._transcriber.load_model()

            self._loading_dialog.setValue(100)
            QApplication.processEvents()

            # Success - close dialog and finish
            self._loading_dialog.close()
            self._loading_dialog = None
            self.toggle_button.setEnabled(True)
            self._on_model_loaded(self._transcriber)

        except Exception as e:
            if self._loading_dialog:
                self._loading_dialog.close()
                self._loading_dialog = None
            self.toggle_button.setEnabled(True)
            logger.error(f"Model loading failed: {e}")
            self._on_loading_error("unknown", str(e))

    def _load_model_step(self):
        """Load model in small steps to keep UI responsive (runs in main thread)"""
        try:
            if self._loading_stage == 0:
                # Stage 0: Import and prepare
                self._on_loading_progress("detect_device", 10)
                from transcriber import Transcriber
                self._transcriber_class = Transcriber
                self._loading_stage = 1

            elif self._loading_stage == 1:
                # Stage 1: Create transcriber instance (without loading model)
                self._on_loading_progress("detect_device", 20)
                self._transcriber = self._transcriber_class(
                    config=self.config.transcriber,
                    progress_callback=self._on_loading_progress,
                    timeout=120
                )
                self._loading_stage = 2

            elif self._loading_stage == 2:
                # Stage 2: Load the actual model
                self._on_loading_progress("load_local_model", 40)
                # This will block briefly but runs in main thread
                # which is safer for C++ libraries
                self._transcriber.load_model()
                self._on_loading_progress("complete", 100)

                # Done - cleanup and finish
                self._loading_timer.stop()
                self._loading_timer = None
                self._on_model_loaded(self._transcriber)

        except Exception as e:
            self._loading_timer.stop()
            self._loading_timer = None
            logger.error(f"Model loading failed: {e}")
            self._on_loading_error("unknown", str(e))

    def _on_loading_progress(self, stage: str, percent: int):
        """Handle loading progress updates"""
        # Update dialog label based on stage
        stage_messages = {
            "detect_device": t("loading_detect", self.language),
            "load_local_model": t("loading_local", self.language),
            "download_model": t("loading_download", self.language),
            "load_model": t("loading_init", self.language),
            "complete": t("loading_init", self.language),
        }
        message = stage_messages.get(stage, t("loading_model", self.language))

        if self._loading_dialog:
            self._loading_dialog.setLabelText(message)
            self._loading_dialog.setValue(percent)

    def _on_loading_error(self, error_type: str, error_msg: str):
        """Handle loading error"""
        # Show error message
        error_messages = {
            "timeout": t("loading_timeout", self.language),
            "import_error": t("loading_error_import", self.language),
            "device_error": t("loading_error_device", self.language),
        }
        msg = error_messages.get(error_type, error_msg)

        if self._loading_dialog:
            self._loading_dialog.close()
            self._loading_dialog = None

        QMessageBox.critical(self, t("loading_failed", self.language), msg)
        self.toggle_button.setEnabled(True)

    def _on_model_loaded(self, transcriber):
        """Handle model loading completion"""
        # Close loading dialog
        if self._loading_dialog:
            self._loading_dialog.close()
            self._loading_dialog = None

        # Re-enable button
        self.toggle_button.setEnabled(True)

        # If transcriber is None, error was already handled by error signal
        if transcriber is None:
            return

        # Initialize each component with proper error handling
        error_msg = None

        # Step 1: Setup transcriber
        try:
            # Store transcriber
            logger.info("Setting up transcriber...")
            self.transcriber = transcriber
            self.transcriber.on_transcription = self._on_transcription
            self.transcriber.start()
            logger.info("Transcriber started")

        except Exception as e:
            error_msg = f"转录器启动失败: {e}"
            logger.error(error_msg)
            QMessageBox.critical(self, t("error_start", self.language), error_msg)
            return

        # Step 2: Initialize audio capture
        try:
            # Initialize audio capture
            logger.info("Initializing audio capture...")
            from audio_capture import get_audio_capture
            self.audio_capture = get_audio_capture()
            self.audio_capture.start()
            logger.info("Audio capture started")

        except Exception as e:
            error_msg = f"音频捕获初始化失败: {e}\n\n请检查:\n1. 麦克风是否已连接\n2. 麦克风权限是否已授予"
            logger.error(f"Audio capture failed: {e}")
            QMessageBox.critical(self, t("error_start", self.language), error_msg)
            # Cleanup transcriber
            try:
                self.transcriber.stop()
            except:
                pass
            self.transcriber = None
            return

        # Step 3: Initialize keyboard emulator
        try:
            # Initialize keyboard emulator
            logger.info("Initializing keyboard emulator...")
            from keyboard_emulator import get_emulator, get_listener
            from vad_detector import ManualVAD

            self.keyboard_emulator = get_emulator()

            # Setup key listener with ALT trigger
            self.key_listener = get_listener()
            self.manual_vad = ManualVAD()

            # ALT key handlers
            self.key_listener.on_alt_press = self._on_alt_press
            self.key_listener.on_alt_release = self._on_alt_release

            self.key_listener.start()
            logger.info("Keyboard listener started")

        except Exception as e:
            error_msg = f"键盘监听器初始化失败: {e}"
            logger.error(f"Keyboard listener failed: {e}")
            QMessageBox.critical(self, t("error_start", self.language), error_msg)
            # Cleanup
            try:
                if self.audio_capture:
                    self.audio_capture.stop()
                if self.transcriber:
                    self.transcriber.stop()
            except:
                pass
            self.audio_capture = None
            self.transcriber = None
            return

        # All components started successfully
        self.is_running = True
        self.model_loaded = True
        self.toggle_button.setText(t("stop", self.language))
        self.status_label.setText(t("running", self.language))
        self.statusBar.showMessage(t("service_running", self.language))
        self.model_label.setText(f"{t('model', self.language)}: {self.config.transcriber.model_size}")

        logger.info("Service started successfully")

    def _stop_service(self):
        """Stop all services"""
        try:
            if self.audio_capture:
                self.audio_capture.stop()
            if self.transcriber:
                self.transcriber.stop()
            if self.key_listener:
                self.key_listener.stop()

            self.is_running = False
            self.is_listening = False
            self.toggle_button.setText(t("start", self.language))
            self.status_label.setText(t("stopped", self.language))
            self.statusBar.showMessage(t("service_stopped", self.language))
            self.status_indicator.set_status("idle")

            logger.info("Service stopped")

        except Exception as e:
            logger.error(f"Error stopping service: {e}")

    def _on_alt_press(self):
        """Handle ALT key press - start recording"""
        # Thread-safe check with explicit attribute verification
        if not self.is_running:
            return
        if self.manual_vad is None:
            return
        if not hasattr(self, 'audio_capture') or self.audio_capture is None:
            return

        try:
            self.is_listening = True
            self.manual_vad.start()
            self.status_indicator.set_status("listening")
            self.status_label.setText(t("listening", self.language))
            logger.debug("ALT pressed - recording started")
        except Exception as e:
            logger.error(f"Error in ALT press handler: {e}")
            self.is_listening = False

    def _on_alt_release(self):
        """Handle ALT key release - process and send"""
        # Thread-safe check
        if not self.is_running or not self.is_listening:
            return
        if self.manual_vad is None:
            return
        if self.transcriber is None:
            return

        try:
            self.is_listening = False
            self.status_indicator.set_status("processing")
            self.status_label.setText(t("processing", self.language))

            # Get recorded audio
            audio = self.manual_vad.stop()

            if audio is not None and len(audio) > 0:
                # Submit for transcription
                self.transcriber.transcribe_async(audio)
            else:
                # No audio captured
                self.status_indicator.set_status("idle")
                self.status_label.setText(t("running", self.language))
        except Exception as e:
            logger.error(f"Error in ALT release handler: {e}")
            self.status_indicator.set_status("idle")
            self.status_label.setText(t("running", self.language))

    def _on_transcription(self, result):
        """Handle transcription result"""
        text = result.text
        text = self.transcriber.post_process(text)

        self.current_text = text
        self.text_display.setPlainText(text)
        self.send_button.setEnabled(True)

        # Update statistics
        stats = self.transcriber.get_statistics()
        self.stats_label.setText(f"{t('transcriptions', self.language)}: {stats['total_transcriptions']}")

        # Auto-send if configured
        # For now, let user review before sending
        self.status_indicator.set_status("idle")
        self.status_label.setText(f"{t('ready', self.language)}: {text[:50]}...")

        logger.info(f"Transcription: {text}")

    def _send_text(self):
        """Send current text to active application"""
        text = self.text_display.toPlainText().strip()
        if not text:
            return

        try:
            # Give user time to switch to target app
            self.status_label.setText(t("switch_app", self.language))
            QApplication.processEvents()

            # Wait a moment for user to switch windows
            time.sleep(1)

            # Send text
            success = self.keyboard_emulator.send_text(text)

            if success:
                self.statusBar.showMessage(f"Sent: {len(text)} characters")
                self.text_display.clear()
                self.send_button.setEnabled(False)
                self.current_text = ""
                self.status_label.setText(t("sent", self.language))
            else:
                self.statusBar.showMessage("Failed to send text")
                self.status_label.setText("Error sending text")

            self.status_indicator.set_status("idle")

        except Exception as e:
            logger.error(f"Error sending text: {e}")
            self.statusBar.showMessage(f"Error: {e}")

    def _clear_text(self):
        """Clear current text"""
        self.text_display.clear()
        self.current_text = ""
        self.send_button.setEnabled(False)
        self.status_label.setText(t("running", self.language))

    def _on_text_changed(self):
        """Handle text display change"""
        self.current_text = self.text_display.toPlainText()
        self.send_button.setEnabled(bool(self.current_text.strip()))

    def _update_status(self):
        """Update status display (called periodically)"""
        pass

    def _open_settings(self):
        """Open settings dialog"""
        dialog = SettingsDialog(self.config, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec_()

    def _on_settings_changed(self, config):
        """Handle settings change"""
        self.config = config

        # Reload transcriber if model changed
        if self.transcriber:
            current_model = self.transcriber.config.model_size
            if current_model != config.transcriber.model_size:
                self.transcriber.reload_model(config.transcriber.model_size)
                self.model_label.setText(f"{t('model', self.language)}: {config.transcriber.model_size}")

        self.statusBar.showMessage("Settings saved")

    def _on_tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()

    def _quit(self):
        """Quit the application"""
        self._stop_service()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """Handle close event - minimize to tray"""
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()


class _ModelLoaderWorker(QObject):
    """Worker for loading model in background thread"""
    finished = pyqtSignal(object)  # Emits transcriber instance or None
    progress = pyqtSignal(str, int)  # Emits (stage, percent)
    error = pyqtSignal(str, str)  # Emits (error_type, error_msg)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def load(self):
        """Load the Whisper model"""
        transcriber = None
        try:
            from transcriber import Transcriber

            logger.info("_ModelLoaderWorker.load() - Starting")

            # Create progress callback
            def progress_callback(stage: str, percent: int):
                logger.debug(f"Progress: {stage} - {percent}%")
                self.progress.emit(stage, percent)

            # Create transcriber WITHOUT loading model yet (avoid nested threading)
            logger.info("_ModelLoaderWorker.load() - Creating Transcriber")
            transcriber = Transcriber(
                config=self.config.transcriber,
                progress_callback=progress_callback,
                timeout=120  # 2 minute timeout
            )
            logger.info("_ModelLoaderWorker.load() - Transcriber created, calling load_model()")

            # Now load the model in this thread
            transcriber.load_model()

            logger.info("_ModelLoaderWorker.load() - Model loaded, emitting finished")
            self.finished.emit(transcriber)

        except TimeoutError as e:
            logger.error(f"Model loading timeout: {e}")
            self.error.emit("timeout", str(e))
            self.finished.emit(None)
        except ImportError as e:
            logger.error(f"Import error: {e}")
            self.error.emit("import_error", str(e))
            self.finished.emit(None)
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            self.error.emit("unknown", str(e))
            self.finished.emit(None)
