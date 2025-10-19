from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
)
from PySide6.QtCore import Qt


class ResultTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        result_layout = QVBoxLayout(self)
        project_group = QGroupBox("Project File")
        project_layout = QHBoxLayout(project_group)
        
        self.project_path_input = QLineEdit()
        self.browse_project_button = QPushButton("Browse...")
        
        project_layout.addWidget(QLabel("Project JSON:"))
        project_layout.addWidget(self.project_path_input)
        project_layout.addWidget(self.browse_project_button)
        
        result_layout.addWidget(project_group)
        
        self.apply_result_button = QPushButton("Apply")
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_result_button.setStyleSheet(primary_style)
        self.apply_result_button_original_style = primary_style
        result_layout.addWidget(self.apply_result_button, alignment=Qt.AlignRight)
        
        self.html_group = QGroupBox("HTML Report")
        html_layout = QVBoxLayout(self.html_group)
        self.html_path_input = QLineEdit()
        self.html_path_input.setReadOnly(True)
        html_layout.addWidget(self.html_path_input)
        self.open_html_button = QPushButton("Open")
        html_layout.addWidget(self.open_html_button, alignment=Qt.AlignRight)
        result_layout.addWidget(self.html_group)
        self.html_group.setVisible(False)
        
        result_layout.addStretch()
