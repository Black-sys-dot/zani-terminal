import os
import datetime
import json
import yaml

class CacheManager:
    def __init__(self, config_path="config/settings.yaml"):
        self.registry_path = ".zani/registry.json"
        # 4 chars per token (2026 standard for code-heavy context)
        self.token_ratio = 4 

    def estimate_tokens(self, file_list):
        total_chars = 0
        for path in file_list:
            if os.path.exists(path):
                total_chars += os.path.getsize(path)
        return total_chars // self.token_ratio

    def calculate_cost(self, tokens):
        # 2026 Storage Price: $1.00 per 1M tokens per hour
        return round((tokens / 1_000_000) * 1.0, 4)

    def save_cache_state(self, cache_id, token_count, ttl_hours):
        expires_at = (datetime.datetime.now() + datetime.timedelta(hours=ttl_hours)).isoformat()
        state = {
            "active_cache_id": cache_id,
            "token_count": token_count,
            "expires_at": expires_at
        }
        with open(self.registry_path, "w") as f:
            json.dump(state, f, indent=4)