from types import SimpleNamespace

from audio_playground.workers.audioldm_worker import (
    _clamp_duration,
    _seeded_generator,
    _select_device,
    _select_dtype,
)


def _torch(*, cuda: bool, mps: bool) -> SimpleNamespace:
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


def test_select_device_prefers_cuda() -> None:
    assert _select_device(_torch(cuda=True, mps=True)) == "cuda"


def test_select_device_uses_mps_on_apple_silicon() -> None:
    assert _select_device(_torch(cuda=False, mps=True)) == "mps"


def test_select_device_uses_cpu_without_accelerator() -> None:
    assert _select_device(_torch(cuda=False, mps=False)) == "cpu"


def test_select_dtype_uses_float16_only_on_cuda() -> None:
    torch = SimpleNamespace(float16="float16", float32="float32")

    assert _select_dtype(torch, "cuda") == "float16"
    assert _select_dtype(torch, "mps") == "float32"
    assert _select_dtype(torch, "cpu") == "float32"


def test_duration_is_limited_to_supported_range() -> None:
    assert _clamp_duration(0) == 1.0
    assert _clamp_duration(5) == 5.0
    assert _clamp_duration(30) == 30.0
    assert _clamp_duration(60) == 30.0


def test_seeded_generator_uses_cpu_for_mps() -> None:
    calls: list[tuple[str, object]] = []

    class Generator:
        def __init__(self, *, device: str) -> None:
            calls.append(("device", device))

        def manual_seed(self, value: int) -> "Generator":
            calls.append(("seed", value))
            return self

    torch = SimpleNamespace(Generator=Generator)

    generator = _seeded_generator(torch, "mps", 9876)

    assert isinstance(generator, Generator)
    assert calls == [("device", "cpu"), ("seed", 9876)]
