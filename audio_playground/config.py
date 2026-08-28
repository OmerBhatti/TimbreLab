from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("AUDIO_PLAYGROUND_OUTPUT_DIR", PROJECT_ROOT / "outputs"))
LOGO_PATH = PROJECT_ROOT / "assets" / "timbrelab-logo.png"
APP_ICON_PATH = PROJECT_ROOT / "assets" / "timbrelab-icon.png"
DEFAULT_GENERATION_SEED = 9999
PRODUCT_NAME = "TimbreLab"


def worker_python(environment_name: str) -> Path:
    executable = "python.exe" if os.name == "nt" else "bin/python"
    return PROJECT_ROOT / environment_name / executable


OMNIVOICE_PYTHON = Path(
    os.environ.get("OMNIVOICE_PYTHON", worker_python(".venv-omnivoice"))
)
SFX_PYTHON = Path(os.environ.get("SFX_PYTHON", worker_python(".venv-sfx")))
