from __future__ import annotations

import gc
import os
import time
import warnings
from contextlib import nullcontext
from typing import Any

from audio_playground.audiocraft_compat import (
    enable_mps_compatibility,
    provide_xformers_import_stub,
)
from audio_playground.workers.common import (
    _format_bytes,
    _model_cache_complete,
    _repo_cache_state,
    emit,
    monitor_model_download,
    monitor_phase,
    run_worker,
)

_model: Any = None
AUDIOGEN_REPO_SIZE = 3_914_199_861


def _select_device(torch: Any) -> tuple[str, str | None]:
    if torch.cuda.is_available():
        return "cuda", None
    if torch.backends.mps.is_available():
        return (
            "mps",
            "Apple Metal detected. Using AudioCraft MPS compatibility mode: the language "
            "model runs on Metal while EnCodec runs on CPU.",
        )
    return "cpu", None


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    with monitor_phase("Importing AudioCraft and PyTorch", interval=5):
        provide_xformers_import_stub()
        import torch

        enable_mps_compatibility()
        from audiocraft.models.audiogen import AudioGen
        from audiocraft.models.loaders import load_compression_model, load_lm_model

    device, fallback_message = _select_device(torch)
    if fallback_message:
        emit("status", message=fallback_message)
    emit(
        "status",
        message=f"Runtime ready: PyTorch {torch.__version__}; selected device: {device}.",
    )
    if device == "cpu":
        emit(
            "status",
            message=(
                "CPU initialization of AudioGen Medium can take several minutes and use "
                "substantial RAM. Keep the worker running; later generations reuse the "
                "loaded model."
            ),
        )
    elif device == "mps":
        total_memory_gb = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
        memory_note = (
            " This is near AudioGen Medium's practical memory limit; close memory-heavy "
            "apps while it loads."
            if total_memory_gb <= 18
            else ""
        )
        emit(
            "status",
            message=(
                f"System memory: {total_memory_gb:.0f} GB.{memory_note}"
            ),
        )

    emit("status", message=f"Preparing facebook/audiogen-medium on {device}…")
    cached_bytes, _signature = _repo_cache_state("facebook/audiogen-medium")
    cache_is_complete = _model_cache_complete(cached_bytes, AUDIOGEN_REPO_SIZE)
    if cache_is_complete:
        emit(
            "status",
            message=f"Model cache complete ({_format_bytes(cached_bytes)}); no download needed.",
        )
    download_monitor = (
        nullcontext()
        if cache_is_complete
        else monitor_model_download("facebook/audiogen-medium", AUDIOGEN_REPO_SIZE)
    )

    with download_monitor:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="torch.nn.utils.weight_norm is deprecated.*",
                category=UserWarning,
            )
            codec_device = "cpu" if device == "mps" else device
            with monitor_phase(f"Loading EnCodec checkpoint on {codec_device}", interval=10):
                compression_model = load_compression_model(
                    "facebook/audiogen-medium", device=codec_device
                )
            gc.collect()

            with monitor_phase(
                f"Building T5 conditioner and AudioGen language model on {device}", interval=10
            ):
                lm = load_lm_model("facebook/audiogen-medium", device=device)
            gc.collect()

            with monitor_phase("Finalizing AudioGen runtime", interval=5):
                _model = AudioGen("facebook/audiogen-medium", compression_model, lm)
    if device == "mps":
        emit("status", message="EnCodec is on CPU; AudioGen language model is on MPS.")
    emit(
        "status",
        message=(
            f"AudioGen ready on {device}: {getattr(_model, 'sample_rate', '?')} Hz, "
            f"{getattr(_model, 'audio_channels', '?')} channel(s)."
        ),
    )
    return _model


def generate(request: dict[str, Any]) -> str:
    import soundfile as sf

    model = _load_model()
    duration = float(request.get("duration", 5.0))
    device_type = getattr(model.device, "type", str(model.device))
    two_step_cfg = device_type == "mps"
    model.set_generation_params(
        duration=duration,
        top_k=int(request.get("top_k", 250)),
        temperature=float(request.get("temperature", 1.0)),
        two_step_cfg=two_step_cfg,
    )
    prompt = str(request["prompt"])
    emit(
        "status",
        message=(
            f"Generation settings: duration={duration:g}s, "
            f"temperature={float(request.get('temperature', 1.0)):g}, "
            f"top_k={int(request.get('top_k', 250))}, "
            f"memory_efficient_cfg={'on' if two_step_cfg else 'off'}."
        ),
    )
    emit("status", message=f"Conditioning on prompt: {prompt[:160]}")

    last_progress = {"percent": -5, "time": 0.0}

    def report_progress(generated_tokens: int, tokens_to_generate: int) -> None:
        if not tokens_to_generate:
            return
        percent = min(int(generated_tokens / tokens_to_generate * 100), 100)
        now = time.monotonic()
        if percent >= last_progress["percent"] + 5 or now - last_progress["time"] >= 5:
            last_progress.update(percent=percent, time=now)
            emit(
                "status",
                message=(
                    f"Generating audio tokens: {generated_tokens}/{tokens_to_generate} "
                    f"({percent}%)."
                ),
            )
            emit("progress", value=percent, label="Generating audio")

    model.set_custom_progress_callback(report_progress)
    try:
        with monitor_phase(f"Rendering {duration:g}s sound effect", interval=10):
            emit("progress", value=0, label="Generating audio")
            waveform = model.generate([prompt], progress=True)[0]
    finally:
        model.set_custom_progress_callback(None)
    emit("progress", value=100, label="Generating audio")
    emit(
        "status",
        message=f"Waveform decoded: shape={tuple(waveform.shape)}; moving audio to CPU.",
    )
    audio = waveform.detach().cpu().float().numpy().T
    emit(
        "status",
        message=f"Preparing {model.sample_rate} Hz WAV preview…",
    )
    sf.write(request["output_path"], audio, model.sample_rate)
    emit("status", message="Sound effect ready for preview.")
    return request["output_path"]


if __name__ == "__main__":
    run_worker(generate)
