"""Per-project chat sessions under `.zani/conversations/` (not shared across projects)."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

NEW_CHAT_ID = "__new__"


@dataclass(frozen=True)
class ConversationMeta:
    id: str
    title: str
    updated_at: str
    message_count: int


def _conversations_dir(project_path: str) -> str:
    return os.path.join(project_path, ".zani", "conversations")


def _conversation_path(project_path: str, conv_id: str) -> str:
    safe = re.sub(r"[^\w\-]", "", conv_id)
    return os.path.join(_conversations_dir(project_path), f"{safe}.json")


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def derive_title(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        one_line = " ".join(text.split())
        if len(one_line) > 56:
            return one_line[:53] + "…"
        return one_line
    return "New chat"


def list_conversations(project_path: str) -> list[ConversationMeta]:
    root = _conversations_dir(project_path)
    if not os.path.isdir(root):
        return []
    rows: list[ConversationMeta] = []
    for name in os.listdir(root):
        if not name.endswith(".json"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        cid = (data.get("id") or name[:-5]).strip()
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            continue
        title = (data.get("title") or derive_title(messages)).strip() or "Chat"
        updated = (data.get("updated_at") or data.get("created_at") or "").strip()
        rows.append(
            ConversationMeta(
                id=cid,
                title=title,
                updated_at=updated,
                message_count=len(messages),
            )
        )
    rows.sort(key=lambda r: r.updated_at or "", reverse=True)
    return rows


def load_messages(project_path: str, conv_id: str) -> list[dict]:
    path = _conversation_path(project_path, conv_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return []
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        return []
    return messages


def save_conversation(
    project_path: str,
    conv_id: str,
    messages: list[dict],
    *,
    title: str | None = None,
) -> None:
    if not messages:
        return
    path = _conversation_path(project_path, conv_id)
    created = _now_iso()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict) and old.get("created_at"):
                created = old["created_at"]
        except (OSError, ValueError, TypeError):
            pass
    payload = {
        "id": conv_id,
        "title": (title or derive_title(messages)).strip() or "Chat",
        "created_at": created,
        "updated_at": _now_iso(),
        "messages": messages,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
