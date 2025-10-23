import os
import shutil
import sys
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QFileDialog,
    QHBoxLayout,
)
from PySide6.QtCore import Qt


class ImportTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Layout Import Group ---
        import_group = QGroupBox("Layout Import")
        import_layout = QGridLayout(import_group)
        import_layout.setColumnStretch(2, 1)  # Stretch the column with the design path

        import_layout.addWidget(QLabel("Layout Type:"), 0, 0)
        self.brd_radio = QRadioButton(".brd")
        self.aedb_radio = QRadioButton(".aedb")
        self.brd_radio.setChecked(True)
        
        layout_type_layout = QHBoxLayout()
        layout_type_layout.addWidget(self.brd_radio)
        layout_type_layout.addWidget(self.aedb_radio)
        import_layout.addLayout(layout_type_layout, 0, 1)

        import_layout.addWidget(QLabel("Design Path:"), 1, 0)
        self.layout_path_label = QLabel("No design loaded")
        self.open_layout_button = QPushButton("Open...")
        self.open_layout_button.setFixedWidth(80)
        import_layout.addWidget(self.layout_path_label, 1, 1, 1, 2)
        import_layout.addWidget(self.open_layout_button, 1, 3)

        import_layout.addWidget(QLabel("EDB Version:"), 2, 0)
        self.edb_version_input = QLineEdit("2024.1")
        self.edb_version_input.setFixedWidth(80)
        import_layout.addWidget(self.edb_version_input, 2, 1)
        
        main_layout.addWidget(import_group)

        # --- Apply Import Button ---
        import_button_layout = QHBoxLayout()
        import_button_layout.addStretch()
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_import_button = QPushButton("Apply")
        self.apply_import_button.setStyleSheet(primary_style)
        self.apply_import_button_original_style = primary_style
        import_button_layout.addWidget(self.apply_import_button)
        main_layout.addLayout(import_button_layout)

        # --- Stackup Edit Group ---
        stackup_group = QGroupBox("Stackup Edit")
        stackup_layout = QGridLayout(stackup_group)
        stackup_layout.setColumnStretch(1, 1)  # Make the input column expandable

        stackup_layout.addWidget(QLabel("Imported Stackup XML:"), 0, 0)
        self.imported_stackup_path = QLineEdit()
        self.imported_stackup_path.setReadOnly(True)
        self.copy_stackup_button = QPushButton("Copy")
        self.copy_stackup_button.setFixedWidth(80)
        stackup_layout.addWidget(self.imported_stackup_path, 0, 1, 1, 2)
        stackup_layout.addWidget(self.copy_stackup_button, 0, 3)

        stackup_layout.addWidget(QLabel("New Stackup XML:"), 1, 0)
        self.new_stackup_path_input = QLineEdit()
        self.browse_new_stackup_button = QPushButton("Browse...")
        self.browse_new_stackup_button.setFixedWidth(80)
        stackup_layout.addWidget(self.new_stackup_path_input, 1, 1, 1, 2)
        stackup_layout.addWidget(self.browse_new_stackup_button, 1, 3)

        main_layout.addWidget(stackup_group)
        
        # --- Apply Stackup Button ---
        stackup_button_layout = QHBoxLayout()
        stackup_button_layout.addStretch()
        self.apply_stackup_button = QPushButton("Apply")
        self.apply_stackup_button.setStyleSheet(primary_style)
        self.apply_stackup_button_original_style = primary_style
        stackup_button_layout.addWidget(self.apply_stackup_button)
        main_layout.addLayout(stackup_button_layout)

        main_layout.addStretch()

    def bind_to_controller(self):
        self.brd_radio.toggled.connect(self.on_layout_type_changed)
        self.aedb_radio.toggled.connect(self.on_layout_type_changed)
        self.open_layout_button.clicked.connect(self.open_layout)
        self.browse_new_stackup_button.clicked.connect(self.browse_new_stackup)
        self.copy_stackup_button.clicked.connect(self.copy_imported_stackup_path)
        self.apply_import_button.clicked.connect(self.run_get_edb)
        self.apply_stackup_button.clicked.connect(self.run_modify_stackup)

    def copy_imported_stackup_path(self):
        path = self.imported_stackup_path.text()
        if path:
            clipboard = QApplication.clipboard()
            clipboard.setText(path)
            self.controller.log(f"Copied to clipboard: {path}")

    def on_layout_type_changed(self, checked):
        if checked:
            self.layout_path_label.setText("No design loaded")
            self.imported_stackup_path.clear()
            self.new_stackup_path_input.clear()

    def open_layout(self):
        path = ""
        if self.brd_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                None, "Select .brd file", "", "BRD files (*.brd)")
        elif self.aedb_radio.isChecked():
            path = QFileDialog.getExistingDirectory(
                None, "Select .aedb directory", ".", QFileDialog.ShowDirsOnly)
        if path:
            self.layout_path_label.setText(path)
            self.controller.load_config()

    def browse_new_stackup(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select New Stackup File", "", "XML files (*.xml)")
        if file_path:
            self.new_stackup_path_input.setText(file_path)

    def run_modify_stackup(self):
        controller = self.controller
        new_stackup_path = self.new_stackup_path_input.text()
        
        if not controller.project_file or not os.path.exists(controller.project_file):
            controller.log("Please run the layout import first.", "red")
            return
            
        if not new_stackup_path or not os.path.exists(new_stackup_path):
            controller.log("Please select a valid new stackup file.", "red")
            return

        controller.log(f"Applying new stackup: {new_stackup_path}")
        controller._set_button_running(self.apply_stackup_button)

        action_spec = controller.get_action_spec("modify_xml", tab_name="import_tab")
        script_path = action_spec["script"]
        python_executable = sys.executable

        command = [python_executable, script_path, controller.project_file, new_stackup_path]
        
        metadata = {
            "type": "modify_xml",
            "description": "Modifying stackup XML",
            "button": self.apply_stackup_button,
            "button_style": self.apply_stackup_button_original_style,
            "button_reset_text": "Apply",
        }

        controller._submit_task(command, metadata=metadata)

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
            session_dir_name = f"{controller.app_name}_{timestamp}"
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

            # For the initial import, the new_stackup_path is the one to use if provided
            stackup_path = self.new_stackup_path_input.text()
            if stackup_path and os.path.exists(stackup_path):
                dest_stackup_path = os.path.join(
                    session_dir, os.path.basename(stackup_path)
                )
                shutil.copy2(stackup_path, dest_stackup_path)
                stackup_path = dest_stackup_path
            else:
                stackup_path = ""

            edb_version = self.edb_version_input.text()
            project_data = {
                "aedb_path": layout_path,
                "edb_version": edb_version,
                "stackup_path": stackup_path,
                "app_name": controller.app_name,
            }
            with open(controller.project_file, "w") as f:
                json.dump(project_data, f, indent=4)
            controller.log(f"Initial project file created: {controller.project_file}")

        except Exception as exc:
            controller.log(f"Error preparing temp folder or project file: {exc}", "red")
            return

        controller.log(f"Opening layout: {layout_path}")
        controller._set_button_running(self.apply_import_button)
        controller.current_layout_path = layout_path

        action_spec = controller.get_action_spec("get_edb", tab_name="import_tab")
        script_path = action_spec["script"]
        python_executable = sys.executable

        command = [python_executable, script_path, controller.project_file]
        
        metadata = {
            "type": "get_edb",
            "description": "Importing layout into EDB",
            "button": self.apply_import_button,
            "button_style": self.apply_import_button_original_style,
            "button_reset_text": "Apply",
        }

        controller._submit_task(
            command,
            metadata=metadata,
            input_path=layout_path,
            output_path=controller.project_file,
            description=metadata["description"],
        )
