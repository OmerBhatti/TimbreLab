from audio_playground.audio_utils import normalize_emotion_tags, output_path


def test_normalize_emotion_tags_translates_tags_in_place() -> None:
    text = "[sad] I miss you. [happy] You're home!"
    assert normalize_emotion_tags(text) == "[sigh] I miss you. [laughter] You're home!"


def test_normalize_emotion_tags_is_case_insensitive() -> None:
    assert normalize_emotion_tags("[SURPRISED] What?") == "[surprise-oh] What?"


def test_normalize_emotion_tags_preserves_native_tags() -> None:
    text = "[sigh] Plain speech. [question-oh] Really?"
    assert normalize_emotion_tags(text) == text


def test_output_path_is_safe_and_unique(tmp_path) -> None:
    first = output_path(tmp_path, "sfx", "Rain / thunder?!")
    second = output_path(tmp_path, "sfx", "Rain / thunder?!")

    assert first.parent == tmp_path
    assert first.name.startswith("sfx-rain-thunder-")
    assert first.suffix == ".wav"
    assert first != second
