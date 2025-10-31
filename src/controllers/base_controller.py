"""Base class for application controllers."""

import json
import os
import sys

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

from src.controllers.tab_context import TabContext
from src.services import AppStateStore, ExternalScriptRunner


class BaseAppController(QObject):
    """Base controller with shared functionality for all apps."""

    def __init__(self, app_name):
        super().__init__()
        self.app_name = app_name
        self.project_file = None
        self.project_log_path = None
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
        self._task_finished_handlers = {}
        self._task_error_handlers = {}

        # Shared state and event plumbing used by TabContext.
        self._shared_state = {}
        self._tab_states = {}
        self._tab_contexts = {}
        self._tab_event_permissions = self.configure_tab_events() or {}
        self._controller_event_handlers = {}
        self._tab_event_subscribers = {}

        # Built-in events exposed to tabs.
        self.register_event_handler("project_update", self._handle_project_update_event)

    def set_project_log_path(self, project_json_path):
        """Sets the path for the project-specific log file."""
        if project_json_path:
            log_dir = os.path.dirname(project_json_path)
            log_name = os.path.splitext(os.path.basename(project_json_path))[0] + ".log"
            self.project_log_path = os.path.join(log_dir, log_name)
            # Optional: Write an initial message to create the log file
            self.log_message(f"Project log initialized at: {self.project_log_path}")
        else:
            self.project_log_path = None

    def connect_signals(self, tabs):
        """Connect signals for all tabs provided by the GUI."""
        self.tabs = tabs or {}
        for tab in self.tabs.values():
            binder = getattr(tab, "bind_to_controller", None)
            if callable(binder):
                binder()

    # ------------------------------------------------------------------ #
    # Tab context lifecycle
    # ------------------------------------------------------------------ #
    def configure_tab_events(self):
        """Return a mapping of tab name -> iterable of allowed event names."""

        return {}

    def create_tab_context(self, tab_name):
        allowed = self._tab_event_permissions.get(tab_name)
        context = TabContext(self, tab_name, allowed_events=allowed)
        self._tab_contexts[tab_name] = context
        return context

    def get_tab_context(self, tab_name):
        return self._tab_contexts.get(tab_name)

    def register_event_handler(self, event_name, handler):
        handlers = self._controller_event_handlers.setdefault(event_name, [])
        if handler not in handlers:
            handlers.append(handler)

    def register_tab_listener(self, tab_name, event_name, callback):
        subscribers = self._tab_event_subscribers.setdefault(event_name, [])
        subscribers.append((tab_name, callback))

    def dispatch_tab_event(self, source_tab, event_name, payload=None):
        allowed = self._tab_event_permissions.get(source_tab)
        if allowed is not None and allowed and event_name not in allowed:
            raise ValueError(
                f"Tab '{source_tab}' attempted to publish unauthorized event '{event_name}'"
            )

        payload = payload or {}

        for handler in self._controller_event_handlers.get(event_name, []):
            handler(source_tab, payload)

        for target_tab, callback in self._tab_event_subscribers.get(event_name, []):
            try:
                callback(source_tab, payload)
            except Exception as exc:
                self.log(f"Error handling event '{event_name}' in {target_tab}: {exc}", "red")

    # ------------------------------------------------------------------ #
    # Shared state utilities
    # ------------------------------------------------------------------ #
    def get_shared_state(self, key, default=None):
        return self._shared_state.get(key, default)

    def set_shared_state(self, key, value):
        self._shared_state[key] = value

    def update_tab_state(self, tab_name, data):
        state = self._tab_states.setdefault(tab_name, {})
        state.update(data)

    def get_tab_state(self, tab_name):
        return self._tab_states.get(tab_name, {})

    # ------------------------------------------------------------------ #
    # Project coordination
    # ------------------------------------------------------------------ #
    def _handle_project_update_event(self, source_tab, payload):
        update_type = payload.get("type")
        data = {k: v for k, v in payload.items() if k != "type"}
        self.handle_project_update(source_tab, update_type, **data)

    def handle_project_update(self, source_tab, update_type, **payload):
        if update_type == "project_file":
            path = payload.get("path")
            self.project_file = path
            if path:
                self.set_shared_state("project_file", path)
        elif update_type == "current_layout_path":
            self.current_layout_path = payload.get("path")
        elif update_type == "current_aedb_path":
            self.current_aedb_path = payload.get("path")
        elif update_type == "report_path":
            self.report_path = payload.get("path")
        elif update_type == "pcb_data":
            self.pcb_data = payload.get("data")
        else:
            handler = getattr(self, "on_project_update", None)
            if callable(handler):
                return handler(source_tab, update_type, **payload)
        return None

    def log_message(self, message, color=None):
        """Log a message to the GUI's log window and the project log file."""
        # Log to GUI
        if self.log_window:
            if color:
                self.log_window.setTextColor(QColor(color))
            self.log_window.append(message)
            self.log_window.setTextColor(QColor("black"))
            self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())

        # Log to file
        if self.project_log_path:
            try:
                with open(self.project_log_path, "a", encoding="utf-8") as f:
                    f.write(message + "\n")
            except IOError as e:
                # If logging to file fails, log an error to the GUI
                error_msg = f"CRITICAL: Could not write to log file {self.project_log_path}. Error: {e}"
                if self.log_window:
                    self.log_window.setTextColor(QColor("red"))
                    self.log_window.append(error_msg)
                    self.log_window.setTextColor(QColor("black"))

    log = log_message  # Alias for backward compatibility

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

    def _reset_task_button(self, context):
        if not context:
            return
        self._restore_button(
            context.get("button"),
            context.get("button_style"),
            context.get("button_reset_text", "Apply"),
        )

    def register_task_handlers(self, *, finished=None, errored=None):
        finished = finished or {}
        errored = errored or {}

        for task_type, handler in finished.items():
            if callable(handler):
                self._task_finished_handlers[task_type] = handler

        for task_type, handler in errored.items():
            if callable(handler):
                self._task_error_handlers[task_type] = handler

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
        # Set the project file and log path as soon as a task with an input path is submitted.
        # This ensures that all subsequent logging for this project context is captured.
        if input_path and os.path.exists(input_path):
            self.project_file = input_path
            self.set_project_log_path(input_path)

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
        task_type = context.get("type")
        handler = self._task_finished_handlers.get(task_type)

        if handler:
            handler(task_id, exit_code, context)
        else:
            self._reset_task_button(context)
            self.log(f"Task '{task_type}' finished.")

    def on_task_error(self, task_id, exit_code, message, metadata):
        """Handle a failed external task."""
        context = self.task_contexts.pop(task_id, metadata or {})
        log_message = message or f"Task failed with exit code {exit_code}."
        task_type = context.get("type")
        handler = self._task_error_handlers.get(task_type)

        if handler:
            handler(task_id, exit_code, log_message, context)
        else:
            self._reset_task_button(context)
            self.log(f"Task '{task_type}' failed: {log_message}", "red")

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
