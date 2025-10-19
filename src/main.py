import sys
import os
import json
import re
import webbrowser
import subprocess
import shutil
from datetime import datetime
from PySide6.QtWidgets import QApplication, QFileDialog, QListWidgetItem
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QColor

from gui import AEDBCCTCalculator
from tabs.import_tab import ImportTab
from tabs.port_setup_tab import PortSetupTab
from tabs.simulation_tab import SimulationTab
from tabs.result_tab import ResultTab


class MainController(AEDBCCTCalculator):
    def __init__(self):
        super().__init__()
        self.project_file = None
        self.report_path = None
        self.pcb_data = None
        self.all_components = []
        
        self.setup_tabs()
        self.load_config()
        self.connect_signals()

    def setup_tabs(self):
        self.import_tab = ImportTab()
        self.port_setup_tab = PortSetupTab()
        self.simulation_tab = SimulationTab()
        self.result_tab = ResultTab()

        self.tabs.addTab(self.import_tab, "Import")
        self.tabs.addTab(self.port_setup_tab, "Port Setup")
        self.tabs.addTab(self.simulation_tab, "Simulation")
        self.tabs.addTab(self.result_tab, "Result")

    def connect_signals(self):
        # Import Tab Signals
        self.import_tab.brd_radio.toggled.connect(self.on_layout_type_changed)
        self.import_tab.aedb_radio.toggled.connect(self.on_layout_type_changed)
        self.import_tab.open_layout_button.clicked.connect(self.open_layout)
        self.import_tab.browse_stackup_button.clicked.connect(self.browse_stackup)
        self.import_tab.apply_import_button.clicked.connect(lambda: self.run_get_edb(self.import_tab.layout_path_label.text()))

        # Port Setup Tab Signals
        self.port_setup_tab.component_filter_input.textChanged.connect(self.filter_components)
        self.port_setup_tab.controller_components_list.itemSelectionChanged.connect(self.update_nets)
        self.port_setup_tab.dram_components_list.itemSelectionChanged.connect(self.update_nets)
        self.port_setup_tab.single_ended_list.itemChanged.connect(self.update_checked_count)
        self.port_setup_tab.differential_pairs_list.itemChanged.connect(self.update_checked_count)
        self.port_setup_tab.apply_button.clicked.connect(self.apply_settings)

        # Simulation Tab Signals
        self.simulation_tab.apply_simulation_button.clicked.connect(self.apply_simulation_settings)

        # Result Tab Signals
        self.result_tab.browse_project_button.clicked.connect(self.browse_project_file)
        self.result_tab.apply_result_button.clicked.connect(self.run_post_processing)
        self.result_tab.open_html_button.clicked.connect(self.open_report_in_browser)

    def on_layout_type_changed(self):
        if self.sender().isChecked():
            self.import_tab.layout_path_label.setText("No design loaded")
            self.import_tab.stackup_path_input.clear()

    def browse_project_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select project.json file", "", "JSON files (*.json)")
        if path:
            self.result_tab.project_path_input.setText(path)

    def run_post_processing(self):
        project_file = self.result_tab.project_path_input.text()
        if not project_file or not os.path.exists(project_file):
            self.log("Please select a valid project.json file.", "red")
            return
        self.project_file = project_file
        self.result_tab.html_group.setVisible(False)
        self.run_get_loss()

    def open_report_in_browser(self):
        if self.report_path and os.path.exists(self.report_path):
            try:
                webbrowser.open(f"file:///{os.path.abspath(self.report_path)}")
                self.log(f"Opening {self.report_path} in browser.")
            except Exception as e:
                self.log(f"Could not open report in browser: {e}", "red")
        else:
            self.log("Report path not found or invalid.", "red")

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

    def load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    sim_settings = config.get("simulation_settings", {})
                    self.simulation_tab.enable_cutout_checkbox.setChecked(sim_settings.get("cutout_enabled", False))
                    self.simulation_tab.expansion_size_input.setText(sim_settings.get("expansion_size", "0.005000"))
                    self.simulation_tab.siwave_version_input.setText(sim_settings.get("siwave_version", "2025.1"))
                    
                    sweeps = sim_settings.get("frequency_sweeps", [])
                    if sweeps:
                        self.simulation_tab.sweeps_table.setRowCount(0)
                        for sweep in sweeps:
                            self.simulation_tab.add_sweep(sweep)
            except (json.JSONDecodeError, KeyError) as e:
                self.log(f"Could not load config: {e}", "orange")

        if self.project_file and os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_config = json.load(f)
                self.import_tab.edb_version_input.setText(project_config.get("edb_version", "2024.1"))
        else:
            self.import_tab.edb_version_input.setText("2024.1")

    def save_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        sweeps = []
        for row in range(self.simulation_tab.sweeps_table.rowCount()):
            sweep_type = self.simulation_tab.sweeps_table.cellWidget(row, 0).currentText()
            start = self.simulation_tab.sweeps_table.item(row, 1).text()
            stop = self.simulation_tab.sweeps_table.item(row, 2).text()
            step = self.simulation_tab.sweeps_table.item(row, 3).text()
            sweeps.append([sweep_type, start, stop, step])

        config = {
            "simulation_settings": {
                "cutout_enabled": self.simulation_tab.enable_cutout_checkbox.isChecked(),
                "expansion_size": self.simulation_tab.expansion_size_input.text(),
                "siwave_version": self.simulation_tab.siwave_version_input.text(),
                "frequency_sweeps": sweeps
            }
        }
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log(f"Could not save config: {e}", "red")

        if self.project_file and os.path.exists(self.project_file):
            try:
                with open(self.project_file, "r") as f:
                    project_config = json.load(f)
                project_config["edb_version"] = self.import_tab.edb_version_input.text()
                with open(self.project_file, "w") as f:
                    json.dump(project_config, f, indent=2)
            except (IOError, json.JSONDecodeError) as e:
                self.log(f"Could not update project config: {e}", "red")

    def log(self, message, color=None):
        if color: self.log_window.setTextColor(QColor(color))
        self.log_window.append(message)
        self.log_window.setTextColor(QColor("black"))
        self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())

    def filter_components(self):
        pattern = self.port_setup_tab.component_filter_input.text()
        try: regex = re.compile(pattern)
        except re.error: return
        self.port_setup_tab.controller_components_list.clear()
        self.port_setup_tab.dram_components_list.clear()
        for comp_name, pin_count in self.all_components:
            if regex.search(comp_name):
                item_text = f"{comp_name} ({pin_count})"
                self.port_setup_tab.controller_components_list.addItem(item_text)
                self.port_setup_tab.dram_components_list.addItem(item_text)

    def update_checked_count(self):
        checked_single = sum(1 for i in range(self.port_setup_tab.single_ended_list.count()) if self.port_setup_tab.single_ended_list.item(i).checkState() == Qt.Checked)
        checked_diff = sum(1 for i in range(self.port_setup_tab.differential_pairs_list.count()) if self.port_setup_tab.differential_pairs_list.item(i).checkState() == Qt.Checked)
        checked_nets = checked_single + (checked_diff * 2)
        ports = (checked_single * 2) + (checked_diff * 4)
        self.port_setup_tab.checked_nets_label.setText(f"Checked nets: {checked_nets} | Ports: {ports}")
        self.port_setup_tab.apply_button.setEnabled(checked_nets > 0)

    def apply_settings(self):
        if not self.pcb_data:
            self.log("No PCB data loaded.", "red")
            return
        aedb_path = self.import_tab.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Invalid AEDB path.", "red")
            return
        
        project_data = {}
        if os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data = json.load(f)

        project_data.update({
            "aedb_path": aedb_path, "reference_net": self.port_setup_tab.ref_net_combo.currentText(),
            "controller_components": [item.text().split(" ")[0] for item in self.port_setup_tab.controller_components_list.selectedItems()],
            "dram_components": [item.text().split(" ")[0] for item in self.port_setup_tab.dram_components_list.selectedItems()],
            "ports": [],
        })
        
        sequence = 1
        diff_pairs_info = self.pcb_data.get("diff", {})
        net_to_diff_pair = {p_net: (pair_name, "positive") for pair_name, (p_net, n_net) in diff_pairs_info.items()}
        net_to_diff_pair.update({n_net: (pair_name, "negative") for pair_name, (p_net, n_net) in diff_pairs_info.items()})

        signal_nets = []
        for i in range(self.port_setup_tab.single_ended_list.count()):
            item = self.port_setup_tab.single_ended_list.item(i)
            if item.checkState() == Qt.Checked:
                net_name = item.text()
                signal_nets.append(net_name)
                for comp in project_data["controller_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "controller", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["dram_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "dram", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
        
        for i in range(self.port_setup_tab.differential_pairs_list.count()):
            item = self.port_setup_tab.differential_pairs_list.item(i)
            if item.checkState() == Qt.Checked:
                pair_name = item.text()
                p_net, n_net = diff_pairs_info[pair_name]
                signal_nets.extend([p_net, n_net])
                for comp in project_data["controller_components"]:
                    if any(pin[1] == p_net for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{p_net}", "component": comp, "component_role": "controller", "net": p_net, "net_type": "differential", "pair": pair_name, "polarity": "positive", "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["dram_components"]:
                    if any(pin[1] == p_net for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{p_net}", "component": comp, "component_role": "dram", "net": p_net, "net_type": "differential", "pair": pair_name, "polarity": "positive", "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["controller_components"]:
                    if any(pin[1] == n_net for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{n_net}", "component": comp, "component_role": "controller", "net": n_net, "net_type": "differential", "pair": pair_name, "polarity": "negative", "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["dram_components"]:
                    if any(pin[1] == n_net for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{n_net}", "component": comp, "component_role": "dram", "net": n_net, "net_type": "differential", "pair": pair_name, "polarity": "negative", "reference_net": project_data["reference_net"]}); sequence += 1
        
        self.simulation_tab.signal_nets_label.setText(", ".join(sorted(signal_nets)))
        self.simulation_tab.reference_net_label.setText(project_data["reference_net"])
        self.current_aedb_path = aedb_path

        try:
            with open(self.project_file, "w") as f: json.dump(project_data, f, indent=2)
            self.log(f"Successfully saved to {self.project_file}. Now applying to EDB...")
            
            self.port_setup_tab.apply_button.setEnabled(False)
            self.port_setup_tab.apply_button.setText("Running...")
            self.port_setup_tab.apply_button.setStyleSheet("background-color: yellow; color: black;")

            script_path = os.path.join(os.path.dirname(__file__), "scripts", "set_edb.py")
            python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
            edb_version = self.import_tab.edb_version_input.text()
            command = [python_executable, script_path, self.project_file, edb_version]
            
            self.set_edb_process = QProcess()
            self.set_edb_process.readyReadStandardOutput.connect(self.handle_set_edb_stdout)
            self.set_edb_process.readyReadStandardError.connect(self.handle_set_edb_stderr)
            self.set_edb_process.finished.connect(self.set_edb_finished)
            self.set_edb_process.start(command[0], command[1:])

        except Exception as e:
            self.log(f"Error during apply: {e}", "red")
            self.port_setup_tab.apply_button.setEnabled(True)
            self.port_setup_tab.apply_button.setText("Apply")
            self.port_setup_tab.apply_button.setStyleSheet(self.port_setup_tab.apply_button_original_style)

    def handle_set_edb_stdout(self):
        data = self.set_edb_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_set_edb_stderr(self):
        data = self.set_edb_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def set_edb_finished(self):
        self.log("Set EDB process finished.")
        self.port_setup_tab.apply_button.setEnabled(True)
        self.port_setup_tab.apply_button.setText("Apply")
        self.port_setup_tab.apply_button.setStyleSheet(self.port_setup_tab.apply_button_original_style)
        
        if self.set_edb_process.exitCode() == 0:
            new_aedb_path = self.current_aedb_path.replace('.aedb', '_applied.aedb')
            self.log(f"Successfully created {new_aedb_path}")
        else:
            self.log(f"Set EDB process failed with exit code {self.set_edb_process.exitCode()}.", "red")

    def open_layout(self):
        path = ""
        if self.import_tab.brd_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(self, "Select .brd file", "", "BRD files (*.brd)")
        elif self.import_tab.aedb_radio.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Select .aedb directory", ".", QFileDialog.ShowDirsOnly)

        if path:
            self.import_tab.layout_path_label.setText(path)
            self.load_config()

    def browse_stackup(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Stackup File", "", "XML files (*.xml)")
        if file_path:
            self.import_tab.stackup_path_input.setText(file_path)

    def run_get_edb(self, layout_path):
        if not layout_path or layout_path == "No design loaded":
            self.log("Please select a design first.", "red")
            return

        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            temp_root = os.path.join(project_root, "temp")
            os.makedirs(temp_root, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            design_name = os.path.splitext(os.path.basename(layout_path))[0]
            session_dir_name = f"{design_name}_{timestamp}"
            session_dir = os.path.join(temp_root, session_dir_name)
            os.makedirs(session_dir)
            self.log(f"Created session directory: {session_dir}")

            base_name = os.path.basename(layout_path)
            dest_path = os.path.join(session_dir, base_name)

            if os.path.isdir(layout_path):
                shutil.copytree(layout_path, dest_path)
                self.log(f"Copied directory {layout_path} to {dest_path}")
            elif os.path.isfile(layout_path):
                shutil.copy2(layout_path, dest_path)
                self.log(f"Copied file {layout_path} to {dest_path}")
            else:
                self.log(f"Error: {layout_path} is not a valid file or directory.", "red")
                return
            
            layout_path = dest_path
            self.project_file = os.path.join(session_dir, "project.json")
            self.log(f"Project file will be created at: {self.project_file}")

            stackup_path = self.import_tab.stackup_path_input.text()
            if stackup_path and os.path.exists(stackup_path):
                stackup_basename = os.path.basename(stackup_path)
                dest_stackup_path = os.path.join(session_dir, stackup_basename)
                shutil.copy2(stackup_path, dest_stackup_path)
                self.log(f"Copied stackup file to {dest_stackup_path}")
                stackup_path = dest_stackup_path
            else:
                stackup_path = ""

        except Exception as e:
            self.log(f"Error preparing temp folder: {e}", "red")
            return

        self.log(f"Opening layout: {layout_path}")
        self.import_tab.apply_import_button.setEnabled(False)
        self.import_tab.apply_import_button.setText("Running...")
        self.import_tab.apply_import_button.setStyleSheet("background-color: yellow; color: black;")
        self.current_layout_path = layout_path

        script_path = os.path.join(os.path.dirname(__file__), "scripts", "get_edb.py")
        python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
        edb_version = self.import_tab.edb_version_input.text()
        
        command = [python_executable, script_path, layout_path, edb_version, stackup_path, self.project_file]
        self.log(f"Running command: {' '.join(command)}")

        self.get_edb_process = QProcess()
        self.get_edb_process.readyReadStandardOutput.connect(self.handle_get_edb_stdout)
        self.get_edb_process.readyReadStandardError.connect(self.handle_get_edb_stderr)
        self.get_edb_process.finished.connect(self.get_edb_finished)
        self.get_edb_process.start(command[0], command[1:])

    def handle_get_edb_stdout(self):
        data = self.get_edb_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_get_edb_stderr(self):
        data = self.get_edb_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def get_edb_finished(self):
        self.log("Get EDB process finished.")
        self.import_tab.apply_import_button.setEnabled(True)
        self.import_tab.apply_import_button.setText("Apply")
        self.import_tab.apply_import_button.setStyleSheet(self.import_tab.apply_import_button_original_style)
        exit_code = self.get_edb_process.exitCode()

        if exit_code == 0:
            layout_path = self.current_layout_path
            if layout_path.lower().endswith('.brd'):
                new_aedb_path = os.path.splitext(layout_path)[0] + '.aedb'
                self.import_tab.layout_path_label.setText(new_aedb_path)
                self.log(f"Design path has been updated to: {new_aedb_path}")
            
            self.log(f"Successfully updated PCB data in {os.path.basename(self.project_file)}")
            
            self.load_pcb_data()
        else:
            self.log(f"Get EDB process failed with exit code {exit_code}.", "red")

    def load_pcb_data(self):
        try:
            if not self.project_file or not os.path.exists(self.project_file):
                self.log("Project file not found.", "red")
                self.pcb_data = None
                return

            with open(self.project_file, "r") as f:
                project_data = json.load(f)
            
            self.pcb_data = project_data.get("pcb_data")

            if not self.pcb_data:
                self.log("No pcb_data found in project file.", "orange")
                return

            self.port_setup_tab.controller_components_list.clear()
            self.port_setup_tab.dram_components_list.clear()
            if "component" in self.pcb_data:
                self.all_components = [(name, len(pins)) for name, pins in self.pcb_data["component"].items()]
                self.all_components.sort(key=lambda x: x[1], reverse=True)
                self.filter_components()
        except json.JSONDecodeError: self.log(f"Error decoding {os.path.basename(self.project_file)}.", "red"); self.pcb_data = None
        except Exception as e: self.log(f"Error loading data: {e}", "red"); self.pcb_data = None

    def update_nets(self):
        if not self.pcb_data or "component" not in self.pcb_data: return
        selected_controllers = [item.text().split(" ")[0] for item in self.port_setup_tab.controller_components_list.selectedItems()]
        selected_drams = [item.text().split(" ")[0] for item in self.port_setup_tab.dram_components_list.selectedItems()]
        
        self.port_setup_tab.single_ended_list.blockSignals(True)
        self.port_setup_tab.differential_pairs_list.blockSignals(True)
        
        self.port_setup_tab.single_ended_list.clear()
        self.port_setup_tab.differential_pairs_list.clear()
        self.port_setup_tab.ref_net_combo.clear()

        try:
            if not selected_controllers or not selected_drams:
                self.port_setup_tab.ref_net_combo.addItem("GND")
                self.update_checked_count()
                return

            controller_nets = set(pin[1] for comp in selected_controllers for pin in self.pcb_data["component"].get(comp, []))
            dram_nets = set(pin[1] for comp in selected_drams for pin in self.pcb_data["component"].get(comp, []))
            common_nets = controller_nets.intersection(dram_nets)
            
            selected_components = selected_controllers + selected_drams
            net_pin_counts = {net: sum(1 for comp_name in selected_components for pin in self.pcb_data["component"].get(comp_name, []) if pin[1] == net) for net in common_nets}
            sorted_nets = sorted(net_pin_counts.items(), key=lambda item: item[1], reverse=True)
            
            for net_name, count in sorted_nets: self.port_setup_tab.ref_net_combo.addItem(net_name)
            if sorted_nets: self.port_setup_tab.ref_net_combo.setCurrentIndex(0)
            
            diff_pairs_info = self.pcb_data.get("diff", {})
            diff_pair_nets = {net for pos_net, neg_net in diff_pairs_info.values() for net in (pos_net, neg_net)}
            
            single_nets = sorted([net for net in common_nets if net not in diff_pair_nets and net.upper() != "GND"])
            for net in single_nets:
                item = QListWidgetItem(net)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.port_setup_tab.single_ended_list.addItem(item)
            
            for pair_name, (pos_net, neg_net) in sorted(diff_pairs_info.items()):
                if pos_net in common_nets and neg_net in common_nets:
                    item = QListWidgetItem(pair_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.port_setup_tab.differential_pairs_list.addItem(item)
            
            self.update_checked_count()
        finally:
            self.port_setup_tab.single_ended_list.blockSignals(False)
            self.port_setup_tab.differential_pairs_list.blockSignals(False)

    def apply_simulation_settings(self):
        aedb_path = self.import_tab.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Please open an .aedb project first.", "red")
            return

        project_data = {}
        if os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data = json.load(f)

        sweeps = []
        for row in range(self.simulation_tab.sweeps_table.rowCount()):
            sweep_type = self.simulation_tab.sweeps_table.cellWidget(row, 0).currentText()
            start = self.simulation_tab.sweeps_table.item(row, 1).text()
            stop = self.simulation_tab.sweeps_table.item(row, 2).text()
            step = self.simulation_tab.sweeps_table.item(row, 3).text()
            sweeps.append([sweep_type, start, stop, step])

        project_data.update({
            "aedb_path": aedb_path,
            "edb_version": self.import_tab.edb_version_input.text(),
            "cutout": {
                "enabled": self.simulation_tab.enable_cutout_checkbox.isChecked(),
                "expansion_size": self.simulation_tab.expansion_size_input.text(),
                "signal_nets": self.simulation_tab.signal_nets_label.text().split(", "),
                "reference_net": [self.simulation_tab.reference_net_label.text()],
            },
            "solver": "SIwave",
            "solver_version": self.simulation_tab.siwave_version_input.text(),
            "frequency_sweeps": sweeps,
        })

        try:
            with open(self.project_file, "w") as f:
                json.dump(project_data, f, indent=2)
            self.log(f"Simulation settings saved to {self.project_file}")

            self.log("Applying simulation settings to EDB...")
            self.simulation_tab.apply_simulation_button.setEnabled(False)
            self.simulation_tab.apply_simulation_button.setText("Running...")
            self.simulation_tab.apply_simulation_button.setStyleSheet("background-color: yellow; color: black;")

            script_path = os.path.join(os.path.dirname(__file__), "scripts", "set_sim.py")
            python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
            command = [python_executable, script_path, self.project_file]
            
            self.set_sim_process = QProcess()
            self.set_sim_process.readyReadStandardOutput.connect(self.handle_set_sim_stdout)
            self.set_sim_process.readyReadStandardError.connect(self.handle_set_sim_stderr)
            self.set_sim_process.finished.connect(self.set_sim_finished)
            self.set_sim_process.start(command[0], command[1:])

        except Exception as e:
            self.log(f"Error applying simulation settings: {e}", color="red")
            self.simulation_tab.apply_simulation_button.setEnabled(True)
            self.simulation_tab.apply_simulation_button.setText("Apply")
            self.simulation_tab.apply_simulation_button.setStyleSheet(self.simulation_tab.apply_simulation_button_original_style)

    def handle_set_sim_stdout(self):
        data = self.set_sim_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_set_sim_stderr(self):
        data = self.set_sim_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def set_sim_finished(self):
        self.log("Set simulation process finished.")
        if self.set_sim_process.exitCode() == 0:
            self.log("Successfully applied simulation settings. Now running simulation...")
            self.run_simulation_script()
        else:
            self.log(f"Set simulation process failed with exit code {self.set_sim_process.exitCode()}.", "red")
            self.simulation_tab.apply_simulation_button.setEnabled(True)
            self.simulation_tab.apply_simulation_button.setText("Apply")
            self.simulation_tab.apply_simulation_button.setStyleSheet(self.simulation_tab.apply_simulation_button_original_style)

    def run_simulation_script(self):
        self.log("Starting simulation...")
        script_path = os.path.join(os.path.dirname(__file__), "scripts", "run_sim.py")
        python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
        command = [python_executable, script_path, self.project_file]

        self.run_sim_process = QProcess()
        self.run_sim_process.readyReadStandardOutput.connect(self.handle_run_sim_stdout)
        self.run_sim_process.readyReadStandardError.connect(self.handle_run_sim_stderr)
        self.run_sim_process.finished.connect(self.run_sim_finished)
        self.run_sim_process.start(command[0], command[1:])

    def handle_run_sim_stdout(self):
        data = self.run_sim_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_run_sim_stderr(self):
        data = self.run_sim_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def run_sim_finished(self):
        self.log("Simulation process finished.")
        self.simulation_tab.apply_simulation_button.setEnabled(True)
        self.simulation_tab.apply_simulation_button.setText("Apply")
        self.simulation_tab.apply_simulation_button.setStyleSheet(self.simulation_tab.apply_simulation_button_original_style)
        if self.run_sim_process.exitCode() == 0:
            self.log("Successfully ran simulation. Project file path has been set in the Result tab.")
            self.result_tab.project_path_input.setText(self.project_file)
        else:
            self.log(f"Run simulation process failed with exit code {self.run_sim_process.exitCode()}.", "red")

    def run_get_loss(self):
        self.log("Getting loss data...")
        script_path = os.path.join(os.path.dirname(__file__), "scripts", "get_loss.py")
        python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
        command = [python_executable, script_path, self.project_file]

        self.get_loss_process = QProcess()
        self.get_loss_process.readyReadStandardOutput.connect(self.handle_get_loss_stdout)
        self.get_loss_process.readyReadStandardError.connect(self.handle_get_loss_stderr)
        self.get_loss_process.finished.connect(self.get_loss_finished)
        self.get_loss_process.start(command[0], command[1:])

    def handle_get_loss_stdout(self):
        data = self.get_loss_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_get_loss_stderr(self):
        data = self.get_loss_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def get_loss_finished(self):
        if self.get_loss_process.exitCode() == 0:
            self.log("Successfully got loss data. Generating HTML report...")
            self.run_generate_report()
        else:
            self.log(f"Get loss process failed with exit code {self.get_loss_process.exitCode()}.", "red")

    def run_generate_report(self):
        self.log("Generating HTML report...")
        script_path = os.path.join(os.path.dirname(__file__), "scripts", "generate_report.py")
        python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
        command = [python_executable, script_path, self.project_file]

        self.generate_report_process = QProcess()
        self.generate_report_process.readyReadStandardOutput.connect(self.handle_generate_report_stdout)
        self.generate_report_process.readyReadStandardError.connect(self.handle_generate_report_stderr)
        self.generate_report_process.finished.connect(self.generate_report_finished)
        self.generate_report_process.start(command[0], command[1:])

    def handle_generate_report_stdout(self):
        data = self.generate_report_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines():
            self.log(line)
            if "HTML report generated at: " in line:
                self.report_path = line.split("HTML report generated at: ")[1].strip()
                self.result_tab.html_path_input.setText(self.report_path)

    def handle_generate_report_stderr(self):
        data = self.generate_report_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def generate_report_finished(self):
        if self.generate_report_process.exitCode() == 0:
            self.log("HTML report generation finished.")
            if self.report_path:
                self.result_tab.html_group.setVisible(True)
        else:
            self.log(f"HTML report generation failed with exit code {self.generate_report_process.exitCode()}.", "red")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainController()
    window.show()
    sys.exit(app.exec())