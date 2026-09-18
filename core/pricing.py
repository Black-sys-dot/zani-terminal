"""
Model rate lookup, fetched once and then cached on disk.

The rule here is deliberate: a rate is fetched only when we have never seen the
model before. Once `.zani/pricing.json` holds an entry it is trusted forever and
no network call is made, so switching models costs one request and running the
agent costs none. Change the model in settings.yaml and the new id simply misses
the cache; call `refresh` to force a re-fetch of one you already have.

OpenRouter's model list is public and unauthenticated, so this never spends the
API key and never counts against a quota.

Rates are dollars per token, taken verbatim from the API.
"""

import json
import os
from datetime import datetime, timezone

import requests

MODELS_URL = "https://openrouter.ai/api/v1/models"
FETCH_TIMEOUT = 10


def _cache_path(project_path):
    return os.path.join(project_path, ".zani", "pricing.json")


def _load_cache(project_path):
    try:
        with open(_cache_path(project_path), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(project_path, cache):
    path = _cache_path(project_path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except OSError:
        # A read-only workspace must not take the TUI down; we just re-fetch
        # next launch.
        pass


def _fetch(model_id):
    """One public request. Returns None on any failure — pricing is optional."""
    try:
        resp = requests.get(MODELS_URL, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        entries = resp.json().get("data", [])
    except Exception:
        return None

    for entry in entries:
        if entry.get("id") != model_id:
            continue
        pricing = entry.get("pricing") or {}
        try:
            return {
                "prompt": float(pricing.get("prompt", 0) or 0),
                "completion": float(pricing.get("completion", 0) or 0),
                "context_length": entry.get("context_length"),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except (TypeError, ValueError):
            return None
    return None


def get_rates(project_path, model_id, refresh=False):
    """
    Cached rate lookup. Hits the network only on a cache miss, or when `refresh`
    is set. Returns None when the model is unknown to OpenRouter — direct Google
    ids will land here, and callers should render an unpriced session rather
    than guessing a number.
    """
    cache = _load_cache(project_path)

    if not refresh and model_id in cache:
        return cache[model_id]

    rates = _fetch(model_id)
    if rates is None:
        return cache.get(model_id)

    cache[model_id] = rates
    _save_cache(project_path, cache)
    return rates


def cost_of(rates, input_tokens, output_tokens):
    """Dollar cost for a token pair. Returns None when rates are unavailable."""
    if not rates:
        return None
    return input_tokens * rates.get("prompt", 0) + output_tokens * rates.get("completion", 0)


def format_cost(value):
    if value is None:
        return "—"
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"
