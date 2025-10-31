"""App controller for the CCT flow."""

import json
import os
import sys

from src.controllers.base_controller import BaseAppController


class AppController(BaseAppController):
    """Controller for the CCT app."""

    def __init__(self, app_name):
        super().__init__(app_name)
        self.register_task_handlers(
            finished={
                "get_edb": self._handle_get_edb_finished,
                "set_edb": self._handle_set_edb_finished,
                "set_sim": self._handle_set_sim_finished,
                "run_sim": self._handle_run_sim_finished,
                "run_cct": self._handle_run_cct_finished,
                "modify_xml": self._handle_modify_xml_finished,
                "get_loss": self._handle_get_loss_finished,
                "generate_report": self._handle_generate_report_finished,
            },
            errored={
                "get_edb": self._handle_get_edb_error,
                "set_edb": self._handle_set_edb_error,
                "set_sim": self._handle_set_sim_error,
                "run_sim": self._handle_run_sim_error,
                "run_cct": self._handle_run_cct_error,
                "get_loss": self._handle_get_loss_error,
                "generate_report": self._handle_generate_report_error,
            },
        )

    def get_config_path(self):
        return os.path.join(os.path.dirname(__file__), "config.json")

    def _apply_simulation_settings_to_tab(self, simulation_tab, settings):
        if not simulation_tab or not isinstance(settings, dict):
            return

        simulation_tab.enable_cutout_checkbox.setChecked(
            settings.get("cutout_enabled", simulation_tab.enable_cutout_checkbox.isChecked())
        )
        simulation_tab.expansion_size_input.setText(
            settings.get("expansion_size", simulation_tab.expansion_size_input.text() or "0.005000")
        )
        simulation_tab.siwave_version_input.setText(
            settings.get("siwave_version", simulation_tab.siwave_version_input.text() or "2025.1")
        )

        sweeps = settings.get("frequency_sweeps")
        if sweeps is not None:
            simulation_tab.sweeps_table.setRowCount(0)
            for sweep in sweeps:
                simulation_tab.add_sweep(sweep)

    def load_config(self):
        """Load configuration but explicitly skip restoring the last project."""
        config_path = self.get_config_path()
        simulation_tab = self.tabs.get("simulation_tab")
        import_tab = self.tabs.get("import_tab")

        # Load app-level defaults from config.json
        defaults = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    defaults = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.log(f"Could not load default config: {e}", "orange")

        actions = defaults.get("actions") if isinstance(defaults, dict) else None
        self.actions_config = actions if isinstance(actions, dict) else {}

        if simulation_tab and defaults.get("settings"):
            self._apply_simulation_settings_to_tab(simulation_tab, defaults.get("settings", {}))

        # Load persisted user state
        state = self.state_store.load(self.app_name)

        if simulation_tab:
            sim_state = state.get("simulation_settings")
            if sim_state:
                self._apply_simulation_settings_to_tab(simulation_tab, sim_state)

        if import_tab:
            edb_version = state.get("edb_version") or "2024.1"
            import_tab.edb_version_input.setText(edb_version)

        # Explicitly do NOT load the last project file.
        self.project_file = None

        # Clear any residual data in CCT-specific tabs.
        cct_tab = self.tabs.get("cct_tab")
        if cct_tab:
            cct_tab.project_path_input.setText("")
            cct_tab.touchstone_path_input.setText("")
            if hasattr(cct_tab, "_clear_port_table"):
                cct_tab._clear_port_table()

        table_tab = self.tabs.get("table")
        if table_tab:
            table_tab.csv_path_input.setText("")
            if hasattr(table_tab, "_clear_table"):
                table_tab._clear_table()
            setattr(table_tab, "_current_project", None)

    def _refresh_cct_tabs(self, project_path=None):
        path = project_path or self.project_file

        def resolve_path(existing_path):
            if existing_path and os.path.exists(existing_path):
                return existing_path
            return None

        tabs_to_update = []
        for name in ("cct_tab", "table"):
            tab = self.tabs.get(name)
            if not tab:
                continue
            loader = getattr(tab, "load_from_project", None)
            if callable(loader):
                tabs_to_update.append((tab, loader))

        if not tabs_to_update:
            return

        candidate_path = resolve_path(path)
        if not candidate_path:
            for tab, _ in tabs_to_update:
                attr = getattr(tab, "project_path_input", None)
                if attr is None:
                    continue
                try:
                    text_value = attr.text().strip()
                except Exception:
                    text_value = ""
                candidate_path = resolve_path(text_value)
                if candidate_path:
                    break

        if not candidate_path:
            return

        for tab, loader in tabs_to_update:
            try:
                loader(candidate_path)
            except Exception as exc:
                self.log(f"Could not refresh {tab.__class__.__name__}: {exc}", "orange")

    def _handle_get_edb_finished(self, task_id, exit_code, context):
        self._reset_task_button(context)
        self.log("Get EDB process finished.")
        layout_path = self.current_layout_path or ""
        import_tab = self.tabs.get("import_tab")
        if layout_path.lower().endswith(".brd") and import_tab:
            new_aedb_path = os.path.splitext(layout_path)[0] + ".aedb"
            import_tab.layout_path_label.setText(new_aedb_path)
            self.log(f"Design path has been updated to: {new_aedb_path}")

        if import_tab and self.project_file and os.path.exists(self.project_file):
            try:
                with open(self.project_file, "r") as f:
                    project_data = json.load(f)
                imported_xml = project_data.get("xml_path", "")
                import_tab.imported_stackup_path.setText(imported_xml)
                self.log(f"Imported stackup path loaded: {imported_xml}")
            except (IOError, json.JSONDecodeError) as e:
                self.log(f"Error reading project file to get imported stackup: {e}", "red")

        self.log(f"Successfully updated PCB data in {os.path.basename(self.project_file)}")
        port_setup_tab = self.tabs.get("port_setup_tab")
        if port_setup_tab:
            port_setup_tab.load_pcb_data()
        self._refresh_cct_tabs()

    def _handle_set_edb_finished(self, task_id, exit_code, context):
        self._reset_task_button(context)
        self.log("Set EDB process finished.")
        if self.current_aedb_path:
            new_aedb_path = self.current_aedb_path.replace(".aedb", "_applied.aedb")
            self.log(f"Successfully created {new_aedb_path}")
        self._refresh_cct_tabs()

    def _handle_set_sim_finished(self, task_id, exit_code, context):
        self.log("Set simulation process finished.")
        self.log("Successfully applied simulation settings. Now running simulation...")
        self._refresh_cct_tabs()
        self._queue_simulation_run(context)

    def _handle_run_sim_finished(self, task_id, exit_code, context):
        result_tab = self.tabs.get("result_tab")
        self._reset_task_button(context)
        self.log("Simulation process finished.")
        if result_tab:
            result_tab.project_path_input.setText(self.project_file)
        self.log("Successfully ran simulation. Project file path has been set in the Result tab.")
        self._refresh_cct_tabs()

    def _handle_run_cct_finished(self, task_id, exit_code, context):
        self._reset_task_button(context)
        self.log("CCT calculation finished.")
        self._refresh_cct_tabs()

    def _handle_modify_xml_finished(self, task_id, exit_code, context):
        self._reset_task_button(context)
        self.log("Stackup modification process finished.")

    def _handle_get_loss_finished(self, task_id, exit_code, context):
        self.log("Successfully got loss data. Generating HTML report...")
        result_tab = self.tabs.get("result_tab")
        if result_tab:
            result_tab.run_generate_report()

    def _handle_generate_report_finished(self, task_id, exit_code, context):
        result_tab = self.tabs.get("result_tab")
        self._reset_task_button(context)
        self.log("HTML report generation finished.")
        if result_tab and self.report_path:
            result_tab.html_group.setVisible(True)

    def _handle_get_edb_error(self, task_id, exit_code, log_message, context):
        self._reset_task_button(context)
        self.log("Get EDB process finished.")
        self.log(f"Get EDB process failed with exit code {exit_code}. {log_message}", "red")

    def _handle_set_edb_error(self, task_id, exit_code, log_message, context):
        self._reset_task_button(context)
        self.log("Set EDB process finished.")
        self.log(f"Set EDB process failed with exit code {exit_code}. {log_message}", "red")

    def _handle_set_sim_error(self, task_id, exit_code, log_message, context):
        self._reset_task_button(context)
        self.log("Set simulation process finished.")
        self.log(f"Set simulation process failed with exit code {exit_code}. {log_message}", "red")

    def _handle_run_sim_error(self, task_id, exit_code, log_message, context):
        self._reset_task_button(context)
        self.log("Simulation process finished.")
        self.log(f"Run simulation process failed with exit code {exit_code}. {log_message}", "red")

    def _handle_run_cct_error(self, task_id, exit_code, log_message, context):
        self._reset_task_button(context)
        self.log("CCT calculation finished.")
        self.log(f"CCT calculation failed with exit code {exit_code}. {log_message}", "red")

    def _handle_get_loss_error(self, task_id, exit_code, log_message, context):
        result_tab = self.tabs.get("result_tab")
        self._reset_task_button(context)
        if result_tab:
            result_tab.html_group.setVisible(False)
        self.log(f"Get loss process failed with exit code {exit_code}. {log_message}", "red")

    def _handle_generate_report_error(self, task_id, exit_code, log_message, context):
        result_tab = self.tabs.get("result_tab")
        self._reset_task_button(context)
        if result_tab:
            result_tab.html_group.setVisible(False)
        self.log(f"HTML report generation failed with exit code {exit_code}. {log_message}", "red")

    def _queue_simulation_run(self, context):
        simulation_tab = self.tabs.get("simulation_tab")
        if not simulation_tab or not self.project_file:
            self.log("Unable to start simulation run: missing project file.", "red")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            return

        action_spec = self.get_action_spec("run_sim", tab_name="simulation_tab")
        script_path = action_spec["script"]
        command = [sys.executable, script_path, self.project_file]
        if action_spec.get("args"):
            command.extend(action_spec["args"])

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
            working_dir=action_spec.get("working_dir"),
            env=action_spec.get("env"),
        )

    def on_task_log_message(self, task_id, level, message, metadata):
        super().on_task_log_message(task_id, level, message, metadata)

        if metadata.get("type") == "generate_report" and "HTML report generated at: " in message:
            result_tab = self.tabs.get("result_tab")
            self.report_path = message.split("HTML report generated at: ")[1].strip()
            if result_tab:
                result_tab.html_path_input.setText(self.report_path)

    def save_config(self):
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

        state = self.state_store.load(self.app_name)
        state["simulation_settings"] = {
            "cutout_enabled": simulation_tab.enable_cutout_checkbox.isChecked(),
            "expansion_size": simulation_tab.expansion_size_input.text(),
            "siwave_version": simulation_tab.siwave_version_input.text(),
            "frequency_sweeps": sweeps
        }

        if import_tab:
            state["edb_version"] = import_tab.edb_version_input.text()

        if self.project_file:
            state["last_project_file"] = self.project_file

        try:
            self.state_store.save(self.app_name, state)
        except Exception as e:
            self.log(f"Could not persist application state: {e}", "red")

        if self.project_file and os.path.exists(self.project_file) and import_tab:
            try:
                with open(self.project_file, "r", encoding="utf-8") as f:
                    project_config = json.load(f)
                project_config["edb_version"] = import_tab.edb_version_input.text()
                project_config["app_name"] = self.app_name
                with open(self.project_file, "w", encoding="utf-8") as f:
                    json.dump(project_config, f, indent=2)
            except (IOError, json.JSONDecodeError) as e:
                self.log(f"Could not update project config: {e}", "red")
