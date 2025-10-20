import os
import shutil
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QFileDialog,
)
from PySide6.QtCore import Qt


class ImportTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        import_group = QGroupBox("Layout Import")
        import_group_layout = QGridLayout(import_group)

        # Row 1: Layout type selection
        self.brd_radio = QRadioButton(".brd")
        self.aedb_radio = QRadioButton(".aedb")
        self.brd_radio.setChecked(True)
        import_group_layout.addWidget(self.brd_radio, 0, 0)
        import_group_layout.addWidget(self.aedb_radio, 0, 1)

        # Row 2: Path selection
        self.open_layout_button = QPushButton("Open...")
        self.layout_path_label = QLabel("No design loaded")
        import_group_layout.addWidget(QLabel("Design:"), 1, 0)
        import_group_layout.addWidget(self.layout_path_label, 1, 1)
        import_group_layout.addWidget(self.open_layout_button, 1, 2)

        # Row 3: Stackup selection
        self.stackup_path_input = QLineEdit()
        self.browse_stackup_button = QPushButton("Browse...")
        import_group_layout.addWidget(QLabel("Stackup (.xml):"), 2, 0)
        import_group_layout.addWidget(self.stackup_path_input, 2, 1)
        import_group_layout.addWidget(self.browse_stackup_button, 2, 2)
        
        # EDB version input
        import_group_layout.addWidget(QLabel("EDB version:"), 3, 0)
        self.edb_version_input = QLineEdit()
        self.edb_version_input.setFixedWidth(60)
        import_group_layout.addWidget(self.edb_version_input, 3, 1)

        layout.addWidget(import_group)

        self.apply_import_button = QPushButton("Apply")
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_import_button.setStyleSheet(primary_style)
        self.apply_import_button_original_style = primary_style
        layout.addWidget(self.apply_import_button, alignment=Qt.AlignRight)

        layout.addStretch()

    def bind_to_controller(self):
        self.brd_radio.toggled.connect(self.on_layout_type_changed)
        self.aedb_radio.toggled.connect(self.on_layout_type_changed)
        self.open_layout_button.clicked.connect(self.open_layout)
        self.browse_stackup_button.clicked.connect(self.browse_stackup)
        self.apply_import_button.clicked.connect(self.run_get_edb)

    def on_layout_type_changed(self, checked):
        if checked:
            self.layout_path_label.setText("No design loaded")
            self.stackup_path_input.clear()

    def open_layout(self):
        path = ""
        if self.brd_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                None,
                "Select .brd file",
                "",
                "BRD files (*.brd)",
            )
        elif self.aedb_radio.isChecked():
            path = QFileDialog.getExistingDirectory(
                None,
                "Select .aedb directory",
                ".",
                QFileDialog.ShowDirsOnly,
            )

        if path:
            self.layout_path_label.setText(path)
            self.controller.load_config()

    def browse_stackup(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Stackup File",
            "",
            "XML files (*.xml)",
        )
        if file_path:
            self.stackup_path_input.setText(file_path)

    def run_get_edb(self):
        controller = self.controller
        layout_path = self.layout_path_label.text()
        if not layout_path or layout_path == "No design loaded":
            controller.log("Please select a design first.", "red")
            return

        try:
            temp_root = os.path.join(controller.project_root, "temp")
            os.makedirs(temp_root, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            design_name = os.path.splitext(os.path.basename(layout_path))[0]
            session_dir_name = f"{design_name}_{timestamp}"
            session_dir = os.path.join(temp_root, session_dir_name)
            os.makedirs(session_dir)
            controller.log(f"Created session directory: {session_dir}")

            base_name = os.path.basename(layout_path)
            dest_path = os.path.join(session_dir, base_name)

            if os.path.isdir(layout_path):
                shutil.copytree(layout_path, dest_path)
            else:
                shutil.copy2(layout_path, dest_path)

            layout_path = dest_path
            controller.project_file = os.path.join(session_dir, "project.json")
            controller.log(
                f"Project file will be created at: {controller.project_file}"
            )

            stackup_path = self.stackup_path_input.text()
            if stackup_path and os.path.exists(stackup_path):
                dest_stackup_path = os.path.join(
                    session_dir, os.path.basename(stackup_path)
                )
                shutil.copy2(stackup_path, dest_stackup_path)
                stackup_path = dest_stackup_path
            else:
                stackup_path = ""

        except Exception as exc:
            controller.log(f"Error preparing temp folder: {exc}", "red")
            return

        controller.log(f"Opening layout: {layout_path}")
        controller._set_button_running(self.apply_import_button)
        controller.current_layout_path = layout_path

        script_path = os.path.join(controller.scripts_dir, "get_edb.py")
        python_executable = sys.executable
        edb_version = self.edb_version_input.text()

        command = [
            python_executable,
            script_path,
            layout_path,
            edb_version,
            stackup_path,
            controller.project_file,
        ]
        controller.log(f"Running command: {' '.join(command)}")
        metadata = {
            "type": "get_edb",
            "description": "Importing layout into EDB",
            "button": self.apply_import_button,
            "button_style": getattr(
                self, "apply_import_button_original_style", ""
            ),
            "button_reset_text": "Apply",
        }

        controller._submit_task(
            command,
            metadata=metadata,
            input_path=layout_path,
            output_path=controller.project_file,
            description=metadata["description"],
        )
