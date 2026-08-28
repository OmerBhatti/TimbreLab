from __future__ import annotations

import math
import os
import re
from typing import Any

from audio_playground.workers.common import (
    emit,
    monitor_model_download,
    monitor_phase,
    run_worker,
)

_model: Any = None
OMNIVOICE_REPO_SIZE = 3_267_470_260
ENGLISH_INSTRUCT_ITEMS = {
    "american accent",
    "australian accent",
    "british accent",
    "canadian accent",
    "child",
    "chinese accent",
    "elderly",
    "female",
    "high pitch",
    "indian accent",
    "japanese accent",
    "korean accent",
    "low pitch",
    "male",
    "middle-aged",
    "moderate pitch",
    "portuguese accent",
    "russian accent",
    "teenager",
    "very high pitch",
    "very low pitch",
    "whisper",
    "young adult",
}


def _estimated_forward_passes(text: str, steps: int) -> int:
    spoken_text = re.sub(r"\[[^]]+\]", "", text)
    estimated_seconds = max(len(spoken_text.strip()) / 15, 1)
    chunks = 1 if estimated_seconds <= 30 else math.ceil(estimated_seconds / 15)
    return max(steps, 1) * chunks


def _validated_voice_instruction(instruction: str) -> tuple[str, list[str]]:
    items = [item.strip().lower() for item in instruction.split(",") if item.strip()]
    valid = [item for item in items if item in ENGLISH_INSTRUCT_ITEMS]
    unsupported = [item for item in items if item not in ENGLISH_INSTRUCT_ITEMS]
    return ", ".join(valid), unsupported


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    with monitor_phase("Importing OmniVoice and PyTorch", interval=5):
        import torch
        from omnivoice import OmniVoice

    if torch.cuda.is_available():
        device, dtype = "cuda:0", torch.float16
    elif torch.backends.mps.is_available():
        device, dtype = "mps", torch.float16
    else:
        device, dtype = "cpu", torch.float32
    emit(
        "status",
        message=f"Runtime ready: PyTorch {torch.__version__}; selected device: {device}.",
    )
    emit("status", message=f"Preparing k2-fsa/OmniVoice on {device}…")
    with monitor_model_download("k2-fsa/OmniVoice", OMNIVOICE_REPO_SIZE):
        _model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice", device_map=device, dtype=dtype
        )
    emit("status", message="OmniVoice model ready.")
    return _model


def generate(request: dict[str, Any]) -> str:
    import soundfile as sf

    model = _load_model()
    kwargs: dict[str, Any] = {
        "text": request["text"],
        "num_step": int(request.get("steps", 32)),
        "speed": float(request.get("speed", 1.0)),
    }
    mode = request.get("mode", "design")
    if mode == "design" and request.get("voice_instruction"):
        instruction, unsupported = _validated_voice_instruction(request["voice_instruction"])
        if unsupported:
            emit(
                "status",
                message=f"Ignoring unsupported voice style items: {', '.join(unsupported)}.",
            )
        if instruction:
            kwargs["instruct"] = instruction

    emit(
        "status",
        message=(
            f"Speech settings: mode={mode}, steps={kwargs['num_step']}, "
            f"speed={kwargs['speed']:g}, characters={len(request['text'])}."
        ),
    )
    estimated_passes = _estimated_forward_passes(request["text"], kwargs["num_step"])
    completed_passes = 0

    def report_forward_pass(_module: Any, _inputs: Any, _output: Any) -> None:
        nonlocal completed_passes
        completed_passes += 1
        percent = min(round(completed_passes / estimated_passes * 95), 95)
        emit("progress", value=percent, label="Estimated speech")

    progress_hook = model.register_forward_hook(report_forward_pass)
    try:
        with monitor_phase("Synthesizing speech", interval=10):
            emit("progress", value=0, label="Estimated speech")
            audio = model.generate(**kwargs)
    finally:
        progress_hook.remove()
    emit("progress", value=100, label="Estimated speech")
    samples = len(audio[0])
    emit(
        "status",
        message=f"Speech decoded: {samples} samples ({samples / 24000:.1f}s at 24000 Hz).",
    )
    emit("status", message="Preparing synthesized WAV preview…")
    sf.write(request["output_path"], audio[0], 24000)
    emit("status", message="Synthesized speech ready for preview.")
    return request["output_path"]


if __name__ == "__main__":
    run_worker(generate)
