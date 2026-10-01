"""TaS runtime helpers (what the API actually uses vs what the UI shows)."""

from __future__ import annotations

from core import audio_playback


def api_model_name(brain) -> str:
    if getattr(brain, "tas_enabled", False) and not audio_playback.playback_ready():
        return getattr(brain, "text_model_fallback", None) or brain.model_name
    return brain.model_name


def tas_status_label(brain) -> str:
    if not getattr(brain, "tas_enabled", False):
        return "off"
    voice = getattr(brain, "tas_voice", "shimmer")
    if audio_playback.playback_ready():
        return f"on ({voice}) live"
    return f"on ({voice}) muted"
