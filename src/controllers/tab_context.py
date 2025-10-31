"""Context objects injected into tabs to expose a controlled API."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Set


class TabContext:
    """Provide a controlled façade over the application controller.

    Tabs interact with the :class:`TabContext` instead of touching the
    controller directly.  This makes the dependencies explicit and offers a
    consistent place to document the supported operations.
    """

    def __init__(
        self,
        controller: "BaseAppController",
        tab_name: str,
        *,
        allowed_events: Optional[Iterable[str]] = None,
    ) -> None:
        self._controller = controller
        self._tab_name = tab_name
        self._allowed_events: Optional[Set[str]] = (
            set(allowed_events) if allowed_events else None
        )

    # ------------------------------------------------------------------
    # Basic metadata helpers
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self._tab_name

    @property
    def app_name(self) -> str:
        return self._controller.app_name

    @property
    def project_root(self) -> str:
        return self._controller.project_root

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def log(self, message: str, color: Optional[str] = None) -> None:
        self._controller.log_message(message, color)

    # ------------------------------------------------------------------
    # Shared state helpers
    # ------------------------------------------------------------------
    def get_shared_state(self, key: str, default: Any = None) -> Any:
        return self._controller.get_shared_state(key, default)

    def set_shared_state(self, key: str, value: Any) -> None:
        self._controller.set_shared_state(key, value)

    def update_state(self, **data: Any) -> None:
        self._controller.update_tab_state(self._tab_name, data)

    def get_state(self) -> Dict[str, Any]:
        return dict(self._controller.get_tab_state(self._tab_name))

    def get_tab_state(self, tab_name: str) -> Dict[str, Any]:
        return dict(self._controller.get_tab_state(tab_name))

    # ------------------------------------------------------------------
    # Project coordination helpers
    # ------------------------------------------------------------------
    @property
    def project_file(self) -> Optional[str]:
        return self._controller.project_file

    @project_file.setter
    def project_file(self, value: Optional[str]) -> None:
        self.request_project_update("project_file", path=value)

    @property
    def current_layout_path(self) -> Optional[str]:
        return self._controller.current_layout_path

    @current_layout_path.setter
    def current_layout_path(self, value: Optional[str]) -> None:
        self.request_project_update("current_layout_path", path=value)

    @property
    def current_aedb_path(self) -> Optional[str]:
        return self._controller.current_aedb_path

    @current_aedb_path.setter
    def current_aedb_path(self, value: Optional[str]) -> None:
        self.request_project_update("current_aedb_path", path=value)

    @property
    def report_path(self) -> Optional[str]:
        return self._controller.report_path

    @report_path.setter
    def report_path(self, value: Optional[str]) -> None:
        self.request_project_update("report_path", path=value)

    @property
    def pcb_data(self) -> Any:
        return self._controller.pcb_data

    @pcb_data.setter
    def pcb_data(self, value: Any) -> None:
        self.request_project_update("pcb_data", data=value)

    def request_project_update(self, update_type: str, **payload: Any) -> Any:
        return self._controller.handle_project_update(
            self._tab_name, update_type, **payload
        )

    def load_config(self) -> Any:
        loader = getattr(self._controller, "load_config", None)
        if callable(loader):
            return loader()
        return None

    # ------------------------------------------------------------------
    # External task helpers
    # ------------------------------------------------------------------
    def get_action_spec(self, action: str, *, tab_name: Optional[str] = None) -> Dict[str, Any]:
        return self._controller.get_action_spec(action, tab_name=tab_name)

    def submit_task(self, command: Iterable[str], *, metadata: Dict[str, Any], **kwargs: Any) -> Any:
        return self._controller._submit_task(command, metadata=metadata, **kwargs)

    def set_button_running(self, button, text: str = "Running...") -> None:
        self._controller._set_button_running(button, text)

    def restore_button(self, button, original_style: Optional[str], text: str = "Apply") -> None:
        self._controller._restore_button(button, original_style, text)

    # ------------------------------------------------------------------
    # Eventing helpers
    # ------------------------------------------------------------------
    def publish_event(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self._allowed_events is not None and event_name not in self._allowed_events:
            raise ValueError(
                f"Tab '{self._tab_name}' attempted to publish unauthorized event '{event_name}'"
            )
        self._controller.dispatch_tab_event(self._tab_name, event_name, payload or {})

    def subscribe(self, event_name: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self._controller.register_tab_listener(self._tab_name, event_name, callback)


__all__ = ["TabContext"]

