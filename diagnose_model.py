"""
Diagnostic script for Whisper model loading issues.
Run this to identify the root cause of crashes.
"""

import sys
import logging
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test all required imports"""
    print("=" * 60)
    print("Testing imports...")
    print("=" * 60)

    tests = []

    # Test numpy
    try:
        import numpy as np
        tests.append(("numpy", True, f"version {np.__version__}"))
    except Exception as e:
        tests.append(("numpy", False, str(e)))

    # Test torch
    try:
        import torch
        cuda = "CUDA available" if torch.cuda.is_available() else "CPU only"
        tests.append(("torch", True, f"version {torch.__version__} ({cuda})"))
    except Exception as e:
        tests.append(("torch", False, str(e)))

    # Test ctranslate2
    try:
        import ctranslate2
        tests.append(("ctranslate2", True, f"version {ctranslate2.__version__}"))
    except Exception as e:
        tests.append(("ctranslate2", False, str(e)))

    # Test faster-whisper
    try:
        from faster_whisper import WhisperModel
        tests.append(("faster-whisper", True, "imported"))
    except Exception as e:
        tests.append(("faster-whisper", False, str(e)))

    for name, success, detail in tests:
        status = "✓ OK" if success else "✗ FAIL"
        print(f"{status:10} {name:20} {detail}")

    all_ok = all(success for _, success, _ in tests)
    return all_ok


def test_model_loading(model_path="models/base", device="cpu", compute_type="int8"):
    """Test actual model loading with different settings"""
    print("\n" + "=" * 60)
    print(f"Testing model loading: device={device}, compute_type={compute_type}")
    print("=" * 60)

    model_path = Path(model_path)
    if not model_path.exists():
        print(f"✗ Model path not found: {model_path}")
        return False

    print(f"✓ Model path exists: {model_path}")

    try:
        from faster_whisper import WhisperModel

        print("Creating WhisperModel...")
        print(f"  Path: {model_path}")
        print(f"  Device: {device}")
        print(f"  Compute type: {compute_type}")

        model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
        )

        print("✓ Model loaded successfully!")
        return True

    except Exception as e:
        print(f"✗ Model loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main diagnostic function"""
    print("\n" + "=" * 60)
    print("Whisper Model Loading Diagnostic Tool")
    print("=" * 60 + "\n")

    # Test imports first
    imports_ok = test_imports()

    # Torch is optional (faster-whisper has its own torch)
    # Only fail if faster-whisper or ctranslate2 failed
    fw_ok = any(name == "faster-whisper" and ok for name, ok, _ in [
        ("numpy", True, ""), ("torch", True, ""),  # placeholders
        ("ctranslate2", True, ""), ("faster-whisper", True, "")
    ])
    ctt_ok = any(name == "ctranslate2" and ok for name, ok, _ in [
        ("numpy", True, ""), ("torch", True, ""),  # placeholders
        ("ctranslate2", True, ""), ("faster-whisper", True, "")
    ])

    if not (fw_ok and ctt_ok):
        print("\nCritical imports failed. Please install:")
        print("   pip install --upgrade faster-whisper ctranslate2")
        return 1

    # Get model path from config or use default
    model_path = "models/base"

    # Test with different compute types
    compute_types = ["int8", "float32", "float16"]
    results = []

    for ct in compute_types:
        print(f"\n--- Testing compute_type='{ct}' ---")
        try:
            success = test_model_loading(model_path=model_path, device="cpu", compute_type=ct)
            results.append((ct, success))
            if success:
                print(f"✓ SUCCESS with compute_type='{ct}'")
                break
        except Exception as e:
            results.append((ct, False))
            print(f"✗ FAILED with compute_type='{ct}': {e}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for ct, success in results:
        status = "✓" if success else "✗"
        print(f"{status} compute_type='{ct}'")

    # Recommendation
    successful = [ct for ct, ok in results if ok]
    if successful:
        print(f"\n✓ Recommended compute_type: '{successful[0]}'")
        print(f"  Set in config.yaml: transcriber.compute_type: {successful[0]}")
        return 0
    else:
        print("\n❌ All compute types failed.")
        print("\nPossible solutions:")
        print("1. Update faster-whisper: pip install --upgrade faster-whisper")
        print("2. Update ctranslate2: pip install --upgrade ctranslate2")
        print("3. Try downloading a fresh model")
        print("4. Check if your CPU supports the required instructions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
