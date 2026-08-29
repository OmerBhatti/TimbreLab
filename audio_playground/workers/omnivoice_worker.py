from __future__ import annotations

import math
import os
import random
import re
from typing import Any

from audio_playground.config import DEFAULT_GENERATION_SEED
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


def _generation_kwargs(request: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "text": request["text"],
        "num_step": int(request.get("steps", 32)),
        "speed": float(request.get("speed", 1.0)),
    }
    mode = request.get("mode", "design")
    if mode == "clone":
        reference = str(request.get("ref_audio", "")).strip()
        transcript = str(request.get("ref_text", "")).strip()
        if not reference or not os.path.isfile(reference):
            raise ValueError(
                "This cloned voice is missing its reference recording. "
                "Re-select the audio file and save the preset again."
            )
        if not transcript:
            raise ValueError("A cloned voice needs the transcript of its reference audio.")
        kwargs["ref_audio"] = reference
        kwargs["ref_text"] = transcript
        return kwargs
    if mode == "design" and request.get("voice_instruction"):
        instruction, unsupported = _validated_voice_instruction(request["voice_instruction"])
        if unsupported:
            emit(
                "status",
                message=f"Ignoring unsupported voice style items: {', '.join(unsupported)}.",
            )
        if instruction:
            kwargs["instruct"] = instruction
    return kwargs


def _fade_dialogue_waveform(waveform: Any, sample_rate: int = 24000) -> Any:
    """Apply short edge fades so independently rendered turns join cleanly."""
    import numpy as np

    faded = np.asarray(waveform, dtype=np.float32).squeeze().copy()
    fade_samples = min(round(0.025 * sample_rate), len(faded) // 2)
    if fade_samples:
        faded[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        faded[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
    return faded


def _seed_random_generators(torch: Any, numpy: Any, seed: int) -> None:
    random.seed(seed)
    numpy.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


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
    import numpy as np
    import soundfile as sf
    import torch

    model = _load_model()
    seed = int(request.get("seed", DEFAULT_GENERATION_SEED))
    _seed_random_generators(torch, np, seed)
    dialogue_segments = request.get("segments")
    is_dialogue = isinstance(dialogue_segments, list)
    segments = dialogue_segments if is_dialogue else [request]
    if not segments:
        raise ValueError("Dialogue contains no lines to synthesize.")

    emit(
        "status",
        message=(
            f"Preparing {'dialogue' if is_dialogue else 'speech'} with {len(segments)} "
            f"line(s) · seed={seed}."
        ),
    )
    estimated_passes = sum(
        _estimated_forward_passes(str(segment["text"]), int(segment.get("steps", 32)))
        for segment in segments
    )
    completed_passes = 0

    def report_forward_pass(_module: Any, _inputs: Any, _output: Any) -> None:
        nonlocal completed_passes
        completed_passes += 1
        percent = min(round(completed_passes / estimated_passes * 95), 95)
        emit("progress", value=percent, label="Estimated speech")

    progress_hook = model.register_forward_hook(report_forward_pass)
    waveforms: list[Any] = []
    try:
        phase = "Synthesizing dialogue" if is_dialogue else "Synthesizing speech"
        with monitor_phase(phase, interval=10):
            emit("progress", value=0, label="Estimated speech")
            for index, segment in enumerate(segments, start=1):
                kwargs = _generation_kwargs(segment)
                speaker = str(segment.get("speaker", "Speech"))
                emit(
                    "status",
                    message=(
                        f"Synthesizing line {index}/{len(segments)} · {speaker} · "
                        f"steps={kwargs['num_step']} · speed={kwargs['speed']:g}."
                    ),
                )
                audio = model.generate(**kwargs)[0]
                if hasattr(audio, "detach"):
                    audio = audio.detach().float().cpu().numpy()
                waveform = np.asarray(audio, dtype=np.float32).squeeze()
                waveforms.append(
                    _fade_dialogue_waveform(waveform) if is_dialogue else waveform
                )
    finally:
        progress_hook.remove()
    emit("progress", value=100, label="Estimated speech")

    if is_dialogue and len(waveforms) > 1:
        leading_pad = np.zeros(round(0.2 * 24000), dtype=np.float32)
        pause = np.zeros(round(0.3 * 24000), dtype=np.float32)
        combined: list[Any] = [leading_pad]
        for index, waveform in enumerate(waveforms):
            if index:
                combined.append(pause)
            combined.append(waveform)
        output_audio = np.concatenate(combined)
    else:
        output_audio = waveforms[0]
    samples = len(output_audio)
    emit(
        "status",
        message=(
            f"{'Dialogue' if is_dialogue else 'Speech'} decoded: {samples} samples "
            f"({samples / 24000:.1f}s at 24000 Hz)."
        ),
    )
    emit("status", message="Preparing synthesized WAV preview…")
    sf.write(request["output_path"], output_audio, 24000)
    emit(
        "status",
        message=f"Synthesized {'dialogue' if is_dialogue else 'speech'} ready for preview.",
    )
    return request["output_path"]


if __name__ == "__main__":
    run_worker(generate)
