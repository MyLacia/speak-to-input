"""
Speech recognition module using FunASR Paraformer.
Provides asynchronous transcription with GPU/CPU auto-detection.
"""

import numpy as np
import logging
import threading
import queue
import time
import os
import re
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Try to import opencc for traditional to simplified Chinese conversion
try:
    import opencc
    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("opencc not available, traditional to simplified Chinese conversion disabled")

from config import TranscriberConfig, get_config


logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of speech transcription"""
    text: str
    language: str
    start_time: float
    end_time: float
    duration: float
    confidence: float = 0.0


class Transcriber:
    """Speech recognition engine using FunASR Paraformer"""

    def __init__(self, config: Optional[TranscriberConfig] = None,
                 progress_callback: Optional[Callable[[str, int], None]] = None,
                 timeout: int = 120):
        """
        Args:
            config: Transcriber configuration
            progress_callback: Callback for progress updates (stage, percent)
            timeout: Maximum seconds to wait for model loading
        """
        self.config = config or get_config().transcriber
        self.model = None
        self.model_loaded = False
        self.lock = threading.Lock()
        self._timeout = timeout

        # Processing queue
        self.audio_queue: queue.Queue = queue.Queue(maxsize=10)
        self.result_queue: queue.Queue = queue.Queue(maxsize=10)
        self.is_running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_transcription: Optional[Callable[[TranscriptionResult], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self._progress_callback = progress_callback

        # Statistics
        self._total_transcriptions = 0
        self._total_duration = 0.0

        # NOTE: Model loading deferred to load() method to avoid thread issues
        # The _ModelLoaderWorker will explicitly call load_model() after creation

        # OpenCC converter for traditional to simplified Chinese
        self._converter = None
        if OPENCC_AVAILABLE:
            try:
                self._converter = opencc.OpenCC('t2s')  # Traditional to Simplified
                logger.info("OpenCC converter initialized for t2s conversion")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenCC: {e}")

    def _convert_to_simplified(self, text: str) -> str:
        """Convert traditional Chinese to simplified Chinese"""
        if not text or not self._converter:
            return text
        try:
            return self._converter.convert(text)
        except Exception as e:
            logger.debug(f"OpenCC conversion failed: {e}")
            return text

    def _detect_silence(self, audio: np.ndarray, threshold: Optional[float] = None) -> bool:
        """
        Detect if audio is mostly silence.

        Args:
            audio: Audio data
            threshold: Energy threshold for silence detection (uses config if None)

        Returns:
            True if audio is considered silence
        """
        if threshold is None:
            from config import get_config
            threshold = get_config().audio.silence_threshold

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio ** 2))
        return rms < threshold

    def has_speech(self, audio: np.ndarray, threshold: Optional[float] = None) -> bool:
        """
        Check if audio contains speech (not silence).

        Args:
            audio: Audio data
            threshold: Minimum energy threshold to consider as speech (uses config if None)

        Returns:
            True if audio contains speech
        """
        if audio.size == 0:
            return False

        if threshold is None:
            from config import get_config
            threshold = get_config().audio.silence_threshold

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio ** 2))
        return rms >= threshold

    def load_model(self) -> None:
        """
        Load the Paraformer model synchronously.
        Call this after __init__ to actually load the model.
        """
        logger.info("load_model() - Starting model load process")
        try:
            self._load_model()
            logger.info("load_model() - Model load completed successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def _report_progress(self, stage: str, percent: int = 0):
        """Report loading progress if callback is set"""
        if self._progress_callback:
            self._progress_callback(stage, percent)

    def _load_model_with_timeout(self) -> None:
        """Load model with timeout mechanism"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._load_model)
            try:
                future.result(timeout=self._timeout)
            except FuturesTimeoutError:
                logger.error(f"Model loading timed out after {self._timeout} seconds")
                raise TimeoutError(f"模型加载超时 ({self._timeout}秒)，请检查网络连接或使用CPU模式")

    def _detect_device(self) -> str:
        """Auto-detect available compute device (GPU/CPU)"""
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA GPU detected")
                return "cuda:0"
        except ImportError:
            pass

        logger.info("Using CPU for inference")
        return "cpu"

    def _load_model(self) -> None:
        """Load the Paraformer model with GPU/CPU auto-detection"""
        with self.lock:
            if self.model_loaded:
                return

            self._report_progress("detect_device", 10)
            from funasr import AutoModel

            device = self.config.device or self._detect_device()
            model_name = self.config.model_size

            logger.info(f"Loading Paraformer model '{model_name}' on {device}...")
            self._report_progress("load_model", 40)

            try:
                self.model = AutoModel(
                    model=model_name,
                    device=device,
                    punc_model="ct-punc",  # Auto-add commas at speech pauses
                )

                self._report_progress("complete", 100)
                self.model_loaded = True
                logger.info(f"Paraformer model loaded successfully on {device}")

            except Exception as e:
                logger.error(f"Failed to load Paraformer model: {e}")
                self.model = None
                self._report_progress("error", 0)
                raise RuntimeError(
                    f"Failed to load Paraformer model '{model_name}' on {device}. "
                    f"Error: {e}"
                ) from e

    def start(self) -> None:
        """Start the transcription worker"""
        with self.lock:
            if self.is_running:
                return

            if not self.model_loaded:
                self._load_model()

            self.is_running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

            logger.info("Transcriber started")

    def stop(self) -> None:
        """Stop the transcription worker"""
        with self.lock:
            if not self.is_running:
                return

            self.is_running = False

            # Clear queues
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break

            logger.info("Transcriber stopped")

    def transcribe_async(self, audio: np.ndarray) -> None:
        """
        Submit audio for asynchronous transcription.

        Args:
            audio: Audio data (float32, 16kHz, mono)
        """
        if not self.is_running:
            logger.warning("Transcriber not running")
            return

        if audio.size == 0:
            logger.warning("Empty audio provided")
            return

        try:
            self.audio_queue.put_nowait(audio)
        except queue.Full:
            logger.warning("Audio queue full, dropping audio")

    def transcribe(self, audio: np.ndarray) -> Optional[TranscriptionResult]:
        """
        Synchronously transcribe audio.

        Args:
            audio: Audio data (float32, 16kHz, mono)

        Returns:
            TranscriptionResult or None if failed
        """
        if not self.model_loaded:
            logger.error("Model not loaded")
            return None

        if audio.size == 0:
            return None

        # Check audio energy
        rms = np.sqrt(np.mean(audio ** 2))
        logger.debug(f"Audio energy: {rms:.6f}, threshold: {get_config().audio.silence_threshold}")

        # Check for silence - return None if audio is too quiet
        if self._detect_silence(audio):
            logger.debug(f"Audio is silence (RMS={rms:.6f}), skipping transcription")
            return None

        start_time = time.time()

        try:
            # Convert to float32 if needed
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Run transcription using FunASR
            results = self.model.generate(
                input=audio,
                beam_size=self.config.beam_size,
            )

            if not results or len(results) == 0:
                return None

            # Extract text from result
            # FunASR returns: [{"key": "...", "text": "识别文本", "timestamp": [...]}]
            result = results[0]
            text = result.get("text", "").strip()

            if not text:
                return None

            # Convert traditional Chinese to simplified
            text = self._convert_to_simplified(text)

            # Calculate confidence from scores if available
            confidence = 0.0
            if "scores" in result and result["scores"]:
                avg_score = sum(result["scores"]) / len(result["scores"])
                confidence = max(0.0, min(1.0, avg_score))

            duration = time.time() - start_time

            lang = self.config.language or "zh"

            transcription = TranscriptionResult(
                text=text,
                language=lang,
                start_time=start_time,
                end_time=time.time(),
                duration=duration,
                confidence=confidence,
            )

            self._total_transcriptions += 1
            self._total_duration += duration

            return transcription

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            if self.on_error:
                self.on_error(e)
            return None

    def _worker_loop(self) -> None:
        """Worker thread for processing audio queue"""
        while self.is_running:
            try:
                # Get audio from queue with timeout
                audio = self.audio_queue.get(timeout=0.5)

                # Transcribe
                result = self.transcribe(audio)

                if result and result.text:
                    # Put result in queue
                    try:
                        self.result_queue.put_nowait(result)
                    except queue.Full:
                        pass

                    # Trigger callback
                    if self.on_transcription:
                        self.on_transcription(result)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")
                if self.on_error:
                    self.on_error(e)

    def get_result(self, timeout: float = 0.0) -> Optional[TranscriptionResult]:
        """
        Get the next transcription result.

        Args:
            timeout: Maximum time to wait (0 for non-blocking)

        Returns:
            TranscriptionResult or None
        """
        try:
            if timeout > 0:
                return self.result_queue.get(timeout=timeout)
            else:
                return self.result_queue.get_nowait()
        except queue.Empty:
            return None

    def post_process(self, text: str) -> str:
        """
        Post-process transcribed text.

        - Convert traditional to simplified Chinese
        - Remove all spaces
        - Remove trailing period
        """
        if not text:
            return ""

        # Convert traditional to simplified Chinese
        text = self._convert_to_simplified(text)

        # Remove all whitespace (spaces between Chinese chars are unwanted)
        text = re.sub(r"\s+", "", text)

        # Remove trailing sentence-ending punctuation (keep commas)
        if text and text[-1] in {"。", ".", "！", "!", "？", "?"}:
            text = text[:-1]

        return text

    def reload_model(self, model_size: str) -> bool:
        """
        Reload with a different model.

        Args:
            model_size: New model name (e.g., "paraformer-zh")

        Returns:
            True if successful
        """
        with self.lock:
            try:
                # Unload current model
                self.model = None
                self.model_loaded = False

                # Update config
                self.config.model_size = model_size

                # Load new model
                self._load_model()

                logger.info(f"Model reloaded: {model_size}")
                return True

            except Exception as e:
                logger.error(f"Failed to reload model: {e}")
                return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get transcription statistics"""
        return {
            "total_transcriptions": self._total_transcriptions,
            "total_duration_seconds": self._total_duration,
            "average_duration": self._total_duration / self._total_transcriptions if self._total_transcriptions > 0 else 0,
            "model_size": self.config.model_size,
            "model_loaded": self.model_loaded,
        }


# Singleton instance
_transcriber_instance: Optional[Transcriber] = None


def get_transcriber(config: Optional[TranscriberConfig] = None,
                    progress_callback: Optional[Callable[[str, int], None]] = None,
                    timeout: int = 120) -> Transcriber:
    """Get singleton transcriber instance"""
    global _transcriber_instance
    if _transcriber_instance is None:
        _transcriber_instance = Transcriber(config, progress_callback, timeout)
    return _transcriber_instance
