"""
Zani's harness UI.

Layout is three columns over a docked input. The character holds the centre, the
left rail carries state Zani produces (mode, memory pressure, model, the tool
chain for the current turn, host telemetry), and the right rail carries the
conversation plus the work product. Nothing on screen is decorative filler —
every number is read from a live source, and a panel with no data says so rather
than inventing one.

The tool graph is turn-scoped: it clears on every prompt so it answers "what is
Zani doing right now", not "what has Zani ever done".
"""

import asyncio
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image as PILImage

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import RichLog, Static, TextArea
from textual.widgets.text_area import TextAreaTheme

# Negotiates the best image path the terminal offers: kitty's graphics protocol
# or sixels draw real pixels, and only if neither exists does it fall back to
# character cells. On a capable terminal the portrait is a true image, not an
# approximation built out of glyphs.
from textual_image.widget import Image as _AutoImage

from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.style import Style
from rich.style import Style as RichStyle
from rich.syntax import Syntax
from rich.text import Text

from core import backdrop
from core.speech import Speaker
from core.mcp_orchestrator import MAX_HISTORY_TOKENS, ZaniMCPOrchestrator
from core import pricing
from core.telemetry import UsageStore, human_tokens, sample_system
from core.tool_registry import ERROR, OK, RUNNING, ToolGraph, describe

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

# ==============================================================
# PALETTE — sandy blossom
# ==============================================================
# Text now sits on a bright photograph rather than a flat cream panel, so every
# colour is pulled dark and saturated. Pastels vanished against the sunlit parts
# of the terrace; these hold at one cell tall over both the pale sky and the
# shaded stonework.
BG = "#f2e2d7"          # sandy blush — retained only as the wash base
PANEL_BG = "#fdf6f1"    # retained for meters; panels themselves are transparent
BORDER = "#7a4a42"      # dusty rose rule
TEXT = "#241619"        # near-black
DIM = "#4a3833"         # dark taupe — a true grey vanished into the stonework
VIOLET = "#4a1d7a"      # deep violet
CYAN = "#0d5a68"        # deep teal
MAGENTA = "#960f4e"     # deep rose
AMBER = "#7a4200"       # deep amber
GREEN = "#2a5f16"       # deep green
RED = "#8a1219"         # deep red
TRACK = "#bda294"       # meter track

# The chat console is the one panel you actually read continuously, so it
# gets its own ink rather than the shared near-black: a deep violet that
# separates it from the telemetry rails at a glance.
CHAT_INK = "#2a1a3d"    # deep purple-black for conversation text
CHAT_USER = "#8f0f52"   # bright rose for the user label
CHAT_ZANI = "#5416a3"   # vivid violet for hers

RAIL_WIDTH = 58         # right rail when collapsed; 1fr when the chat is focused
TRANSCRIPT_LIMIT = 500  # console lines retained for re-wrapping on toggle

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Alpha-cut so she composites onto the terrace rather than sitting in a white
# box. The full body is used again rather than the hero crop: placed directly
# through kitty she is no longer confined to a widget, so instead of being
# trimmed to fit she is sized past the bottom of the screen and simply
# continues behind the input dock.
PORTRAIT_ASSET = "zani_soul_cut.png"
PORTRAIT_MAX_COLS = 76   # her width in cells; height follows from the aspect
PORTRAIT_SHIFT_ROWS = 4  # slid up, so the flat horn cut clears the top edge
PROMPT_MAX_LINES = 8     # prompt grows to this many wrapped lines, then scrolls
BASE_DOCK_ROWS = 5       # dock height with a one-line prompt

# Sent to kitty as a real image and placed behind the text layer — see
# core/backdrop.py. Opacity and brightness are baked into the pixels before
# transmission, because terminal cells have no alpha to do it at composite time.
BACKDROP_ASSET = "zani_backdrop.png"
BACKDROP_OPACITY = 1.0   # 1.0 = no sandy wash; the photograph keeps its own colour
BACKDROP_LIFT = 0.0      # no whitening: the photograph at full strength
# Raised to compensate. Lift and scrim compound, so dropping lift to zero
# would have darkened the panels too; 0.65 reproduces the previous panel
# tone exactly while the open background gains the full ~28%.
BACKDROP_SCRIM = 0.65    # extra lightening behind panels only, never the centre
FRAME_ASSET = "zani_frame_cut.png"    # ornamental border, nine-sliced per panel
FRAME_WIDE_ASSET = "zani_frame_wide.png"  # used once a panel gets focus-mode wide

# The prompt is the one opaque surface in the UI — a solid slab rather than a
# framed panel, so it stays legible no matter what is behind it.
PROMPT_BG = "#0d0b12"    # near-black
PROMPT_INK = "#ffffff"   # white, on the black slab
PROMPT_EDGE = "#3a2d4d"  # faint rule top and bottom only
PROMPT_CURSOR = "#c79ae8"  # caret block
PROMPT_SELECT = "#33265c"  # selection behind text
BASE_RGB = (242, 226, 215)  # BG as rgb, for blending


def now_stamp():
    return datetime.now().strftime("%H:%M:%S")


