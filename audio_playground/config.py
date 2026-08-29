from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("AUDIO_PLAYGROUND_OUTPUT_DIR", PROJECT_ROOT / "outputs"))
VOICE_LIBRARY_DIR = Path(
    os.environ.get("AUDIO_PLAYGROUND_VOICE_DIR", PROJECT_ROOT / "voices")
)
LOGO_PATH = PROJECT_ROOT / "assets" / "timbrelab-logo.png"
APP_ICON_PATH = PROJECT_ROOT / "assets" / "timbrelab-icon.png"
ICON_DIR = PROJECT_ROOT / "assets" / "icons"
WINDOW_BACKGROUND = "#10131a"
WINDOW_BACKGROUND_RGB = (0x10 / 255, 0x13 / 255, 0x1a / 255)
DEFAULT_GENERATION_SEED = 99999
PRODUCT_NAME = "TimbreLab"
VENDOR_NAME = "TensorPeak Labs"
VENDOR_URL = "https://timbrelab.tensorpeak.org"


def worker_python(environment_name: str) -> Path:
    executable = "python.exe" if os.name == "nt" else "bin/python"
    return PROJECT_ROOT / environment_name / executable


OMNIVOICE_PYTHON = Path(
    os.environ.get("OMNIVOICE_PYTHON", worker_python(".venv-omnivoice"))
)
SFX_PYTHON = Path(os.environ.get("SFX_PYTHON", worker_python(".venv-sfx")))
