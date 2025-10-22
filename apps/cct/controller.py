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
