import asyncio
import os
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import RichLog, Static
from textual.reactive import reactive

from rich.style import Style
from rich.text import Text

from core.tui import ZaniTUI, PromptArea, DIM, CHAT_USER, now_stamp, CHAT_ZANI, RED, SHEEN_INTERVAL, SPINNER, GREEN
from core.mcp_orchestrator import MAX_HISTORY_TOKENS

class BaseHeader(Static):
    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def render(self) -> str:
        model = getattr(self.app.brain, "model_name", "unknown")
        used = self.app.orchestrator._history_tokens() if hasattr(self.app, "orchestrator") else 0
        max_ctx = MAX_HISTORY_TOKENS

        m_val = model[:31]
        c_val = f"{used} / {max_ctx}"

        z_color = "#8338ec" # bright violet for cool effect
        return f"""\
             [bold italic {z_color}]z[/]
          [bold italic {z_color}]z[/]
       [bold italic {z_color}]Z[/]
╭────      ────────────────────────────────╮
│ [dim]Model:[/dim]   {m_val:<31} │
│ [dim]Context:[/dim] {c_val:<31} │
╰──────────────────────────────────────────╯"""

class BaseTUI(ZaniTUI):
    CSS = """
    Screen { background: transparent; }
    #root { layout: vertical; width: 100%; height: 100%; background: transparent; }
    #base_header {
        dock: top;
        height: 7;
        width: 100%;
        padding: 0 2;
        background: transparent;
    }
    #chat_log {
        height: 1fr; background: transparent; border: none; padding: 0 1;
        scrollbar-size: 1 1;
    }
    #input_dock {
        dock: bottom; height: auto; width: 100%;
        padding: 0; background: transparent;
        border-top: solid #444;
    }
    #chat_input {
        height: auto;
        border: none;
        background: transparent;
        padding: 0 1;
    }
    #hint { height: 1; padding: 0 2; color: #888; }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+t", "toggle_mode", "Toggle mode"),
        ("ctrl+s", "toggle_speech", "Speak replies"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield BaseHeader(id="base_header")
            yield RichLog(id="chat_log", highlight=False, markup=True, wrap=True)
            with Container(id="input_dock"):
                yield PromptArea(id="chat_input")
                yield Static(id="hint")

    def on_mount(self) -> None:
        self.title = "ZANI Base"
        self.query_one("#chat_input", PromptArea).focus()
        
        log = self.query_one("#chat_log", RichLog)
        self.log_write(f"[{DIM}]harness online — {len(self.orchestrator.tools_schema)} tools registered[/]")
        self.log_write(f"[{DIM}]/mode chat|act · ctrl+t toggles · /clear resets the console[/]")
        
        self.set_interval(SHEEN_INTERVAL, self.advance_sheen)
        self.refresh_hint()

    # Stub out methods that update visual panels not present in BaseTUI
    def refresh_header(self): pass
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
        line = Text()
        if self.is_running_task:
            glyph = SPINNER[self._sheen_phase_frame(len(SPINNER))]
            line.append(f"{glyph} working…", style=Style(color=self.pulse(), bold=True))
        else:
            line.append("ready", style=Style(color=GREEN, bold=True))
        self.query_one("#hint", Static).update(line)
