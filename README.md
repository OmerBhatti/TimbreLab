# AI Audio Playground

A local PyQt desktop app with two independently loaded AI audio engines:

- **OmniVoice** for multilingual TTS, voice design, and supported expressive tags.
- **AudioCraft AudioGen** for prompt-based sound effects and environmental audio.

The engines use separate Python environments because their official PyTorch requirements conflict. They run as persistent background workers, so the UI stays responsive and each model is loaded only once per session.

## Requirements

- Python 3.10 or 3.11 (3.11 is recommended)
- `ffmpeg`
- Plenty of free disk space for Python packages and downloaded model weights
- A capable GPU, or an Apple Silicon Mac with ample unified memory, is strongly recommended

AudioGen Medium is a 1.5B-parameter model and its official documentation recommends a GPU with at least 16 GB of memory. CPU generation can be very slow.

The `facebook/audiogen-medium` checkpoint is published under CC-BY-NC 4.0. Review that license before using generated assets in commercial work.

## Automatic setup and launch

On macOS or Linux, use the self-bootstrapping launcher:

```bash
chmod +x run.sh scripts/setup.sh
./run.sh
```

It automatically finds Python 3.11 or 3.10, checks all three environments,
installs only missing or incomplete components, and starts the app with the
correct interpreter. Subsequent launches skip setup and start immediately.

To prepare or verify the environments without opening the UI:

```bash
./run.sh --setup-only
```

## Manual install

On macOS or Linux:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

If a slow download is interrupted, resume just that environment with
`./scripts/setup.sh omnivoice` or `./scripts/setup.sh audiocraft`.

To select a different compatible Python executable for either launcher:

```bash
PYTHON_BIN=/path/to/python3.11 ./scripts/setup.sh
```

Or launch with automatic environment checks:

```bash
PYTHON_BIN=/path/to/python3.11 ./run.sh
```

The setup creates three local environments: `.venv` for PyQt, `.venv-omnivoice` for speech, and `.venv-audiocraft` for sound effects.

## Run

```bash
.venv/bin/python -m audio_playground
```

The first generation with either engine downloads its pretrained weights. Progress messages appear at the bottom of the window. Generated WAV files are temporary previews until **Download audio** is pressed.

## Emotional TTS controls

OmniVoice supports a defined set of inline expressive cues rather than an arbitrary emotion-strength parameter. Insert friendly tags such as `[happy]`, `[sad]`, `[surprised]`, `[questioning]`, and `[dissatisfied]` anywhere in the dialogue. The app translates each tag in place to the closest supported OmniVoice cue, such as `[laughter]` or `[sigh]`; these are expressive/non-verbal cues rather than precise emotion-intensity controls. Native OmniVoice tags can also be typed directly. Voice design supports gender, age, pitch, accent, and normal or whispering delivery. OmniVoice rejects arbitrary style descriptions, so broader expression should be controlled with inline cues.

Voice configurations can be saved under a custom name and reapplied from the
**Voice preset** dropdown. Presets include voice mode, design attributes,
speaking speed, and diffusion steps.

## Configuration

Worker interpreters and the output directory can be overridden:

```bash
OMNIVOICE_PYTHON=/path/to/python \
AUDIOCRAFT_PYTHON=/path/to/python \
AUDIO_PLAYGROUND_OUTPUT_DIR=/path/to/outputs \
.venv/bin/python -m audio_playground
```

## Tests

```bash
.venv/bin/pytest
```

The tests cover request-independent utility behavior. Full model generation is an integration check because it requires multi-gigabyte model downloads and suitable hardware.

## Common issues

- **Worker environment not found:** run `./scripts/setup.sh` from the project directory.
- **Out of memory:** close other GPU-heavy applications, shorten SFX duration, then restart the app to unload and reload workers.
- **AudioCraft installation on Apple Silicon:** the setup skips `xformers`, which is a CUDA optimization, and uses a newer binary PyAV wheel because AudioCraft's old PyAV pin requires native build tools.
- **Slow first generation:** both workers download weights on first use and cache them through Hugging Face.
- **Download remains at `0/N`:** the outer Hugging Face counter only advances after a complete model blob finishes. The live log reports cached bytes and transfer activity instead. The app disables the Xet downloader so interrupted downloads resume through standard HTTP. Supplying an optional `HF_TOKEN` environment variable may improve Hugging Face rate limits.
- **AudioCraft appears idle:** the live log emits timed heartbeats for imports, model preparation, token-generation percentages, waveform decoding, CPU transfer, and WAV writing. A download with no cache growth for two minutes is explicitly labeled as a possible stall.
