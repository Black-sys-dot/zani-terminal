"""TaS picker: Off, model, then voice."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.model_catalog import ModelChoice
from core.tas_voices import list_tas_voices, DEFAULT_TAS_VOICE

OFF_ID = "__tas_off__"
VOICE_PREFIX = "__voice__"
VISIBLE_ROWS = 8


def _voice_row(voice_id: str, label: str) -> ModelChoice:
    return ModelChoice(f"{VOICE_PREFIX}{voice_id}", label)


@dataclass
class TasPickerState:
    active: bool = False
    loading: bool = False
    error: str | None = None
    step: str = "model"  # model | voice
    pending_model: str = ""
    rows: list[ModelChoice] = field(default_factory=list)
    filtered: list[ModelChoice] = field(default_factory=list)
    index: int = 0
    scroll_offset: int = 0
    search: str = ""
    tas_enabled: bool = False
    current_model: str = ""
    current_voice: str = DEFAULT_TAS_VOICE

    def reset(self) -> None:
        self.active = False
        self.loading = False
        self.error = None
        self.step = "model"
        self.pending_model = ""
        self.rows = []
        self.filtered = []
        self.index = 0
        self.scroll_offset = 0
        self.search = ""

    def set_models(self, models: list[ModelChoice], *, tas_enabled: bool, current_model: str, current_voice: str) -> None:
        self.step = "model"
        self.pending_model = ""
        self.rows = [ModelChoice(OFF_ID, "Off — text only, no speech")] + list(models)
        self.tas_enabled = tas_enabled
        self.current_model = current_model
        self.current_voice = current_voice or DEFAULT_TAS_VOICE
        self.loading = False
        self.error = None
        self.apply_filter(self.search)

    def begin_voice_step(self, model_id: str) -> None:
        self.step = "voice"
        self.pending_model = model_id
        self.rows = [_voice_row(v.id, v.label) for v in list_tas_voices()]
        self.search = ""
        self.index = 0
        self.scroll_offset = 0
        self.apply_filter("")

    def apply_filter(self, query: str) -> None:
        if query == self.search and self.filtered:
            return
        self.search = query
        q = query.strip().lower()
        if not q:
            self.filtered = list(self.rows)
        else:
            self.filtered = [
                m
                for m in self.rows
                if q in m.id.lower() or q in (m.label or "").lower()
            ]
        self.index = 0
        self.scroll_offset = 0
        self._sync_index_to_selection()

    def _sync_index_to_selection(self) -> None:
        if not self.filtered:
            return
        if self.step == "voice":
            want = f"{VOICE_PREFIX}{self.current_voice}"
            for i, m in enumerate(self.filtered):
                if m.id == want:
                    self.index = i
                    if self.index >= VISIBLE_ROWS:
                        self.scroll_offset = self.index - VISIBLE_ROWS + 1
                    return
            return
        if not self.tas_enabled:
            if self.filtered[0].id == OFF_ID:
                self.index = 0
            return
        for i, m in enumerate(self.filtered):
            if m.id == self.current_model:
                self.index = i
                if self.index >= VISIBLE_ROWS:
                    self.scroll_offset = self.index - VISIBLE_ROWS + 1
                return

    def selected(self) -> ModelChoice | None:
        if not self.filtered:
            return None
        self.index = max(0, min(len(self.filtered) - 1, self.index))
        return self.filtered[self.index]

    def selected_voice_id(self) -> str | None:
        sel = self.selected()
        if not sel or not sel.id.startswith(VOICE_PREFIX):
            return None
        return sel.id[len(VOICE_PREFIX) :]

    def move(self, delta: int) -> None:
        if not self.filtered:
            return
        self.index = max(0, min(len(self.filtered) - 1, self.index + delta))
        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + VISIBLE_ROWS:
            self.scroll_offset = self.index - VISIBLE_ROWS + 1

    def visible_slice(self) -> list[ModelChoice]:
        end = self.scroll_offset + VISIBLE_ROWS
        return self.filtered[self.scroll_offset : end]


def render_tas_picker(state: TasPickerState, theme) -> str:
    if not state.active:
        return ""

    title = "Text and Speech (TaS)" if state.step == "model" else "TaS — choose voice"
    lines = [f"[bold]{title}[/]", ""]
    if state.loading:
        lines.append(f"[{theme.subtext}]Loading OpenRouter audio models…[/]")
        return "\n".join(lines)
    if state.error:
        lines.append(f"[{theme.red}]{state.error}[/]")
        lines.append(f"[{theme.subtext}]esc to close[/]")
        return "\n".join(lines)

    if state.step == "voice" and state.pending_model:
        lines.append(f"[{theme.subtext}]Model:[/] {state.pending_model}")
    lines.append(f"[{theme.subtext}]Search:[/] {state.search or ''}")
    lines.append("")

    visible = state.visible_slice()
    if not visible:
        lines.append(f"[{theme.subtext}]No matches.[/]")
    else:
        for i, entry in enumerate(visible):
            abs_i = state.scroll_offset + i
            sel = abs_i == state.index
            if entry.id.startswith(VOICE_PREFIX):
                name = entry.label
            elif entry.id == OFF_ID:
                name = entry.label
            else:
                name = entry.id
            if len(name) > 56:
                name = name[:53] + "…"
            mark = ""
            if state.step == "model" and entry.id == OFF_ID and not state.tas_enabled:
                mark = " [dim](current)[/]"
            elif state.step == "model" and entry.id == state.current_model and state.tas_enabled:
                mark = " [dim](current)[/]"
            elif state.step == "voice" and entry.id == f"{VOICE_PREFIX}{state.current_voice}":
                mark = " [dim](current)[/]"
            prefix = "> " if sel else "  "
            if sel:
                lines.append(f"[reverse]{prefix}{name}[/]{mark}")
            else:
                lines.append(f"{prefix}{name}{mark}")

    lines.append("")
    hint = "↑/↓ · enter select · esc back"
    if state.step == "voice":
        hint += " · voice applies with model"
    lines.append(f"[{theme.subtext}]{hint}[/]")
    return "\n".join(lines)
