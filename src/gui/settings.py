"""
Settings dialog for configuring the speech-to-text application.
"""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QGroupBox, QLabel, QTabWidget,
    QLineEdit, QFileDialog, QWidget
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from config import Config, get_config


logger = logging.getLogger(__name__)


# Translations for settings dialog
SETTINGS_TEXTS = {
    "en": {
        "title": "Settings",
        "save": "Save",
        "cancel": "Cancel",
        "tab_transcription": "Transcription",
        "tab_audio": "Audio",
        "tab_vad": "Voice Detection",
        "tab_keyboard": "Keyboard",
        "tab_hotkey": "Hotkeys",
        "tab_general": "General",
        "group_model": "Speech Recognition Model",
        "label_model_size": "Model Size:",
        "label_language": "Language (empty for auto):",
        "label_compute_type": "Compute Type:",
        "label_beam_size": "Beam Size:",
        "group_audio": "Audio Capture",
        "label_sample_rate": "Sample Rate (Hz):",
        "label_channels": "Channels:",
        "label_device": "Input Device:",
        "button_refresh": "Refresh Devices",
        "no_devices": "No devices found",
        "group_vad": "Voice Activity Detection",
        "check_enable_vad": "Enable VAD",
        "label_silence": "Min Silence Duration:",
        "label_padding": "Speech Padding:",
        "label_threshold": "Speech Threshold:",
        "vad_note": "Note: When ALT key trigger is enabled, VAD is bypassed.\nSpeech is captured while ALT is held, sent on release.",
        "group_input": "Input Method",
        "label_method": "Method:",
        "label_typing_speed": "Typing Speed (s):",
        "label_paste_delay": "Paste Delay (s):",
        "input_note": "Clipboard method: Copies text to clipboard and simulates Ctrl+V.\nDirect method: Simulates individual keystrokes (slower, no Chinese).",
        "group_hotkey": "Global Hotkeys",
        "check_alt_trigger": "Enable ALT Key Trigger",
        "hotkey_info": "When ALT Key Trigger is enabled:\n"
                       "• Press and hold ALT to start capturing speech\n"
                       "• Release ALT to transcribe and send text\n\n"
                       "This mode is recommended for most users as it provides\n"
                       "direct control over when to start and stop recognition.",
        "group_general": "General Settings",
        "label_ui_language": "UI Language:",
        "lang_chinese": "中文 (Chinese)",
        "lang_english": "English",
    },
    "zh": {
        "title": "设置",
        "save": "保存",
        "cancel": "取消",
        "tab_transcription": "转录",
        "tab_audio": "音频",
        "tab_vad": "语音检测",
        "tab_keyboard": "键盘",
        "tab_hotkey": "快捷键",
        "tab_general": "通用",
        "group_model": "语音识别模型",
        "label_model_size": "模型大小:",
        "label_language": "语言 (留空为自动检测):",
        "label_compute_type": "计算类型:",
        "label_beam_size": "Beam 大小:",
        "group_audio": "音频捕获",
        "label_sample_rate": "采样率 (Hz):",
        "label_channels": "声道数:",
        "label_device": "输入设备:",
        "button_refresh": "刷新设备",
        "no_devices": "未找到设备",
        "group_vad": "语音活动检测",
        "check_enable_vad": "启用 VAD",
        "label_silence": "最小静音时长:",
        "label_padding": "语音填充:",
        "label_threshold": "语音阈值:",
        "vad_note": "注意: 当 ALT 键触发启用时，VAD 被绕过。\n按住 ALT 捕获语音，松开发送。",
        "group_input": "输入方式",
        "label_method": "方式:",
        "label_typing_speed": "打字速度 (秒):",
        "label_paste_delay": "粘贴延迟 (秒):",
        "input_note": "剪贴板方式: 复制文本到剪贴板并模拟 Ctrl+V。\n直接方式: 模拟单个按键 (较慢，不支持中文)。",
        "group_hotkey": "全局快捷键",
        "check_alt_trigger": "启用 ALT 键触发",
        "hotkey_info": "启用 ALT 键触发后:\n"
                       "• 按住 ALT 键开始捕获语音\n"
                       "• 松开 ALT 键识别并发送文本\n\n"
                       "推荐大多数用户使用此模式，\n"
                       "因为它可以直接控制识别的开始和停止。",
        "group_general": "通用设置",
        "label_ui_language": "界面语言:",
        "lang_chinese": "中文",
        "lang_english": "English",
    }
}


def st(key: str, lang: str = "zh") -> str:
    """Get settings translation for a key"""
    return SETTINGS_TEXTS.get(lang, {}).get(key, SETTINGS_TEXTS["en"].get(key, key))


