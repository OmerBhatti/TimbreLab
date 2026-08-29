import pytest

from audio_playground.workers.omnivoice_worker import (
    _generation_kwargs,
    _spoken_text,
    can_lock_voice,
    speaker_seed,
    _estimated_forward_passes,
    _seed_random_generators,
    _validated_voice_instruction,
)


def test_short_speech_estimate_uses_one_diffusion_pass_set() -> None:
    assert _estimated_forward_passes("[happy] Hello there.", 32) == 32


def test_long_speech_estimate_accounts_for_chunks() -> None:
    assert _estimated_forward_passes("a" * 600, 16) == 48


def test_voice_instruction_drops_unsupported_styles() -> None:
    instruction, unsupported = _validated_voice_instruction(
        "female, young adult, american accent, dramatic, whisper"
    )

    assert instruction == "female, young adult, american accent, whisper"
    assert unsupported == ["dramatic"]


def test_seed_is_applied_to_numpy_and_torch() -> None:
    calls: list[tuple[str, int]] = []

    class FakeNumpy:
        class random:
            @staticmethod
            def seed(value: int) -> None:
                calls.append(("numpy", value))

    class FakeTorch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return True

            @staticmethod
            def manual_seed_all(value: int) -> None:
                calls.append(("cuda", value))

        @staticmethod
        def manual_seed(value: int) -> None:
            calls.append(("torch", value))

    _seed_random_generators(FakeTorch, FakeNumpy, 1234)

    assert calls == [("numpy", 1234), ("torch", 1234), ("cuda", 1234)]


def test_clone_request_passes_reference_audio_and_transcript(tmp_path) -> None:
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"RIFF")

    kwargs = _generation_kwargs(
        {
            "text": "Hello.",
            "mode": "clone",
            "ref_audio": str(reference),
            "ref_text": "This is the reference.",
            "voice_instruction": "female, elderly",
            "steps": 16,
        }
    )

    assert kwargs["ref_audio"] == str(reference)
    assert kwargs["ref_text"] == "This is the reference."
    assert "instruct" not in kwargs


def test_clone_request_requires_an_existing_recording(tmp_path) -> None:
    with pytest.raises(ValueError, match="reference recording"):
        _generation_kwargs(
            {
                "text": "Hello.",
                "mode": "clone",
                "ref_audio": str(tmp_path / "missing.wav"),
                "ref_text": "Present.",
            }
        )


def test_clone_request_requires_a_transcript(tmp_path) -> None:
    reference = tmp_path / "voice.wav"
    reference.write_bytes(b"RIFF")

    with pytest.raises(ValueError, match="transcript"):
        _generation_kwargs(
            {"text": "Hello.", "mode": "clone", "ref_audio": str(reference), "ref_text": "  "}
        )


def test_speaker_seed_is_stable_per_speaker_and_case_insensitive() -> None:
    assert speaker_seed(9999, "Emma") == speaker_seed(9999, "emma")
    assert speaker_seed(9999, "Emma") != speaker_seed(9999, "John")
    assert speaker_seed(9999, "Emma") != speaker_seed(1234, "Emma")
    assert 0 <= speaker_seed(2_147_483_647, "Emma") < 2_147_483_648


def test_voice_is_locked_only_from_a_long_enough_line() -> None:
    assert can_lock_voice([0.0] * 36_000) is True
    assert can_lock_voice([0.0] * 12_000) is False


def test_spoken_text_drops_inline_cues() -> None:
    assert _spoken_text("[sigh] I wasn't expecting you. [laughter]") == "I wasn't expecting you."