def sheen(label, stops, phase=0.0, bold=True):
    """
    Colour a string per character along a moving gradient.

    A static gradient just reads as coloured text — what makes something look
    metallic is a narrow bright band travelling across a darker base, so the
    stops carry a highlight and `phase` slides it along on a timer. The first
    and last stop are identical, which lets the pattern wrap without a seam.
    """
    text = Text()
    span = max(1, len(label) - 1)
    segments = len(stops) - 1

    for index, char in enumerate(label):
        position = ((index / span + phase) % 1.0) * segments
        left = min(int(position), segments - 1)
        blend = position - left
        start, end = stops[left], stops[left + 1]
        rgb = tuple(
            int(round(a + (b - a) * blend))
            for a, b in zip(
                tuple(int(start[i:i + 2], 16) for i in (1, 3, 5)),
                tuple(int(end[i:i + 2], 16) for i in (1, 3, 5)),
            )
        )
        text.append(char, style=Style(color=f"rgb({rgb[0]},{rgb[1]},{rgb[2]})", bold=bold))
    return text


# A dark base with one narrow highlight, so the glint is a small part of the
# run rather than half of it. Ends match so the sweep loops seamlessly.
SHEEN_HEADER = ("#5c1040", "#5c1040", "#a3175c", "#ff9ec4", "#ffe6b8",
                "#ff9ec4", "#a3175c", "#5c1040", "#5c1040")
SHEEN_HINT = ("#3a1660", "#3a1660", "#6d2a9c", "#c79ae8", "#6d2a9c",
              "#3a1660", "#3a1660")
SHEEN_STEP = 0.035      # phase advanced per tick
SHEEN_INTERVAL = 0.08   # seconds between ticks


def bar(percent, width=14, color=VIOLET):
    """A proportional meter that degrades gracefully on junk input."""
    try:
        percent = max(0.0, min(100.0, float(percent)))
    except (TypeError, ValueError):
        percent = 0.0
    filled = int(percent / 100 * width)
    return f"[{color}]{'█' * filled}[/][{TRACK}]{'░' * (width - filled)}[/]"


AutoImage = _AutoImage


def portrait_path():
    """Full-resolution source; kitty does the scaling."""
    return ASSETS_DIR / PORTRAIT_ASSET


@lru_cache(maxsize=1)
def portrait_aspect():
    """Width/height of the source, used to derive her cell height."""
    try:
        with PILImage.open(portrait_path()) as image:
            return image.width / image.height
    except Exception:
        return 0.61


class PromptArea(TextArea):
    """
    The prompt box, wrapping instead of scrolling sideways.

    Textual's Input is single-line by construction — it has no soft-wrap at all,
    so a long prompt slides out of view to the left. TextArea wraps, and Enter
    is rebound to submit since the default would insert a newline.
    """

    class Submitted(Message):
        def __init__(self, value):
            self.value = value
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(soft_wrap=True, show_line_numbers=False, **kwargs)
        # TextArea paints from a theme object, not from CSS. Its styles resolved
        # correctly — background #0d0b12 — while it still rendered #121212 on
        # #e0e0e0, because the built-in theme wins at draw time. Registering an
        # explicit theme is the only thing that actually changes the pixels.
        self.register_theme(
            TextAreaTheme(
                name="zani",
                # Explicit bgcolor. TextArea paints a background either way —
                # leaving it unset just yielded Textual's #1b1b1b — so it may
                # as well paint the colour we want. The slab image behind is
                # the belt to this braces: whichever actually reaches the
                # terminal, the prompt ends up the same near-black.
                base_style=RichStyle(color=PROMPT_INK, bgcolor=PROMPT_BG),
                cursor_style=RichStyle(color=PROMPT_BG, bgcolor=PROMPT_CURSOR),
                cursor_line_style=RichStyle(bgcolor=PROMPT_BG),

                selection_style=RichStyle(bgcolor=PROMPT_SELECT),
            )
        )
        self.theme = "zani"

    async def _on_key(self, event):
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.Submitted(self.text))
            return
        await super()._on_key(event)


