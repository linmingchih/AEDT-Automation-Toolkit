"""Shared base classes for GUI tabs."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from src.controllers.tab_context import TabContext


class BaseTab(QWidget):
    """Base class that stores a :class:`TabContext` reference."""

    def __init__(self, context: TabContext):
        super().__init__()
        self.context = context
        # ``controller`` is kept as an alias for backward compatibility with
        # existing tab implementations.  All logic routes through
        # :class:`TabContext` now, so downstream code interacts with the
        # controlled API.
        self.controller = context


__all__ = ["BaseTab"]

