import argparse
import os
import json
import sys
import yaml

from google.genai import types

from core.safety_layers import SafetyShield
from core.memory import MemoryManager
from core.tools import AVAILABLE_TOOLS
from core.cache_manager import CacheManager
from core.zani_brain import ZaniBrain

from core.project_state import (
    scan_project,
    diff_projects,
    compute_change_magnitude
)

from core.registry_manager import RegistryManager
from core.rebake_engine import rebake_decision, compute_expiry

from core.visuals import (
    show_init,
    show_threshold,
    show_cache_maker,
    show_chat,
    show_act
)


# ==============================
# ✨ RICH UI
# ==============================
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


GENESIS_MARKER = "--- INITIAL CODEBASE SNAPSHOT ---"

SUMMARY_THRESHOLD_TOKENS = 3000
RECENT_KEEP_RATIO = 0.25


# ==============================================================
# CONFIG LOADING
# ==============================================================

def load_config():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "config", "settings.yaml")
    if not os.path.exists(path):
        return {}
    return yaml.safe_load(open(path, "r"))


# ==============================================================
# PROJECT SNAPSHOT
# ==============================================================

def build_project_context():
    shield = SafetyShield()
    files = sorted(shield.scan_workspace(os.getcwd()))
    files = [f for f in files if not f.startswith(".zani")]

    context = GENESIS_MARKER + "\n"
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as file:
                context += f"\nFile: {f}\n```\n{file.read()}\n```\n"
        except Exception:
            pass

    return context, files


# ==============================================================
# GENESIS SPLIT
# ==============================================================

def split_history_genesis(history):
    if not history:
        return None, []

    first = history[0]["parts"][0]["text"]
    if GENESIS_MARKER in first:
        return history[0], history[1:]
    return None, history


# ==============================================================
# TOKEN ESTIMATION
# ==============================================================

def estimate_project_tokens(files):
    cm = CacheManager()
    return cm.estimate_tokens(files)


def estimate_history_tokens(memory):
    history = memory.load_history()
    _, convo = split_history_genesis(history)
    total_chars = len(json.dumps(convo))
    return total_chars // 4


# ==============================================================
# HISTORY SUMMARIZATION
# ==============================================================

def maybe_summarize_history(memory, brain):
    history = memory.load_history()
    genesis, convo = split_history_genesis(history)

    if not convo:
        return

    protected = []
    summarizable = []

    for m in convo:
        text = m["parts"][0]["text"]

        if memory.is_file_update(text):
            protected.append(m)
        elif memory.is_summary(text):
            protected.append(m)
        else:
            summarizable.append(m)

    token_est = len(json.dumps(summarizable)) // 4

    if token_est < SUMMARY_THRESHOLD_TOKENS:
        return

    console.print("\n[bold yellow]⚠ History exceeds threshold. Compressing...[/bold yellow]")

    keep_n = max(2, int(len(summarizable) * RECENT_KEEP_RATIO))
    old_block = summarizable[:-keep_n]
    recent_block = summarizable[-keep_n:]

    text_to_summarize = "\n".join(
        f"{m['role']}: {m['parts'][0]['text']}"
        for m in old_block
    )

    summary_prompt = (
        "Summarize the following conversation.\n"
        "Preserve:\n"
        "- decisions made\n"
        "- file changes\n"
        "- architectural modifications\n"
        "Be concise but technically accurate.\n\n"
        + text_to_summarize
    )

    session = brain.start_session([], None)
    resp = session.send_message(summary_prompt)
    summary_text = resp.text or "Summary unavailable."

    new_history = []

    if genesis:
        new_history.append(genesis)

    new_history.extend(protected)

    new_history.append({
        "role": "system",
        "parts": [{
            "text": "Conversation summary:\n" + summary_text
        }]
    })

    new_history.extend(recent_block)

    memory._write(new_history)

    console.print("[bold green]✓ History compressed[/bold green]\n")


# ==============================================================
# HISTORY PREPARATION
# ==============================================================

def get_prepared_history(memory, active_cache):
    history = memory.load_history()

    if not history and not active_cache:
        ctx, _ = build_project_context()
        memory.save_genesis_block(ctx)
        history = memory.load_history()

    genesis, convo = split_history_genesis(history)

    if active_cache:
        history_to_send = convo
    else:
        history_to_send = history

    prepared = []

    for h in history_to_send:
        role = h["role"]
        if role not in ("user", "model"):
            role = "user"

        parts = [types.Part(text=p["text"]) for p in h["parts"]]
        prepared.append(types.Content(role=role, parts=parts))

    return prepared


# ==============================================================
# TOKEN RECEIPT (PRETTY)
# ==============================================================

