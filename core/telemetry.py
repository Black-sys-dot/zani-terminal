"""
Live machine telemetry and persistent token accounting.

Two unrelated things live here because the gauges panel needs both: what the
host is doing right now (sampled, thrown away) and what this project has cost
over its lifetime (accumulated, written to disk).

The usage store is per-project and survives restarts, which makes it the first
piece of Zani state to outlive a session since the MCP rewrite. It lives in
`.zani/` alongside the pricing cache and is gitignored by the existing rules.
"""

import json
import os
from datetime import datetime, timezone

import psutil

# psutil's first cpu_percent call always reports 0.0 because it has no previous
# sample to diff against. Prime it at import so the first frame is truthful.
psutil.cpu_percent(interval=None)


# ==============================================================
# HOST SAMPLING
# ==============================================================
def sample_system():
    """
    One non-blocking snapshot. `interval=None` diffs against the previous call
    rather than sleeping, so this is safe to run on a UI timer.
    """
    try:
        cpu = psutil.cpu_percent(interval=None)
    except Exception:
        cpu = 0.0

    try:
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = mem.used / (1024 ** 3)
        ram_total_gb = mem.total / (1024 ** 3)
    except Exception:
        ram_percent, ram_used_gb, ram_total_gb = 0.0, 0.0, 0.0

    battery_percent = None
    plugged = False
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            battery_percent = battery.percent
            plugged = bool(battery.power_plugged)
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "battery": battery_percent,
        "plugged": plugged,
    }


# ==============================================================
# PERSISTENT TOKEN ACCOUNTING
# ==============================================================
class UsageStore:
    """Lifetime input/output token totals for one project."""

    def __init__(self, project_path):
        self.path = os.path.join(project_path, ".zani", "usage.json")
        self.data = {
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
            "first_seen": None,
            "last_updated": None,
        }
        self.session_input = 0
        self.session_output = 0
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update({k: stored.get(k, v) for k, v in self.data.items()})
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass

    def record(self, input_tokens, output_tokens):
        """Fold one API call's usage into both the session and lifetime totals."""
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        if not input_tokens and not output_tokens:
            return

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.data["input_tokens"] += input_tokens
        self.data["output_tokens"] += output_tokens
        self.data["calls"] += 1
        self.data["first_seen"] = self.data["first_seen"] or now
        self.data["last_updated"] = now

        self.session_input += input_tokens
        self.session_output += output_tokens
        self._save()

    @property
    def total_input(self):
        return self.data["input_tokens"]

    @property
    def total_output(self):
        return self.data["output_tokens"]

    @property
    def calls(self):
        return self.data["calls"]


def human_tokens(value):
    """Compact token counts so a narrow gauge never wraps."""
    if value < 1000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1000:.1f}k"
    return f"{value / 1_000_000:.2f}M"
