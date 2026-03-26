"""
Voice Activity Detection (VAD) module.
Detects speech segments in audio stream using faster-whisper's VAD.
"""

import numpy as np
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass
from collections import deque
import time

from config import VADConfig, get_config


logger = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    """A detected speech segment"""
    start_sample: int
    end_sample: int
    start_time: float
    end_time: float
    audio: np.ndarray


class VADDetector:
    """Voice Activity Detection using faster-whisper VAD"""

    def __init__(self, config: Optional[VADConfig] = None, sample_rate: int = 16000):
        """
        Args:
            config: VAD configuration
            sample_rate: Audio sample rate
        """
        self.config = config or get_config().vad
        self.sample_rate = sample_rate

        # VAD model (lazy loaded)
        self._vad_model = None
        self._vad_enabled = self.config.enabled

        # Speech state tracking
        self.is_speech_active = False
        self.speech_start_time: Optional[float] = None
        self.silence_start_time: Optional[float] = None

        # Audio buffer for current speech segment
        self.speech_buffer: List[np.ndarray] = []
        self.silence_buffer: List[np.ndarray] = []

        # Callbacks
        self.on_speech_start: Optional[callable] = None
        self.on_speech_end: Optional[callable] = None

        # Statistics
        self._total_samples_processed = 0
        self._speech_samples = 0

        # Lazy load VAD if enabled
        if self._vad_enabled:
            self._load_vad_model()

    def _load_vad_model(self) -> None:
        """Load the VAD model"""
        try:
            from faster_whisper import VadModel
            logger.info("Loading faster-whisper VAD model...")
            self._vad_model = VadModel()
            logger.info("VAD model loaded successfully")
        except ImportError:
            logger.warning("faster-whisper not available, VAD disabled")
            self._vad_enabled = False
        except Exception as e:
            logger.warning(f"Failed to load VAD model: {e}, VAD disabled")
            self._vad_enabled = False

    def process_audio(self, audio: np.ndarray) -> Optional[SpeechSegment]:
        """
        Process audio chunk and return speech segment if speech ends.

        Args:
            audio: Audio chunk (float32, [-1, 1] range)

        Returns:
            SpeechSegment if speech ended, None otherwise
        """
        if not self._vad_enabled or audio.size == 0:
            return None

        self._total_samples_processed += len(audio)

        # Run VAD on audio chunk
        is_speech = self._detect_speech(audio)

        current_time = time.time()

        if is_speech:
            self._speech_samples += len(audio)

            # Speech started
            if not self.is_speech_active:
                self.is_speech_active = True
                self.speech_start_time = current_time
                self.speech_buffer = []
                self.silence_buffer = []
                logger.debug("Speech started")

                # Trigger callback
                if self.on_speech_start:
                    self.on_speech_start()

            # Add to speech buffer
            self.speech_buffer.append(audio)
            self.silence_buffer = []  # Clear silence buffer

        else:
            # Silence detected
            if self.is_speech_active:
                self.silence_buffer.append(audio)

                # Check if silence duration exceeded threshold
                silence_samples = sum(len(chunk) for chunk in self.silence_buffer)
                silence_duration_ms = (silence_samples / self.sample_rate) * 1000

                if silence_duration_ms >= self.config.min_silence_duration_ms:
                    # Speech ended, return segment
                    return self._create_speech_segment(current_time)

            # Still add silence to buffer for continuity
            elif self.speech_buffer:
                self.silence_buffer.append(audio)

        return None

    def _detect_speech(self, audio: np.ndarray) -> bool:
        """Detect if audio contains speech using VAD"""
        if self._vad_model is None:
            return False

        try:
            # faster-whisper VAD expects specific input format
            # Process in chunks for better accuracy
            chunk_size = int(self.sample_rate * 0.5)  # 500ms chunks
            speech_chunks = 0
            total_chunks = 0

            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i + chunk_size]
                if len(chunk) < chunk_size:
                    continue

                # Convert to int16 for VAD
                chunk_int16 = (chunk * 32767).astype(np.int16)

                # Run VAD
                try:
                    speech_prob = self._vad_model(chunk_int16, self.sample_rate)
                    if speech_prob > self.config.threshold:
                        speech_chunks += 1
                    total_chunks += 1
                except Exception:
                    # Fallback: treat as speech if VAD fails
                    speech_chunks += 1
                    total_chunks += 1

            # If majority of chunks contain speech, return True
            if total_chunks > 0:
                return speech_chunks / total_chunks > 0.3

            return False

        except Exception as e:
            logger.debug(f"VAD detection error: {e}")
            return False

    def _create_speech_segment(self, end_time: float) -> SpeechSegment:
        """Create a speech segment from buffered audio"""
        # Concatenate all audio chunks
        audio_chunks = []
        if self.speech_buffer:
            audio_chunks.extend(self.speech_buffer)
        if self.silence_buffer:
            audio_chunks.extend(self.silence_buffer)  # Include trailing silence

        if audio_chunks:
            full_audio = np.concatenate(audio_chunks)
        else:
            full_audio = np.array([], dtype=np.float32)

        # Apply padding if configured
        pad_samples = int((self.config.speech_pad_ms / 1000) * self.sample_rate)
        if pad_samples > 0 and len(full_audio) > 0:
            # Add silence padding at beginning and end
            padding = np.zeros(pad_samples, dtype=np.float32)
            full_audio = np.concatenate([padding, full_audio, padding])

        segment = SpeechSegment(
            start_sample=0,
            end_sample=len(full_audio),
            start_time=self.speech_start_time or end_time,
            end_time=end_time,
            audio=full_audio
        )

        # Reset state
        self.is_speech_active = False
        self.speech_start_time = None
        self.speech_buffer = []
        self.silence_buffer = []

        logger.debug(f"Speech ended: {len(full_audio)} samples")

        # Trigger callback
        if self.on_speech_end:
            self.on_speech_end(segment)

        return segment

    def reset(self) -> None:
        """Reset VAD state"""
        self.is_speech_active = False
        self.speech_start_time = None
        self.silence_start_time = None
        self.speech_buffer = []
        self.silence_buffer = []

    def get_statistics(self) -> dict:
        """Get VAD statistics"""
        total_duration = self._total_samples_processed / self.sample_rate
        speech_duration = self._speech_samples / self.sample_rate

        return {
            "total_duration_seconds": total_duration,
            "speech_duration_seconds": speech_duration,
            "speech_ratio": speech_duration / total_duration if total_duration > 0 else 0,
            "total_samples": self._total_samples_processed,
            "speech_samples": self._speech_samples,
        }

    def is_speaking(self) -> bool:
        """Check if speech is currently active"""
        return self.is_speech_active