def print_receipt(usage, model):
    in_t = getattr(usage, 'prompt_token_count', 0) or 0
    out_t = getattr(usage, 'candidates_token_count', 0) or 0
    cached = getattr(usage, 'cached_content_token_count', 0) or 0

    table = Table(box=box.ROUNDED, title=f"{model.upper()} TOKEN USAGE")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Input", str(in_t))
    table.add_row("Output", str(out_t))
    table.add_row("Cached", str(cached))
    table.add_row("Cache Status", "HIT" if cached else "MISS")

    console.print()
    console.print(table)
    console.print()


# ==============================================================
# TOOL EXECUTION
# ==============================================================

def execute_tools(response, memory, act_mode):

    if not response.candidates:
        return

    content = response.candidates[0].content
    if not content or not content.parts:
        return

    tool_calls_found = False

    for part in content.parts:

        if not part.function_call:
            continue

        tool_calls_found = True
        call = part.function_call

        console.print(Panel(
            f"[bold]MODEL REQUESTED TOOL[/bold]\n{call.name}",
            border_style="magenta"
        ))

        if not act_mode:
            console.print("[red]⚠ Tool execution blocked (CHAT MODE)[/red]")
            memory.save_turn(
                "user",
                f"BLOCKED TOOL CALL {call.name} {call.args}"
            )
            continue

        if input("confirm? (y/n): ").lower() != "y":
            continue

        result = AVAILABLE_TOOLS[call.name](**call.args)

        if call.name == "write_to_file":
            memory.save_file_update(
                call.args["filename"],
                call.args["content"]
            )

        memory.save_turn("model", f"TOOL CALL {call.name} {call.args}")
        memory.save_turn("user", f"TOOL RESULT {result}")

    if not tool_calls_found:
        console.print("[dim]No tool calls in response.[/dim]")


# ==============================================================
# CACHE CHECK
# ==============================================================

def check_cache_and_project(brain, cfg):
    registry_mgr = RegistryManager()
    registry = registry_mgr.load()

    context, files = build_project_context()
    project_tokens = estimate_project_tokens(files)

    if not registry:

        if project_tokens >= cfg["explicit_cache"]["min_tokens"]:
            show_threshold()
            console.print(Rule("EXPLICIT CACHE THRESHOLD REACHED"))
            console.print(f"Project tokens: [cyan]{project_tokens}[/cyan]")
            console.print(f"Threshold: [cyan]{cfg['explicit_cache']['min_tokens']}[/cyan]\n")

            if input("Create explicit cache now? (y/n): ").lower() == "y":
                show_cache_maker()
                cache = brain.create_explicit_cache(
                    context,
                    cfg["explicit_cache"]["ttl_hours"]
                )

                new_hashes, new_total, new_sizes = scan_project(os.getcwd(), files)

                registry_mgr.save({
                    "cache_id": cache.name,
                    "file_hashes": new_hashes,
                    "file_sizes": new_sizes,
                    "total_project_bytes": new_total,
                    "ttl_expiry": compute_expiry(cfg["explicit_cache"]["ttl_hours"])
                })

                console.print(f"[bold green]✓ Explicit cache active[/bold green]: {cache.name}")
                return cache.name, context

        return None, context

    old_hashes = registry.get("file_hashes", {})
    old_sizes = registry.get("file_sizes", {})
    total_old_bytes = registry.get("total_project_bytes", 0)
    ttl_expiry = registry.get("ttl_expiry")

    new_hashes, new_total, new_sizes = scan_project(os.getcwd(), files)
    added, modified, deleted = diff_projects(old_hashes, new_hashes)

    changed_bytes, percent, changed_tokens = compute_change_magnitude(
        added, modified, deleted,
        new_sizes, old_sizes, total_old_bytes
    )

    registry_expired = False
    if ttl_expiry:
        from datetime import datetime, timezone
        registry_expired = datetime.now(timezone.utc).isoformat() > ttl_expiry

    decision, reason = rebake_decision(
        percent,
        changed_tokens,
        added,
        modified,
        deleted,
        cfg["explicit_cache"],
        registry_expired
    )

    if decision in ("recommend", "force"):

        style = "red" if decision == "force" else "yellow"
        show_threshold()
        console.print(Panel(
            f"{'CRITICALLY OUTDATED' if decision=='force' else 'UPDATE RECOMMENDED'}\n"
            f"Reason: {reason}",
            border_style=style
        ))

        console.print(f"Project change: {percent:.2f}%")
        console.print(f"Changed tokens: {changed_tokens}\n")

        if input("Rebuild explicit cache now? (y/n): ").lower() == "y":

            console.print("[yellow]Rebuilding cache...[/yellow]")
            brain.terminate_cache(registry["cache_id"])
            show_cache_maker()
            cache = brain.create_explicit_cache(
                context,
                cfg["explicit_cache"]["ttl_hours"]
            )

            registry_mgr.save({
                "cache_id": cache.name,
                "file_hashes": new_hashes,
                "file_sizes": new_sizes,
                "total_project_bytes": new_total,
                "ttl_expiry": compute_expiry(cfg["explicit_cache"]["ttl_hours"])
            })

            console.print(f"[bold green]✓ Explicit cache rebuilt[/bold green]: {cache.name}")
            return cache.name, context
        else:
            console.print("[dim]Continuing with existing cache.[/dim]")

    return registry.get("cache_id"), context


