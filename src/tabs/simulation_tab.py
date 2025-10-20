import json
import os
import sys

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QCheckBox,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt


class SimulationTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        simulation_layout = QVBoxLayout(self)

        cutout_group = QGroupBox("Cutout")
        cutout_layout = QGridLayout(cutout_group)
        self.enable_cutout_checkbox = QCheckBox("Enable cutout")
        self.expansion_size_input = QLineEdit("0.005000")
        self.signal_nets_label = QLabel("(not set)")
        self.signal_nets_label.setWordWrap(True)
        self.reference_net_label = QLabel("(not set)")
        cutout_layout.addWidget(self.enable_cutout_checkbox, 0, 0)
        cutout_layout.addWidget(QLabel("Expansion size (m)"), 1, 0)
        cutout_layout.addWidget(self.expansion_size_input, 1, 1)
        cutout_layout.addWidget(QLabel("Signal nets"), 2, 0)
        cutout_layout.addWidget(self.signal_nets_label, 2, 1)
        cutout_layout.addWidget(QLabel("Reference net"), 3, 0)
        cutout_layout.addWidget(self.reference_net_label, 3, 1)
        simulation_layout.addWidget(cutout_group)

        solver_group = QGroupBox("Solver")
        solver_layout = QHBoxLayout(solver_group)
        self.siwave_label = QLabel("SIwave")
        self.siwave_version_input = QLineEdit("2025.1")
        self.siwave_version_input.setFixedWidth(60)
        solver_layout.addWidget(self.siwave_label)
        solver_layout.addWidget(self.siwave_version_input)
        solver_layout.addStretch()
        simulation_layout.addWidget(solver_group)

        sweeps_group = QGroupBox("Frequency Sweeps")
        sweeps_layout = QVBoxLayout(sweeps_group)
        self.sweeps_table = QTableWidget()
        self.sweeps_table.setColumnCount(4)
        self.sweeps_table.setHorizontalHeaderLabels(["Sweep Type", "Start", "Stop", "Step/Count"])
        self.sweeps_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.add_sweep(["linear count", "0", "1kHz", "3"])
        self.add_sweep(["log scale", "1kHz", "0.1GHz", "10"])
        self.add_sweep(["linear scale", "0.1GHz", "10GHz", "0.1GHz"])
        sweeps_layout.addWidget(self.sweeps_table)
        
        sweep_buttons_layout = QHBoxLayout()
        add_sweep_button = QPushButton("Add Sweep")
        add_sweep_button.clicked.connect(lambda: self.add_sweep())
        remove_sweep_button = QPushButton("Remove Selected")
        remove_sweep_button.clicked.connect(self.remove_selected_sweep)
        sweep_buttons_layout.addWidget(add_sweep_button)
        sweep_buttons_layout.addWidget(remove_sweep_button)
        sweep_buttons_layout.addStretch()
        sweeps_layout.addLayout(sweep_buttons_layout)
        simulation_layout.addWidget(sweeps_group)

        self.apply_simulation_button = QPushButton("Apply")
        primary_style = "background-color: #007bff; color: white; border: none;"
        self.apply_simulation_button.setStyleSheet(primary_style)
        self.apply_simulation_button_original_style = primary_style
        simulation_layout.addWidget(self.apply_simulation_button, alignment=Qt.AlignRight)
        simulation_layout.addStretch()

    def add_sweep(self, sweep_data=None):
        if sweep_data is None:
            sweep_data = ["linear count", "", "", ""]
        row_position = self.sweeps_table.rowCount()
        self.sweeps_table.insertRow(row_position)

        sweep_type_combo = QComboBox()
        sweep_type_combo.addItems(["linear count", "log scale", "linear scale"])
        sweep_type_combo.setCurrentText(sweep_data[0])

        self.sweeps_table.setCellWidget(row_position, 0, sweep_type_combo)
        self.sweeps_table.setItem(row_position, 1, QTableWidgetItem(str(sweep_data[1])))
        self.sweeps_table.setItem(row_position, 2, QTableWidgetItem(str(sweep_data[2])))
        self.sweeps_table.setItem(row_position, 3, QTableWidgetItem(str(sweep_data[3])))

    def remove_selected_sweep(self):
        selected_ranges = self.sweeps_table.selectedRanges()
        if not selected_ranges:
            return

        rows_to_remove = set()
        for s_range in selected_ranges:
            for row in range(s_range.topRow(), s_range.bottomRow() + 1):
                rows_to_remove.add(row)

        for row in sorted(list(rows_to_remove), reverse=True):
            self.sweeps_table.removeRow(row)

    def bind_to_controller(self):
        self.apply_simulation_button.clicked.connect(self.apply_simulation_settings)

    def apply_simulation_settings(self):
        controller = self.controller
        import_tab = controller.tabs.get("import_tab")
        if not import_tab:
            return

        signal_nets_text = self.signal_nets_label.text()
        if not signal_nets_text or signal_nets_text == "(not set)":
            controller.log(
                "Signal nets are not defined. Please complete the 'Port Setup' tab first.",
                "red",
            )
            return

        aedb_path = import_tab.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            controller.log("Please open an .aedb project first.", "red")
            return

        project_data = {"app_name": controller.app_name}
        if controller.project_file and os.path.exists(controller.project_file):
            with open(controller.project_file, "r") as handle:
                project_data.update(json.load(handle))

        sweeps = []
        for row in range(self.sweeps_table.rowCount()):
            sweeps.append(
                [
                    self.sweeps_table.cellWidget(row, 0).currentText(),
                    self.sweeps_table.item(row, 1).text(),
                    self.sweeps_table.item(row, 2).text(),
                    self.sweeps_table.item(row, 3).text(),
                ]
            )

        project_data.update(
            {
                "aedb_path": aedb_path,
                "edb_version": import_tab.edb_version_input.text(),
                "cutout": {
                    "enabled": self.enable_cutout_checkbox.isChecked(),
                    "expansion_size": self.expansion_size_input.text(),
                    "signal_nets": self.signal_nets_label.text().split(", "),
                    "reference_net": [self.reference_net_label.text()],
                },
                "solver": "SIwave",
                "solver_version": self.siwave_version_input.text(),
                "frequency_sweeps": sweeps,
            }
        )

        try:
            with open(controller.project_file, "w") as handle:
                json.dump(project_data, handle, indent=2)
            controller.log(
                f"Simulation settings saved to {controller.project_file}"
            )

            controller.log("Applying simulation settings to EDB...")
            controller._set_button_running(self.apply_simulation_button)
            script_path = os.path.join(controller.scripts_dir, "set_sim.py")
            python_executable = sys.executable
            command = [python_executable, script_path, controller.project_file]

            metadata = {
                "type": "set_sim",
                "description": "Applying simulation setup",
                "button": self.apply_simulation_button,
                "button_style": getattr(
                    self, "apply_simulation_button_original_style", ""
                ),
                "button_reset_text": "Apply",
            }

            controller._submit_task(
                command,
                metadata=metadata,
                input_path=controller.project_file,
                description=metadata["description"],
            )

        except Exception as exc:
            controller.log(f"Error applying simulation settings: {exc}", color="red")
            controller._restore_button(
                self.apply_simulation_button,
                getattr(self, "apply_simulation_button_original_style", ""),
                "Apply",
            )
