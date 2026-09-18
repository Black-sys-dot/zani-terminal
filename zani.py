#!/usr/bin/env python3
import argparse
import asyncio
import os
import shutil
import sys

import yaml
from rich.console import Console

from core.zani_brain import ZaniBrain
from core.mcp_orchestrator import ZaniMCPOrchestrator
from core.visuals import show_init, show_chat, show_act

console = Console()

# ==============================================================
# MODE GATING
# ==============================================================
# Only the TUI is active for now. Every other entry point is left intact
# below and simply refused at dispatch, so re-enabling one is a matter of
# removing its name from this set.
DISABLED_COMMANDS = {"init", "stop", "chat", "act"}

# ==============================================================
# CONFIG LOADING
# ==============================================================
def load_config():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "config", "settings.yaml")
    if not os.path.exists(path):
        return {}
    return yaml.safe_load(open(path, "r"))

def load_env_file():
    install_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    local_env = os.path.join(os.getcwd(), ".env")

    for path in (install_env, local_env):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            os.environ[key.strip()] = val.strip().strip('"').strip("'")
            except Exception:
                pass


def detect_lsp_command(target_project):
    """
    Pick an LSP server for the target project, degrading gracefully.

    Python is Zani's default ecosystem and its server ships with the install.
    Other languages need their server installed separately; when it is missing
    we return None and the filesystem server's global search still covers code
    navigation.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pylsp_path = os.path.join(base_dir, ".venv", "bin", "pylsp")

    command = pylsp_path if os.path.exists(pylsp_path) else "pylsp"

    try:
        files_in_root = set(os.listdir(target_project))
    except OSError:
        files_in_root = set()

    if any(f.endswith(".go") for f in files_in_root) or "go.mod" in files_in_root:
        command = "gopls"
    elif any(f.endswith(".rs") for f in files_in_root) or "Cargo.toml" in files_in_root:
        command = "rust-analyzer"
    elif any(f.endswith((".js", ".ts")) for f in files_in_root) or "package.json" in files_in_root:
        command = "typescript-language-server"
    elif any(f.endswith((".c", ".cpp")) for f in files_in_root) or "CMakeLists.txt" in files_in_root:
        command = "clangd"

    # Only the Python path is ever absolute; the rest are binary names that
    # must resolve on PATH.
    if os.path.isabs(command) and os.path.exists(command):
        return command
    if shutil.which(command):
        return command

    console.print(
        f"[yellow]LSP server '{command}' not found — continuing without LSP code "
        "intelligence (global search still works).[/yellow]"
    )
    return None


async def handle_run(brain, prompt, act=False):
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
        "If tools_enabled=true you may call tools multiple times to complete the user request.\n"
    )

    final_prompt = prompt + runtime_block

    target_project = os.getcwd()
    lsp_command = detect_lsp_command(target_project)

    orchestrator = ZaniMCPOrchestrator(target_project, lsp_command)

    try:
        console.print("[cyan]Initializing MCP Servers (Filesystem, LSP, Bash)...[/cyan]")
        await orchestrator.initialize_servers()

        # In CHAT mode we strip tools from the schema so the model can't act.
        if not act:
            orchestrator.tools_schema = []
            console.print("[yellow]Chat Mode: Tools disabled.[/yellow]")

        await orchestrator.orchestration_loop(final_prompt, brain.llm_api_caller)
    finally:
        await orchestrator.shutdown()


async def run_tui(brain, args):
    from core.tui import launch_tui

    target_project = os.getcwd()
    lsp_command = detect_lsp_command(target_project)

    orchestrator = ZaniMCPOrchestrator(target_project, lsp_command)
    try:
        console.print("[cyan]Initializing MCP Servers for TUI...[/cyan]")
        await orchestrator.initialize_servers()
        profile = "zani" if args.zani else "base"
        await launch_tui(brain, orchestrator, target_project, profile=profile)
    finally:
        await orchestrator.shutdown()


def main():
    parser = argparse.ArgumentParser(
        prog="zani",
        description="Agentic CLI terminal with project-aware reasoning.",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="(disabled)")
    sub.add_parser("stop", help="(disabled)")
    tui_parser = sub.add_parser("tui", help="Launch the Zani TUI - the only active mode")
    tui_parser.add_argument("--zani", action="store_true", help="Launch the Zani visual profile (default is base TUI)")

    for c in ["chat", "act"]:
        p = sub.add_parser(c, help="(disabled)")
        p.add_argument("prompt", nargs="+")

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        return

    if args.cmd in DISABLED_COMMANDS:
        console.print(
            f"[yellow]'{args.cmd}' is currently disabled.[/yellow] "
            "Only [bold]zani tui[/bold] is active right now."
        )
        return

    # Load config and credentials only after parsing, so `--help` and the
    # disabled-command notices never require an API key.
    load_env_file()
    cfg = load_config()

    provider = cfg.get("model", {}).get("provider", "google").lower()

    if provider == "openrouter":
        api_key_env = cfg.get("model", {}).get("openrouter_key_env", "OPENROUTER_KEY")
        model_name = cfg.get("model", {}).get("openrouter_model", "google/gemma-4-31b-it")
    else:
        api_key_env = cfg.get("model", {}).get("api_key_env", "GOOGLE_API_KEY")
        model_name = cfg.get("model", {}).get("google_model", "gemini-3-flash-preview")

    api_key = os.getenv(api_key_env)
    if not api_key:
        sys.exit(
            f"Missing API key for provider '{provider}'. "
            f"Set '{api_key_env}' or create a .env file next to the install or in the current directory."
        )

    brain = ZaniBrain(api_key, model_name, provider=provider)

    if args.cmd == "tui":
        asyncio.run(run_tui(brain, args))
    else:
        # init/stop/chat/act are gated above; re-enabling one only needs a branch here.
        parser.print_help()


if __name__ == "__main__":
    main()
