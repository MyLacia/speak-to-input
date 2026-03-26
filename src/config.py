"""
Configuration management for the speech-to-text application.
Supports loading from YAML file and default values.
"""

import os
import sys
import yaml
import logging
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path


logger = logging.getLogger(__name__)


def get_bundle_dir() -> Path:
    """Get the bundle directory (for PyInstaller) or source directory"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        # PyInstaller 6+ extracts data to _internal subdirectory
        exe_dir = Path(sys.executable).parent
        internal_dir = exe_dir / "_internal"
        if internal_dir.exists():
            return internal_dir
        return exe_dir
    else:
        # Running from source
        return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Get path to resource file, handling PyInstaller bundling"""
    bundle_dir = get_bundle_dir()
    return bundle_dir / relative_path


@dataclass
class VADConfig:
    """Voice Activity Detection configuration"""
    enabled: bool = True
    min_silence_duration_ms: int = 800  # Wait this long after silence before transcribing
    speech_pad_ms: int = 400  # Padding around speech segments
    threshold: float = 0.5  # Speech probability threshold


@dataclass
class TranscriberConfig:
    """Speech recognition configuration"""
    model_size: Literal["tiny", "base", "small", "medium", "large"] = "base"
    language: Optional[str] = None  # None for auto-detect
    compute_type: str = "auto"  # auto, float16, int8, etc.
    device: Optional[str] = None  # None for auto-detect (cuda/cpu)
    num_workers: int = 1
    beam_size: int = 5


@dataclass
class AudioConfig:
    """Audio capture configuration"""
    sample_rate: int = 16000  # Whisper native sample rate
    channels: int = 1
    chunk_duration: float = 0.5  # Duration of each audio chunk in seconds
    device_index: Optional[int] = None  # None for default microphone


@dataclass
class KeyboardConfig:
    """Keyboard emulation configuration"""
    method: Literal["clipboard", "direct"] = "clipboard"
    typing_speed: float = 0.01  # Delay between keystrokes (for direct method)
    paste_delay: float = 0.1  # Delay after paste


@dataclass
class HotkeyConfig:
    """Global hotkey configuration"""
    toggle: str = "<ctrl>+<shift>+<r>"  # Start/stop recognition
    pause: str = "<ctrl>+<shift>+<p>"  # Pause/resume
    clear: str = "<ctrl>+<shift>+<c>"  # Clear current text
    # ALT key trigger (press to speak, release to send)
    use_alt_trigger: bool = True


@dataclass
class Config:
    """Main configuration class"""
    vad: VADConfig = field(default_factory=VADConfig)
    transcriber: TranscriberConfig = field(default_factory=TranscriberConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)

    # UI Language (zh = Chinese, en = English)
    language: str = "zh"

    # Paths
    model_cache_dir: str = "models"
    log_dir: str = "logs"
    config_file: str = "config.yaml"

    def __post_init__(self):
        """Ensure directories exist as paths"""
        # Use bundle-aware path resolution
        base_dir = get_bundle_dir()

        # For models, check environment variable first (for dev mode)
        env_models = os.environ.get('SPEAKTOINPUT_MODELS_DIR')
        if env_models and Path(env_models).exists():
            self.model_cache_dir = env_models
        else:
            # Check if bundled
            bundled_models = base_dir / "models"
            if bundled_models.exists() and any(bundled_models.iterdir()):
                self.model_cache_dir = str(bundled_models)
            else:
                # Use user directory for downloaded models
                self.model_cache_dir = str(base_dir / self.model_cache_dir)

        # For logs and config, always use base directory
        self.log_dir = str(base_dir / self.log_dir)
        self.config_file = str(base_dir / self.config_file)

        # Create directories
        os.makedirs(self.log_dir, exist_ok=True)
        # Note: Don't create model_cache_dir if using bundled models (read-only)
        bundled_models = base_dir / "models"
        if not (env_models and Path(env_models).exists()) and \
           (not bundled_models.exists() or not any(bundled_models.iterdir())):
            os.makedirs(self.model_cache_dir, exist_ok=True)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file"""
        if not os.path.exists(path):
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Parse nested configs
        config = cls()

        if "vad" in data:
            config.vad = VADConfig(**data["vad"])
        if "transcriber" in data:
            config.transcriber = TranscriberConfig(**data["transcriber"])
        if "audio" in data:
            config.audio = AudioConfig(**data["audio"])
        if "keyboard" in data:
            config.keyboard = KeyboardConfig(**data["keyboard"])
        if "hotkey" in data:
            config.hotkey = HotkeyConfig(**data["hotkey"])

        return config

    def to_yaml(self, path: Optional[str] = None) -> None:
        """Save configuration to YAML file"""
        path = path or self.config_file

        data = {
            "vad": self.vad.__dict__,
            "transcriber": self.transcriber.__dict__,
            "audio": self.audio.__dict__,
            "keyboard": self.keyboard.__dict__,
            "hotkey": self.hotkey.__dict__,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# Default configuration instance
_default_config: Optional[Config] = None


def get_config() -> Config:
    """Get the default configuration instance (singleton)"""
    global _default_config
    if _default_config is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
        _default_config = Config.from_yaml(str(config_path))
    return _default_config


def reset_config() -> None:
    """Reset the configuration singleton"""
    global _default_config
    _default_config = None
