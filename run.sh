#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="$PROJECT_DIR/scripts/setup.sh"
MODE="${1:-run}"

if [[ "$MODE" != "run" && "$MODE" != "--setup-only" ]]; then
  echo "Usage: $0 [--setup-only]" >&2
  exit 1
fi

cd "$PROJECT_DIR"

find_compatible_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 12) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$PYTHON_BIN"
      return 0
    fi
    echo "PYTHON_BIN must point to Python 3.10 or 3.11." >&2
    return 1
  fi

  local candidate
  for candidate in python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 12) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "Python 3.10 or 3.11 is required. Install it and run this launcher again." >&2
  return 1
}

BASE_PYTHON="$(find_compatible_python)"
echo "Using $BASE_PYTHON to verify local environments."

if ! .venv/bin/python -c 'import PyQt6, audio_playground' >/dev/null 2>&1; then
  echo "PyQt environment is missing or incomplete; setting it up now."
  PYTHON_BIN="$BASE_PYTHON" "$SETUP_SCRIPT" ui
fi

if ! .venv-omnivoice/bin/python -c \
  'import importlib.util as u; raise SystemExit(0 if all(u.find_spec(x) for x in ("torch", "torchaudio", "omnivoice", "soundfile", "audio_playground")) else 1)' \
  >/dev/null 2>&1; then
  echo "OmniVoice environment is missing or incomplete; setting it up now."
  PYTHON_BIN="$BASE_PYTHON" "$SETUP_SCRIPT" omnivoice
fi

if ! .venv-sfx/bin/python -c \
  'import importlib.util as u; raise SystemExit(0 if all(u.find_spec(x) for x in ("torch", "diffusers", "transformers", "soundfile", "audio_playground")) else 1)' \
  >/dev/null 2>&1; then
  echo "AudioLDM environment is missing or incomplete; setting it up now."
  PYTHON_BIN="$BASE_PYTHON" "$SETUP_SCRIPT" sfx
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg is not installed; some audio operations may fail." >&2
fi

if [[ "$MODE" == "--setup-only" ]]; then
  echo "All environments are ready."
  exit 0
fi

echo "Starting AI Audio Playground…"
exec .venv/bin/python -m audio_playground
