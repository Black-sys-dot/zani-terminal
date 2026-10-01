"""Picker for saved project chats (+ new chat)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.conversation_store import NEW_CHAT_ID, ConversationMeta

VISIBLE_ROWS = 8


@dataclass
class ChatPickerState:
    active: bool = False
    include_new: bool = True
    conversations: list[ConversationMeta] = field(default_factory=list)
    index: int = 0
    scroll_offset: int = 0

    def reset(self) -> None:
        self.active = False
        self.conversations = []
        self.index = 0
        self.scroll_offset = 0

    def set_conversations(self, items: list[ConversationMeta], *, include_new: bool = True) -> None:
        self.conversations = list(items)
        self.include_new = include_new
        self.index = 0
        self.scroll_offset = 0

    def row_count(self) -> int:
        n = len(self.conversations)
        return n + (1 if self.include_new else 0)

    def selected_id(self) -> str | None:
        if not self.active or self.row_count() == 0:
            return None
        if self.include_new and self.index == 0:
            return NEW_CHAT_ID
        offset = 1 if self.include_new else 0
        idx = self.index - offset
        if 0 <= idx < len(self.conversations):
            return self.conversations[idx].id
        return None

    def move(self, delta: int) -> None:
        total = self.row_count()
        if total <= 0:
            return
        self.index = max(0, min(total - 1, self.index + delta))
        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + VISIBLE_ROWS:
            self.scroll_offset = self.index - VISIBLE_ROWS + 1

    def all_rows(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        if self.include_new:
            rows.append((NEW_CHAT_ID, "＋ New chat", "start a fresh conversation"))
        for meta in self.conversations:
            rows.append((meta.id, meta.title, _subtitle(meta)))
        return rows

    def visible_rows(self) -> list[tuple[str, str, str]]:
        start = self.scroll_offset
        return self.all_rows()[start : start + VISIBLE_ROWS]


def _subtitle(meta: ConversationMeta) -> str:
    parts = [f"{meta.message_count} msgs"]
    if meta.updated_at:
        parts.append(meta.updated_at.replace("T", " ").replace("+00:00", " UTC")[:19])
    return " · ".join(parts)


def render_chat_picker(state: ChatPickerState, theme) -> str:
    if not state.active:
        return ""
    lines = [f"[bold {theme.text}]Chats in this project[/]", ""]
    if state.row_count() == 0:
        lines.append(f"[{theme.subtext}]No saved chats yet.[/]")
        return "\n".join(lines)

    visible = state.visible_rows()
    for i, (cid, title, sub) in enumerate(visible):
        row_index = state.scroll_offset + i
        prefix = "> " if row_index == state.index else "  "
        if row_index == state.index:
            lines.append(f"[reverse]{prefix}{title[:48]:<48}[/] [{theme.subtext}]{sub}[/]")
        else:
            lines.append(f"{prefix}{title[:48]:<48} [{theme.subtext}]{sub}[/]")

    extra = state.row_count() - state.scroll_offset - len(visible)
    if extra > 0:
        lines.append(f"[{theme.subtext}]  + {extra} more[/]")
    lines.append(f"[{theme.subtext}]↑/↓ · enter · esc[/]")
    return "\n".join(lines)
