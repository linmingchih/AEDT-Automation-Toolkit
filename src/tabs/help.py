"""A tab for displaying Markdown-based help content."""

import os
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget
import markdown


class HelpTab(QWidget):
    """A widget that renders and displays a Markdown help file."""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        """Initialise the user interface."""
        layout = QVBoxLayout(self)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        layout.addWidget(self.text_browser)

    def load_help_content(self, markdown_path):
        """Load and render the content of a given Markdown file."""
        if not os.path.exists(markdown_path):
            self.text_browser.setHtml("<h1>Help file not found</h1>")
            return

        try:
            with open(markdown_path, "r", encoding="utf-8") as handle:
                markdown_text = handle.read()
            html = markdown.markdown(markdown_text)
            self.text_browser.setHtml(html)
        except Exception as exc:
            self.text_browser.setHtml(f"<h1>Error loading help file</h1><p>{exc}</p>")
