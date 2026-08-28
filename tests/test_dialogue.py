import pytest

from audio_playground.dialogue import parse_dialogue, voice_instruction_from_preset


def test_parse_dialogue_preserves_speaker_order_and_colons_in_text() -> None:
    assert parse_dialogue("Alice: Hello\n\nBob: Time: 8 PM") == [
        ("Alice", "Hello"),
        ("Bob", "Time: 8 PM"),
    ]


def test_parse_dialogue_reports_invalid_line_number() -> None:
    with pytest.raises(ValueError, match="Line 2"):
        parse_dialogue("Alice: Hello\nThis has no speaker")


def test_voice_instruction_uses_saved_whispering_style() -> None:
    config = {
        "gender": "male",
        "age": "elderly",
        "pitch": "very low pitch",
        "accent": "british accent",
        "style": "whispering",
    }
    assert voice_instruction_from_preset(config) == (
        "male, elderly, very low pitch, british accent, whisper"
    )
