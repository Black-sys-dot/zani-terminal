"""
Secret-file policy for the Zani visual harness (`zani tui --zani`).

`.zani.env` is never exposed to the model and cannot be read even with user
approval. `.env` is hidden from listings/search; reading it requires an explicit
user grant in the TUI (`/allow-env`). Writes and git staging/commits involving
either file are blocked in harness mode.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ALWAYS_BLOCKED_NAMES = frozenset({".zani.env"})
ENV_FILE_NAME = ".env"

_GIT_ADD = re.compile(r"\bgit\s+add\b", re.I)
_GIT_COMMIT = re.compile(r"\bgit\s+commit\b", re.I)
_GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(-A|--all|\.\s*$|\.\s+)", re.I)


def secret_kind(relative_path: str) -> str | None:
    """
    Return 'always_blocked' for `.zani.env`, 'env_gated' for `.env`, else None.
    """
    if not relative_path:
        return None
    name = Path(relative_path).name
    if name in ALWAYS_BLOCKED_NAMES:
        return "always_blocked"
    if name == ENV_FILE_NAME:
        return "env_gated"
    return None


def should_hide_from_listing(filename: str, *, harness: bool) -> bool:
    if filename in ALWAYS_BLOCKED_NAMES:
        return True
    if harness and filename == ENV_FILE_NAME:
        return True
    return False


def should_skip_in_search(filename: str, *, harness: bool) -> bool:
    if filename in ALWAYS_BLOCKED_NAMES:
        return True
    if harness and filename == ENV_FILE_NAME:
        return True
    if filename == ENV_FILE_NAME:
        return True
    return False


def guard_filesystem_tool(
    tool_name: str,
    arguments: dict,
    *,
    harness: bool,
    env_read_granted: bool,
) -> str | None:
    """Return an error message to send to the model, or None to proceed."""
    path = arguments.get("path")
    if path and isinstance(path, str):
        kind = secret_kind(path)
        if kind == "always_blocked":
            return (
                "Harness policy: `.zani.env` is blocked. It is not readable, writable, "
                "or visible to the agent."
            )
        if kind == "env_gated":
            if tool_name == "read_file":
                if harness and not env_read_granted:
                    return (
                        "Harness policy: reading `.env` requires explicit user permission. "
                        "Ask the user to run `/allow-env` in the TUI, then retry."
                    )
                if not harness:
                    return "Security violation: Access to `.env` files is prohibited."
            if tool_name == "write_file" and harness:
                return "Harness policy: writing `.env` is blocked."

    if harness and tool_name == "write_file" and path:
        if secret_kind(str(path)):
            return "Harness policy: cannot write secret env files."

    return None


def guard_bash_command(command: str, project_dir: str, *, harness: bool) -> str | None:
    if not harness or not command:
        return None

    cmd = command.strip()

    if _GIT_ADD.search(cmd):
        if _GIT_ADD_ALL.search(cmd):
            return (
                "Harness policy: `git add -A` / `git add .` is blocked (may include "
                "`.env` or `.zani.env`). Stage paths individually, excluding secret files."
            )
        for token in cmd.split():
            if secret_kind(token):
                return f"Harness policy: cannot `git add` secret file `{token}`."

    if _GIT_COMMIT.search(cmd):
        blocked = _staged_secret_paths(project_dir)
        if blocked:
            names = ", ".join(f"`{p}`" for p in blocked)
            return f"Harness policy: commit blocked — staged secret file(s): {names}."

    return None


def _staged_secret_paths(project_dir: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    blocked = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if secret_kind(line):
            blocked.append(line)
    return blocked
