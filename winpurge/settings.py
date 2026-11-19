"""User preferences, saved in %APPDATA%\\WinPurge\\settings.json."""
from __future__ import annotations

import json

from .trash import app_data_dir


class Settings:
    def __init__(self):
        self.path = app_data_dir() / "settings.json"
        try:
            self.data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("project_roots", [])
        self.data.setdefault("project_age_days", 30)
        self.data.setdefault("theme", "system")   # system, light, dark

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1), "utf-8")
        except OSError:
            pass
