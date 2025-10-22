"""App controller for the CCT flow.

Currently the CCT automation shares the same behaviour as the SI app for the
first three tabs (import, port setup, simulation). We reuse the existing SI
controller implementation to keep the flows consistent while additional CCT
tabs are defined.
"""

import json
import os

from apps.si_app.controller import AppController as _SiAppController


class AppController(_SiAppController):
    """Thin wrapper around the SI flow controller for the CCT app."""

    def __init__(self, app_name):
        super().__init__(app_name)

    def load_config(self):
        """Load configuration but explicitly skip restoring the last project."""
        # This is a customized version of the parent AppController.load_config
        # to avoid loading the last project file and triggering a premature refresh.

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
