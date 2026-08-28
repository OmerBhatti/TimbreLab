# AI Audio Playground

A local PyQt desktop app with two independently loaded AI audio engines:

- **OmniVoice** for multilingual TTS, voice design, and supported expressive tags.
- **AudioLDM Small v2** for prompt-based sound effects and environmental audio.

The engines use separate Python environments because their official PyTorch requirements conflict. They run as persistent background workers, so the UI stays responsive and each model is loaded only once per session. Sound-effect generation is handled by a Diffusers-based AudioLDM worker.

## Requirements

- Python 3.10 or 3.11 (3.11 is recommended)
- `ffmpeg`
- Plenty of free disk space for Python packages and downloaded model weights
- A capable GPU, or an Apple Silicon Mac with ample unified memory, is strongly recommended

AudioLDM Small v2 is a 421M-parameter latent diffusion model. It runs through
PyTorch MPS on Apple Silicon and downloads about 1.7 GB of model files.

The `cvssp/audioldm-s-full-v2` checkpoint is published under CC-BY-NC-SA 4.0.
Review that license before using generated assets in commercial work.

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
`./scripts/setup.sh omnivoice` or `./scripts/setup.sh sfx`.

To select a different compatible Python executable for either launcher:

```bash
PYTHON_BIN=/path/to/python3.11 ./scripts/setup.sh
```

Or launch with automatic environment checks:

```bash
PYTHON_BIN=/path/to/python3.11 ./run.sh
```

The setup creates three local environments:

| Environment | Purpose |
| --- | --- |
| `.venv` | PyQt desktop application and tests |
| `.venv-omnivoice` | OmniVoice speech generation |
| `.venv-sfx` | AudioLDM sound-effect generation |

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

## Sound-effect controls

Open **SFX & Effects**, describe the sound, and select **Generate sound effect**.
AudioLDM accepts descriptive prompts such as:

> A cinematic thunder crack followed by heavy rain on a metal rooftop,
> realistic, no music

- **Duration** controls the generated clip length from 1 to 10 seconds.
- **Prompt guidance** controls how strongly the result follows the description.
  The default of 2.5 is a useful starting point; high values may reduce variety.
- **Diffusion steps** trade speed for refinement. Start with 25 and increase only
  when the extra generation time is worthwhile.

The first SFX request downloads approximately 1.7 GB of AudioLDM weights. The
worker then stays loaded for later requests during the same app session. The log
panel reports download activity, model-loading heartbeats, and diffusion-step
progress. **Stop** is shown only while a worker is active.

## Configuration

Worker interpreters and the output directory can be overridden:

```bash
OMNIVOICE_PYTHON=/path/to/python \
SFX_PYTHON=/path/to/python \
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
- **AudioLDM on Apple Silicon:** the worker uses PyTorch MPS with float32 precision and attention slicing. Float16 is intentionally limited to CUDA because it can produce silent AudioLDM waveforms on MPS.
- **Slow first generation:** both workers download weights on first use and cache them through Hugging Face.
- **Download remains at `0/N`:** the outer Hugging Face counter only advances after a complete model blob finishes. The live log reports cached bytes and transfer activity instead. The app disables the Xet downloader so interrupted downloads resume through standard HTTP. Supplying an optional `HF_TOKEN` environment variable may improve Hugging Face rate limits.
- **AudioLDM appears idle:** the live log emits timed heartbeats for imports, model preparation, diffusion-step percentages, and WAV writing. A download with no cache growth for two minutes is explicitly labeled as a possible stall.
