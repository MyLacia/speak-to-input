"""
Audio capture module for recording microphone input.
Implements a circular buffer to manage continuous audio streaming.
"""

import numpy as np
import sounddevice as sd
import threading
import queue
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field

from config import AudioConfig, get_config


logger = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    """A chunk of audio data with metadata"""
    data: np.ndarray
    sample_rate: int
    timestamp: float
    is_speech: bool = False


class CircularBuffer:
    """Thread-safe circular buffer for audio data"""

    def __init__(self, max_duration: float, sample_rate: int):
        """
        Args:
            max_duration: Maximum duration in seconds to keep
            sample_rate: Audio sample rate
        """
        self.max_samples = int(max_duration * sample_rate)
        self.sample_rate = sample_rate
        self.buffer: np.ndarray = np.zeros(self.max_samples, dtype=np.float32)
        self.write_pos = 0
        self.lock = threading.Lock()
        self._size = 0

    def write(self, data: np.ndarray) -> None:
        """Write audio data to the buffer"""
        with self.lock:
            n_samples = len(data)

            # If data is larger than buffer, only keep the most recent portion
            if n_samples >= self.max_samples:
                self.buffer[:] = data[-self.max_samples:]
                self.write_pos = 0
                self._size = self.max_samples
                return

            # Calculate available space until end of buffer
            space_to_end = self.max_samples - self.write_pos

            if n_samples <= space_to_end:
                # Data fits in the remaining space
                self.buffer[self.write_pos:self.write_pos + n_samples] = data
            else:
                # Need to wrap around
                self.buffer[self.write_pos:] = data[:space_to_end]
                self.buffer[:n_samples - space_to_end] = data[space_to_end:]

            self.write_pos = (self.write_pos + n_samples) % self.max_samples
            self._size = min(self._size + n_samples, self.max_samples)

    def read(self, duration: float) -> np.ndarray:
        """Read the most recent audio data"""
        with self.lock:
            n_samples = int(duration * self.sample_rate)
            n_samples = min(n_samples, self._size)

            if n_samples == 0:
                return np.array([], dtype=np.float32)

            # Calculate read position (wrap backwards from write_pos)
            read_pos = (self.write_pos - n_samples) % self.max_samples

            space_to_end = self.max_samples - read_pos

            if n_samples <= space_to_end:
                return self.buffer[read_pos:read_pos + n_samples].copy()
            else:
                # Need to wrap around
                result = np.empty(n_samples, dtype=np.float32)
                result[:space_to_end] = self.buffer[read_pos:]
                result[space_to_end:] = self.buffer[:n_samples - space_to_end]
                return result

    def clear(self) -> None:
        """Clear the buffer"""
        with self.lock:
            self.buffer.fill(0)
            self.write_pos = 0
            self._size = 0

    def size(self) -> int:
        """Get current buffer size in samples"""
        with self.lock:
            return self._size

    def duration(self) -> float:
        """Get current buffer duration in seconds"""
        with self.lock:
            return self._size / self.sample_rate


