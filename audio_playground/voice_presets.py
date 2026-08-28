from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QSettings

from audio_playground.config import DEFAULT_GENERATION_SEED


class VoicePresetStore:
    """Persistent named voice configurations backed by QSettings."""

    DEFAULT_SEED = DEFAULT_GENERATION_SEED
    SETTINGS_KEY = "voice_presets/v1"
    DEFAULTS_SEEDED_KEY = "voice_presets/defaults_v1_seeded"
    ADDITIONAL_DEFAULTS_SEEDED_KEY = "voice_presets/defaults_v2_seeded"
    DEFAULT_SEED_MIGRATED_KEY = "voice_presets/default_seed_9999_migrated"
    LEGACY_DEFAULT_SEED = 42
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
            "seed": DEFAULT_SEED,
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
        for config in presets.values():
            if "seed" not in config:
                config["seed"] = self.DEFAULT_SEED
                changed = True
        if not self.settings.value(self.DEFAULT_SEED_MIGRATED_KEY, False, type=bool):
            for config in presets.values():
                if config.get("seed") == self.LEGACY_DEFAULT_SEED:
                    config["seed"] = self.DEFAULT_SEED
                    changed = True
            self.settings.setValue(self.DEFAULT_SEED_MIGRATED_KEY, True)
        if changed:
            self.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, sort_keys=True))
        self.settings.sync()