# ==============================================================
# RUN
# ==============================================================

def handle_run(brain, prompt, cfg, act=False):
    memory = MemoryManager()

    maybe_summarize_history(memory, brain)

    cache_id, _ = check_cache_and_project(brain, cfg)
    history = get_prepared_history(memory, cache_id)
    session = brain.start_session(history, cache_id)

    if act:
        show_act()
    else:
        show_chat()

    mode_label = "ACT" if act else "CHAT"
    tools_enabled = "true" if act else "false"

    runtime_block = (
        "\n\n[ZANI RUNTIME MODE]\n"
        f"mode = {mode_label}\n"
        f"tools_enabled = {tools_enabled}\n"
        "If tools_enabled=false do not call tools.\n"
        "If tools_enabled=true you may call tools multiple times.\n"
        "Update all required files in one turn when modifying project.\n"
    )

    final_prompt = prompt + runtime_block

    response = session.send_message(final_prompt)
    memory.save_turn("user", final_prompt)

    if act:
        execute_tools(response, memory, True)
    else:
        console.print(
            Panel(
                Markdown(response.text or "No response."),
                title="ZANI RESPONSE",
                border_style="bright_magenta",
                padding=(1, 2)
            )
        )
        memory.save_turn("model", response.text)

    print_receipt(response.usage_metadata, brain.model_name)

    context, files = build_project_context()
    project_tokens = estimate_project_tokens(files)
    history_tokens = estimate_history_tokens(memory)

    stats = Table(box=box.ROUNDED, title="CONTEXT SIZE")
    stats.add_column("Type")
    stats.add_column("Tokens", justify="right")
    stats.add_row("Project", str(project_tokens))
    stats.add_row("History", str(history_tokens))
    console.print(stats)


# ==============================================================
# INIT / STOP / MAIN
# ==============================================================

def handle_init(brain, cfg):
    show_init()
    registry_mgr = RegistryManager()
    memory = MemoryManager()

    context, files = build_project_context()
    memory.clear_history()
    memory.save_genesis_block(context)

    project_tokens = estimate_project_tokens(files)

    console.print(Rule("ZANI WORKSPACE ASSESSMENT"))
    console.print(f"Files scanned: {len(files)}")
    console.print(f"Estimated project tokens: {project_tokens}")
    console.print("Genesis stored locally.\n")

    if project_tokens >= cfg["explicit_cache"]["min_tokens"]:
        if input("Create explicit cache? (y/n): ").lower() == "y":
            cache = brain.create_explicit_cache(
                context,
                cfg["explicit_cache"]["ttl_hours"]
            )

            new_hashes, new_total, new_sizes = scan_project(os.getcwd(), files)

            registry_mgr.save({
                "cache_id": cache.name,
                "file_hashes": new_hashes,
                "file_sizes": new_sizes,
                "total_project_bytes": new_total,
                "ttl_expiry": compute_expiry(cfg["explicit_cache"]["ttl_hours"])
            })

            console.print(f"[bold green]✓ Explicit cache active[/bold green]: {cache.name}")


def handle_stop(brain):
    registry = RegistryManager().load()
    if not registry:
        console.print("[yellow]No active cache.[/yellow]")
        return

    if input("Terminate cache? (y/n): ").lower() == "y":
        brain.terminate_cache(registry["cache_id"])
        RegistryManager().clear()
        console.print("[bold green]✓ Cache removed[/bold green]")


def main():
    cfg = load_config()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("Missing API key")

    brain = ZaniBrain(api_key, cfg["model"]["name"])

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init")
    sub.add_parser("stop")


    for c in ["chat", "act"]:
        p = sub.add_parser(c)
        p.add_argument("prompt", nargs='+')

    args = parser.parse_args()

    if args.cmd == "init":
        handle_init(brain, cfg)
    elif args.cmd == "stop":
        handle_stop(brain)
    elif args.cmd == "chat":
        handle_run(brain, " ".join(args.prompt), cfg, act=False)
    elif args.cmd == "act":
        handle_run(brain, " ".join(args.prompt), cfg, act=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
