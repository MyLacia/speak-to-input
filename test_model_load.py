"""
Test model loading in the same way the GUI does it.
This simulates the _load_model_step() process from main_window.py
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_gui_style_loading():
    """Test model loading the same way GUI does it"""
    print("=" * 60)
    print("Testing GUI-style Model Loading")
    print("=" * 60)

    try:
        # Stage 0: Import transcriber class
        print("\n[Stage 0] Importing Transcriber class...")
        from transcriber import Transcriber
        print("  OK")

        # Stage 1: Create transcriber instance (without loading model)
        print("\n[Stage 1] Creating Transcriber instance...")
        from config import get_config
        config = get_config()

        def progress_callback(stage, percent):
            print(f"  Progress: {stage} - {percent}%")

        transcriber = Transcriber(
            config=config.transcriber,
            progress_callback=progress_callback,
            timeout=120
        )
        print("  OK")

        # Stage 2: Load the actual model
        print("\n[Stage 2] Loading model (this may take 30-60 seconds)...")
        transcriber.load_model()
        print("  OK - Model loaded successfully!")

        # Test transcription
        print("\n[Stage 3] Testing transcription...")
        import numpy as np
        # Create 1 second of silence audio
        audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(audio)
        print(f"  OK - Transcription complete: {result}")

        # Cleanup
        transcriber.stop()
        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 60)
        print("Test FAILED")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = test_gui_style_loading()
    sys.exit(0 if success else 1)
