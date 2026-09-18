"""
Tool identity and the per-turn execution graph.

Every tool Zani can reach gets a glyph, a short label and a colour, so a call
chain stays readable at a glance inside a narrow rail. The graph is turn-scoped
on purpose: it clears the moment a new prompt starts, so the panel always shows
what Zani is doing *now* rather than an ever-growing log. The chat console is
where history belongs.

Unknown tools still render. A language server can expose whatever it likes, so
anything missing from the registry falls back to a neutral glyph rather than
breaking the panel.
"""

import time

# ==============================================================
# PALETTE — sandy blossom
# ==============================================================
# Names are historical. Values match core/tui.py: pulled dark and saturated so
# they survive against a bright photographic backdrop.
VIOLET = "#5d2f86"      # deep violet
CYAN = "#14606e"        # deep teal
MAGENTA = "#9c1f57"     # deep rose
AMBER = "#7d4a08"       # deep amber
GREEN = "#33601f"       # deep green
RED = "#8c1f24"         # deep red
DIM = "#5f4a43"         # dark taupe

# ==============================================================
# REGISTRY
# ==============================================================
# glyph, label shown in the graph, accent colour, owning server.
TOOL_REGISTRY = {
    # -- filesystem ------------------------------------------------
    "read_file":          ("📖", "read",      CYAN,    "filesystem"),
    "write_file":         ("🖊",  "write",     MAGENTA, "filesystem"),
    "list_directory":     ("📁", "list dir",  CYAN,    "filesystem"),
    "zani_global_search": ("🔎", "search",    VIOLET,  "filesystem"),
    # -- lsp -------------------------------------------------------
    "diagnostics":        ("🩺", "diagnose",  AMBER,   "lsp"),
    "edit_file":          ("✏",  "edit",      MAGENTA, "lsp"),
    "hover":              ("👁",  "inspect",   VIOLET,  "lsp"),
    "references":         ("🔗", "refs",      VIOLET,  "lsp"),
    "rename_symbol":      ("🏷",  "rename",    MAGENTA, "lsp"),
    # -- bash ------------------------------------------------------
    "run_bash_command":   ("⚡", "shell",     AMBER,   "bash"),
}

FALLBACK = ("🔧", "tool", DIM, "?")


def describe(tool_name):
    """glyph, label, colour, server for a tool. Never raises on unknown names."""
    glyph, label, colour, server = TOOL_REGISTRY.get(tool_name, FALLBACK)
    if tool_name not in TOOL_REGISTRY:
        # Keep the real name visible so an unregistered tool is obvious.
        label = tool_name[:12]
    return glyph, label, colour, server


# ==============================================================
# EXECUTION GRAPH
# ==============================================================
RUNNING = "running"
OK = "ok"
ERROR = "error"


class ToolCall:
    def __init__(self, name, detail=""):
        self.name = name
        self.detail = detail
        self.status = RUNNING
        self.started = time.monotonic()
        self.duration = None

    def finish(self, ok=True):
        self.status = OK if ok else ERROR
        self.duration = time.monotonic() - self.started


class ToolGraph:
    """
    Ordered record of the tool calls in the current turn.

    Reset at the start of every user prompt. `start` opens a node, `finish`
    closes the most recent open one — the orchestrator executes tool calls
    sequentially, so last-open is unambiguous.
    """

    def __init__(self):
        self.calls = []
        self.turn = 0

    def reset(self):
        self.calls = []
        self.turn += 1

    def start(self, name, detail=""):
        call = ToolCall(name, detail)
        self.calls.append(call)
        return call

    def finish(self, ok=True):
        for call in reversed(self.calls):
            if call.status == RUNNING:
                call.finish(ok)
                return call
        return None

    @property
    def active(self):
        return any(c.status == RUNNING for c in self.calls)

    def counts(self):
        ok = sum(1 for c in self.calls if c.status == OK)
        err = sum(1 for c in self.calls if c.status == ERROR)
        return ok, err
