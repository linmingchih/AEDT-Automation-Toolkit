"""App controller for the CCT flow.

Currently the CCT automation shares the same behaviour as the SI app for the
first three tabs (import, port setup, simulation). We reuse the existing SI
controller implementation to keep the flows consistent while additional CCT
tabs are defined.
"""

from apps.si_app.controller import AppController as _SiAppController


class AppController(_SiAppController):
    """Thin wrapper around the SI flow controller for the CCT app."""

    def __init__(self, app_name):
        super().__init__(app_name)

    def load_config(self):
        """Load base configuration and then clear UI state for a fresh session."""
        super().load_config()

        # Override to prevent reloading the last project in the CCT flow
        self.project_file = None

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

        # After clearing the UI, this call will reset dependent tabs.
        self._refresh_cct_tabs()
