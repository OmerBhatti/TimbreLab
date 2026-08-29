import pytest

from audio_playground.workers.omnivoice_worker import (
    _generation_kwargs,
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
