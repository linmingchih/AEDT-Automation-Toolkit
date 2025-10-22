import json
import os
import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

from src.services import AppStateStore, ExternalScriptRunner

class AppController(QObject):
    def __init__(self, app_name):
        super().__init__()
        self.app_name = app_name
        self.project_file = None
        self.report_path = None
        self.pcb_data = None
        self.log_window = None  # This will be set by the GUI
        self.tabs = {}  # This will be populated with tab instances
        self.actions_config = {}
        
        # Define project root and scripts directory robustly
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.scripts_dir = os.path.join(self.project_root, "src", "scripts")

        # Persistence and external process coordination
        self.state_store = AppStateStore()
        self.script_runner = ExternalScriptRunner(parent=self)
        self.script_runner.started.connect(self.on_task_started)
        self.script_runner.finished.connect(self.on_task_finished)
        self.script_runner.error.connect(self.on_task_error)
        self.script_runner.log_message.connect(self.on_task_log_message)

        self.task_contexts = {}
        self.current_layout_path = None
        self.current_aedb_path = None

    def connect_signals(self, tabs):
        self.tabs = tabs or {}
        for tab in self.tabs.values():
            binder = getattr(tab, "bind_to_controller", None)
            if callable(binder):
                binder()

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

    def _resolve_relative_path(self, path):
        if not path:
            return path
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.project_root, path))

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

    def get_action_spec(self, action, *, tab_name=None):
        """Return script metadata for a given action, falling back to default scripts directory."""
        spec = None
        if tab_name:
            tab_actions = self.actions_config.get(tab_name)
            if isinstance(tab_actions, dict):
                spec = tab_actions.get(action)
        if spec is None:
            spec = self.actions_config.get(action)

        if spec is None:
            spec = {"script": f"{action}.py"}
        elif isinstance(spec, str):
            spec = {"script": spec}
        else:
            spec = dict(spec)

        script_path = spec.get("script")
        if not script_path:
            script_path = f"{action}.py"

        base_dir = spec.get("base_dir")
        if os.path.isabs(script_path):
            resolved_script = os.path.normpath(script_path)
        elif base_dir:
            resolved_base = self._resolve_relative_path(base_dir)
            resolved_script = os.path.normpath(os.path.join(resolved_base, script_path))
        else:
            resolved_script = os.path.normpath(os.path.join(self.scripts_dir, script_path))
        spec["script"] = resolved_script

        working_dir = spec.get("working_dir")
        if working_dir:
            spec["working_dir"] = self._resolve_relative_path(working_dir)

        args = spec.get("args")
        if args is not None:
            if isinstance(args, (str, bytes)):
                spec["args"] = [str(args)]
            else:
                spec["args"] = [str(item) for item in args]

        env = spec.get("env")
        if env and isinstance(env, dict):
            spec["env"] = {str(key): str(value) for key, value in env.items()}

        return spec

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
            port_setup_tab = self.tabs.get("port_setup_tab")
            if port_setup_tab:
                port_setup_tab.load_pcb_data()
            self._refresh_cct_tabs()

        elif task_type == "set_edb":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Set EDB process finished.")
            if self.current_aedb_path:
                new_aedb_path = self.current_aedb_path.replace(".aedb", "_applied.aedb")
                self.log(f"Successfully created {new_aedb_path}")
            self._refresh_cct_tabs()

        elif task_type == "set_sim":
            self.log("Set simulation process finished.")
            self.log("Successfully applied simulation settings. Now running simulation...")
            self._refresh_cct_tabs()
            self._queue_simulation_run(context)

        elif task_type == "run_sim":
            simulation_tab = self.tabs.get("simulation_tab")
            result_tab = self.tabs.get("result_tab")
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("Simulation process finished.")
            if result_tab:
                result_tab.project_path_input.setText(self.project_file)
            self.log("Successfully ran simulation. Project file path has been set in the Result tab.")
            self._refresh_cct_tabs()

        elif task_type == "run_cct":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("CCT calculation finished.")
            self._refresh_cct_tabs()

        elif task_type == "get_loss":
            self.log("Successfully got loss data. Generating HTML report...")
            result_tab = self.tabs.get("result_tab")
            if result_tab:
                result_tab.run_generate_report()

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

        elif task_type == "run_cct":
            self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
            self.log("CCT calculation finished.")
            self.log(f"CCT calculation failed with exit code {exit_code}. {log_message}", "red")

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
        config_path = self.get_config_path()
        simulation_tab = self.tabs.get("simulation_tab")
        import_tab = self.tabs.get("import_tab")
        result_tab = self.tabs.get("result_tab")

        defaults = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    defaults = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.log(f"Could not load default config: {e}", "orange")

        actions = defaults.get("actions") if isinstance(defaults, dict) else None
        if isinstance(actions, dict):
            self.actions_config = actions
        else:
            self.actions_config = {}

        if simulation_tab and defaults.get("settings"):
            self._apply_simulation_settings_to_tab(simulation_tab, defaults.get("settings", {}))

        state = self.state_store.load(self.app_name)

        if simulation_tab:
            sim_state = state.get("simulation_settings")
            if sim_state:
                self._apply_simulation_settings_to_tab(simulation_tab, sim_state)

        if import_tab:
            edb_version = state.get("edb_version") or "2024.1"
            import_tab.edb_version_input.setText(edb_version)

        last_project = state.get("last_project_file")
        if last_project and os.path.exists(last_project):
            self.project_file = last_project
            if result_tab:
                result_tab.project_path_input.setText(last_project)

        if self.project_file and os.path.exists(self.project_file) and import_tab:
            try:
                with open(self.project_file, "r", encoding="utf-8") as f:
                    project_config = json.load(f)
                import_tab.edb_version_input.setText(
                    project_config.get("edb_version", import_tab.edb_version_input.text() or "2024.1")
                )
            except (IOError, json.JSONDecodeError) as e:
                self.log(f"Could not read project config: {e}", "orange")

        self._refresh_cct_tabs()

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

