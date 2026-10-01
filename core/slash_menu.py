"""Agy-style `/` command palette — terminal colours only."""

from __future__ import annotations

from dataclasses import dataclass

SLASH_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/clear", "clear the chat view"),
    ("/model", "switch text model"),
    ("/TaS", "text + speech (OpenRouter)"),
    ("/new", "start a new saved chat"),
    ("/resume", "open a saved chat"),
    ("/exit", "quit zani"),
)


@dataclass
class SlashMenuState:
    visible: bool = False
    index: int = 0
    matches: list[tuple[str, str]] | None = None

    def sync(self, text: str) -> None:
        if not text.startswith("/"):
            self.visible = False
            self.matches = []
            self.index = 0
            return

        token = text.split()[0] if text.strip() else "/"
        token_lower = token.lower()
        self.matches = [
            (cmd, hint)
            for cmd, hint in SLASH_COMMANDS
            if token == "/" or cmd.lower().startswith(token_lower)
        ]
        self.visible = bool(self.matches)
        if self.index >= len(self.matches):
            self.index = max(0, len(self.matches) - 1)

    def selected(self) -> tuple[str, str] | None:
        if not self.matches:
            return None
        return self.matches[self.index]

    def move(self, delta: int) -> None:
        if not self.matches:
            return
        self.index = (self.index + delta) % len(self.matches)

    def apply_to_line(self, text: str) -> str:
        sel = self.selected()
        if not sel:
            return text
        cmd, _ = sel
        rest = text.split(maxsplit=1)
        suffix = f" {rest[1]}" if len(rest) > 1 and not rest[1].startswith("/") else ""
        return f"{cmd}{suffix}".strip() + " "


def render_menu(state: SlashMenuState, theme, *, max_rows: int = 8) -> str:
    if not state.visible or not state.matches:
        return ""

    lines = []
    shown = state.matches[:max_rows]
    for i, (cmd, hint) in enumerate(shown):
        if i == state.index:
            lines.append(f"[reverse]> {cmd:<12}[/] [{theme.subtext}]{hint}[/]")
        else:
            lines.append(f"  {cmd:<12} [{theme.subtext}]{hint}[/]")

    extra = len(state.matches) - len(shown)
    if extra > 0:
        lines.append(f"[{theme.subtext}]  + {extra} more[/]")

    lines.append(f"[{theme.subtext}]↑/↓ · enter/tab · esc[/]")
    return "\n".join(lines)
