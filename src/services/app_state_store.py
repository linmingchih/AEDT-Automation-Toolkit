import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _default_base_dir(product_name: str) -> Path:
    if sys.platform.startswith("win"):
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / product_name
        return Path.home() / "AppData" / "Roaming" / product_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / product_name
    return Path.home() / ".config" / product_name


class AppStateStore:
    """Lightweight persistence helper for per-app runtime preferences."""

    def __init__(self, product_name: str = "si-automation-flow", base_dir: Optional[Path] = None):
        self.base_dir = base_dir or _default_base_dir(product_name)

    def _state_file(self, app_name: str) -> Path:
        return self.base_dir / app_name / "state.json"

    def load(self, app_name: str) -> Dict[str, Any]:
        path = self._state_file(app_name)
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}

    def save(self, app_name: str, data: Dict[str, Any]) -> None:
        path = self._state_file(app_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
