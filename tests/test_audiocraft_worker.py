from types import SimpleNamespace

from audio_playground.workers.audiocraft_worker import _select_device


def _torch(*, cuda: bool, mps: bool) -> SimpleNamespace:
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


def test_select_device_prefers_cuda() -> None:
    device, warning = _select_device(_torch(cuda=True, mps=True))

    assert device == "cuda"
    assert warning is None


def test_select_device_uses_mps_compatibility_mode() -> None:
    device, warning = _select_device(_torch(cuda=False, mps=True))

    assert device == "mps"
    assert warning is not None
    assert "compatibility mode" in warning


def test_select_device_uses_cpu_without_accelerator() -> None:
    device, warning = _select_device(_torch(cuda=False, mps=False))

    assert device == "cpu"
    assert warning is None
