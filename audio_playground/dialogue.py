from __future__ import annotations

from typing import Any


def parse_dialogue(script: str) -> list[tuple[str, str]]:
    """Parse non-empty `Speaker: dialogue` lines while preserving their order."""
    lines: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(script.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        speaker, separator, text = line.partition(":")
        speaker = speaker.strip()
        text = text.strip()
        if not separator or not speaker or not text:
            raise ValueError(
                f"Line {line_number} must use the format `Speaker: dialogue`."
            )
        lines.append((speaker, text))
    if not lines:
        raise ValueError("Write at least one dialogue line using `Speaker: dialogue`.")
    return lines


def voice_instruction_from_preset(config: dict[str, Any]) -> str:
    style = str(config.get("style", "")).lower()
    style_instruction = "whisper" if style in {"whisper", "whispering"} else ""
    return ", ".join(
        str(value)
        for value in (
            config.get("gender", ""),
            config.get("age", ""),
            config.get("pitch", ""),
            config.get("accent", ""),
            style_instruction,
        )
        if value
    )
