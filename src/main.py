import sys
import os
import json
import re
import subprocess
from PySide6.QtWidgets import QApplication, QFileDialog, QListWidgetItem, QTableWidgetItem
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QColor
from gui import AEDBCCTCalculator

class MainController(AEDBCCTCalculator):
    def __init__(self):
        super().__init__()
        self.project_file = None
        self.load_config()
        self.connect_signals()

    def connect_signals(self):
        self.brd_radio.toggled.connect(self.on_layout_type_changed)
        self.aedb_radio.toggled.connect(self.on_layout_type_changed)
        self.open_layout_button.clicked.connect(self.open_layout)
        self.browse_stackup_button.clicked.connect(self.browse_stackup)
        self.apply_import_button.clicked.connect(lambda: self.run_get_edb(self.layout_path_label.text()))
        self.component_filter_input.textChanged.connect(self.filter_components)
        self.controller_components_list.itemSelectionChanged.connect(self.update_nets)
        self.dram_components_list.itemSelectionChanged.connect(self.update_nets)
        self.single_ended_list.itemChanged.connect(self.update_checked_count)
        self.differential_pairs_list.itemChanged.connect(self.update_checked_count)
        self.apply_button.clicked.connect(self.apply_settings)
        self.apply_simulation_button.clicked.connect(self.apply_simulation_settings)

    def on_layout_type_changed(self):
        if self.sender().isChecked():
            self.layout_path_label.setText("No design loaded")
            self.stackup_path_input.clear()

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

    def load_config(self):
        if self.project_file and os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                config = json.load(f)
                self.edb_version_input.setText(config.get("edb_version", "2024.1"))
        else:
            self.edb_version_input.setText("2024.1")

    def save_config(self):
        if self.project_file:
            os.makedirs(os.path.dirname(self.project_file), exist_ok=True)
            config = {"edb_version": self.edb_version_input.text()}
            with open(self.project_file, "w") as f:
                json.dump(config, f, indent=2)

    def log(self, message, color=None):
        if color: self.log_window.setTextColor(QColor(color))
        self.log_window.append(message)
        self.log_window.setTextColor(QColor("black"))
        self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())

    def filter_components(self):
        pattern = self.component_filter_input.text()
        try: regex = re.compile(pattern)
        except re.error: return
        self.controller_components_list.clear()
        self.dram_components_list.clear()
        for comp_name, pin_count in self.all_components:
            if regex.search(comp_name):
                item_text = f"{comp_name} ({pin_count})"
                self.controller_components_list.addItem(item_text)
                self.dram_components_list.addItem(item_text)

    def update_checked_count(self):
        checked_single = sum(1 for i in range(self.single_ended_list.count()) if self.single_ended_list.item(i).checkState() == Qt.Checked)
        checked_diff = sum(1 for i in range(self.differential_pairs_list.count()) if self.differential_pairs_list.item(i).checkState() == Qt.Checked)
        checked_nets = checked_single + (checked_diff * 2)
        ports = (checked_single * 2) + (checked_diff * 4)
        self.checked_nets_label.setText(f"Checked nets: {checked_nets} | Ports: {ports}")
        self.apply_button.setEnabled(checked_nets > 0)

    def apply_settings(self):
        if not self.pcb_data:
            self.log("No PCB data loaded.", "red")
            return
        aedb_path = self.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Invalid AEDB path.", "red")
            return
        
        project_data = {}
        if os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data = json.load(f)

        project_data.update({
            "aedb_path": aedb_path, "reference_net": self.ref_net_combo.currentText(),
            "controller_components": [item.text().split(" ")[0] for item in self.controller_components_list.selectedItems()],
            "dram_components": [item.text().split(" ")[0] for item in self.dram_components_list.selectedItems()],
            "ports": [],
        })
        
        sequence = 1
        diff_pairs_info = self.pcb_data.get("diff", {})
        net_to_diff_pair = {p_net: (pair_name, "positive") for pair_name, (p_net, n_net) in diff_pairs_info.items()}
        net_to_diff_pair.update({n_net: (pair_name, "negative") for pair_name, (p_net, n_net) in diff_pairs_info.items()})

        signal_nets = []
        for i in range(self.single_ended_list.count()):
            item = self.single_ended_list.item(i)
            if item.checkState() == Qt.Checked:
                net_name = item.text()
                signal_nets.append(net_name)
                for comp in project_data["controller_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "controller", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["dram_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "dram", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
        
        for i in range(self.differential_pairs_list.count()):
            item = self.differential_pairs_list.item(i)
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
        
        self.signal_nets_label.setText(", ".join(sorted(signal_nets)))
        self.reference_net_label.setText(project_data["reference_net"])
        self.current_aedb_path = aedb_path

        try:
            with open(self.project_file, "w") as f: json.dump(project_data, f, indent=2)
            self.log(f"Successfully saved to {self.project_file}. Now applying to EDB...")
            
            self.apply_button.setEnabled(False)
            self.apply_button.setText("Running...")
            self.apply_button.setStyleSheet("background-color: yellow; color: black;")

            script_path = os.path.join(os.path.dirname(__file__), "set_edb.py")
            python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
            edb_version = self.edb_version_input.text()
            command = [python_executable, script_path, self.project_file, edb_version]
            
            self.set_edb_process = QProcess()
            self.set_edb_process.readyReadStandardOutput.connect(self.handle_set_edb_stdout)
            self.set_edb_process.readyReadStandardError.connect(self.handle_set_edb_stderr)
            self.set_edb_process.finished.connect(self.set_edb_finished)
            self.set_edb_process.start(command[0], command[1:])

        except Exception as e:
            self.log(f"Error during apply: {e}", "red")
            self.apply_button.setEnabled(True)
            self.apply_button.setText("Apply")
            self.apply_button.setStyleSheet(self.apply_button_original_style)

    def handle_set_edb_stdout(self):
        data = self.set_edb_process.readAllStandardOutput().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line)

    def handle_set_edb_stderr(self):
        data = self.set_edb_process.readAllStandardError().data().decode(errors='ignore').strip()
        for line in data.splitlines(): self.log(line, color="red")

    def set_edb_finished(self):
        self.log("Set EDB process finished.")
        self.apply_button.setEnabled(True)
        self.apply_button.setText("Apply")
        self.apply_button.setStyleSheet(self.apply_button_original_style)
        
        if self.set_edb_process.exitCode() == 0:
            new_aedb_path = self.current_aedb_path.replace('.aedb', '_applied.aedb')
            self.log(f"Successfully created {new_aedb_path}")
        else:
            self.log(f"Set EDB process failed with exit code {self.set_edb_process.exitCode()}.", "red")

    def open_layout(self):
        path = ""
        if self.brd_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(self, "Select .brd file", "", "BRD files (*.brd)")
        elif self.aedb_radio.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Select .aedb directory", ".", QFileDialog.ShowDirsOnly)

        if path:
            self.layout_path_label.setText(path)
            project_dir = os.path.dirname(path)
            self.project_file = os.path.join(project_dir, "project.json")
            self.load_config()

    def browse_stackup(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Stackup File", "", "XML files (*.xml)")
        if file_path:
            self.stackup_path_input.setText(file_path)

    def run_get_edb(self, layout_path):
        if not layout_path or layout_path == "No design loaded":
            self.log("Please select a design first.", "red")
            return

        self.log(f"Opening layout: {layout_path}")
        self.apply_import_button.setEnabled(False)
        self.apply_import_button.setText("Running...")
        self.apply_import_button.setStyleSheet("background-color: yellow; color: black;")
        self.current_layout_path = layout_path # Store for finished handler

        script_path = os.path.join(os.path.dirname(__file__), "get_edb.py")
        python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
        edb_version = self.edb_version_input.text()
        
        stackup_path = self.stackup_path_input.text()
        if not (stackup_path and os.path.exists(stackup_path)):
            stackup_path = ""

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
        self.apply_import_button.setEnabled(True)
        self.apply_import_button.setText("Apply")
        self.apply_import_button.setStyleSheet(self.apply_import_button_original_style)
        exit_code = self.get_edb_process.exitCode()

        if exit_code == 0:
            layout_path = self.current_layout_path
            if layout_path.lower().endswith('.brd'):
                new_aedb_path = os.path.splitext(layout_path)[0] + '.aedb'
                self.layout_path_label.setText(new_aedb_path)
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

            self.controller_components_list.clear()
            self.dram_components_list.clear()
            if "component" in self.pcb_data:
                self.all_components = [(name, len(pins)) for name, pins in self.pcb_data["component"].items()]
                self.all_components.sort(key=lambda x: x[1], reverse=True)
                self.filter_components()
        except json.JSONDecodeError: self.log(f"Error decoding {os.path.basename(self.project_file)}.", "red"); self.pcb_data = None
        except Exception as e: self.log(f"Error loading data: {e}", "red"); self.pcb_data = None

    def update_nets(self):
        if not self.pcb_data or "component" not in self.pcb_data: return
        selected_controllers = [item.text().split(" ")[0] for item in self.controller_components_list.selectedItems()]
        selected_drams = [item.text().split(" ")[0] for item in self.dram_components_list.selectedItems()]
        
        # Block signals to prevent excessive updates
        self.single_ended_list.blockSignals(True)
        self.differential_pairs_list.blockSignals(True)
        
        self.single_ended_list.clear()
        self.differential_pairs_list.clear()
        self.ref_net_combo.clear()

        try:
            if not selected_controllers or not selected_drams:
                self.ref_net_combo.addItem("GND")
                self.update_checked_count()
                return

            controller_nets = set(pin[1] for comp in selected_controllers for pin in self.pcb_data["component"].get(comp, []))
            dram_nets = set(pin[1] for comp in selected_drams for pin in self.pcb_data["component"].get(comp, []))
            common_nets = controller_nets.intersection(dram_nets)
            
            selected_components = selected_controllers + selected_drams
            net_pin_counts = {net: sum(1 for comp_name in selected_components for pin in self.pcb_data["component"].get(comp_name, []) if pin[1] == net) for net in common_nets}
            sorted_nets = sorted(net_pin_counts.items(), key=lambda item: item[1], reverse=True)
            
            for net_name, count in sorted_nets: self.ref_net_combo.addItem(net_name)
            if sorted_nets: self.ref_net_combo.setCurrentIndex(0)
            
            diff_pairs_info = self.pcb_data.get("diff", {})
            diff_pair_nets = {net for pos_net, neg_net in diff_pairs_info.values() for net in (pos_net, neg_net)}
            
            single_nets = sorted([net for net in common_nets if net not in diff_pair_nets and net.upper() != "GND"])
            for net in single_nets:
                item = QListWidgetItem(net)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.single_ended_list.addItem(item)
            
            for pair_name, (pos_net, neg_net) in sorted(diff_pairs_info.items()):
                if pos_net in common_nets and neg_net in common_nets:
                    item = QListWidgetItem(pair_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.differential_pairs_list.addItem(item)
            
            self.update_checked_count()
        finally:
            # Unblock signals
            self.single_ended_list.blockSignals(False)
            self.differential_pairs_list.blockSignals(False)

    def apply_simulation_settings(self):
        aedb_path = self.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Please open an .aedb project first.", "red")
            return

        project_data = {}
        if os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data = json.load(f)

        sweeps = []
        for row in range(self.sweeps_table.rowCount()):
            sweep_type = self.sweeps_table.cellWidget(row, 0).currentText()
            start = self.sweeps_table.item(row, 1).text()
            stop = self.sweeps_table.item(row, 2).text()
            step = self.sweeps_table.item(row, 3).text()
            sweeps.append([sweep_type, start, stop, step])

        project_data.update({
            "aedb_path": aedb_path,
            "edb_version": self.edb_version_input.text(),
            "cutout": {
                "enabled": self.enable_cutout_checkbox.isChecked(),
                "expansion_size": self.expansion_size_input.text(),
                "signal_nets": self.signal_nets_label.text().split(", "),
                "reference_net": [self.reference_net_label.text()],
            },
            "solver": "SIwave",
            "solver_version": self.siwave_version_input.text(),
            "frequency_sweeps": sweeps,
        })

        try:
            with open(self.project_file, "w") as f:
                json.dump(project_data, f, indent=2)
            self.log(f"Simulation settings saved to {self.project_file}")

            self.log("Applying simulation settings to EDB...")
            self.apply_simulation_button.setEnabled(False)
            self.apply_simulation_button.setText("Running...")
            self.apply_simulation_button.setStyleSheet("background-color: yellow; color: black;")

            script_path = os.path.join(os.path.dirname(__file__), "set_sim.py")
            python_executable = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")
            command = [python_executable, script_path, self.project_file]
            
            self.set_sim_process = QProcess()
            self.set_sim_process.readyReadStandardOutput.connect(self.handle_set_sim_stdout)
            self.set_sim_process.readyReadStandardError.connect(self.handle_set_sim_stderr)
            self.set_sim_process.finished.connect(self.set_sim_finished)
            self.set_sim_process.start(command[0], command[1:])

        except Exception as e:
            self.log(f"Error applying simulation settings: {e}", color="red")
            self.apply_simulation_button.setEnabled(True)
            self.apply_simulation_button.setText("Apply Simulation")
            self.apply_simulation_button.setStyleSheet(self.apply_simulation_button_original_style)

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
            self.apply_simulation_button.setEnabled(True)
            self.apply_simulation_button.setText("Apply Simulation")
            self.apply_simulation_button.setStyleSheet(self.apply_simulation_button_original_style)

    def run_simulation_script(self):
        self.log("Starting simulation...")
        script_path = os.path.join(os.path.dirname(__file__), "run_sim.py")
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
        self.apply_simulation_button.setEnabled(True)
        self.apply_simulation_button.setText("Apply Simulation")
        self.apply_simulation_button.setStyleSheet(self.apply_simulation_button_original_style)
        if self.run_sim_process.exitCode() == 0:
            self.log("Successfully ran simulation. Starting post-processing...")
            self.run_get_loss()
        else:
            self.log(f"Run simulation process failed with exit code {self.run_sim_process.exitCode()}.", "red")

    def run_get_loss(self):
        self.log("Getting loss data...")
        script_path = os.path.join(os.path.dirname(__file__), "get_loss.py")
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
            self.generate_html_report()
        else:
            self.log(f"Get loss process failed with exit code {self.get_loss_process.exitCode()}.", "red")

    def generate_html_report(self):
        try:
            with open(self.project_file, "r") as f:
                project_data = json.load(f)

            results = project_data.get("result", {})
            if not results:
                self.log("No results found in project file.", "red")
                return

            import plotly.graph_objects as go
            import base64

            html_content = "<html><head><title>Simulation Results</title></head><body>"
            html_content += "<h1>Simulation Results</h1>"
            html_content += '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">'

            for signal, data in results.items():
                # Insertion Loss
                fig_il = go.Figure()
                fig_il.add_trace(go.Scatter(x=data['insertion_loss']['freq'], y=data['insertion_loss']['insetion loss'], mode='lines', name='Insertion Loss'))
                fig_il.update_layout(title=f'{signal} - Insertion Loss', xaxis_title='Frequency (Hz)', yaxis_title='Loss (dB)')
                img_bytes_il = fig_il.to_image(format="png")
                base64_img_il = base64.b64encode(img_bytes_il).decode('utf-8')

                # Return Loss
                fig_rl = go.Figure()
                fig_rl.add_trace(go.Scatter(x=data['return_loss']['freq'], y=data['return_loss']['return loss'], mode='lines', name='Return Loss'))
                fig_rl.update_layout(title=f'{signal} - Return Loss', xaxis_title='Frequency (Hz)', yaxis_title='Loss (dB)')
                img_bytes_rl = fig_rl.to_image(format="png")
                base64_img_rl = base64.b64encode(img_bytes_rl).decode('utf-8')
                
                html_content += f'<div><h2>{signal}</h2>'
                html_content += f'<h3>Insertion Loss</h3><img src="data:image/png;base64,{base64_img_il}" />'
                html_content += f'<h3>Return Loss</h3><img src="data:image/png;base64,{base64_img_rl}" /></div>'


            html_content += "</div></body></html>"

            report_path = os.path.join(os.path.dirname(self.project_file), "report.html")
            with open(report_path, "w") as f:
                f.write(html_content)
            self.log(f"HTML report generated at: {report_path}")

        except Exception as e:
            self.log(f"Error generating HTML report: {e}", "red")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainController()
    window.show()
    sys.exit(app.exec())
