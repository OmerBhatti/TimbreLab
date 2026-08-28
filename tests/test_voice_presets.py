from PyQt6.QtCore import QSettings

from audio_playground.voice_presets import VoicePresetStore


def test_voice_preset_store_saves_and_deletes_named_configs(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    config = {"mode": "design", "gender": "female", "speed": 1.2, "steps": 32}

    store.save("Narrator", config)
    assert store.all() == {"Narrator": config}

    store.delete("Narrator")
    assert store.all() == {}


def test_voice_preset_store_handles_invalid_settings(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(VoicePresetStore.SETTINGS_KEY, "not valid json")

    assert VoicePresetStore(settings).all() == {}

