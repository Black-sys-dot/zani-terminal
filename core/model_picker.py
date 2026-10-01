"""Interactive model picker (agy-style list + search, no chat dump)."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.model_catalog import ModelChoice

VISIBLE_ROWS = 7


@dataclass
class ModelPickerState:
    active: bool = False
    loading: bool = False
    error: str | None = None
    all_models: list[ModelChoice] = field(default_factory=list)
    filtered: list[ModelChoice] = field(default_factory=list)
    index: int = 0
    scroll_offset: int = 0
    search: str = ""

    def reset(self) -> None:
        self.active = False
        self.loading = False
        self.error = None
        self.all_models = []
        self.filtered = []
        self.index = 0
        self.scroll_offset = 0
        self.search = ""

    def set_models(self, models: list[ModelChoice]) -> None:
        self.all_models = models
        self.loading = False
        self.error = None
        self.apply_filter(self.search)

    def apply_filter(self, query: str) -> None:
        # Textual delivers `TextArea.Changed` on the message pump, so clearing the
        # prompt when the picker opens arrives *after* the initial selection is
        # set. Treating an unchanged query as a no-op keeps that selection.
        if query == self.search and self.filtered:
            return
        self.search = query
        q = query.strip().lower()
        if not q:
            self.filtered = list(self.all_models)
        else:
            self.filtered = [
                m
                for m in self.all_models
                if q in m.id.lower() or q in (m.label or "").lower()
            ]
        self.index = 0
        self.scroll_offset = 0

    def selected(self) -> ModelChoice | None:
        if not self.filtered:
            return None
        if self.index >= len(self.filtered):
            self.index = len(self.filtered) - 1
        if self.index < 0:
            self.index = 0
        return self.filtered[self.index]

    def move(self, delta: int) -> None:
        if not self.filtered:
            return
        self.index = max(0, min(len(self.filtered) - 1, self.index + delta))
        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + VISIBLE_ROWS:
            self.scroll_offset = self.index - VISIBLE_ROWS + 1

    def focus_id(self, model_id: str) -> None:
        for i, m in enumerate(self.filtered):
            if m.id == model_id:
                self.index = i
                if self.index >= VISIBLE_ROWS:
                    self.scroll_offset = self.index - VISIBLE_ROWS + 1
                else:
                    self.scroll_offset = 0
                return

    def visible_slice(self) -> list[ModelChoice]:
        end = self.scroll_offset + VISIBLE_ROWS
        return self.filtered[self.scroll_offset : end]


def render_picker(state: ModelPickerState, theme, current_model: str) -> str:
    if not state.active:
        return ""

    lines = [f"[bold {theme.text}]Switch Model[/]", ""]

    if state.loading:
        lines.append(f"[{theme.subtext}]Loading models…[/]")
        return "\n".join(lines)

    if state.error:
        lines.append(f"[{theme.red}]{state.error}[/]")
        lines.append(f"[{theme.subtext}]esc to close[/]")
        return "\n".join(lines)

    lines.append(f"[{theme.subtext}]Search:[/] [{theme.text}]{state.search or ''}[/]")
    lines.append("")

    visible = state.visible_slice()
    if not visible:
        lines.append(f"[{theme.subtext}]No models match.[/]")
    else:
        for i, entry in enumerate(visible):
            abs_i = state.scroll_offset + i
            is_sel = abs_i == state.index
            current = " [dim](current)[/]" if entry.id == current_model else ""
            name = entry.id
            if len(name) > 52:
                name = name[:49] + "…"
            if is_sel:
                lines.append(f"[reverse]> {name}[/]{current}")
            else:
                lines.append(f"  {name}{current}")

    below = len(state.filtered) - (state.scroll_offset + len(visible))
    above = state.scroll_offset
    if above > 0 or below > 0:
        lines.append(
            f"[{theme.subtext}]  ({state.index + 1}/{len(state.filtered)}"
            f"{f' · ↑{above} above' if above else ''}"
            f"{f' · ↓{below} below' if below else ''})[/]"
        )

    lines.append("")
    lines.append(
        f"[{theme.subtext}]↑/↓ navigate · enter select · esc back[/]"
    )
    return "\n".join(lines)
