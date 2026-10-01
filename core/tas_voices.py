"""OpenRouter / OpenAI-style voices for TaS chat audio output."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TAS_VOICE = "shimmer"

# OpenRouter streaming audio requires stream=true; OpenAI rejects mp3 there.
TAS_STREAM_AUDIO_FORMAT = "pcm16"
TAS_PCM_SAMPLE_RATE = 24000
TAS_PCM_CHANNELS = 1

# Curated for a natural young-adult female tone; providers ignore unknown voices.
TAS_VOICE_CHOICES: tuple[tuple[str, str], ...] = (
    ("shimmer", "Shimmer — warm young adult woman (default)"),
    ("nova", "Nova — bright young adult woman"),
    ("coral", "Coral — conversational woman"),
    ("sage", "Sage — calm young woman"),
    ("fable", "Fable — soft, expressive"),
)


@dataclass(frozen=True)
class TasVoice:
    id: str
    label: str


def list_tas_voices() -> list[TasVoice]:
    return [TasVoice(v, label) for v, label in TAS_VOICE_CHOICES]


def normalize_voice(voice: str | None) -> str:
    v = (voice or "").strip().lower()
    ids = {x.id for x in list_tas_voices()}
    if v in ids:
        return v
    return DEFAULT_TAS_VOICE
