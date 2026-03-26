"""
Speech recognition module using faster-whisper.
Provides asynchronous transcription with GPU/CPU auto-detection.
"""

import numpy as np
import logging
import threading
import queue
import time
import os
import sys
import subprocess
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from config import TranscriberConfig, get_config


logger = logging.getLogger(__name__)


# Global flag to control safe mode (subprocess isolation)
USE_SUBPROCESS_LOADING = os.environ.get('WHISPER_SUBPROCESS_LOADING', 'auto').lower()


def _check_avx_support() -> bool:
    """Check if CPU supports AVX2 instruction set"""
    try:
        import cpuinfo
        info = cpuinfo.get_cpu_info()
        flags = info.get('flags', [])
        # Check for AVX2 support
        has_avx2 = 'avx2' in flags or 'AVX2' in flags
        logger.info(f"CPU AVX2 support: {has_avx2}")
        return has_avx2
    except ImportError:
        # cpuinfo not available, assume NO for safety
        logger.info("cpuinfo not available, assuming NO AVX2 support")
        return False
    except Exception as e:
        logger.warning(f"Failed to check AVX support: {e}, assuming NO")
        return False


# Check AVX support at module load
_AVX_SUPPORTED = _check_avx_support()


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
    """Speech recognition engine using faster-whisper"""

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

    def load_model(self) -> None:
        """
        Load the Whisper model synchronously.
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

    def _load_model(self) -> None:
        """Load the Whisper model with GPU/CPU auto-detection and fallback"""
        with self.lock:
            if self.model_loaded:
                return

            self._report_progress("detect_device", 10)
            from faster_whisper import WhisperModel

            model_path = Path(get_config().model_cache_dir)
            logger.info(f"Model cache directory: {model_path}")

            # Check if local model exists
            local_model_path = model_path / self.config.model_size
            model_bin = local_model_path / "model.bin"

            if not (local_model_path.exists() and model_bin.exists()):
                # Download model (will use model_size name)
                self._report_progress("download_model", 40)
                logger.info(f"Model not found locally, downloading to: {model_path}")

            # Try different compute types in order of preference
            compute_types_to_try = self._get_compute_type_fallback_list()
            device = self.config.device or self._detect_device()

            logger.info(f"Loading Whisper model '{self.config.model_size}' on {device}...")
            logger.info(f"Will try compute types in order: {compute_types_to_try}")

            last_error = None
            for idx, compute_type in enumerate(compute_types_to_try):
                try:
                    progress = 20 + (idx * 20)
                    self._report_progress("detect_device", progress)
                    logger.info(f"Attempt {idx + 1}: Trying compute_type='{compute_type}' on device='{device}'")

                    # Test import before actual model loading
                    self._safe_import_test()

                    if local_model_path.exists() and model_bin.exists():
                        self._report_progress("load_local_model", progress + 10)
                        logger.info(f"Using local model: {local_model_path}")
                        logger.info("Creating WhisperModel (this may take a moment)...")
                        self.model = WhisperModel(
                            str(local_model_path),
                            device=device,
                            compute_type=compute_type,
                        )
                    else:
                        self._report_progress("download_model", progress + 10)
                        logger.info(f"Downloading model to: {model_path}")
                        logger.info("Creating WhisperModel (this may take a moment)...")
                        self.model = WhisperModel(
                            self.config.model_size,
                            device=device,
                            compute_type=compute_type,
                            download_root=str(model_path),
                            num_workers=self.config.num_workers,
                        )

                    # If we got here, model loaded successfully
                    logger.info(f"WhisperModel created successfully with compute_type='{compute_type}'")
                    self._report_progress("complete", 100)
                    self.model_loaded = True
                    logger.info(f"Whisper model loaded successfully on {device} with compute_type={compute_type}")
                    return

                except Exception as e:
                    last_error = e
                    logger.warning(f"Failed with compute_type='{compute_type}': {e}")
                    # Clean up failed model
                    self.model = None
                    continue

            # All attempts failed
            logger.error(f"Failed to load Whisper model after trying all compute types")
            logger.error(f"Last error: {last_error}")
            self._report_progress("error", 0)
            raise RuntimeError(
                f"Failed to load Whisper model '{self.config.model_size}'. "
                f"Tried compute types: {compute_types_to_try}. "
                f"Last error: {last_error}"
            ) from last_error

    def _get_compute_type_fallback_list(self) -> list:
        """Get list of compute types to try in order"""
        if self.config.compute_type != "auto":
            logger.info(f"Using configured compute_type: {self.config.compute_type}")
            return [self.config.compute_type]

        # Fallback order based on device and AVX support
        device = self.config.device or self._detect_device()

        if device == "cuda":
            # GPU: try float16 first, then float32
            logger.info("Auto compute_type for CUDA: trying float16, then float32")
            return ["float16", "float32"]
        else:
            # CPU: prioritize based on AVX support
            if _AVX_SUPPORTED:
                logger.info("Auto compute_type for CPU (AVX2 supported): trying int8, then float32")
                return ["int8", "float32"]
            else:
                # No AVX2 support - use float32 which is more compatible
                logger.info("Auto compute_type for CPU (no AVX2): using float32")
                return ["float32"]

    def _safe_import_test(self) -> None:
        """Test if critical imports work before model loading"""
        try:
            import torch
            logger.debug(f"PyTorch version: {torch.__version__}")
            if torch.cuda.is_available():
                logger.debug(f"CUDA available: {torch.cuda.get_device_name(0)}")
        except ImportError as e:
            logger.warning(f"PyTorch not available: {e}")

        try:
            importctranslate2 = __import__('ctranslate2')
            logger.debug(f"CTranslate2 version: {getattr(importctranslate2, '__version__', 'unknown')}")
        except ImportError as e:
            logger.warning(f"CTranslate2 not available: {e}")

    def _detect_device(self) -> str:
        """Auto-detect available compute device (GPU/CPU)"""
        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA GPU detected")
                return "cuda"
        except ImportError:
            pass

        logger.info("Using CPU for inference")
        return "cpu"

    def _get_compute_type(self, device: str) -> str:
        """Get optimal compute type for device"""
        if self.config.compute_type != "auto":
            return self.config.compute_type

        if device == "cuda":
            return "float16"
        return "int8"

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

        start_time = time.time()

        try:
            # Convert to float32 if needed
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Run transcription
            segments, info = self.model.transcribe(
                audio,
                language=self.config.language,
                beam_size=self.config.beam_size,
                vad_filter=False,  # We handle VAD separately
                word_timestamps=True,
            )

            # Collect all text
            text_parts = []
            confidence_sum = 0
            confidence_count = 0

            for segment in segments:
                text_parts.append(segment.text.strip())
                if segment.avg_logprob is not None:
                    confidence_sum += segment.avg_logprob
                    confidence_count += 1

            text = " ".join(text_parts).strip()

            if not text:
                return None

            # Calculate confidence (convert logprob to approximate probability)
            avg_logprob = confidence_sum / confidence_count if confidence_count > 0 else -1.0
            confidence = max(0.0, min(1.0, (avg_logprob + 1) / 2))  # Rough approximation

            duration = time.time() - start_time

            result = TranscriptionResult(
                text=text,
                language=info.language,
                start_time=start_time,
                end_time=time.time(),
                duration=duration,
                confidence=confidence,
            )

            self._total_transcriptions += 1
            self._total_duration += duration

            return result

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

        - Add punctuation for Chinese
        - Remove extra spaces
        - Capitalize first letter
        """
        if not text:
            return ""

        # Remove leading/trailing whitespace
        text = text.strip()

        # Remove extra spaces
        import re
        text = re.sub(r"\s+", " ", text)

        # Capitalize first letter (for English)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        # Add period at end if no punctuation
        if text and text[-1] not in {".", "!", "?", "。", "！", "？", "，", ","}:
            # Check if mostly Chinese
            chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            if chinese_chars > len(text) * 0.3:
                text += "。"  # Chinese period
            else:
                text += "."  # English period

        return text

    def reload_model(self, model_size: str) -> bool:
        """
        Reload with a different model size.

        Args:
            model_size: New model size (tiny, base, small, medium, large)

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
