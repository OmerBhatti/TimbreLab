from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QSettings


class VoicePresetStore:
    """Persistent named voice configurations backed by QSettings."""

    SETTINGS_KEY = "voice_presets/v1"
    DEFAULTS_SEEDED_KEY = "voice_presets/defaults_v1_seeded"
    ADDITIONAL_DEFAULTS_SEEDED_KEY = "voice_presets/defaults_v2_seeded"
    DEFAULT_PRESETS = {
        "male-narrator": {
            "mode": "design",
            "gender": "male",
            "age": "elderly",
            "pitch": "very low pitch",
            "accent": "british accent",
            "style": "normal",
            "speed": 0.9,
            "steps": 64,
        },
        "female-narrator": {
            "mode": "design",
            "gender": "female",
            "age": "middle-aged",
            "pitch": "high pitch",
            "accent": "british accent",
            "style": "normal",
            "speed": 0.9,
            "steps": 64,
        },
    }
    ADDITIONAL_DEFAULT_PRESETS = {
        "warm-female-narrator": {
            "mode": "design",
            "gender": "female",
            "age": "middle-aged",
            "pitch": "moderate pitch",
            "accent": "canadian accent",
            "style": "normal",
            "speed": 0.95,
            "steps": 48,
        },
        "young-male-narrator": {
            "mode": "design",
            "gender": "male",
            "age": "young adult",
            "pitch": "moderate pitch",
            "accent": "american accent",
            "style": "normal",
            "speed": 1.0,
            "steps": 48,
        },
        "deep-male-announcer": {
            "mode": "design",
            "gender": "male",
            "age": "middle-aged",
            "pitch": "very low pitch",
            "accent": "american accent",
            "style": "normal",
            "speed": 0.85,
            "steps": 64,
        },
        "soft-female-whisper": {
            "mode": "design",
            "gender": "female",
            "age": "young adult",
            "pitch": "low pitch",
            "accent": "british accent",
            "style": "whispering",
            "speed": 0.85,
            "steps": 48,
        },
        "elderly-female-storyteller": {
            "mode": "design",
            "gender": "female",
            "age": "elderly",
            "pitch": "low pitch",
            "accent": "british accent",
            "style": "normal",
            "speed": 0.9,
            "steps": 64,
        },
        "energetic-female-host": {
            "mode": "design",
            "gender": "female",
            "age": "young adult",
            "pitch": "high pitch",
            "accent": "american accent",
            "style": "normal",
            "speed": 1.1,
            "steps": 48,
        },
    }

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

    def ensure_defaults(self) -> None:
        """Seed built-in examples once without overwriting user configurations."""
        presets = self.all()
        changed = False
        batches = (
            (self.DEFAULTS_SEEDED_KEY, self.DEFAULT_PRESETS),
            (self.ADDITIONAL_DEFAULTS_SEEDED_KEY, self.ADDITIONAL_DEFAULT_PRESETS),
        )
        for settings_key, defaults in batches:
            if self.settings.value(settings_key, False, type=bool):
                continue
            for name, config in defaults.items():
                if name not in presets:
                    presets[name] = config.copy()
                    changed = True
            self.settings.setValue(settings_key, True)
        if changed:
            self.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, sort_keys=True))
        self.settings.sync()