class ZaniTUI(App):
    CSS = f"""
    /* Nothing may be opaque: any solid background punches a hole in the
       backdrop kitty draws behind the text layer. Structure comes from borders
       and colour, and legibility from weight — bold is the only tool a terminal
       gives you for holding text against a photograph. */
    Screen {{ background: transparent; color: {TEXT}; }}

    #root {{
        layout: vertical; width: 100%; height: 100%;
        background: transparent;
    }}

    #header {{
        height: 1; padding: 0 2; color: {VIOLET};
        background: transparent; text-style: bold;
    }}

    #body {{ height: 1fr; width: 100%; padding: 0; background: transparent; }}

    #left_rail  {{ width: 34; min-width: 30; height: 100%; background: transparent; }}
    #center     {{ width: 1fr; height: 100%; background: transparent; }}
    #right_rail {{ width: {RAIL_WIDTH}; min-width: 46; height: 100%; background: transparent; }}

    /* `blank` keeps the border cell reserved for layout while drawing
       nothing — the ornamental frame image supplies the visual. */
    .frame {{
        border: blank; background: transparent;
        /* Vertical padding is not cosmetic: the art's rule sits ~1.7 rows in
           at panel scale, so content starting at row 1 lands under it. */
        padding: 1 2; margin-bottom: 1;
    }}
    .frame-title {{ height: 1; color: {VIOLET}; text-style: bold; }}
    .frame-body  {{ height: auto; color: {TEXT}; text-style: bold; }}

    #status_frame  {{ height: 12; }}
    #graph_frame   {{ height: 1fr; min-height: 10; }}
    #gauges_frame  {{ height: 17; }}

    /* No frame in the centre: she stands on the backdrop itself. */
    #center_frame  {{ height: 100%; background: transparent; }}
    #portrait_box  {{ width: 100%; height: 1fr; align: center middle; background: transparent; }}
    #portrait      {{ width: auto; height: 100%; }}
    #caption       {{ width: 100%; height: 2; content-align: center middle; text-style: bold; }}

    #chat_frame    {{ height: 3fr; min-height: 14; border: blank; }}
    #ledger_frame  {{ height: 2fr; min-height: 10; }}
    #chat_log {{
        height: 1fr; background: transparent; border: none; padding: 0;
        color: {CHAT_INK}; text-style: bold;
        scrollbar-size: 1 1;
        scrollbar-background: {TRACK};
        scrollbar-color: {BORDER};
        scrollbar-background-hover: {TRACK};
        scrollbar-color-hover: {MAGENTA};
        scrollbar-corner-color: {BORDER};
    }}

    #input_dock {{
        dock: bottom; height: 5; width: 100%;
        /* No horizontal padding: the slab is meant to run the full width,
           and padding here would inset it from both edges. */
        padding: 0; background: transparent;
    }}
    /* The one deliberately opaque surface. Everything else is transparent so
       the terrace shows through, but the prompt reads better as a solid slab
       floating over it — and an opaque background simply covers the backdrop,
       no scrim or frame needed. No side borders, so it runs edge to edge. */
    #chat_input {{
        height: 3;
        border: none;
        border-top: solid {PROMPT_EDGE};
        border-bottom: solid {PROMPT_EDGE};
        background: transparent;
        color: {PROMPT_INK};
        text-style: bold;
        padding: 0 1;
    }}
    #hint {{ height: 1; padding: 0 2; color: {DIM}; text-style: bold; }}
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+t", "toggle_mode", "Toggle mode"),
        ("ctrl+f", "toggle_chat", "Focus chat"),
        ("ctrl+s", "toggle_speech", "Speak replies"),
    ]

    def __init__(self, brain, orchestrator: ZaniMCPOrchestrator, project_path=None):
        super().__init__()
        backdrop.configure(
            ASSETS_DIR / BACKDROP_ASSET, BASE_RGB, BACKDROP_OPACITY,
            BACKDROP_LIFT, BACKDROP_SCRIM, ASSETS_DIR / FRAME_ASSET,
            ASSETS_DIR / FRAME_WIDE_ASSET,
        )
        self.brain = brain
        self.orchestrator = orchestrator
        self.project_path = project_path or os.getcwd()

        self.mode = "act"
        self.is_running_task = False
        self.chat_expanded = False
        # Every line ever shown, kept so the console can be re-rendered at a
        # new width. RichLog rasterises to strips on write and never re-wraps,
        # so widening the panel alone leaves old text at the old column count.
        self.transcript = []
        self.graph = ToolGraph()
        self.usage = UsageStore(self.project_path)
        self.rates = None
        self.telemetry = sample_system()
        self.files_touched = []
        self.spinner_frame = 0
        self._last_error = None
        self._sheen_phase = 0.0
        self._backdrop_timer = None
        self._prompt_rows = 1
        # Off by default and never self-starting: each spoken line is a
        # billed call, so it waits for /tts or ctrl+s.
        self.speaker = Speaker(getattr(brain, 'api_key', '') or '')

    # ----------------------------------------------------------
    # COMPOSE
    # ----------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield Static(id="header")
            with Horizontal(id="body"):
                with Vertical(id="left_rail"):
                    with Vertical(id="status_frame", classes="frame"):
                        yield Static("▪ AGENT_STATUS", classes="frame-title")
                        yield Static(id="status_body", classes="frame-body")
                    with Vertical(id="graph_frame", classes="frame"):
                        yield Static("▪ TOOL_EXECUTION_GRAPH", classes="frame-title")
                        yield Static(id="graph_body", classes="frame-body")
                    with Vertical(id="gauges_frame", classes="frame"):
                        yield Static("▪ RESOURCE_GAUGES", classes="frame-title")
                        yield Static(id="gauges_body", classes="frame-body")

                with Vertical(id="center"):
                    with Vertical(id="center_frame"):
                        # The widget keeps the decoded full-resolution image and
                        # re-renders it whenever its box changes, so scaling costs
                        # cells rather than fidelity.
                        with Container(id="portrait_box"):
                            # Under kitty she is placed directly (see
                            # _paint_backdrop); the widget is only the
                            # fallback for terminals without the protocol.
                            if not backdrop.supported():
                                yield AutoImage(portrait_path(), id="portrait")
                        yield Static(id="caption")

                with Vertical(id="right_rail"):
                    with Vertical(id="chat_frame", classes="frame"):
                        yield Static("▪ CHAT_CONSOLE", classes="frame-title")
                        yield RichLog(id="chat_log", highlight=False, markup=True, wrap=True)
                    with Vertical(id="ledger_frame", classes="frame"):
                        yield Static("▪ SESSION_LEDGER", classes="frame-title")
                        yield Static(id="ledger_body", classes="frame-body")

            with Container(id="input_dock"):
                yield PromptArea(id="chat_input")
                yield Static(id="hint")

    # ----------------------------------------------------------
    # LIFECYCLE
    # ----------------------------------------------------------
    def on_mount(self) -> None:
        self.title = "ZANI_HARNESS"
        self.refresh_all()
        self.refresh_caption()
        self.freeze_body()
        self.query_one("#chat_input", PromptArea).focus()

        log = self.query_one("#chat_log", RichLog)
        self.log_write(f"[{DIM}]harness online — {len(self.orchestrator.tools_schema)} tools registered[/]")
        self.log_write(f"[{DIM}]/mode chat|act · ctrl+t toggles · /clear resets the console[/]")

        self.set_interval(1.0, self.tick_gauges)
        self.set_interval(SHEEN_INTERVAL, self.advance_sheen)
        self.set_interval(0.1, self.tick_spinner)
        self.load_rates()

        # After the first paint: Textual's own screen setup would wipe an image
        # placed any earlier.
        self.call_after_refresh(self._paint_backdrop)

    def freeze_body(self) -> None:
        """
        Pin the body to its resting height so a growing dock overlays it.

        Left it free, `dock: bottom` reserves the dock's space and the body
        shrinks into what is left — which the fractional right-hand panels
        absorb by compressing, while the fixed-height left ones just get
        covered. Pinning the height makes every panel behave like the left
        rail: nothing resizes, the dock simply rides over the top.
        """
        body = self.query_one("#body")
        body.styles.height = max(1, self.size.height - 1 - BASE_DOCK_ROWS)

    def fit_padding(self) -> None:
        """
        Pad each panel clear of its own ornament.

        A fixed padding cannot work: the ornament's reach in cells depends on
        the panel's size, because the sheet resolution cap changes the cell
        scale. At 3 cells of padding the collapsed console was fine and the
        focus-mode one had text sitting ~2 cells outside the scrim. Asking the
        backdrop how far the ornament actually reaches keeps content inside it
        at any size.
        """
        for widget in self.query(".frame"):
            region = widget.region
            if region.width < 2 or region.height < 2:
                continue
            horizontal, vertical = backdrop.ornament_cells(region.width, region.height)
            # The border already occupies one cell, so padding covers the rest.
            widget.styles.padding = (
                max(1, vertical - 1),
                max(1, horizontal - 1),
            )

    def panel_rects(self):
        """
        Cell rectangles the scrims cover.

        Framed panels only — the prompt is opaque and covers the backdrop on
        its own, so scrimming behind it would be wasted work.
        """
        rects = []
        for selector in (".frame",):
            for widget in self.query(selector):
                region = widget.region
                if region.width > 0 and region.height > 0:
                    rects.append((region.x, region.y, region.width, region.height))
        return rects

    def settle_layout(self) -> None:
        """Repaint the placements against the settled geometry."""
        self.call_after_refresh(self._paint_backdrop)

    def _sheen_phase_frame(self, count):
        """Map the shared phase onto a frame index of `count`."""
        return int(self._sheen_phase * count) % count

    def pulse(self, cold=(122, 66, 0), hot=(255, 176, 64)):
        """Breathe between two colours on the shared phase, as a smooth ramp."""
        import math
        t = (math.sin(self._sheen_phase * math.tau) + 1) / 2
        r, g, b = (int(round(c + (h - c) * t)) for c, h in zip(cold, hot))
        return f"rgb({r},{g},{b})"

    def advance_sheen(self) -> None:
        """One step of the highlight sweep. Only two short lines re-render."""
        self._sheen_phase = (self._sheen_phase + SHEEN_STEP) % 1.0
        try:
            self.refresh_header()
            self.refresh_hint()
        except NoMatches:
            # The timer can outlive the widget tree during shutdown.
            pass

    def on_text_area_changed(self, event) -> None:
        self.resize_prompt()

    def resize_prompt(self) -> None:
        """
        Grow the prompt to fit its wrapped text, up to a cap.

        The dock is bottom-docked, so adding rows pushes its top edge upward and
        the body above simply yields the space.
        """
        area = self.query_one("#chat_input", PromptArea)
        width = area.size.width
        if width <= 0:
            return

        needed = area.get_content_height(self.size, self.size, width)
        rows = max(1, min(PROMPT_MAX_LINES, needed))
        if rows == self._prompt_rows:
            return
        self._prompt_rows = rows

        # Set directly rather than eased. Height is quantised to whole rows, so
        # a 1 -> 5 row change has only four possible intermediate states however
        # long it is given; easing does not smooth that, it just spreads four
        # hard jumps over 180ms and makes each one easier to see. Snapping and
        # repainting the scrims in the same frame reads cleaner.
        dock = self.query_one("#input_dock")
        area.styles.height = rows + 2
        dock.styles.height = rows + 4
        self.call_after_refresh(self.settle_layout)

    def log_write(self, item) -> None:
        """
        Write to the console and remember it, so it can be replayed later.

        `expand=True` matters: RichLog otherwise renders each item at its own
        measured width and never stretches it to the console, so widening the
        panel changed nothing at all. With expand the panels fill the available
        width and long replies wrap across it instead of running down the page.
        """
        self.transcript.append(item)
        # Bounded, or a long session keeps every renderable alive purely so it
        # can be replayed. Older lines scroll out of reach long before this.
        if len(self.transcript) > TRANSCRIPT_LIMIT:
            del self.transcript[:-TRANSCRIPT_LIMIT]
        self.query_one("#chat_log", RichLog).write(item, expand=True)

    def log_clear(self) -> None:
        self.transcript.clear()
        self.query_one("#chat_log", RichLog).clear()

    def log_replay(self) -> None:
        """Re-render the whole transcript at the console's current width."""
        log = self.query_one("#chat_log", RichLog)
        log.clear()
        for item in self.transcript:
            log.write(item, expand=True)

    def action_toggle_chat(self) -> None:
        """
        Give the console the whole window, or hand the space back.

        This reflows the layout rather than floating a panel over it. Floating
        was tried and lost on three counts: a translucent sheet over her read as
        a ghost, RichLog renders its lines to strips at write time so old
        content never re-wrapped to the new width, and lifting the frame onto an
        overlay layer freed its slot so the ledger jumped up the rail. Hiding
        the other columns instead means Textual reflows everything properly and
        no z-index games are needed.
        """
        self.chat_expanded = not self.chat_expanded

        # Snapped, not eased. Animating the rail widths was tried and measured:
        # every frame costs a full relayout and repaint of the tree — five
        # framed panels, the RichLog and the TextArea — at a median of 289ms
        # against a 33ms budget, 16 frames out of 16 over. The "animation" was
        # really one or two long stalls, which is why it read as blocking. In a
        # TUI colour and glyphs are cheap to animate; layout is not.
        for selector in ("#left_rail", "#center", "#ledger_frame"):
            self.query_one(selector).display = not self.chat_expanded

        rail = self.query_one("#right_rail")
        rail.styles.width = "1fr" if self.chat_expanded else RAIL_WIDTH

        # She is a kitty placement, not a widget, so hiding the centre column
        # does not remove her — she has to be deleted explicitly or she would
        # sit behind the expanded console.
        if self.chat_expanded:
            backdrop.clear_portrait()

        self.refresh_hint()
        # Replay after layout, so lines re-wrap to the new column count —
        # wide messages then occupy far fewer rows.
        self.call_after_refresh(self.log_replay)
        self.call_after_refresh(self.settle_layout)

    def _paint_backdrop(self) -> None:
        """
        Redraw both kitty placements from the current layout.

        Geometry is read after layout rather than hardcoded, so everything
        tracks a resize. The centre column is deliberately absent from the scrim
        list — she stands on the photograph itself.
        """
        # Framed panels only. The prompt used to be in this list, which is why it
        # wore the same pale scrim as everything else — it gets an opaque black
        # slab instead, below.
        scrims = []
        for widget in self.query(".frame"):
            region = widget.region
            if region.width > 0 and region.height > 0:
                scrims.append((region.x, region.y, region.width, region.height))
        backdrop.draw(self.size.width, self.size.height)
        backdrop.draw_scrims(tuple(scrims))
        self.fit_padding()

        prompt = self.query_one("#chat_input").region
        if prompt.width > 1 and prompt.height > 0:
            backdrop.draw_slab(prompt.x, prompt.y, prompt.width, prompt.height)

        if not backdrop.supported() or self.chat_expanded:
            return
        try:
            centre = self.query_one("#center").region
        except Exception:
            return

        # Width drives the size; height falls out of the source aspect and is
        # allowed to exceed the screen, which is the whole point — kitty clips at
        # the edge, so her legs pass behind the dock rather than stopping at it.
        aspect = portrait_aspect()
        width = max(20, min(centre.width - 2, PORTRAIT_MAX_COLS))
        rows = max(1, round(width / (aspect * backdrop.CELL_ASPECT)))
        x = centre.x + (centre.width - width) // 2
        backdrop.draw_portrait(portrait_path(), x, 1, width, rows, PORTRAIT_SHIFT_ROWS)

    def on_resize(self, event) -> None:
        # draw() no-ops unless the cell grid actually changed.
        self.call_after_refresh(self._paint_backdrop)

    def on_unmount(self) -> None:
        backdrop.clear()
        backdrop.clear_portrait()
        backdrop.clear_slab()

    @work(thread=True)
    def load_rates(self) -> None:
        """Off the event loop: one cached lookup, network only on a cache miss."""
        rates = pricing.get_rates(self.project_path, self.brain.model_name)
        self.rates = rates
        self.call_from_thread(self.refresh_gauges)
        self.call_from_thread(self.refresh_ledger)

    def on_resize(self, event) -> None:
        self.freeze_body()
        self.settle_layout()

    def tick_gauges(self) -> None:
        self.telemetry = sample_system()
        self.refresh_gauges()
        self.refresh_header()
        self.refresh_status()

    def tick_spinner(self) -> None:
        if self.graph.active:
            self.spinner_frame = (self.spinner_frame + 1) % len(SPINNER)
            self.refresh_graph()

    def refresh_all(self) -> None:
        self.refresh_header()
        self.refresh_status()
        self.refresh_graph()
        self.refresh_gauges()
        self.refresh_ledger()
        self.refresh_hint()

    # ----------------------------------------------------------
    # HEADER + CENTRE
    # ----------------------------------------------------------
    def refresh_header(self) -> None:
        project = os.path.basename(self.project_path.rstrip("/")) or "workspace"
        line = sheen("◈ ZANI_HARNESS", SHEEN_HEADER, self._sheen_phase)
        line.append("  ::  ", style=Style(color=DIM, bold=True))
        line.append(project, style=Style(color=TEXT, bold=True))
        line.append("   //  ", style=Style(color=DIM, bold=True))
        line.append(f"{self.mode.upper()}_MODE", style=Style(color=VIOLET, bold=True))
        line.append("   //  ", style=Style(color=DIM, bold=True))
        line.append(now_stamp(), style=Style(color=DIM, bold=True))
        self.query_one("#header", Static).update(line)

    def refresh_caption(self) -> None:
        accent = MAGENTA if self.mode == "act" else CYAN
        self.query_one("#caption", Static).update(
            Align.center(
                Group(
                    Text("反逆者", style=f"bold {accent}"),
                    Text("REBEL SOUL", style=f"bold {VIOLET}"),
                    Text("no rules · just me", style=DIM),
                )
            )
        )

    # ----------------------------------------------------------
    # AGENT STATUS
    # ----------------------------------------------------------
    def refresh_status(self) -> None:
        used = self.orchestrator._history_tokens()
        pct = min(100.0, used / MAX_HISTORY_TOKENS * 100)
        colour = GREEN if pct < 50 else AMBER if pct < 80 else RED
        mode_colour = MAGENTA if self.mode == "act" else CYAN

        model = self.brain.model_name
        if len(model) > 24:
            model = "…" + model[-23:]

        self.query_one("#status_body", Static).update(
            f"[{DIM}]MODE[/]      [{mode_colour}]{self.mode.upper()}[/]"
            f"  [{DIM}]({'tools live' if self.mode == 'act' else 'tools held'})[/]\n"
            f"[{DIM}]MEMORY[/]    {bar(pct, 14, colour)} [{colour}]{pct:4.1f}%[/]\n"
            f"[{DIM}]          {human_tokens(used)} / {human_tokens(MAX_HISTORY_TOKENS)} ctx[/]\n"
            f"[{DIM}]MODEL[/]     [{VIOLET}]{model}[/]\n"
            f"[{DIM}]PROVIDER[/]  [{DIM}]{self.brain.provider}[/]"
        )

    # ----------------------------------------------------------
    # TOOL EXECUTION GRAPH
    # ----------------------------------------------------------
    def refresh_graph(self) -> None:
        body = self.query_one("#graph_body", Static)

        if not self.graph.calls:
            body.update(
                f"[{DIM}]idle — no tools this turn[/]\n\n"
                f"[{DIM}]the chain builds here as[/]\n"
                f"[{DIM}]zani works, and resets on[/]\n"
                f"[{DIM}]every new prompt.[/]"
            )
            return

        lines = []
        for index, call in enumerate(self.graph.calls):
            glyph, label, colour, _ = describe(call.name)

            if call.status == RUNNING:
                mark = f"[{AMBER}]{SPINNER[self.spinner_frame]}[/]"
                timing = ""
            elif call.status == OK:
                mark = f"[{GREEN}]✓[/]"
                timing = f"[{DIM}]{call.duration:.1f}s[/]" if call.duration else ""
            else:
                mark = f"[{RED}]✗[/]"
                timing = f"[{DIM}]{call.duration:.1f}s[/]" if call.duration else ""

            lines.append(f" {glyph} [{colour}]{label:<10}[/] {mark} {timing}")
            if call.detail:
                lines.append(f"    [{DIM}]{call.detail[:24]}[/]")
            if index < len(self.graph.calls) - 1:
                lines.append(f"    [{BORDER}]│[/]")

        ok, err = self.graph.counts()
        lines.append("")
        lines.append(f"[{DIM}]turn {self.graph.turn} · {ok} ok · {err} err[/]")
        body.update("\n".join(lines))

    # ----------------------------------------------------------
    # RESOURCE GAUGES
    # ----------------------------------------------------------
    def refresh_gauges(self) -> None:
        t = self.telemetry

        cpu = t["cpu"]
        ram = t["ram_percent"]
        batt = t["battery"]

        if batt is None:
            batt_line = f"[{DIM}]BATTERY[/]  [{DIM}]no battery[/]"
        else:
            bcolour = GREEN if batt > 40 else AMBER if batt > 15 else RED
            plug = f" [{CYAN}]⚡[/]" if t["plugged"] else ""
            batt_line = f"[{DIM}]BATTERY[/]  {bar(batt, 10, bcolour)} [{bcolour}]{batt:3.0f}%[/]{plug}"

        total_in = self.usage.total_input
        total_out = self.usage.total_output
        cost = pricing.cost_of(self.rates, total_in, total_out)

        if self.rates:
            rate_line = (
                f"[{DIM}]RATE[/]     [{DIM}]in ${self.rates['prompt'] * 1_000_000:.2f}/M · "
                f"out ${self.rates['completion'] * 1_000_000:.2f}/M[/]"
            )
        else:
            rate_line = f"[{DIM}]RATE[/]     [{DIM}]unpriced model[/]"

        self.query_one("#gauges_body", Static).update(
            f"[{DIM}]CPU[/]      {bar(cpu, 10, CYAN)} [{CYAN}]{cpu:3.0f}%[/]\n"
            f"[{DIM}]RAM[/]      {bar(ram, 10, VIOLET)} [{VIOLET}]{ram:3.0f}%[/]\n"
            f"[{DIM}]         {t['ram_used_gb']:.1f}G / {t['ram_total_gb']:.1f}G[/]\n"
            f"{batt_line}\n"
            f"[{BORDER}]{'─' * 32}[/]\n"
            f"[{DIM}]TOKENS IN [/] [{CYAN}]{human_tokens(total_in):>8}[/]\n"
            f"[{DIM}]TOKENS OUT[/] [{MAGENTA}]{human_tokens(total_out):>8}[/]\n"
            f"[{DIM}]API CALLS [/] [{TEXT}]{self.usage.calls:>8}[/]\n"
            f"[{DIM}]SPEND     [/] [{AMBER}]{pricing.format_cost(cost):>8}[/]\n"
            f"{rate_line}"
        )

    # ----------------------------------------------------------
    # SESSION LEDGER
    # ----------------------------------------------------------
    def refresh_ledger(self) -> None:
        lines = []

        if self._last_error:
            lines.append(f"[{RED}]⚠ api error[/]")
            lines.append(f"[{DIM}]{str(self._last_error)[:80]}[/]")
            lines.append("")

        if self.files_touched:
            lines.append(f"[{DIM}]FILES TOUCHED THIS SESSION[/]")
            for glyph, path, action in self.files_touched[-8:]:
                lines.append(f" {glyph} [{TEXT}]{path[:28]}[/] [{DIM}]{action}[/]")
            if len(self.files_touched) > 8:
                lines.append(f" [{DIM}]…+{len(self.files_touched) - 8} earlier[/]")
        else:
            lines.append(f"[{DIM}]FILES TOUCHED THIS SESSION[/]")
            lines.append(f" [{DIM}]nothing written yet[/]")

        session_cost = pricing.cost_of(self.rates, self.usage.session_input, self.usage.session_output)
        lines.append("")
        lines.append(f"[{BORDER}]{'─' * 40}[/]")
        lines.append(
            f"[{DIM}]session[/] [{CYAN}]{human_tokens(self.usage.session_input)}[/] in · "
            f"[{MAGENTA}]{human_tokens(self.usage.session_output)}[/] out · "
            f"[{AMBER}]{pricing.format_cost(session_cost)}[/]"
        )
        lines.append(f"[{DIM}]lifetime totals persist in .zani/usage.json[/]")

        self.query_one("#ledger_body", Static).update("\n".join(lines))

    def refresh_hint(self) -> None:
        chat = "shrink chat" if self.chat_expanded else "focus chat"
        speech = "speech off" if self.speaker.enabled else "speech"
        line = Text()
        if self.is_running_task:
            # Colour is a continuous domain, unlike row heights, so this can
            # genuinely ease: the glyph cycles while its hue breathes between
            # two ambers on the same clock as the sheen.
            glyph = SPINNER[self._sheen_phase_frame(len(SPINNER))]
            line.append(f"{glyph} working…", style=Style(color=self.pulse(), bold=True))
        else:
            line.append("ready", style=Style(color=GREEN, bold=True))
        line.append("  ")
        line.append_text(
            sheen(f"· ctrl+t mode · ctrl+f {chat} · ctrl+s {speech} · /clear · ctrl+c quit",
                  SHEEN_HINT, self._sheen_phase)
        )
        self.query_one("#hint", Static).update(line)

    # ----------------------------------------------------------
    # INPUT
    # ----------------------------------------------------------
    def action_toggle_speech(self) -> None:
        """Turn speech on or off. Silences anything mid-sentence on the way out."""
        from core.speech import available

        if not self.speaker.enabled and not available():
            self.log_write(
                f"[{RED}]no audio player found — install mpv, ffplay or mpg123[/]"
            )
            return

        self.speaker.enabled = not self.speaker.enabled
        if not self.speaker.enabled:
            self.speaker.stop()

        state = "on" if self.speaker.enabled else "off"
        colour = GREEN if self.speaker.enabled else DIM
        self.log_write(
            f"[{DIM}][{now_stamp()}][/] [{CHAT_ZANI}]zani[/] [{DIM}]>[/] "
            f"speech [{colour}]{state}[/]"
            + (f"[{DIM}] · voice {self.speaker.voice}[/]" if self.speaker.enabled else "")
        )
        self.refresh_hint()

    def action_toggle_mode(self) -> None:
        self.set_mode("chat" if self.mode == "act" else "act")

    def set_mode(self, mode) -> None:
        if mode not in ("chat", "act") or mode == self.mode:
            return
        self.mode = mode
        self.refresh_caption()
        self.refresh_status()
        self.refresh_header()
        self.log_write(
            f"[{DIM}][{now_stamp()}][/] [{CHAT_ZANI}]zani[/] [{DIM}]>[/] mode → "
            f"[{MAGENTA if mode == 'act' else CYAN}]{mode.upper()}[/]"
            f"[{DIM}] ({'tools live' if mode == 'act' else 'tools withheld'})[/]"
        )

    async def on_prompt_area_submitted(self, message: PromptArea.Submitted) -> None:
        prompt = message.value.strip()
        if not prompt or self.is_running_task:
            return

        self.query_one("#chat_input", PromptArea).text = ""
        self.resize_prompt()
        log = self.query_one("#chat_log", RichLog)

        if prompt.startswith("/"):
            self.handle_command(prompt, log)
            return

        self.is_running_task = True
        self.refresh_hint()

        self.graph.reset()
        self.refresh_graph()

        self.log_write("")
        self.log_write(f"[{DIM}][{now_stamp()}][/] [{CHAT_USER}]user[/] [{DIM}]>[/] {prompt}")
        await asyncio.sleep(0)

        self.run_orchestration(prompt)

    def handle_command(self, prompt, log) -> None:
        parts = prompt.split()
        command = parts[0].lower()

        if command == "/mode":
            if len(parts) > 1 and parts[1].lower() in ("chat", "act"):
                self.set_mode(parts[1].lower())
            else:
                self.log_write(f"[{DIM}]usage: /mode chat|act[/]")
        elif command == "/tts":
            wanted = parts[1].lower() if len(parts) > 1 else None
            if wanted in ("on", "off"):
                if (wanted == "on") != self.speaker.enabled:
                    self.action_toggle_speech()
            elif wanted is None:
                self.action_toggle_speech()
            else:
                self.log_write(f"[{DIM}]usage: /tts on|off[/]")
        elif command == "/clear":
            self.log_clear()
            self.log_write(f"[{DIM}]console cleared — agent history untouched[/]")
        else:
            self.log_write(f"[{DIM}]unknown command: {command} (try /mode, /tts or /clear)[/]")

    # ----------------------------------------------------------
    # ORCHESTRATION
    # ----------------------------------------------------------
    def on_agent_event(self, kind, **data) -> None:
        """Structured events from the orchestrator, on the event loop."""
        if kind == "turn_start":
            self.graph.reset()
        elif kind == "tool_start":
            args = data.get("args") or {}
            detail = ""
            if isinstance(args, dict):
                detail = str(args.get("path") or args.get("query") or args.get("command") or "")
            call = self.graph.start(data["name"], detail)
            if data["name"] in ("write_file", "edit_file") and detail:
                glyph, _, _, _ = describe(data["name"])
                self.files_touched.append((glyph, detail, "written"))
                self.refresh_ledger()
            self.refresh_graph()
        elif kind == "tool_end":
            self.graph.finish(ok=data.get("ok", True))
            self.refresh_graph()
        elif kind == "usage":
            self.usage.record(data.get("input", 0), data.get("output", 0))
            self.refresh_gauges()
            self.refresh_ledger()
        elif kind == "api_error":
            self._last_error = data.get("error")
            self.refresh_ledger()

    @work(exclusive=True, thread=False)
    async def run_orchestration(self, prompt: str) -> None:
        log = self.query_one("#chat_log", RichLog)

        runtime_block = (
            "\n\n[ZANI RUNTIME MODE]\n"
            f"mode = {self.mode.upper()}\n"
            f"tools_enabled = {'true' if self.mode == 'act' else 'false'}\n"
            "If tools_enabled=false do not call tools.\n"
            "If tools_enabled=true you may call tools multiple times to complete the user request.\n"
        )

        try:
            await self.orchestrator.orchestration_loop(
                prompt + runtime_block,
                self.brain.llm_api_caller,
                ui_callback=self._write_to_log,
                event_cb=self.on_agent_event,
                tools_enabled=(self.mode == "act"),
            )
        except Exception as error:
            self.log_write(f"[{RED}][{now_stamp()}] system > {error}[/]")
        finally:
            self.is_running_task = False
            self.refresh_hint()
            self.refresh_status()
            self.refresh_graph()

    @work(exclusive=True, thread=True)
    def speak_reply(self, text: str) -> None:
        """
        Synthesis runs ~2x realtime, so it goes on a thread.

        `exclusive` means a new reply pre-empts one still being spoken rather
        than queueing behind it — stale narration is worse than none.
        """
        problem = self.speaker.speak(text)
        if problem and problem != self.speaker.last_error:
            self.speaker.last_error = problem
            self.call_from_thread(
                self.log_write, f"[{RED}][{now_stamp()}] speech > {problem}[/]"
            )

    def _write_to_log(self, text=None, panel_content=None, title=None, style=None,
                      is_markdown=False, is_syntax=False, language="json") -> None:
        if panel_content:
            if is_markdown:
                content = Markdown(panel_content)
            elif is_syntax:
                content = Syntax(panel_content, language, theme="monokai",
                                 background_color="default", line_numbers=False)
            else:
                content = panel_content

            # Only the finished reply is spoken — tool panels and progress
            # lines are noise out loud, and each one would be billed.
            if is_markdown and self.speaker.enabled:
                self.speak_reply(panel_content)

            # Stored as a renderable rather than pre-rendered text, so a replay
            # re-wraps it to whatever width the console currently has.
            self.log_write(
                Panel(
                    content,
                    title=f"[{CHAT_ZANI}]{title or 'zani'}[/]",
                    border_style=CHAT_ZANI,
                    padding=(0, 1),
                )
            )
        elif text:
            self.log_write(text)


async def launch_tui(brain, orchestrator, project_path=None, profile="base"):
    if profile == "base":
        from core.base_tui import BaseTUI
        app = BaseTUI(brain, orchestrator, project_path)
    else:
        app = ZaniTUI(brain, orchestrator, project_path)
    await app.run_async()