class SimpleVAD:
    """Simple energy-based VAD fallback (no model required)"""

    def __init__(self, config: Optional[VADConfig] = None, sample_rate: int = 16000):
        self.config = config or get_config().vad
        self.sample_rate = sample_rate
        self.threshold = 0.01  # Energy threshold

    def detect(self, audio: np.ndarray) -> bool:
        """Detect speech based on audio energy"""
        if audio.size == 0:
            return False

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio ** 2))
        return rms > self.threshold


class ManualVAD:
    """
    Manual VAD for ALT key trigger mode.
    Speech is active when ALT is pressed, inactive when released.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_active = False
        self.start_time: Optional[float] = None
        self.buffer: List[np.ndarray] = []

    def start(self) -> None:
        """Start speech detection (ALT pressed)"""
        if not self.is_active:
            self.is_active = True
            self.start_time = time.time()
            self.buffer = []
            logger.debug("Manual VAD started")

    def stop(self) -> Optional[np.ndarray]:
        """Stop speech detection and return audio (ALT released)"""
        if not self.is_active:
            return None

        self.is_active = False

        if self.buffer:
            audio = np.concatenate(self.buffer)
            logger.debug(f"Manual VAD stopped: {len(audio)} samples")
            return audio

        return None

    def add_audio(self, audio: np.ndarray) -> None:
        """Add audio to buffer when active"""
        if self.is_active:
            self.buffer.append(audio)

    def is_speaking(self) -> bool:
        """Check if speech is active"""
        return self.is_active

    def reset(self) -> None:
        """Reset state"""
        self.is_active = False
        self.start_time = None
        self.buffer = []
