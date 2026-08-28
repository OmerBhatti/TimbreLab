#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
COMPONENT="${1:-all}"

is_compatible_python() {
  "$1" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 12) else 1)' \
    >/dev/null 2>&1
}

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && is_compatible_python "$candidate"; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [[ "$COMPONENT" != "all" && "$COMPONENT" != "ui" && "$COMPONENT" != "omnivoice" && "$COMPONENT" != "audiocraft" ]]; then
  echo "Usage: $0 [all|ui|omnivoice|audiocraft]"
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || ! is_compatible_python "$PYTHON_BIN"; then
  echo "Python 3.10 or 3.11 is required. Install it or set PYTHON_BIN to its executable."
  exit 1
fi

echo "Using $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

cd "$PROJECT_DIR"

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "ui" ]]; then
  echo "[1/3] Creating the PyQt application environment"
  "$PYTHON_BIN" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/python -m pip install -e '.[dev]'
fi

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "omnivoice" ]]; then
  echo "[2/3] Creating the OmniVoice environment"
  "$PYTHON_BIN" -m venv .venv-omnivoice
  .venv-omnivoice/bin/python -m pip install --upgrade pip setuptools wheel
  .venv-omnivoice/bin/python -m pip install torch==2.8.0 torchaudio==2.8.0
  .venv-omnivoice/bin/python -m pip install omnivoice
  .venv-omnivoice/bin/python -m pip install --no-deps -e .
fi

if [[ "$COMPONENT" == "all" || "$COMPONENT" == "audiocraft" ]]; then
  echo "[3/3] Creating the AudioCraft environment"
  "$PYTHON_BIN" -m venv .venv-audiocraft
  .venv-audiocraft/bin/python -m pip install --upgrade pip setuptools wheel
  .venv-audiocraft/bin/python -m pip install \
    'numpy<2' torch==2.1.0 torchaudio==2.1.0 torchvision==0.16.0 \
    transformers==4.44.2

  if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
    # AudioCraft declares xformers, but xformers has no supported Apple Silicon wheel.
    .venv-audiocraft/bin/python -m pip install audiocraft --no-deps
    .venv-audiocraft/bin/python -m pip install \
      'av>=12' einops 'flashy>=0.0.1' 'hydra-core>=1.1' hydra-colorlog \
      julius num2words sentencepiece spacy==3.7.6 huggingface-hub tqdm demucs \
      librosa soundfile torchmetrics encodec protobuf torchdiffeq click
  else
    .venv-audiocraft/bin/python -m pip install audiocraft
  fi
  .venv-audiocraft/bin/python -m pip install --no-deps -e .
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg is not installed. AudioCraft may need it for some audio operations."
fi

echo
echo "Setup complete. Start the app with:"
echo "  .venv/bin/python -m audio_playground"
