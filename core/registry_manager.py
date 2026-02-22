import json
import os
from datetime import datetime, timezone

REG_PATH = ".zani/registry.json"


class RegistryManager:

    def load(self):
        if not os.path.exists(REG_PATH):
            return None
        with open(REG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict):
        os.makedirs(".zani", exist_ok=True)
        with open(REG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def clear(self):
        if os.path.exists(REG_PATH):
            os.remove(REG_PATH)

    def is_expired(self, registry):
        expiry = registry.get("ttl_expiry")
        if not expiry:
            return False
        return datetime.now(timezone.utc).isoformat() > expiry
