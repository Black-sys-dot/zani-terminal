from datetime import datetime, timezone, timedelta


# ---- Gemini 3 Flash pricing ----
STANDARD_INPUT_PER_M = 0.50
CACHE_HIT_PER_M = 0.05
CACHE_STORAGE_PER_M_PER_HR = 1.00


def estimate_cache_write_cost(tokens):
    return (tokens / 1_000_000) * STANDARD_INPUT_PER_M


def estimate_cache_storage_cost(tokens, ttl_hours):
    return (tokens / 1_000_000) * CACHE_STORAGE_PER_M_PER_HR * ttl_hours


def rebake_decision(
    percent,
    tokens,
    added,
    modified,
    deleted,
    config,
    registry_expired
):
    if registry_expired:
        return "force", "cache expired"

    critical = set(config.get("critical_files", []))
    if critical.intersection(set(added + modified + deleted)):
        return "force", "critical file changed"

    if percent >= config["force_percent"]:
        return "force", f"project changed {percent:.2f}%"

    if tokens >= config["force_tokens"]:
        return "force", f"{tokens} tokens changed"

    if percent >= config["recommend_percent"]:
        return "recommend", f"project changed {percent:.2f}%"

    if tokens >= config["recommend_tokens"]:
        return "recommend", f"{tokens} tokens changed"

    return "keep", None


def compute_expiry(ttl_hours):
    return (
        datetime.now(timezone.utc)
        + timedelta(hours=ttl_hours)
    ).isoformat()
