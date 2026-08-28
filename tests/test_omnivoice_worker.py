from audio_playground.workers.omnivoice_worker import (
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
