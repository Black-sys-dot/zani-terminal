"""
Fetch chat model ids from the active provider and persist the user's choice per project.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import requests

from google import genai

MODELS_URL = "https://openrouter.ai/api/v1/models"
FETCH_TIMEOUT = 15


@dataclass(frozen=True)
class ModelChoice:
    id: str
    label: str = ""


def _model_path(project_path: str) -> str:
    return os.path.join(project_path, ".zani", "model.json")


def _read_model_file(project_path: str) -> dict:
    try:
        with open(_model_path(project_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def load_project_model(project_path: str) -> str | None:
    data = _read_model_file(project_path)
    model = (data.get("model") or "").strip()
    return model or None


def load_project_model_state(project_path: str) -> dict:
    data = _read_model_file(project_path)
    return {
        "model": (data.get("model") or "").strip(),
        "text_model": (data.get("text_model") or data.get("model") or "").strip(),
        "tas_enabled": bool(data.get("tas_enabled")),
        "tas_voice": (data.get("tas_voice") or "").strip(),
    }


def save_project_model(project_path: str, model_id: str, **extra) -> None:
    path = _model_path(project_path)
    data = _read_model_file(project_path)
    data["model"] = model_id
    for key, value in extra.items():
        data[key] = value
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def list_openrouter_models(api_key: str | None = None) -> list[ModelChoice]:
    headers = {
        "HTTP-Referer": "https://github.com/Black-sys-dot/zani-terminal",
        "X-Title": "Zani Terminal",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.get(MODELS_URL, headers=headers, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    rows = resp.json().get("data") or []
    choices: list[ModelChoice] = []
    for row in rows:
        mid = (row.get("id") or "").strip()
        if not mid:
            continue
        name = (row.get("name") or mid).strip()
        choices.append(ModelChoice(id=mid, label=name))
    choices.sort(key=lambda c: c.id.lower())
    return choices


def list_google_models(api_key: str) -> list[ModelChoice]:
    client = genai.Client(api_key=api_key)
    choices: list[ModelChoice] = []
    for model in client.models.list():
        raw = getattr(model, "name", None) or ""
        if not raw:
            continue
        if "/models/" in raw:
            mid = raw.split("/models/")[-1]
        else:
            mid = raw.split("/")[-1]
        if not mid:
            continue
        display = getattr(model, "display_name", None) or mid
        choices.append(ModelChoice(id=mid, label=str(display)))
    # Prefer Gemini chat models; drop obvious non-chat entries.
    filtered = [c for c in choices if "gemini" in c.id.lower() or "gemma" in c.id.lower()]
    use = filtered if filtered else choices
    use.sort(key=lambda c: c.id.lower())
    return use


def list_models(provider: str, api_key: str) -> list[ModelChoice]:
    provider = (provider or "google").lower()
    if provider == "openrouter":
        return list_openrouter_models(api_key)
    if not api_key:
        raise ValueError("API key required to list Google models.")
    return list_google_models(api_key)


def resolve_model_id(query: str, choices: list[ModelChoice]) -> str | None:
    q = query.strip()
    if not q:
        return None
    ids = [c.id for c in choices]
    if q in ids:
        return q
    lower = q.lower()
    exact_ci = [c.id for c in choices if c.id.lower() == lower]
    if len(exact_ci) == 1:
        return exact_ci[0]
    prefix = [c.id for c in choices if c.id.lower().startswith(lower)]
    if len(prefix) == 1:
        return prefix[0]
    contains = [c.id for c in choices if lower in c.id.lower()]
    if len(contains) == 1:
        return contains[0]
    return None
