from __future__ import annotations

import inspect
from typing import Any

from audio_playground.workers.common import emit, monitor_model_download, monitor_phase, run_worker

MODEL_ID = "cvssp/audioldm-s-full-v2"
MODEL_REPO_SIZE = 1_685_000_000

_pipeline: Any = None
_device = "cpu"


def _select_device(torch: Any) -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _select_dtype(torch: Any, device: str) -> Any:
    # AudioLDM's vocoder can collapse to all-zero output with float16 on MPS.
    # CUDA supports the lower-precision path reliably; MPS and CPU use float32.
    return torch.float16 if device == "cuda" else torch.float32


def _clamp_duration(value: Any) -> float:
    return max(1.0, min(float(value), 30.0))


def _load_pipeline() -> Any:
    global _device, _pipeline
    if _pipeline is not None:
        return _pipeline

    with monitor_phase("Importing AudioLDM, Diffusers, and PyTorch", interval=5):
        import torch
        from diffusers import AudioLDMPipeline

    _device = _select_device(torch)
    dtype = _select_dtype(torch, _device)
    emit(
        "status",
        message=(
            f"Runtime ready: PyTorch {torch.__version__}; selected device: {_device}; "
            f"precision: {dtype}."
        ),
    )
    emit("status", message=f"Preparing lightweight AudioLDM model {MODEL_ID}…")
    with monitor_model_download(MODEL_ID, MODEL_REPO_SIZE):
        _pipeline = AudioLDMPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
            use_safetensors=True,
        )
    with monitor_phase(f"Moving AudioLDM pipeline to {_device}", interval=5):
        _pipeline = _pipeline.to(_device)
        if _device == "mps":
            _pipeline.enable_attention_slicing()
    emit("status", message=f"AudioLDM ready on {_device}.")
    return _pipeline


def _progress_kwargs(pipeline: Any, total_steps: int) -> dict[str, Any]:
    parameters = inspect.signature(pipeline.__call__).parameters

    def report(step: int) -> None:
        percent = min(round((step + 1) / max(total_steps, 1) * 100), 100)
        emit(
            "status",
            message=f"Generating sound effect: diffusion step {step + 1}/{total_steps} ({percent}%).",
        )
        emit("progress", value=percent, label="Generating audio")

    if "callback_on_step_end" in parameters:
        def callback_on_step_end(_pipe: Any, step: int, _timestep: Any, callback_kwargs: Any):
            report(step)
            return callback_kwargs

        return {"callback_on_step_end": callback_on_step_end}

    if "callback" in parameters:
        def callback(step: int, _timestep: Any, _latents: Any) -> None:
            report(step)

        return {"callback": callback, "callback_steps": 1}

    return {}


def generate(request: dict[str, Any]) -> str:
    import numpy as np
    import soundfile as sf

    pipeline = _load_pipeline()
    prompt = str(request["prompt"])
    duration = _clamp_duration(request.get("duration", 5.0))
    guidance = float(request.get("guidance", 2.5))
    inference_steps = int(request.get("inference_steps", 25))
    emit(
        "status",
        message=(
            f"Generation settings: duration={duration:g}s, guidance={guidance:g}, "
            f"diffusion_steps={inference_steps}."
        ),
    )
    emit("status", message=f"Conditioning on prompt: {prompt[:160]}")
    emit("progress", value=0, label="Generating audio")
    kwargs = _progress_kwargs(pipeline, inference_steps)
    with monitor_phase(f"Rendering {duration:g}s sound effect", interval=10):
        result = pipeline(
            prompt,
            audio_length_in_s=duration,
            guidance_scale=guidance,
            num_inference_steps=inference_steps,
            **kwargs,
        )
    emit("progress", value=100, label="Generating audio")

    audio = np.asarray(result.audios[0], dtype=np.float32).squeeze()
    if audio.ndim != 1:
        raise RuntimeError(f"AudioLDM returned an unexpected audio shape: {audio.shape}.")
    if not np.isfinite(audio).all():
        raise RuntimeError("AudioLDM returned invalid samples. Restart the SFX worker and try again.")

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    emit("status", message=f"Waveform check: peak={peak:.4f}, RMS={rms:.4f}.")
    if peak < 1e-5:
        raise RuntimeError(
            "AudioLDM produced a silent waveform. Restart the app to reload the model "
            "with float32 precision."
        )

    sample_rate = int(getattr(pipeline.vocoder.config, "sampling_rate", 16000))
    emit("status", message=f"Preparing {sample_rate} Hz WAV preview…")
    sf.write(request["output_path"], audio, sample_rate)
    emit("status", message="Sound effect ready for preview.")
    return request["output_path"]


if __name__ == "__main__":
    run_worker(generate)
