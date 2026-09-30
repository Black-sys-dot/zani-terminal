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

console = Console()


def load_config():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "config", "settings.yaml")
    if not os.path.exists(path):
        return {}
    return yaml.safe_load(open(path, "r"))


def _apply_env_file(path):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass


def load_env_file(project_dir=None):
    """Install `.env` then project `.zani.env` (later entries override)."""
    install_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if project_dir is None:
        project_dir = os.getcwd()
    project_env = os.path.join(project_dir, ".zani.env")

    for path in (install_env, project_env):
        _apply_env_file(path)


def ensure_project_zani_env(project_dir, api_key_env):
    """Create `.zani.env` with an empty key line when the project has none yet."""
    path = os.path.join(project_dir, ".zani.env")
    if os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{api_key_env}=\n")
        console.print(f"[dim]Created {path} — add your API key there if needed.[/dim]")
    except OSError as exc:
        console.print(f"[yellow]Could not create {path}: {exc}[/yellow]")


def resolve_model_settings(cfg):
    provider = cfg.get("model", {}).get("provider", "google").lower()
    if provider == "openrouter":
        api_key_env = cfg.get("model", {}).get("openrouter_key_env", "OPENROUTER_KEY")
        model_name = cfg.get("model", {}).get("openrouter_model", "google/gemma-4-31b-it")
    else:
        api_key_env = cfg.get("model", {}).get("api_key_env", "GOOGLE_API_KEY")
        model_name = cfg.get("model", {}).get("google_model", "gemini-3-flash-preview")
    return provider, api_key_env, model_name


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

    if os.path.isabs(command) and os.path.exists(command):
        return command
    if shutil.which(command):
        return command

    console.print(
        f"[yellow]LSP server '{command}' not found — continuing without LSP code "
        "intelligence (global search still works).[/yellow]"
    )
    return None


async def run_tui(brain, args):
    from core.tui import launch_tui

    target_project = os.getcwd()
    lsp_command = detect_lsp_command(target_project)
    harness_mode = bool(args.zani)

    orchestrator = ZaniMCPOrchestrator(
        target_project, lsp_command, harness_mode=harness_mode
    )
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
    sub = parser.add_subparsers(dest="cmd", required=True)

    tui_parser = sub.add_parser("tui", help="Launch the Zani terminal UI")
    tui_parser.add_argument(
        "--zani",
        action="store_true",
        help="Full Zani visual profile (default: base TUI without character harness)",
    )

    args = parser.parse_args()

    cfg = load_config()
    provider, api_key_env, model_name = resolve_model_settings(cfg)
    project_dir = os.getcwd()

    if args.cmd == "tui":
        ensure_project_zani_env(project_dir, api_key_env)

    load_env_file(project_dir)

    api_key = os.getenv(api_key_env)
    if not api_key:
        project_env = os.path.join(project_dir, ".zani.env")
        install_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        sys.exit(
            f"Missing API key for provider '{provider}'. "
            f"Set {api_key_env} in {project_env}, {install_env}, or your shell environment."
        )

    brain = ZaniBrain(api_key, model_name, provider=provider)

    if args.cmd == "tui":
        asyncio.run(run_tui(brain, args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
