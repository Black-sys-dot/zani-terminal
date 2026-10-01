import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import RichLog, Static
from textual.widgets.text_area import TextAreaTheme

from rich.style import Style
from rich.text import Text

from core.tui import (
    ZaniTUI,
    SlashPromptArea,
    PromptArea,
    SHEEN_INTERVAL,
    SPINNER,
    PROMPT_MAX_LINES,
)
from core.mcp_orchestrator import MAX_HISTORY_TOKENS
from core.themes import get_theme, TuiTheme
from core.tas_runtime import api_model_name, tas_status_label
from core import audio_playback


class BaseStatusBox(Static):
    """Status panel in the bottom dock — Z horns above the box (original layout)."""

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> str:
        t = self.app.zani_theme
        brain = self.app.brain
        model = api_model_name(brain)
        used = self.app.orchestrator._history_tokens() if hasattr(self.app, "orchestrator") else 0
        tas = tas_status_label(brain)
        if len(model) > 31:
            model = model[:28] + "…"
        ctx = f"{used:,} / {MAX_HISTORY_TOKENS:,}"
        z, dim, tx = t.mauve, t.subtext, t.text
        return (
            f"             [{z}]z[/]\n"
            f"          [{z}]z[/]\n"
            f"       [{z}]Z[/]\n"
            f"╭────      ────────────────────────────────╮\n"
            f"│ [{dim}]Model:[/]   [{tx}]{model:<31}[/] │\n"
            f"│ [{dim}]Context:[/] [{tx}]{ctx:<31}[/] │\n"
            f"│ [{dim}]TaS:[/]     [{tx}]{tas:<31}[/] │\n"
            f"╰──────────────────────────────────────────╯"
        )


class BaseTUI(ZaniTUI):
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+q", "swallow_ctrl_q", show=False, priority=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zani_theme: TuiTheme = get_theme()
        self.ansi_color = True

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield RichLog(id="chat_log", highlight=False, markup=True, wrap=True)
            with Vertical(id="input_dock"):
                yield BaseStatusBox(id="status_box")
                yield Static("", id="tas_picker")
                yield Static("", id="model_picker")
                yield Static("", id="slash_menu")
                yield SlashPromptArea(id="chat_input")
                yield Static(id="hint")

    def on_mount(self) -> None:
        self.title = "zani"
        self._apply_theme()
        self._style_prompt()
        self.query_one("#chat_input", SlashPromptArea).focus()
        self.log_write(
            f"[{self.zani_theme.subtext}]{len(self.orchestrator.tools_schema)} tools · "
            f"type [/][{self.zani_theme.mauve}]/[/][{self.zani_theme.subtext}] for commands[/]"
        )
        self.log_write(
            f"[{self.zani_theme.subtext}]/model · /TaS · /clear · /exit[/]"
        )
        if getattr(self.brain, "tas_enabled", False) and not audio_playback.playback_ready():
            if audio_playback.in_docker():
                hint = (
                    "TaS muted — container cannot reach host audio (is Pulse TCP on port "
                    f"{os.environ.get('PULSE_SERVER', '4713').split(':')[-1]} loaded?). "
                    "Chat uses your text model (no audio charges)."
                )
            else:
                hint = (
                    "No working audio output here. Chat uses your text model — no audio charges."
                )
            self.log_write(f"[{self.zani_theme.subtext}]{hint}[/]")
        self.set_interval(SHEEN_INTERVAL, self.advance_sheen)
        self.refresh_hint()

    def _apply_theme(self) -> None:
        t = self.zani_theme
        css = f"""
        Screen {{ background: {t.css_bg}; color: {t.css_fg}; }}
        #root {{ background: {t.css_bg}; height: 100%; }}
        #chat_log {{
            width: 100%;
            height: 100%;
            background: {t.css_bg};
            color: {t.css_fg};
            padding: 0 2;
            border: none;
            scrollbar-size: 1 1;
        }}
        #input_dock {{
            dock: bottom;
            width: 100%;
            height: auto;
            background: {t.css_panel_bg};
            border-top: solid {t.css_border};
            padding: 0 1 1 1;
        }}
        #status_box {{
            height: auto;
            padding: 0 1 0 1;
            background: {t.css_panel_bg};
        }}
        #tas_picker, #model_picker, #slash_menu {{
            display: none;
            height: auto;
            padding: 0 1;
            background: {t.css_panel_bg};
        }}
        #tas_picker.-visible, #model_picker.-visible, #slash_menu.-visible {{ display: block; }}
        #chat_input {{
            height: auto;
            min-height: 1;
            max-height: 6;
            border: solid {t.css_border};
            padding: 0 1;
            margin: 0 1;
            background: {t.css_panel_bg};
            color: {t.css_fg};
        }}
        #hint {{
            height: 1;
            padding: 0 2 1 2;
            color: {t.css_dim};
            background: {t.css_panel_bg};
        }}
        """
        self.stylesheet.add_source(css)
        self.stylesheet.reparse()
        self.stylesheet.update(self)

    def _style_prompt(self) -> None:
        try:
            area = self.query_one("#chat_input", SlashPromptArea)
        except NoMatches:
            return
        area.register_theme(
            TextAreaTheme(
                name="zani_base_runtime",
                base_style=Style(color="default", bgcolor="default"),
                cursor_style=Style(reverse=True),
                cursor_line_style=Style(bgcolor="default"),
                selection_style=Style(reverse=True),
            )
        )
        area.theme = "zani_base_runtime"

    def resize_prompt(self) -> None:
        try:
            area = self.query_one("#chat_input", SlashPromptArea)
        except NoMatches:
            return
        width = area.size.width
        if width <= 0:
            return
        needed = area.get_content_height(self.size, self.size, width)
        rows = max(1, min(PROMPT_MAX_LINES, needed))
        if rows == self._prompt_rows:
            return
        self._prompt_rows = rows
        area.styles.height = rows + 2

    def refresh_header(self):
        try:
            self.query_one("#status_box", BaseStatusBox).refresh()
        except Exception:
            pass

    def refresh_caption(self): pass
    def refresh_status(self): pass
    def refresh_graph(self): pass
    def refresh_gauges(self): pass
    def refresh_ledger(self): pass
    def _paint_backdrop(self): pass
    def settle_layout(self): pass
    def fit_padding(self): pass
    def freeze_body(self): pass
    def action_toggle_chat(self): pass
    def tick_gauges(self): pass
    def tick_spinner(self): pass

    def refresh_hint(self) -> None:
        t = self.zani_theme
        line = Text()
        if self.is_running_task:
            g = SPINNER[self._sheen_phase_frame(len(SPINNER))]
            line.append(f"{g} working", style=Style(color=t.mauve))
        else:
            line.append("ready", style=Style(color=t.green))
        line.append(f"  ·  {t.name}", style=Style(color=t.subtext))
        line.append("  ·  /exit", style=Style(color=t.subtext))
        self.query_one("#hint", Static).update(line)
