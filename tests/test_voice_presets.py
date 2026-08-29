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


def test_voice_preset_store_seeds_defaults_once_without_overwriting_user_values(
    tmp_path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    custom = {"mode": "auto", "speed": 1.25, "steps": 16}
    store.save("male-narrator", custom)

    store.ensure_defaults()

    assert store.all()["male-narrator"] == {
        **custom,
        "seed": VoicePresetStore.DEFAULT_SEED,
    }
    assert store.all()["female-narrator"] == VoicePresetStore.DEFAULT_PRESETS[
        "female-narrator"
    ]
    assert store.all()["deep-male-announcer"] == (
        VoicePresetStore.ADDITIONAL_DEFAULT_PRESETS["deep-male-announcer"]
    )

    assert store.delete("female-narrator") is False
    store.ensure_defaults()
    assert "female-narrator" in store.all()


def test_existing_users_receive_only_the_new_default_preset_batch(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(VoicePresetStore.DEFAULTS_SEEDED_KEY, True)
    store = VoicePresetStore(settings)

    store.ensure_defaults()

    assert "male-narrator" not in store.all()
    assert set(store.all()) == set(VoicePresetStore.ADDITIONAL_DEFAULT_PRESETS)


def test_existing_presets_receive_default_seed_without_overwriting_values(
    tmp_path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    store.save("Custom", {"mode": "design", "speed": 1.25, "steps": 16})

    store.ensure_defaults()

    custom = store.all()["Custom"]
    assert custom["speed"] == 1.25
    assert custom["steps"] == 16
    assert custom["seed"] == VoicePresetStore.DEFAULT_SEED


def test_all_built_in_presets_have_an_explicit_default_seed() -> None:
    presets = {
        **VoicePresetStore.DEFAULT_PRESETS,
        **VoicePresetStore.ADDITIONAL_DEFAULT_PRESETS,
    }

    assert all(
        config["seed"] == VoicePresetStore.DEFAULT_SEED
        for config in presets.values()
    )


def test_previous_default_seed_is_migrated_once(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    store.save("Old default", {"mode": "design", "seed": 42})
    store.save("Custom seed", {"mode": "design", "seed": 123})

    store.ensure_defaults()

    assert store.all()["Old default"]["seed"] == 9999
    assert store.all()["Custom seed"]["seed"] == 123

    store.save("Intentionally 42", {"mode": "design", "seed": 42})
    store.ensure_defaults()
    assert store.all()["Intentionally 42"]["seed"] == 42


def test_system_presets_cannot_be_deleted(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    store.ensure_defaults()

    for name in store.system_names():
        assert store.is_system(name)
        assert store.delete(name) is False
        assert name in store.all()


def test_user_presets_can_still_be_deleted(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store = VoicePresetStore(settings)
    store.save("my-voice", {"mode": "design", "seed": 7})

    assert store.is_system("my-voice") is False
    assert store.delete("my-voice") is True
    assert "my-voice" not in store.all()
    assert store.delete("my-voice") is False