class AudioCapture:
    """Continuous audio capture from microphone"""

    def __init__(self, config: Optional[AudioConfig] = None):
        """
        Args:
            config: Audio configuration
        """
        self.config = config or get_config().audio
        self.sample_rate = self.config.sample_rate
        self.channels = self.config.channels

        # Circular buffer for recent audio (keeps up to 30 seconds)
        self.buffer: Optional[CircularBuffer] = None

        # Recording buffer for current speech segment
        self.recording_buffer: list[np.ndarray] = []
        self.is_recording = False

        # Stream control
        self.stream: Optional[sd.InputStream] = None
        self.is_running = False
        self.lock = threading.Lock()

        # Audio queue for callback
        self.audio_queue: queue.Queue = queue.Queue()

        # Callback for speech detection events
        self.on_audio_chunk: Optional[Callable[[AudioChunk], None]] = None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: int) -> None:
        """Callback function for audio stream"""
        if status:
            logger.warning(f"Audio callback status: {status}")

        # Convert to float32 and mono if needed
        audio = indata[:, 0].astype(np.float32) if self.channels == 1 else indata.astype(np.float32)

        # Normalize to [-1, 1] range
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max

        # Put in queue for processing
        try:
            self.audio_queue.put_nowait(audio)
        except queue.Full:
            pass

    def start(self) -> None:
        """Start audio capture"""
        with self.lock:
            if self.is_running:
                return

            # Initialize buffer
            self.buffer = CircularBuffer(max_duration=30.0, sample_rate=self.sample_rate)

            # Create input stream
            try:
                device = self.config.device_index if self.config.device_index is not None else None

                # Log device information
                if device is not None:
                    logger.info(f"Using configured audio device: {device}")
                    device_info = sd.query_devices(device)
                    logger.info(f"  Device name: {device_info['name']}")
                else:
                    # Use system default
                    default_device = sd.default.device[0]
                    logger.info(f"Using system default audio device: {default_device}")
                    device_info = sd.query_devices(default_device)
                    logger.info(f"  Device name: {device_info['name']}")

                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=np.float32,
                    callback=self._audio_callback,
                    device=device
                )
                self.stream.start()
                self.is_running = True

                # Start processing thread
                self._processing_thread = threading.Thread(target=self._process_audio, daemon=True)
                self._processing_thread.start()

                logger.info(f"Audio capture started: {self.sample_rate}Hz, {self.channels} channel(s)")
            except Exception as e:
                logger.error(f"Failed to start audio capture: {e}")
                raise

    def stop(self) -> None:
        """Stop audio capture"""
        with self.lock:
            if not self.is_running:
                return

            self.is_running = False

            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None

            logger.info("Audio capture stopped")

    def _process_audio(self) -> None:
        """Process audio chunks from queue"""
        import time

        while self.is_running:
            try:
                # Get audio chunk with timeout
                audio = self.audio_queue.get(timeout=0.1)

                # Write to circular buffer
                if self.buffer is not None:
                    self.buffer.write(audio)

                # If recording, add to recording buffer
                if self.is_recording:
                    self.recording_buffer.append(audio)

                # Notify callback
                if self.on_audio_chunk:
                    chunk = AudioChunk(
                        data=audio,
                        sample_rate=self.sample_rate,
                        timestamp=time.time()
                    )
                    self.on_audio_chunk(chunk)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing audio: {e}")

    def start_recording(self) -> None:
        """Start recording speech segment"""
        with self.lock:
            self.is_recording = True
            self.recording_buffer = []
            logger.debug("Recording started")

    def stop_recording(self) -> Optional[np.ndarray]:
        """Stop recording and return concatenated audio"""
        with self.lock:
            self.is_recording = False

            if not self.recording_buffer:
                return None

            # Concatenate all chunks
            audio = np.concatenate(self.recording_buffer)
            self.recording_buffer = []

            logger.debug(f"Recording stopped: {len(audio)} samples")
            return audio

    def get_recent_audio(self, duration: float) -> np.ndarray:
        """Get recent audio from circular buffer"""
        if self.buffer is None:
            return np.array([], dtype=np.float32)

        return self.buffer.read(duration)

    def get_buffer_duration(self) -> float:
        """Get current buffer duration"""
        if self.buffer is None:
            return 0.0
        return self.buffer.duration()

    @staticmethod
    def list_devices() -> list[dict]:
        """List available audio input devices"""
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] > 0:
                devices.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': device['default_samplerate']
                })
        return devices


# Convenience function for getting audio capture instance
_capture_instance: Optional[AudioCapture] = None


def get_audio_capture() -> AudioCapture:
    """Get singleton audio capture instance"""
    global _capture_instance
    if _capture_instance is None:
        _capture_instance = AudioCapture()
    return _capture_instance
