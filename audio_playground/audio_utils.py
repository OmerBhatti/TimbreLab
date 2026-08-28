from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


INLINE_EMOTION_TAGS = {
    "[happy]": "[laughter]",
    "[sad]": "[sigh]",
    "[surprised]": "[surprise-oh]",
    "[questioning]": "[question-en]",
    "[dissatisfied]": "[dissatisfaction-hnn]",
}

OMNIVOICE_NONVERBAL_TAGS = (
    "[laughter]",
    "[sigh]",
    "[confirmation-en]",
    "[question-en]",
    "[question-ah]",
    "[question-oh]",
    "[question-ei]",
    "[question-yi]",
    "[surprise-ah]",
    "[surprise-oh]",
    "[surprise-wa]",
    "[surprise-yo]",
    "[dissatisfaction-hnn]",
)


def normalize_emotion_tags(text: str) -> str:
    """Translate friendly inline emotion tags to OmniVoice-supported cues."""
    normalized = text.strip()
    for friendly_tag, omnivoice_tag in INLINE_EMOTION_TAGS.items():
        normalized = re.sub(
            re.escape(friendly_tag), omnivoice_tag, normalized, flags=re.IGNORECASE
        )
    return normalized


def output_path(output_dir: Path, kind: str, hint: str = "") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_hint = re.sub(r"[^a-zA-Z0-9]+", "-", hint.lower()).strip("-")[:28]
    parts = [kind]
    if safe_hint:
        parts.append(safe_hint)
    parts.append(datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    return output_dir / f"{'-'.join(parts)}.wav"
