from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("AUDIO_PLAYGROUND_OUTPUT_DIR", PROJECT_ROOT / "outputs"))


def worker_python(environment_name: str) -> Path:
    executable = "python.exe" if os.name == "nt" else "bin/python"
    return PROJECT_ROOT / environment_name / executable


OMNIVOICE_PYTHON = Path(
    os.environ.get("OMNIVOICE_PYTHON", worker_python(".venv-omnivoice"))
)
AUDIOCRAFT_PYTHON = Path(
    os.environ.get("AUDIOCRAFT_PYTHON", worker_python(".venv-audiocraft"))
)

