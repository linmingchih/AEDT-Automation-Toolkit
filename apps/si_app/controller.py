import json
import os
import re
import shutil
import sys
import webbrowser
from datetime import datetime

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QListWidgetItem

from src.services import ExternalScriptRunner

class AppController(QObject):
    def __init__(self, app_name):
        super().__init__()
        self.app_name = app_name
        self.project_file = None
        self.report_path = None
        self.pcb_data = None
        self.all_components = []
        self.log_window = None  # This will be set by the GUI
        self.tabs = {}  # This will be populated with tab instances
        
        # Define project root and scripts directory robustly
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.scripts_dir = os.path.join(self.project_root, "src", "scripts")

        # External process coordination
        self.script_runner = ExternalScriptRunner(parent=self)
        self.script_runner.started.connect(self.on_task_started)
        self.script_runner.finished.connect(self.on_task_finished)
        self.script_runner.error.connect(self.on_task_error)
        self.script_runner.log_message.connect(self.on_task_log_message)

        self.task_contexts = {}
        self.current_layout_path = None
        self.current_aedb_path = None

    def connect_signals(self, tabs):
        self.tabs = tabs
        import_tab = tabs.get("import_tab")
        port_setup_tab = tabs.get("port_setup_tab")
        simulation_tab = tabs.get("simulation_tab")
        result_tab = tabs.get("result_tab")

        if import_tab:
            import_tab.brd_radio.toggled.connect(self.on_layout_type_changed)
            import_tab.aedb_radio.toggled.connect(self.on_layout_type_changed)
            import_tab.open_layout_button.clicked.connect(self.open_layout)
            import_tab.browse_stackup_button.clicked.connect(self.browse_stackup)
            import_tab.apply_import_button.clicked.connect(lambda: self.run_get_edb(import_tab.layout_path_label.text()))

        if port_setup_tab:
            port_setup_tab.component_filter_input.textChanged.connect(self.filter_components)
            port_setup_tab.controller_components_list.itemSelectionChanged.connect(self.update_nets)
            port_setup_tab.dram_components_list.itemSelectionChanged.connect(self.update_nets)
            port_setup_tab.single_ended_list.itemChanged.connect(self.update_checked_count)
            port_setup_tab.differential_pairs_list.itemChanged.connect(self.update_checked_count)
            port_setup_tab.apply_button.clicked.connect(self.apply_settings)

        if simulation_tab:
            simulation_tab.apply_simulation_button.clicked.connect(self.apply_simulation_settings)

        if result_tab:
            result_tab.browse_project_button.clicked.connect(self.browse_project_file)
            result_tab.apply_result_button.clicked.connect(self.run_post_processing)
            result_tab.open_html_button.clicked.connect(self.open_report_in_browser)

    def log(self, message, color=None):
        if not self.log_window: return
        if color: self.log_window.setTextColor(QColor(color))
        self.log_window.append(message)
        self.log_window.setTextColor(QColor("black"))
        self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())

    # ------------------------------------------------------------------ #
    # External task coordination helpers
    # ------------------------------------------------------------------ #
    def _set_button_running(self, button, text="Running..."):
        if not button: return
        button.setEnabled(False)
        button.setText(text)
        button.setStyleSheet("background-color: yellow; color: black;")

    def _restore_button(self, button, original_style, text="Apply"):
        if not button: return
        button.setEnabled(True)
        button.setText(text)
        if original_style:
            button.setStyleSheet(original_style)
        else:
            button.setStyleSheet("")

    def _submit_task(
        self,
        command,
        *,
        metadata,
        retries=0,
        input_path=None,
        output_path=None,
        working_dir=None,
        description=None,
        env=None,
    ):
        try:
            task_id, _ = self.script_runner.run_task(
                command,
                metadata=metadata,
                retries=retries,
                input_path=input_path,
                output_path=output_path,
                working_dir=working_dir,
                description=description or metadata.get("description"),
                env=env,
            )
        except Exception as exc:
            self.log(f"Failed to start external task: {exc}", "red")
            button = metadata.get("button")
            self._restore_button(button, metadata.get("button_style"), metadata.get("button_reset_text", "Apply"))
            return None

        self.task_contexts[task_id] = metadata
        return task_id

    def run_external_script(
        self,
        command,
        *,
        metadata,
        retries=0,
        input_path=None,
        output_path=None,
        working_dir=None,
        description=None,
        env=None,
    ):
        """Public helper so tabs can enqueue external scripts through the controller."""
        return self._submit_task(
            command,
            metadata=metadata,
            retries=retries,
            input_path=input_path,
            output_path=output_path,
            working_dir=working_dir,
            description=description,
            env=env,
        )

    def on_task_started(self, task_id, attempt, metadata):
        metadata["attempt"] = attempt

    def on_task_finished(self, task_id, exit_code, metadata):
        context = self.task_contexts.pop(task_id, metadata or {})
        task_type = context.get("type")

        if task_type == "get_edb":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Get EDB process finished.")
            layout_path = self.current_layout_path or ""
            import_tab = self.tabs.get("import_tab")
            if layout_path.lower().endswith(".brd") and import_tab:
                new_aedb_path = os.path.splitext(layout_path)[0] + ".aedb"
                import_tab.layout_path_label.setText(new_aedb_path)
                self.log(f"Design path has been updated to: {new_aedb_path}")
            self.log(f"Successfully updated PCB data in {os.path.basename(self.project_file)}")
            self.load_pcb_data()

        elif task_type == "set_edb":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Set EDB process finished.")
            if self.current_aedb_path:
                new_aedb_path = self.current_aedb_path.replace(".aedb", "_applied.aedb")
                self.log(f"Successfully created {new_aedb_path}")

        elif task_type == "set_sim":
            self.log("Set simulation process finished.")
            self.log("Successfully applied simulation settings. Now running simulation...")
            self._queue_simulation_run(context)

        elif task_type == "run_sim":
            simulation_tab = self.tabs.get("simulation_tab")
            result_tab = self.tabs.get("result_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Simulation process finished.")
            if result_tab:
                result_tab.project_path_input.setText(self.project_file)
            self.log("Successfully ran simulation. Project file path has been set in the Result tab.")

        elif task_type == "get_loss":
            self.log("Successfully got loss data. Generating HTML report...")
            self.run_generate_report()

        elif task_type == "generate_report":
            result_tab = self.tabs.get("result_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("HTML report generation finished.")
            if result_tab and self.report_path:
                result_tab.html_group.setVisible(True)

    def on_task_error(self, task_id, exit_code, message, metadata):
        context = self.task_contexts.pop(task_id, metadata or {})
        task_type = context.get("type")
        log_message = message or f"Task failed with exit code {exit_code}."

        if task_type == "get_edb":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Get EDB process finished.")
            self.log(f"Get EDB process failed with exit code {exit_code}. {log_message}", "red")

        elif task_type == "set_edb":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Set EDB process finished.")
            self.log(f"Set EDB process failed with exit code {exit_code}. {log_message}", "red")

        elif task_type == "set_sim":
            simulation_tab = self.tabs.get("simulation_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Set simulation process finished.")
            self.log(f"Set simulation process failed with exit code {exit_code}. {log_message}", "red")

        elif task_type == "run_sim":
            simulation_tab = self.tabs.get("simulation_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Simulation process finished.")
            self.log(f"Run simulation process failed with exit code {exit_code}. {log_message}", "red")

        elif task_type == "get_loss":
            result_tab = self.tabs.get("result_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            if result_tab:
                result_tab.html_group.setVisible(False)
            self.log(f"Get loss process failed with exit code {exit_code}. {log_message}", "red")

        elif task_type == "generate_report":
            result_tab = self.tabs.get("result_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            if result_tab:
                result_tab.html_group.setVisible(False)
            self.log(f"HTML report generation failed with exit code {exit_code}. {log_message}", "red")

    def on_task_log_message(self, task_id, level, message, metadata):
        if level == "debug":
            return

        color = None
        if level == "error":
            color = "red"
        elif level == "warning":
            color = "orange"

        prefix = metadata.get("description")
        formatted = f"[{prefix}] {message}" if prefix else message

        self.log(formatted, color)

        if metadata.get("type") == "generate_report" and "HTML report generated at: " in message:
            result_tab = self.tabs.get("result_tab")
            self.report_path = message.split("HTML report generated at: ")[1].strip()
            if result_tab:
                result_tab.html_path_input.setText(self.report_path)

    def _queue_simulation_run(self, context):
        simulation_tab = self.tabs.get("simulation_tab")
        if not simulation_tab or not self.project_file:
            self.log("Unable to start simulation run: missing project file.", "red")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            return

        script_path = os.path.join(self.scripts_dir, "run_sim.py")
        command = [sys.executable, script_path, self.project_file]

        run_metadata = {
            "type": "run_sim",
            "description": "Running SIwave simulation",
            "button": context.get("button") or simulation_tab.apply_simulation_button,
            "button_style": context.get("button_style") or getattr(simulation_tab, "apply_simulation_button_original_style", ""),
            "button_reset_text": context.get("button_reset_text", "Apply"),
        }

        self._submit_task(
            command,
            metadata=run_metadata,
            input_path=self.project_file,
            description=run_metadata["description"],
        )

    def get_config_path(self):
        return os.path.join(os.path.dirname(__file__), "config.json")

    def load_config(self):
        config_path = self.get_config_path()
        simulation_tab = self.tabs.get("simulation_tab")
        import_tab = self.tabs.get("import_tab")

        if os.path.exists(config_path) and simulation_tab:
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    sim_settings = config.get("settings", {})
                    simulation_tab.enable_cutout_checkbox.setChecked(sim_settings.get("cutout_enabled", False))
                    simulation_tab.expansion_size_input.setText(sim_settings.get("expansion_size", "0.005000"))
                    simulation_tab.siwave_version_input.setText(sim_settings.get("siwave_version", "2025.1"))
                    
                    sweeps = sim_settings.get("frequency_sweeps", [])
                    if sweeps:
                        simulation_tab.sweeps_table.setRowCount(0)
                        for sweep in sweeps:
                            simulation_tab.add_sweep(sweep)
            except (json.JSONDecodeError, KeyError) as e:
                self.log(f"Could not load config: {e}", "orange")

        if self.project_file and os.path.exists(self.project_file) and import_tab:
            with open(self.project_file, "r") as f:
                project_config = json.load(f)
                import_tab.edb_version_input.setText(project_config.get("edb_version", "2024.1"))
        elif import_tab:
            import_tab.edb_version_input.setText("2024.1")

    def save_config(self):
        config_path = self.get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        simulation_tab = self.tabs.get("simulation_tab")
        import_tab = self.tabs.get("import_tab")
        if not simulation_tab: return

        sweeps = []
        for row in range(simulation_tab.sweeps_table.rowCount()):
            sweep_type = simulation_tab.sweeps_table.cellWidget(row, 0).currentText()
            start = simulation_tab.sweeps_table.item(row, 1).text()
            stop = simulation_tab.sweeps_table.item(row, 2).text()
            step = simulation_tab.sweeps_table.item(row, 3).text()
            sweeps.append([sweep_type, start, stop, step])

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config["settings"] = {
            "cutout_enabled": simulation_tab.enable_cutout_checkbox.isChecked(),
            "expansion_size": simulation_tab.expansion_size_input.text(),
            "siwave_version": simulation_tab.siwave_version_input.text(),
            "frequency_sweeps": sweeps
        }
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log(f"Could not save config: {e}", "red")

        if self.project_file and os.path.exists(self.project_file) and import_tab:
            try:
                with open(self.project_file, "r") as f:
                    project_config = json.load(f)
                project_config["edb_version"] = import_tab.edb_version_input.text()
                project_config["app_name"] = self.app_name
                with open(self.project_file, "w") as f:
                    json.dump(project_config, f, indent=2)
            except (IOError, json.JSONDecodeError) as e:
                self.log(f"Could not update project config: {e}", "red")

    def on_layout_type_changed(self):
        import_tab = self.tabs.get("import_tab")
        if self.sender().isChecked() and import_tab:
            import_tab.layout_path_label.setText("No design loaded")
            import_tab.stackup_path_input.clear()

    def browse_project_file(self):
        result_tab = self.tabs.get("result_tab")
        if not result_tab: return
        path, _ = QFileDialog.getOpenFileName(None, "Select project.json file", "", "JSON files (*.json)")
        if path:
            result_tab.project_path_input.setText(path)

    def run_post_processing(self):
        result_tab = self.tabs.get("result_tab")
        if not result_tab: return
        project_file = result_tab.project_path_input.text()
        if not project_file or not os.path.exists(project_file):
            self.log("Please select a valid project.json file.", "red")
            return
        self.project_file = project_file
        result_tab.html_group.setVisible(False)
        self._set_button_running(result_tab.apply_result_button)
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

    def filter_components(self):
        port_setup_tab = self.tabs.get("port_setup_tab")
        if not port_setup_tab: return
        pattern = port_setup_tab.component_filter_input.text()
        try: regex = re.compile(pattern)
        except re.error: return
        port_setup_tab.controller_components_list.clear()
        port_setup_tab.dram_components_list.clear()
        for comp_name, pin_count in self.all_components:
            if regex.search(comp_name):
                item_text = f"{comp_name} ({pin_count})"
                port_setup_tab.controller_components_list.addItem(item_text)
                port_setup_tab.dram_components_list.addItem(item_text)

    def update_checked_count(self):
        port_setup_tab = self.tabs.get("port_setup_tab")
        if not port_setup_tab: return
        checked_single = sum(1 for i in range(port_setup_tab.single_ended_list.count()) if port_setup_tab.single_ended_list.item(i).checkState() == Qt.Checked)
        checked_diff = sum(1 for i in range(port_setup_tab.differential_pairs_list.count()) if port_setup_tab.differential_pairs_list.item(i).checkState() == Qt.Checked)
        checked_nets = checked_single + (checked_diff * 2)
        ports = (checked_single * 2) + (checked_diff * 4)
        port_setup_tab.checked_nets_label.setText(f"Checked nets: {checked_nets} | Ports: {ports}")
        port_setup_tab.apply_button.setEnabled(checked_nets > 0)

    def apply_settings(self):
        import_tab = self.tabs.get("import_tab")
        port_setup_tab = self.tabs.get("port_setup_tab")
        simulation_tab = self.tabs.get("simulation_tab")
        if not all([import_tab, port_setup_tab, simulation_tab]): return

        if not self.pcb_data:
            self.log("No PCB data loaded.", "red")
            return
        aedb_path = import_tab.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Invalid AEDB path.", "red")
            return
        
        project_data = {"app_name": self.app_name}
        if self.project_file and os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data.update(json.load(f))

        project_data.update({
            "aedb_path": aedb_path, "reference_net": port_setup_tab.ref_net_combo.currentText(),
            "controller_components": [item.text().split(" ")[0] for item in port_setup_tab.controller_components_list.selectedItems()],
            "dram_components": [item.text().split(" ")[0] for item in port_setup_tab.dram_components_list.selectedItems()],
            "ports": [],
        })
        
        sequence = 1
        diff_pairs_info = self.pcb_data.get("diff", {})

        signal_nets = []
        for i in range(port_setup_tab.single_ended_list.count()):
            item = port_setup_tab.single_ended_list.item(i)
            if item.checkState() == Qt.Checked:
                net_name = item.text()
                signal_nets.append(net_name)
                for comp in project_data["controller_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "controller", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
                for comp in project_data["dram_components"]:
                    if any(pin[1] == net_name for pin in self.pcb_data["component"].get(comp, [])):
                        project_data["ports"].append({"sequence": sequence, "name": f"{sequence}_{comp}_{net_name}", "component": comp, "component_role": "dram", "net": net_name, "net_type": "single", "pair": None, "polarity": None, "reference_net": project_data["reference_net"]}); sequence += 1
        
        for i in range(port_setup_tab.differential_pairs_list.count()):
            item = port_setup_tab.differential_pairs_list.item(i)
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

        simulation_tab.signal_nets_label.setText(", ".join(sorted(signal_nets)))
        simulation_tab.reference_net_label.setText(project_data["reference_net"])
        self.current_aedb_path = aedb_path

        try:
            with open(self.project_file, "w") as f:
                json.dump(project_data, f, indent=2)
            self.log(f"Successfully saved to {self.project_file}. Now applying to EDB...")

            self._set_button_running(port_setup_tab.apply_button)
            script_path = os.path.join(self.scripts_dir, "set_edb.py")
            python_executable = sys.executable
            edb_version = import_tab.edb_version_input.text()
            command = [python_executable, script_path, self.project_file, edb_version]

            metadata = {
                "type": "set_edb",
                "description": "Applying port definitions to EDB",
                "button": port_setup_tab.apply_button,
                "button_style": getattr(port_setup_tab, "apply_button_original_style", ""),
                "button_reset_text": "Apply",
            }

            self._submit_task(
                command,
                metadata=metadata,
                input_path=self.project_file,
                description=metadata["description"],
            )

        except Exception as e:
            self.log(f"Error during apply: {e}", "red")
            self._restore_button(
                port_setup_tab.apply_button,
                getattr(port_setup_tab, "apply_button_original_style", ""),
                "Apply",
            )

    def open_layout(self):
        import_tab = self.tabs.get("import_tab")
        if not import_tab: return
        path = ""
        if import_tab.brd_radio.isChecked():
            path, _ = QFileDialog.getOpenFileName(None, "Select .brd file", "", "BRD files (*.brd)")
        elif import_tab.aedb_radio.isChecked():
            path = QFileDialog.getExistingDirectory(None, "Select .aedb directory", ".", QFileDialog.ShowDirsOnly)

        if path:
            import_tab.layout_path_label.setText(path)
            self.load_config()

    def browse_stackup(self):
        import_tab = self.tabs.get("import_tab")
        if not import_tab: return
        file_path, _ = QFileDialog.getOpenFileName(None, "Select Stackup File", "", "XML files (*.xml)")
        if file_path:
            import_tab.stackup_path_input.setText(file_path)

    def run_get_edb(self, layout_path):
        import_tab = self.tabs.get("import_tab")
        if not import_tab: return
        if not layout_path or layout_path == "No design loaded":
            self.log("Please select a design first.", "red")
            return

        try:
            temp_root = os.path.join(self.project_root, "temp")
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
            else:
                shutil.copy2(layout_path, dest_path)
            
            layout_path = dest_path
            self.project_file = os.path.join(session_dir, "project.json")
            self.log(f"Project file will be created at: {self.project_file}")

            stackup_path = import_tab.stackup_path_input.text()
            if stackup_path and os.path.exists(stackup_path):
                dest_stackup_path = os.path.join(session_dir, os.path.basename(stackup_path))
                shutil.copy2(stackup_path, dest_stackup_path)
                stackup_path = dest_stackup_path
            else:
                stackup_path = ""

        except Exception as e:
            self.log(f"Error preparing temp folder: {e}", "red")
            return

        self.log(f"Opening layout: {layout_path}")
        self._set_button_running(import_tab.apply_import_button)
        self.current_layout_path = layout_path

        script_path = os.path.join(self.scripts_dir, "get_edb.py")
        python_executable = sys.executable
        edb_version = import_tab.edb_version_input.text()
        
        command = [python_executable, script_path, layout_path, edb_version, stackup_path, self.project_file]
        self.log(f"Running command: {' '.join(command)}")
        metadata = {
            "type": "get_edb",
            "description": "Importing layout into EDB",
            "button": import_tab.apply_import_button,
            "button_style": getattr(import_tab, "apply_import_button_original_style", ""),
            "button_reset_text": "Apply",
        }

        self._submit_task(
            command,
            metadata=metadata,
            input_path=layout_path,
            output_path=self.project_file,
            description=metadata["description"],
        )

    def load_pcb_data(self):
        port_setup_tab = self.tabs.get("port_setup_tab")
        if not port_setup_tab: return
        try:
            if not self.project_file or not os.path.exists(self.project_file):
                self.log("Project file not found.", "red")
                return

            with open(self.project_file, "r") as f:
                project_data = json.load(f)
            
            self.pcb_data = project_data.get("pcb_data")
            if not self.pcb_data:
                self.log("No pcb_data found in project file.", "orange")
                return

            port_setup_tab.controller_components_list.clear()
            port_setup_tab.dram_components_list.clear()
            if "component" in self.pcb_data:
                self.all_components = [(name, len(pins)) for name, pins in self.pcb_data["component"].items()]
                self.all_components.sort(key=lambda x: x[1], reverse=True)
                self.filter_components()
        except Exception as e: self.log(f"Error loading data: {e}", "red")

    def update_nets(self):
        port_setup_tab = self.tabs.get("port_setup_tab")
        if not port_setup_tab or not self.pcb_data or "component" not in self.pcb_data:
            return

        selected_controllers = [item.text().split(" ")[0] for item in port_setup_tab.controller_components_list.selectedItems()]
        selected_drams = [item.text().split(" ")[0] for item in port_setup_tab.dram_components_list.selectedItems()]

        port_setup_tab.single_ended_list.blockSignals(True)
        port_setup_tab.differential_pairs_list.blockSignals(True)

        port_setup_tab.single_ended_list.clear()
        port_setup_tab.differential_pairs_list.clear()
        port_setup_tab.ref_net_combo.clear()

        try:
            if not selected_controllers or not selected_drams:
                port_setup_tab.ref_net_combo.addItem("GND")
                self.update_checked_count()
                return

            controller_nets = set(pin[1] for comp in selected_controllers for pin in self.pcb_data["component"].get(comp, []))
            dram_nets = set(pin[1] for comp in selected_drams for pin in self.pcb_data["component"].get(comp, []))
            common_nets = controller_nets.intersection(dram_nets)

            selected_components = selected_controllers + selected_drams
            net_pin_counts = {net: sum(1 for comp_name in selected_components for pin in self.pcb_data["component"].get(comp_name, []) if pin[1] == net) for net in common_nets}
            sorted_nets = sorted(net_pin_counts.items(), key=lambda item: item[1], reverse=True)

            for net_name, count in sorted_nets:
                port_setup_tab.ref_net_combo.addItem(net_name)
            if sorted_nets:
                port_setup_tab.ref_net_combo.setCurrentIndex(0)

            diff_pairs_info = self.pcb_data.get("diff", {})
            diff_pair_nets = {net for pos_net, neg_net in diff_pairs_info.values() for net in (pos_net, neg_net)}

            single_nets = sorted([net for net in common_nets if net not in diff_pair_nets and net.upper() != "GND"])
            for net in single_nets:
                item = QListWidgetItem(net)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                port_setup_tab.single_ended_list.addItem(item)

            for pair_name, (pos_net, neg_net) in sorted(diff_pairs_info.items()):
                if pos_net in common_nets and neg_net in common_nets:
                    item = QListWidgetItem(pair_name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    port_setup_tab.differential_pairs_list.addItem(item)

            self.update_checked_count()
        finally:
            port_setup_tab.single_ended_list.blockSignals(False)
            port_setup_tab.differential_pairs_list.blockSignals(False)

    def apply_simulation_settings(self):
        import_tab = self.tabs.get("import_tab")
        simulation_tab = self.tabs.get("simulation_tab")
        if not import_tab or not simulation_tab: return

        # --- VALIDATION START ---
        signal_nets_text = simulation_tab.signal_nets_label.text()
        if not signal_nets_text or signal_nets_text == "(not set)":
            self.log("Signal nets are not defined. Please complete the 'Port Setup' tab first.", "red")
            return
        # --- VALIDATION END ---

        aedb_path = import_tab.layout_path_label.text()
        if not os.path.isdir(aedb_path):
            self.log("Please open an .aedb project first.", "red")
            return

        project_data = {"app_name": self.app_name}
        if self.project_file and os.path.exists(self.project_file):
            with open(self.project_file, "r") as f:
                project_data.update(json.load(f))

        sweeps = []
        for row in range(simulation_tab.sweeps_table.rowCount()):
            sweeps.append([
                simulation_tab.sweeps_table.cellWidget(row, 0).currentText(),
                simulation_tab.sweeps_table.item(row, 1).text(),
                simulation_tab.sweeps_table.item(row, 2).text(),
                simulation_tab.sweeps_table.item(row, 3).text(),
            ])

        project_data.update({
            "aedb_path": aedb_path,
            "edb_version": import_tab.edb_version_input.text(),
            "cutout": {
                "enabled": simulation_tab.enable_cutout_checkbox.isChecked(),
                "expansion_size": simulation_tab.expansion_size_input.text(),
                "signal_nets": simulation_tab.signal_nets_label.text().split(", "),
                "reference_net": [simulation_tab.reference_net_label.text()],
            },
            "solver": "SIwave",
            "solver_version": simulation_tab.siwave_version_input.text(),
            "frequency_sweeps": sweeps,
        })

        try:
            with open(self.project_file, "w") as f:
                json.dump(project_data, f, indent=2)
            self.log(f"Simulation settings saved to {self.project_file}")

            self.log("Applying simulation settings to EDB...")
            self._set_button_running(simulation_tab.apply_simulation_button)
            script_path = os.path.join(self.scripts_dir, "set_sim.py")
            python_executable = sys.executable
            command = [python_executable, script_path, self.project_file]

            metadata = {
                "type": "set_sim",
                "description": "Applying simulation setup",
                "button": simulation_tab.apply_simulation_button,
                "button_style": getattr(simulation_tab, "apply_simulation_button_original_style", ""),
                "button_reset_text": "Apply",
            }

            self._submit_task(
                command,
                metadata=metadata,
                input_path=self.project_file,
                description=metadata["description"],
            )

        except Exception as e:
            self.log(f"Error applying simulation settings: {e}", color="red")
            self._restore_button(
                simulation_tab.apply_simulation_button,
                getattr(simulation_tab, "apply_simulation_button_original_style", ""),
                "Apply",
            )

    def run_get_loss(self):
        if not self.project_file or not os.path.exists(self.project_file):
            result_tab = self.tabs.get("result_tab")
            self.log("Project file not set. Cannot retrieve loss data.", "red")
            if result_tab:
                self._restore_button(
                    result_tab.apply_result_button,
                    getattr(result_tab, "apply_result_button_original_style", ""),
                    "Apply",
                )
            return

        result_tab = self.tabs.get("result_tab")
        metadata = {
            "type": "get_loss",
            "description": "Collecting SIwave loss data",
            "button": result_tab.apply_result_button if result_tab else None,
            "button_style": getattr(result_tab, "apply_result_button_original_style", "") if result_tab else "",
            "button_reset_text": "Apply",
        }

        script_path = os.path.join(self.scripts_dir, "get_loss.py")
        command = [sys.executable, script_path, self.project_file]

        self._submit_task(
            command,
            metadata=metadata,
            input_path=self.project_file,
            description=metadata["description"],
        )

    def run_generate_report(self):
        if not self.project_file or not os.path.exists(self.project_file):
            result_tab = self.tabs.get("result_tab")
            self.log("Project file not set. Cannot generate report.", "red")
            if result_tab:
                self._restore_button(
                    result_tab.apply_result_button,
                    getattr(result_tab, "apply_result_button_original_style", ""),
                    "Apply",
                )
            return

        result_tab = self.tabs.get("result_tab")
        metadata = {
            "type": "generate_report",
            "description": "Generating HTML report",
            "button": result_tab.apply_result_button if result_tab else None,
            "button_style": getattr(result_tab, "apply_result_button_original_style", "") if result_tab else "",
            "button_reset_text": "Apply",
        }

        script_path = os.path.join(self.scripts_dir, "generate_report.py")
        command = [sys.executable, script_path, self.project_file]

        self._submit_task(
            command,
            metadata=metadata,
            input_path=self.project_file,
            description=metadata["description"],
        )
