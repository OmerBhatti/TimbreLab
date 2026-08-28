from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QSettings


class VoicePresetStore:
    """Persistent named voice configurations backed by QSettings."""

    SETTINGS_KEY = "voice_presets/v1"

    def __init__(self, settings: QSettings | None = None) -> None:
        self.settings = settings or QSettings()

    def all(self) -> dict[str, dict[str, Any]]:
        raw = self.settings.value(self.SETTINGS_KEY, "{}")
        try:
            presets = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(presets, dict):
            return {}
        return {
            str(name): config
            for name, config in presets.items()
            if isinstance(config, dict)
        }

    def save(self, name: str, config: dict[str, Any]) -> None:
        presets = self.all()
        presets[name] = config
        self.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, sort_keys=True))
        self.settings.sync()

    def delete(self, name: str) -> None:
        presets = self.all()
        if name in presets:
            del presets[name]
            self.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, sort_keys=True))
            self.settings.sync()

