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
            "steps": 32,
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
            "steps": 32,
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
            "steps": 32,
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
            "steps": 32,
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
            "steps": 32,
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
            "steps": 32,
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
            "steps": 32,
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

    DISPLAY_NAMES = {
        "male-narrator": "Male Narrator — elderly, British",
        "female-narrator": "Female Narrator — middle-aged, British",
        "warm-female-narrator": "Warm Female Narrator — Canadian",
        "young-male-narrator": "Young Male Narrator — American",
        "deep-male-announcer": "Deep Male Announcer — American",
        "soft-female-whisper": "Soft Female Whisper — British",
        "elderly-female-storyteller": "Elderly Female Storyteller — British",
        "energetic-female-host": "Energetic Female Host — American",
    }

    @classmethod
    def display_name(cls, name: str) -> str:
        """Readable label for a preset; stored names stay untouched."""
        return cls.DISPLAY_NAMES.get(name, name)

    def grouped(self) -> dict[str, list[str]]:
        """Preset names split into the sections the pickers show."""
        sections: dict[str, list[str]] = {"Built-in voices": [], "Cloned voices": [], "Your voices": []}
        for name, config in self.all().items():
            if self.is_system(name):
                sections["Built-in voices"].append(name)
            elif str(config.get("mode")) == "clone":
                sections["Cloned voices"].append(name)
            else:
                sections["Your voices"].append(name)
        return {
            section: sorted(names, key=str.casefold)
            for section, names in sections.items()
            if names
        }

    def is_system(self, name: str) -> bool:
        """Built-in starter presets belong to the app and cannot be removed."""
        return name in self.system_names()

    @classmethod
    def system_names(cls) -> frozenset[str]:
        return frozenset(cls.DEFAULT_PRESETS) | frozenset(cls.ADDITIONAL_DEFAULT_PRESETS)

    def delete(self, name: str) -> bool:
        """Remove a user preset. Returns False when the name is protected or unknown."""
        if self.is_system(name):
            return False
        presets = self.all()
        if name not in presets:
            return False
        del presets[name]
        self.settings.setValue(self.SETTINGS_KEY, json.dumps(presets, sort_keys=True))
        self.settings.sync()
        return True

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
