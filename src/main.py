import sys
import os

# Add the project root to the Python path to allow for absolute imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from src.gui import MainApplicationWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApplicationWindow()
    window.show()
    sys.exit(app.exec())