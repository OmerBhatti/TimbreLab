from audio_playground.workers.omnivoice_worker import (
    _estimated_forward_passes,
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
