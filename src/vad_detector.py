# -*- coding: utf-8 -*-
"""
Voice Activity Detection (VAD) module.
Detects speech segments in audio stream using faster-whisper's VAD.
"""

import numpy as np
import logging
import threading
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
        # Use config threshold instead of hardcoded value
        self.threshold = get_config().audio.silence_threshold

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


class ContinuousVAD:
    """
    Continuous VAD for keyword-triggered listening mode.
    Detects trigger keyword and captures audio after a pause.
    Uses async trigger detection to avoid blocking the audio thread.
    """

    def __init__(self, config=None, sample_rate: int = 16000, transcriber=None):
        """
        Args:
            config: ContinuousConfig or None for default
            sample_rate: Audio sample rate
            transcriber: Transcriber instance for keyword detection
        """
        from config import ContinuousConfig, get_config

        self.config = config or get_config().continuous
        self.sample_rate = sample_rate
        self.transcriber = transcriber

        # States: IDLE, TRIGGERED, CAPTURING
        self.state = "IDLE"
        self.start_time: Optional[float] = None
        self.last_audio_time: Optional[float] = None
        self.last_speech_time: Optional[float] = None  # Only updated during CAPTURING
        self.trigger_time: Optional[float] = None

        # Audio buffers
        self.pre_buffer = deque()  # Circular buffer for audio before trigger
        self.capture_buffer: List[np.ndarray] = []  # Buffer for capturing after trigger

        # Pre-buffer size (keep last N seconds)
        self._pre_buffer_max_samples = int(self.config.buffer_duration * sample_rate)
        self._pre_buffer_current_samples = 0

        # Callbacks
        self.on_trigger_detected: Optional[callable] = None
        self.on_capture_start: Optional[callable] = None
        self.on_capture_complete: Optional[callable] = None

        # For keyword detection - we accumulate audio chunks for transcription
        self.detection_buffer: deque = deque()  # Use deque for O(1) popleft
        self._detection_buffer_samples = 0
        self._detection_chunk_samples = int(sample_rate * 0.4)  # 0.4s chunks for faster response
        self._sliding_window_overlap = 0.5  # Keep 50% of buffer for overlap detection

        # Async trigger detection state
        self._detection_checking = False  # True while Whisper is running in background
        self._detection_result: Optional[bool] = None  # Result from background check
        self._detection_thread: Optional[threading.Thread] = None
        self._detection_lock = threading.Lock()

        logger.info(f"ContinuousVAD initialized: trigger_word='{self.config.trigger_word}'")

    def process_audio(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """
        Process audio chunk and return captured audio if recording completes.

        Args:
            audio: Audio chunk (float32, [-1, 1] range)

        Returns:
            Audio array if capture completed, None otherwise
        """
        current_time = time.time()
        self.last_audio_time = current_time

        if self.state == "IDLE":
            return self._process_idle(audio, current_time)
        elif self.state == "TRIGGERED":
            return self._process_triggered(audio, current_time)
        elif self.state == "CAPTURING":
            # Only update last_speech_time during CAPTURING
            if not self._is_audio_silent(audio):
                self.last_speech_time = current_time
            return self._process_capturing(audio, current_time)

        return None

    def _process_idle(self, audio: np.ndarray, current_time: float) -> Optional[np.ndarray]:
        """Process audio while waiting for trigger word"""
        # Check if a background detection result is ready
        self._check_detection_result()

        # Add to pre-buffer
        self._add_to_pre_buffer(audio)

        # Skip accumulating new detection audio while a check is already running
        if self._detection_checking:
            return None

        # Add to detection buffer for keyword spotting
        self.detection_buffer.append(audio)
        self._detection_buffer_samples += len(audio)

        # When we have enough audio, submit async check for trigger word
        if self._detection_buffer_samples >= self._detection_chunk_samples:
            logger.debug(f"Detection buffer full: {self._detection_buffer_samples} samples, submitting async check")
            self._submit_trigger_check()

        return None

    def _check_detection_result(self) -> None:
        """Check if async trigger detection has a result"""
        with self._detection_lock:
            if self._detection_result is None:
                return

            detected = self._detection_result
            self._detection_result = None
            self._detection_checking = False

        if detected:
            # Trigger word detected!
            self.state = "TRIGGERED"
            self.trigger_time = time.time()
            self.detection_buffer.clear()
            self._detection_buffer_samples = 0

            logger.info(f"Trigger word '{self.config.trigger_word}' detected")
            print(f"\n[检测] 触发词 '{self.config.trigger_word}' 检测成功！")
            if self.on_trigger_detected:
                self.on_trigger_detected()
        else:
            # SLIDING WINDOW: Keep 50% of buffer for overlap detection
            keep_samples = int(self._detection_chunk_samples * self._sliding_window_overlap)
            while self._detection_buffer_samples > keep_samples and self.detection_buffer:
                removed = self.detection_buffer.popleft()
                self._detection_buffer_samples -= len(removed)
            logger.debug(f"Sliding window: kept {self._detection_buffer_samples}/{self._detection_chunk_samples} samples")

    def _submit_trigger_check(self) -> None:
        """Submit trigger word check to a background thread"""
        # Snapshot the detection buffer for the background thread
        audio = np.concatenate(list(self.detection_buffer))

        self._detection_checking = True

        def _check_async():
            result = self._do_trigger_check(audio)
            with self._detection_lock:
                self._detection_result = result

        t = threading.Thread(target=_check_async, daemon=True)
        t.start()

    def _do_trigger_check(self, audio: np.ndarray) -> bool:
        """Perform trigger word check (runs in background thread)"""
        if self.transcriber and self.transcriber.model_loaded:
            try:
                logger.debug(f"Background trigger check, audio samples: {len(audio)}")
                result = self.transcriber.transcribe(audio)
                if result and result.text:
                    trigger_word = self.config.trigger_word.lower()
                    transcribed_text = result.text.lower().strip()

                    # Remove punctuation and extra spaces for cleaner matching
                    import re
                    transcribed_clean = re.sub(r'[^\w\s]', '', transcribed_text)
                    transcribed_clean = ' '.join(transcribed_clean.split())

                    # Log for debugging
                    print(f"\n[检测] 识别到: '{transcribed_clean}' | 查找: '{trigger_word}'")
                    logger.info(f"Checking for '{trigger_word}' in: '{transcribed_clean}'")

                    # Direct match
                    if trigger_word in transcribed_clean:
                        logger.info(f"Trigger word found in: '{result.text}'")
                        return True

                    # Fuzzy match - handle common ASR misrecognitions
                    fuzzy_matches = ['嘿', '诶', '哎', '咳', '黑', '喂', '哈', '和', '赫', '合']
                    for match in fuzzy_matches:
                        if match in transcribed_clean:
                            logger.info(f"Trigger word (fuzzy) found: '{match}' in '{result.text}'")
                            print(f"[检测] 模糊匹配成功: '{match}'")
                            return True

                    logger.debug(f"No match found in: '{transcribed_clean}'")
                else:
                    logger.debug("Transcription returned empty result")
            except Exception as e:
                logger.error(f"Error checking for trigger word: {e}")
        else:
            logger.warning("Transcriber not available or model not loaded")

        return False

    def _process_triggered(self, audio: np.ndarray, current_time: float) -> Optional[np.ndarray]:
        """Process audio after trigger word, waiting for pause"""
        # Keep buffering audio in case we need to capture
        self._add_to_pre_buffer(audio)

        # Add to detection buffer to monitor for silence
        self.detection_buffer.append(audio)
        self._detection_buffer_samples += len(audio)

        # Check for pause (silence) after trigger word
        time_since_trigger = current_time - self.trigger_time

        if time_since_trigger >= self.config.pause_threshold:
            # Check if we've had silence after the trigger
            if self._is_silence_in_buffer():
                # Pause detected, start capturing
                self.state = "CAPTURING"
                self.start_time = current_time
                self.last_speech_time = None  # Reset for capture phase
                self.capture_buffer = []

                # Move pre-buffer content to capture buffer
                while self.pre_buffer:
                    self.capture_buffer.append(self.pre_buffer.popleft())
                self._pre_buffer_current_samples = 0

                logger.info("Pause detected after trigger, starting capture")
                if self.on_capture_start:
                    self.on_capture_start()

                # Clear detection buffer
                self.detection_buffer.clear()
                self._detection_buffer_samples = 0
            else:
                # Still speaking, reset trigger time to wait for pause
                self.trigger_time = current_time
                # Trim detection buffer to only keep recent audio for silence check
                max_samples = int(self.sample_rate * self.config.pause_threshold)
                while self._detection_buffer_samples > max_samples and self.detection_buffer:
                    removed = self.detection_buffer.popleft()
                    self._detection_buffer_samples -= len(removed)
                logger.debug("Still speaking after trigger, waiting for pause...")

        return None

    def _process_capturing(self, audio: np.ndarray, current_time: float) -> Optional[np.ndarray]:
        """Process audio while capturing"""
        # Add audio to capture buffer
        self.capture_buffer.append(audio)

        # Ensure minimum capture duration before allowing timeout
        if self.start_time and (current_time - self.start_time) < self.config.min_capture_duration:
            return None

        # Safety: maximum capture duration (30 seconds)
        if self.start_time and (current_time - self.start_time) > 30.0:
            return self._complete_capture(current_time)

        # Check for timeout (silence after speech)
        if self._is_audio_silent(audio):
            if self.last_speech_time:
                silence_since_speech = current_time - self.last_speech_time
                if silence_since_speech > self.config.timeout_duration:
                    return self._complete_capture(current_time)
            elif self.start_time and (current_time - self.start_time) > self.config.timeout_duration:
                # No speech detected since capture started, timeout
                return self._complete_capture(current_time)

        return None

    def _is_silence_in_buffer(self) -> bool:
        """Check if the detection buffer contains only silence"""
        if not self.detection_buffer:
            return True

        audio = np.concatenate(list(self.detection_buffer))
        rms = np.sqrt(np.mean(audio ** 2))
        from config import get_config
        threshold = get_config().audio.silence_threshold
        return rms < threshold

    def _is_audio_silent(self, audio: np.ndarray) -> bool:
        """Check if audio chunk is silent"""
        rms = np.sqrt(np.mean(audio ** 2))
        from config import get_config
        threshold = get_config().audio.silence_threshold
        return rms < threshold

    def _add_to_pre_buffer(self, audio: np.ndarray) -> None:
        """Add audio to pre-buffer (circular)"""
        self.pre_buffer.append(audio)
        self._pre_buffer_current_samples += len(audio)

        # Trim pre-buffer if it exceeds max size
        while self._pre_buffer_current_samples > self._pre_buffer_max_samples and self.pre_buffer:
            removed = self.pre_buffer.popleft()
            self._pre_buffer_current_samples -= len(removed)

    def _complete_capture(self, end_time: float) -> np.ndarray:
        """Complete capture and return audio"""
        if not self.capture_buffer:
            return np.array([], dtype=np.float32)

        # Concatenate all captured audio
        audio = np.concatenate(self.capture_buffer)

        # Reset state
        self.state = "IDLE"
        self.capture_buffer = []
        self.detection_buffer.clear()
        self._detection_buffer_samples = 0
        self.last_speech_time = None

        logger.info(f"Capture completed: {len(audio)} samples ({len(audio)/self.sample_rate:.2f}s)")

        if self.on_capture_complete:
            self.on_capture_complete(audio)

        return audio

    def reset(self) -> None:
        """Reset VAD state"""
        self.state = "IDLE"
        self.start_time = None
        self.last_audio_time = None
        self.last_speech_time = None
        self.trigger_time = None
        self.pre_buffer.clear()
        self.capture_buffer = []
        self.detection_buffer.clear()
        self._pre_buffer_current_samples = 0
        self._detection_buffer_samples = 0
        self._detection_checking = False
        self._detection_result = None
        logger.debug("ContinuousVAD reset")

    def get_state(self) -> str:
        """Get current state"""
        return self.state

    def is_capturing(self) -> bool:
        """Check if currently capturing"""
        return self.state == "CAPTURING"
