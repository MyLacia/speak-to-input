"""
Speak to Input - Real-time Speech-to-Text Desktop Application
Main entry point for the application.
"""

import sys
import logging
import faulthandler
from pathlib import Path

# Enable crash handler for C++ extensions
faulthandler.enable()

# Add src to path for imports
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    src_path = Path(sys.executable).parent / "_internal" / "src"
    if not src_path.exists():
        src_path = Path(sys.executable).parent / "src"
else:
    # Running from source
    src_path = Path(__file__).parent / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main application entry point"""
    try:
        # Enable high DPI scaling
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("Speak to Input")
        app.setOrganizationName("SpeakToInput")

        # Import and create main window
        from gui.main_window import MainWindow

        window = MainWindow()
        window.show()

        logger.info("Application started")

        # Run application
        result = app.exec_()

        logger.info(f"Application exiting with code: {result}")
        sys.exit(result)

    except Exception as e:
        logger.exception(f"Fatal error in main: {e}")
        import traceback
        traceback.print_exc()

        # Show error dialog if possible
        try:
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("启动错误")
            msg.setText(f"程序启动时发生错误：\n\n{str(e)}")
            msg.setDetailedText(traceback.format_exc())
            msg.exec_()
        except:
            pass

        sys.exit(1)


if __name__ == "__main__":
    main()
