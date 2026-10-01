"""OpenRouter models that can return text and audio in one chat completion."""

from __future__ import annotations

import requests

from core.model_catalog import MODELS_URL, FETCH_TIMEOUT, ModelChoice

# OpenRouter: audio output is streamed via chat/completions + modalities.


def _output_modalities(row: dict) -> list[str]:
    arch = row.get("architecture") or {}
    mods = arch.get("output_modalities") or row.get("output_modalities") or []
    if isinstance(mods, str):
        return [mods]
    return [str(m).lower() for m in mods]


def list_tas_models(api_key: str) -> list[ModelChoice]:
    if not api_key:
        return []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/Black-sys-dot/zani-terminal",
        "X-Title": "Zani Terminal",
    }
    resp = requests.get(
        f"{MODELS_URL}?output_modalities=audio",
        headers=headers,
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json().get("data") or []
    choices: list[ModelChoice] = []
    for row in rows:
        mid = (row.get("id") or "").strip()
        if not mid:
            continue
        outs = _output_modalities(row)
        if "audio" not in outs or "text" not in outs:
            continue
        name = (row.get("name") or mid).strip()
        choices.append(ModelChoice(id=mid, label=name))
    choices.sort(key=lambda c: c.id.lower())
    return choices
