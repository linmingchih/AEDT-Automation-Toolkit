"""Base class for application controllers."""

import json
import os
import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

from src.services import AppStateStore, ExternalScriptRunner


class BaseAppController(QObject):
    """Base controller with shared functionality for all apps."""

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
        """Connect signals for all tabs provided by the GUI."""
        self.tabs = tabs or {}
        for tab in self.tabs.values():
            binder = getattr(tab, "bind_to_controller", None)
            if callable(binder):
                binder()

    def log(self, message, color=None):
        """Log a message to the GUI's log window."""
        if not self.log_window:
            return
        if color:
            self.log_window.setTextColor(QColor(color))
        self.log_window.append(message)
        self.log_window.setTextColor(QColor("black"))
        self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())

    # ------------------------------------------------------------------ #
    # External task coordination helpers
    # ------------------------------------------------------------------ #
    def _set_button_running(self, button, text="Running..."):
        if not button:
            return
        button.setEnabled(False)
        button.setText(text)
        button.setStyleSheet("background-color: yellow; color: black;")

    def _restore_button(self, button, original_style, text="Apply"):
        if not button:
            return
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
        """Handle the start of an external task."""
        metadata["attempt"] = attempt

    def on_task_finished(self, task_id, exit_code, metadata):
        """Handle the successful completion of an external task."""
        context = self.task_contexts.pop(task_id, metadata or {})
        self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
        self.log(f"Task '{context.get('type')}' finished.")

    def on_task_error(self, task_id, exit_code, message, metadata):
        """Handle a failed external task."""
        context = self.task_contexts.pop(task_id, metadata or {})
        log_message = message or f"Task failed with exit code {exit_code}."
        self._restore_button(context.get("button"), context.get("button_style"), context.get("button_reset_text", "Apply"))
        self.log(f"Task '{context.get('type')}' failed: {log_message}", "red")

    def on_task_log_message(self, task_id, level, message, metadata):
        """Log messages from an external task."""
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

    def get_global_settings(self):
        """Load global settings."""
        return self.state_store.load("_global")

    def set_global_setting(self, key, value):
        """Save a global setting."""
        settings = self.get_global_settings()
        settings[key] = value
        self.state_store.save("_global", settings)

    def get_config_path(self):
        """Get the path to the app's config.json file."""
        # This is a default implementation. Subclasses should override this if their
        # config.json is not in the same directory as the controller file.
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    def load_config(self):
        """Load the application's configuration."""
        # This method should be overridden by subclasses with app-specific logic.
        pass

    def save_config(self):
        """Save the application's configuration."""
        # This method should be overridden by subclasses with app-specific logic.
        pass
