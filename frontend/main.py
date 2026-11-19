import sys
import os
import signal
import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Add repository root to sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from frontend.ui.main_window import MainWindow

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(name)s/%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

def main():
    setup_logging()
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.setApplicationName("SIH 2026 PS 26052 Live Defence Dashboard")
    
    config_path = os.path.join(repo_root, "frontend", "config", "frontend_config.json")
    if not os.path.exists(config_path):
        # Fallback to local relative config path
        config_path = os.path.expanduser("~/Documents/anc sih/frontend/config/frontend_config.json")
        
    window = MainWindow(config_path=config_path)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
