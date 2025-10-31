import os
import sys
import webbrowser

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QFileDialog,
)
from PySide6.QtCore import Qt

from .base import BaseTab


class ResultTab(BaseTab):
    def __init__(self, context):
        super().__init__(context)
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

    def bind_to_controller(self):
        self.browse_project_button.clicked.connect(self.browse_project_file)
        self.apply_result_button.clicked.connect(self.run_post_processing)
        self.open_html_button.clicked.connect(self.open_report_in_browser)

    def browse_project_file(self):
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Select project.json file",
            "",
            "JSON files (*.json)",
        )
        if path:
            self.project_path_input.setText(path)

    def run_post_processing(self):
        controller = self.controller
        project_file = self.project_path_input.text()
        if not project_file or not os.path.exists(project_file):
            controller.log("Please select a valid project.json file.", "red")
            return

        controller.project_file = project_file
        self.html_group.setVisible(False)
        controller.set_button_running(self.apply_result_button)
        self.run_get_loss()

    def open_report_in_browser(self):
        controller = self.controller
        if controller.report_path and os.path.exists(controller.report_path):
            try:
                webbrowser.open(f"file:///{os.path.abspath(controller.report_path)}")
                controller.log(f"Opening {controller.report_path} in browser.")
            except Exception as exc:
                controller.log(f"Could not open report in browser: {exc}", "red")
        else:
            controller.log("Report path not found or invalid.", "red")

    def run_get_loss(self):
        controller = self.controller
        if not controller.project_file or not os.path.exists(controller.project_file):
            controller.log("Project file not set. Cannot retrieve loss data.", "red")
            controller.restore_button(
                self.apply_result_button,
                getattr(self, "apply_result_button_original_style", ""),
                "Apply",
            )
            return

        metadata = {
            "type": "get_loss",
            "description": "Collecting SIwave loss data",
            "button": self.apply_result_button,
            "button_style": getattr(self, "apply_result_button_original_style", ""),
            "button_reset_text": "Apply",
        }

        action_spec = controller.get_action_spec("get_loss", tab_name="result_tab")
        script_path = action_spec["script"]
        command = [sys.executable, script_path, controller.project_file]
        if action_spec.get("args"):
            command.extend(action_spec["args"])

        controller.submit_task(
            command,
            metadata=metadata,
            input_path=controller.project_file,
            description=metadata["description"],
            working_dir=action_spec.get("working_dir"),
            env=action_spec.get("env"),
        )

    def run_generate_report(self):
        controller = self.controller
        if not controller.project_file or not os.path.exists(controller.project_file):
            controller.log("Project file not set. Cannot generate report.", "red")
            controller.restore_button(
                self.apply_result_button,
                getattr(self, "apply_result_button_original_style", ""),
                "Apply",
            )
            return

        metadata = {
            "type": "generate_report",
            "description": "Generating HTML report",
            "button": self.apply_result_button,
            "button_style": getattr(self, "apply_result_button_original_style", ""),
            "button_reset_text": "Apply",
        }

        action_spec = controller.get_action_spec("generate_report", tab_name="result_tab")
        script_path = action_spec["script"]
        command = [sys.executable, script_path, controller.project_file]
        if action_spec.get("args"):
            command.extend(action_spec["args"])

        controller.submit_task(
            command,
            metadata=metadata,
            input_path=controller.project_file,
            description=metadata["description"],
            working_dir=action_spec.get("working_dir"),
            env=action_spec.get("env"),
        )