class SettingsDialog(QDialog):
    """Settings configuration dialog"""

    settings_changed = pyqtSignal(Config)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.ui_language = getattr(config, 'language', 'zh')

        self.setWindowTitle(st("title", self.ui_language))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout(self)

        # Tab widget for different settings categories
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # General tab (new - for language selection)
        general_tab = self._create_general_tab()
        tabs.addTab(general_tab, st("tab_general", self.ui_language))

        # Transcriber tab
        transcriber_tab = self._create_transcriber_tab()
        tabs.addTab(transcriber_tab, st("tab_transcription", self.ui_language))

        # Audio tab
        audio_tab = self._create_audio_tab()
        tabs.addTab(audio_tab, st("tab_audio", self.ui_language))

        # VAD tab
        vad_tab = self._create_vad_tab()
        tabs.addTab(vad_tab, st("tab_vad", self.ui_language))

        # Keyboard tab
        keyboard_tab = self._create_keyboard_tab()
        tabs.addTab(keyboard_tab, st("tab_keyboard", self.ui_language))

        # Hotkey tab
        hotkey_tab = self._create_hotkey_tab()
        tabs.addTab(hotkey_tab, st("tab_hotkey", self.ui_language))

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton(st("save", self.ui_language))
        self.save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton(st("cancel", self.ui_language))
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _create_general_tab(self):
        """Create general settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_general", self.ui_language))
        form = QFormLayout(group)

        # UI Language selection
        self.language_combo = QComboBox()
        self.language_combo.addItem(st("lang_chinese", self.ui_language), "zh")
        self.language_combo.addItem(st("lang_english", self.ui_language), "en")
        form.addRow(st("label_ui_language", self.ui_language), self.language_combo)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_transcriber_tab(self):
        """Create transcription settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_model", self.ui_language))
        form = QFormLayout(group)

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_combo.setCurrentIndex(1)  # base
        form.addRow(st("label_model_size", self.ui_language), self.model_combo)

        # Language
        self.language_edit = QLineEdit()
        self.language_edit.setPlaceholderText("Auto-detect")
        form.addRow(st("label_language", self.ui_language), self.language_edit)

        # Compute type
        self.compute_combo = QComboBox()
        self.compute_combo.addItems(["auto", "float16", "float32", "int8", "int8_float16"])
        self.compute_combo.setCurrentIndex(0)
        form.addRow(st("label_compute_type", self.ui_language), self.compute_combo)

        # Beam size
        self.beam_spin = QSpinBox()
        self.beam_spin.setRange(1, 10)
        self.beam_spin.setValue(5)
        form.addRow(st("label_beam_size", self.ui_language), self.beam_spin)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_audio_tab(self):
        """Create audio settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_audio", self.ui_language))
        form = QFormLayout(group)

        # Sample rate
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["16000", "22050", "44100", "48000"])
        self.sample_rate_combo.setCurrentIndex(0)
        form.addRow(st("label_sample_rate", self.ui_language), self.sample_rate_combo)

        # Channels
        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 2)
        self.channels_spin.setValue(1)
        form.addRow(st("label_channels", self.ui_language), self.channels_spin)

        # Device info
        device_layout = QHBoxLayout()
        self.device_label = QLabel("Default")
        device_info = QPushButton(st("button_refresh", self.ui_language))
        device_info.clicked.connect(self._refresh_devices)
        device_layout.addWidget(self.device_label)
        device_layout.addWidget(device_info)
        form.addRow(st("label_device", self.ui_language), device_layout)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_vad_tab(self):
        """Create VAD settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_vad", self.ui_language))
        form = QFormLayout(group)

        # Enable VAD
        self.vad_enabled_check = QCheckBox(st("check_enable_vad", self.ui_language))
        self.vad_enabled_check.setChecked(True)
        form.addRow("", self.vad_enabled_check)

        # Silence duration
        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(100, 5000)
        self.silence_spin.setValue(800)
        self.silence_spin.setSuffix(" ms")
        form.addRow(st("label_silence", self.ui_language), self.silence_spin)

        # Speech padding
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 2000)
        self.padding_spin.setValue(400)
        self.padding_spin.setSuffix(" ms")
        form.addRow(st("label_padding", self.ui_language), self.padding_spin)

        # Threshold
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(0.5)
        form.addRow(st("label_threshold", self.ui_language), self.threshold_spin)

        layout.addWidget(group)

        # Info
        info = QLabel(st("vad_note", self.ui_language))
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info)

        layout.addStretch()
        return widget

    def _create_keyboard_tab(self):
        """Create keyboard settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_input", self.ui_language))
        form = QFormLayout(group)

        # Input method
        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems(["clipboard", "direct"])
        self.input_method_combo.setCurrentIndex(0)
        form.addRow(st("label_method", self.ui_language), self.input_method_combo)

        # Typing speed (for direct)
        self.typing_speed_spin = QDoubleSpinBox()
        self.typing_speed_spin.setRange(0.001, 0.1)
        self.typing_speed_spin.setValue(0.01)
        self.typing_speed_spin.setSingleStep(0.001)
        form.addRow(st("label_typing_speed", self.ui_language), self.typing_speed_spin)

        # Paste delay (for clipboard)
        self.paste_delay_spin = QDoubleSpinBox()
        self.paste_delay_spin.setRange(0.01, 1.0)
        self.paste_delay_spin.setValue(0.1)
        self.paste_delay_spin.setSingleStep(0.01)
        form.addRow(st("label_paste_delay", self.ui_language), self.paste_delay_spin)

        layout.addWidget(group)

        # Info
        info = QLabel(st("input_note", self.ui_language))
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info)

        layout.addStretch()
        return widget

    def _create_hotkey_tab(self):
        """Create hotkey settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox(st("group_hotkey", self.ui_language))
        form = QFormLayout(group)

        # ALT trigger
        self.alt_trigger_check = QCheckBox(st("check_alt_trigger", self.ui_language))
        self.alt_trigger_check.setChecked(True)
        self.alt_trigger_check.setToolTip("Hold ALT to speak, release to send")
        form.addRow("", self.alt_trigger_check)

        # Info
        info = QLabel(st("hotkey_info", self.ui_language))
        info.setWordWrap(True)
        info.setStyleSheet("background: #e8f4e8; padding: 10px; border-radius: 4px;")

        layout.addWidget(group)
        layout.addWidget(info)
        layout.addStretch()
        return widget

    def _load_settings(self):
        """Load settings from config"""
        config = self.config

        # General
        current_lang = getattr(config, 'language', 'zh')
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_lang:
                self.language_combo.setCurrentIndex(i)
                break

        # Transcriber
        model_sizes = ["tiny", "base", "small", "medium", "large"]
        self.model_combo.setCurrentIndex(model_sizes.index(config.transcriber.model_size))
        if config.transcriber.language:
            self.language_edit.setText(config.transcriber.language)
        self.compute_combo.setCurrentText(config.transcriber.compute_type)
        self.beam_spin.setValue(config.transcriber.beam_size)

        # Audio
        self.sample_rate_combo.setCurrentText(str(config.audio.sample_rate))
        self.channels_spin.setValue(config.audio.channels)

        # VAD
        self.vad_enabled_check.setChecked(config.vad.enabled)
        self.silence_spin.setValue(config.vad.min_silence_duration_ms)
        self.padding_spin.setValue(config.vad.speech_pad_ms)
        self.threshold_spin.setValue(config.vad.threshold)

        # Keyboard
        self.input_method_combo.setCurrentText(config.keyboard.method)
        self.typing_speed_spin.setValue(config.keyboard.typing_speed)
        self.paste_delay_spin.setValue(config.keyboard.paste_delay)

        # Hotkeys
        self.alt_trigger_check.setChecked(config.hotkey.use_alt_trigger)

    def _save_settings(self):
        """Save settings to config"""
        config = self.config

        # General - save UI language
        config.language = self.language_combo.currentData()

        # Transcriber
        config.transcriber.model_size = self.model_combo.currentText()
        lang = self.language_edit.text().strip()
        config.transcriber.language = lang if lang else None
        config.transcriber.compute_type = self.compute_combo.currentText()
        config.transcriber.beam_size = self.beam_spin.value()

        # Audio
        config.audio.sample_rate = int(self.sample_rate_combo.currentText())
        config.audio.channels = self.channels_spin.value()

        # VAD
        config.vad.enabled = self.vad_enabled_check.isChecked()
        config.vad.min_silence_duration_ms = self.silence_spin.value()
        config.vad.speech_pad_ms = self.padding_spin.value()
        config.vad.threshold = self.threshold_spin.value()

        # Keyboard
        config.keyboard.method = self.input_method_combo.currentText()
        config.keyboard.typing_speed = self.typing_speed_spin.value()
        config.keyboard.paste_delay = self.paste_delay_spin.value()

        # Hotkeys
        config.hotkey.use_alt_trigger = self.alt_trigger_check.isChecked()

        # Save to file
        config.to_yaml()

        # Emit signal
        self.settings_changed.emit(config)

        logger.info("Settings saved")
        self.accept()

    def _refresh_devices(self):
        """Refresh audio device list"""
        from audio_capture import AudioCapture
        devices = AudioCapture.list_devices()

        if devices:
            device_names = [f"{d['index']}: {d['name']}" for d in devices]
            self.device_label.setText("\n".join(device_names[:5]))
        else:
            self.device_label.setText(st("no_devices", self.ui_language))
