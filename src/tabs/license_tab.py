"""A tab for checking license server status."""

import os
import subprocess
from PySide6.QtWidgets import (
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QPushButton,
    QLineEdit,
    QHBoxLayout,
    QLabel,
)


class LicenseTab(QWidget):
    """A widget to check license server status."""

    def __init__(self, context):
        super().__init__()
        self.controller = context
        self.setup_ui()

    def setup_ui(self):
        """Initialise the user interface."""
        layout = QVBoxLayout(self)

        # lmutil path selector
        lmutil_layout = QHBoxLayout()
        lmutil_label = QLabel("lmutil.exe path:")
        self.lmutil_path_input = QLineEdit()
        self.lmutil_path_button = QPushButton("Browse...")
        self.lmutil_path_button.clicked.connect(self.select_lmutil_path)
        lmutil_layout.addWidget(lmutil_label)
        lmutil_layout.addWidget(self.lmutil_path_input)
        lmutil_layout.addWidget(self.lmutil_path_button)
        layout.addLayout(lmutil_layout)

        # IP/Machine name input
        server_layout = QHBoxLayout()
        server_label = QLabel("License server (ip@port):")
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("e.g., 1055@127.0.0.1")
        server_layout.addWidget(server_label)
        server_layout.addWidget(self.server_input)
        layout.addLayout(server_layout)

        # Check license button
        button_layout = QHBoxLayout()
        self.check_license_button = QPushButton("Check License Status")
        self.check_license_button.setStyleSheet("background-color: #007bff; color: white; border: none;")
        self.check_license_button.clicked.connect(self.check_license_status)
        button_layout.addStretch()
        button_layout.addWidget(self.check_license_button)
        layout.addLayout(button_layout)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        layout.addWidget(self.text_browser)

        self.load_settings()
        self.lmutil_path_input.textChanged.connect(
            lambda text: self._on_setting_changed("lmutil_path", text)
        )
        self.server_input.textChanged.connect(
            lambda text: self._on_setting_changed("license_server", text)
        )

    def load_settings(self):
        """Load settings from the controller."""
        if self.controller:
            settings = self.controller.get_global_settings()
            self.lmutil_path_input.setText(settings.get("lmutil_path", ""))
            self.server_input.setText(settings.get("license_server", ""))

    def _on_setting_changed(self, key, value):
        """Save a setting to the controller."""
        if self.controller:
            self.controller.set_global_setting(key, value)

    def select_lmutil_path(self):
        """Open a file dialog to select lmutil.exe."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select lmutil.exe", "", "Executable files (*.exe)")
        if file_path:
            self.lmutil_path_input.setText(file_path)

    def check_license_status(self):
        """Check the license status using lmutil.exe."""
        lmutil_path = self.lmutil_path_input.text()
        server = self.server_input.text()

        if not os.path.exists(lmutil_path):
            self.text_browser.setHtml("<h1>lmutil.exe not found</h1>")
            return

        if not server:
            self.text_browser.setHtml("<h1>Please enter a license server</h1>")
            return

        try:
            command = [lmutil_path, "lmstat", "-a", "-c", server]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.text_browser.setPlainText(result.stdout)
        except subprocess.CalledProcessError as e:
            self.text_browser.setPlainText(f"Error executing lmutil.exe:\n{e.stderr}")
        except Exception as e:
            self.text_browser.setHtml(f"<h1>An error occurred</h1><p>{e}</p>")
