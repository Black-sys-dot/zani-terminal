import os
import sys
import asyncio
import json
import shutil
from contextlib import AsyncExitStack

# Note: Requires `pip install mcp`
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from core.context_distiller import (
    distill_tool_arguments,
    distill_tool_result,
    estimate_tokens,
)
from core.context_summarizer import (
    LEDGER_MAX_ENTRIES,
    build_carryover,
    carryover_budget,
    summarize_conversation,
    summarize_tool_bodies,
)

# ==============================================================
# INTERNAL SYSTEM PROMPT
# ==============================================================
ZANI_SYSTEM_INSTRUCTIONS = """
You are Zani, a highly autonomous, self-correcting engineering assistant. You have full access to a Filesystem server, an LSP code intelligence server, and a live Bash execution environment.

Your operational pipeline must adhere to these rigid behavioral laws:
1. CODE NAVIGATION & COGNITIVE FALLBACKS: When trying to locate or analyze a function, variable, or class, always prioritize the LSP 'definition' or 'references' tool first. If the LSP returns an empty array [] or null (due to uncompiled code or dynamic types), you must immediately pivot. Invoke the Filesystem 'search_files' or text search tools to brute-force text match the keyword on disk.
2. COMPILER VERIFICATION: Every time you write or modify a file using filesystem tools, you are strictly required to call the LSP 'diagnostics' tool immediately afterward. Review any errors or warnings you introduced and patch them silently.
3. RUNTIME TESTING: You cannot consider a task complete just because the code looks correct. Once LSP diagnostics run clean, use the Bash executor to run the project's verification suite (e.g., 'npm test', 'pytest', or running the script directly). If the console logs a runtime crash, capture the stack trace, open the file, rewrite the fix, and test again. Loop until the terminal returns a success code.
4. DESTRUCTIVE SAFEGUARDS: You have raw command access, but you are forbidden from running dangerous paths (like rm -rf outside the workspace) or force-pushing Git branches without stopping the loop to ask the user for explicit confirmation.
"""

MAX_LOOP_ITERATIONS = 6
MAX_HISTORY_TOKENS = 500000

# Turns kept byte-identical. A turn is a user message plus every assistant and
# tool message that follows it, up to the next user message.
KEEP_RECENT_TURNS = 3

class ZaniMCPOrchestrator:
    def __init__(self, project_path: str, lang_server_command: str):
        self.project_path = os.path.abspath(project_path)
        self.lang_server_command = lang_server_command
        self.exit_stack = AsyncExitStack()
        self.sessions = {}
        self.tools_schema = []
        self.history = []

        # Compaction state. These survive across compactions and are refolded
        # into themselves each time, which is what keeps the carry-over block a
        # fixed size instead of a growing one.
        self.rolling_summary = ""
        self.body_digest = ""
        self.tool_ledger = []
        self.llm_caller = None

    async def initialize_servers(self):
        """Spins up the MCP servers (filesystem, bash, and optionally LSP)."""
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        python_exe = sys.executable
        
        fs_server_path = os.path.join(base_dir, "servers", "filesystem_server.py")
        bash_server_path = os.path.join(base_dir, "servers", "bash_server.py")
        
        # 1. Filesystem Server (Python)
        fs_params = StdioServerParameters(
            command=python_exe,
            args=[fs_server_path, self.project_path]
        )
        
        # 2. Bash Server (Python)
        bash_params = StdioServerParameters(
            command=python_exe,
            args=[bash_server_path]
        )

        servers = {"filesystem": fs_params}

        # 3. LSP Server (optional). Needs an external `mcp-language-server`
        # binary plus a language server for the project. When either is missing
        # we skip LSP and keep filesystem + bash + global search working.
        if self.lang_server_command and shutil.which("mcp-language-server"):
            servers["lsp"] = StdioServerParameters(
                command="mcp-language-server",
                args=["--workspace", self.project_path, "--lsp", self.lang_server_command]
            )
        else:
            print("⚠️ LSP unavailable — skipping LSP server (filesystem + bash still active).")

        servers["bash"] = bash_params

        # Launch sequentially to ensure they are bound to the main task's AsyncExitStack.
        # (Using asyncio.gather spawns separate tasks, causing anyio to crash when closing context managers)
        for name, params in servers.items():
            await self._connect_and_register(name, params)
        print(f"✅ Successfully connected to {len(self.sessions)} MCP servers.")

    async def _connect_and_register(self, name: str, params: StdioServerParameters):
        try:
            transport = await self.exit_stack.enter_async_context(stdio_client(params))
            read, write = transport
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            
            await session.initialize()
            self.sessions[name] = session
            
            # Fetch tools for this server
            response = await session.list_tools()
            for tool in response.tools:
                # Filter out the broken 'definition' tool from the LSP since pylsp doesn't natively support workspace/symbol
                if name == "lsp" and tool.name == "definition":
                    continue
                
                # Add an internal mapping so we know which server handles which tool
                self.tools_schema.append({
                    "server": name,
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })
        except Exception as e:
            print(f"❌ Failed to initialize {name} server: {e}")

    async def execute_tool(self, tool_name: str, arguments: dict):
        """Routes a tool call to the appropriate MCP server."""
        # Find which server owns this tool
        server_name = next((t["server"] for t in self.tools_schema if t["function"]["name"] == tool_name), None)
        
        if not server_name:
            return f"Error: Tool '{tool_name}' not found."

        session = self.sessions.get(server_name)
        if not session:
            return f"Error: Session for '{server_name}' disconnected."

        try:
            result = await session.call_tool(tool_name, arguments)
            # Flatten text contents
            return "\n".join(content.text for content in result.content if content.type == "text")
        except Exception as e:
            return f"Tool Execution Error: {str(e)}"

    def estimate_tokens(self, text: str) -> int:
        # A rough heuristic: 1 token ~ 4 characters
        return estimate_tokens(text)

    def _history_tokens(self):
        return sum(estimate_tokens(json.dumps(msg, default=str)) for msg in self.history)

    def _turn_starts(self):
        return [i for i, msg in enumerate(self.history) if msg.get("role") == "user"]

    def _ledger_entry(self, call, result_by_id):
        """One line recording that a call happened, with its outputs stripped."""
        func = call.get("function", {})
        name = func.get("name", "?")

        args = distill_tool_arguments(func.get("arguments"))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {"args": args}
        if not isinstance(args, dict):
            args = {"args": args}

        rendered = []
        for key, value in list(args.items())[:4]:
            text = str(value)
            if len(text) > 60:
                text = text[:60] + "…"
            rendered.append(f"{key}={text!r}")

        result = result_by_id.get(call.get("id"), "")
        if result.startswith("Error") or result.startswith("Tool Execution Error"):
            status = "error"
        elif not result:
            status = "no result"
        else:
            status = f"ok, {estimate_tokens(result):,}tok"

        return f"{name}({', '.join(rendered)}) -> {status}"

    def _partition(self, old_messages):
        """Split the region being compacted into conversation text, call ledger and bodies."""
        result_by_id = {
            msg.get("tool_call_id"): msg.get("content", "")
            for msg in old_messages
            if msg.get("role") == "tool"
        }

        exchanges = []
        ledger = []
        bodies = []

        for msg in old_messages:
            role = msg.get("role")

            if role == "tool":
                # Deterministic pre-shrink, so the summarizer sees skeletons and
                # error lines rather than raw megabytes.
                distilled = distill_tool_result(msg.get("name"), msg.get("content", ""))
                bodies.append(f"[{msg.get('name', '?')}]\n{distilled}")
                continue

            if msg.get("content"):
                speaker = "USER" if role == "user" else "ZANI"
                exchanges.append(f"{speaker}: {msg['content']}")

            for call in msg.get("tool_calls", []):
                ledger.append(self._ledger_entry(call, result_by_id))

        return "\n\n".join(exchanges), ledger, "\n\n".join(bodies)

    async def compact_history(self, log=print):
        """
        Rebuild the history as: one compacted preamble, then the last
        KEEP_RECENT_TURNS turns byte-identical.

        The preamble carries three sections. A rolling prose summary of the whole
        conversation, regenerated from its own previous value so it stays one
        size however long the session runs. A ledger of every tool call made,
        arguments kept and outputs dropped. A digest of what those dropped
        outputs actually showed. Sections one and three come from separate model
        calls that use the summarizer prompts rather than Zani's persona; the
        ledger is deterministic. Every section is hard-capped on the way in.
        """
        before = self._history_tokens()
        if before < MAX_HISTORY_TOKENS:
            return True

        turn_starts = self._turn_starts()
        if len(turn_starts) > KEEP_RECENT_TURNS:
            cutoff = turn_starts[-KEEP_RECENT_TURNS]
        elif turn_starts:
            # Fewer turns than we normally protect: shield the last one only,
            # otherwise a single oversized turn leaves nothing to compact.
            cutoff = turn_starts[-1]
        else:
            return True

        old, recent = self.history[:cutoff], self.history[cutoff:]

        # A previous carry-over lives on in self.rolling_summary and friends, so
        # drop the message itself instead of folding it back in as conversation.
        old = [msg for msg in old if not msg.get("_carryover")]
        if not old:
            log(f"⚠️ Context at ~{before:,} tokens but the recent turns alone fill it.")
            return False

        log(f"⚠️ Context at ~{before:,} tokens — compacting {len(old)} messages "
            f"and keeping the last {KEEP_RECENT_TURNS} turns...")

        exchanges, new_ledger, bodies = self._partition(old)

        if self.llm_caller:
            # Independent calls, so pay for one round trip rather than two.
            self.rolling_summary, self.body_digest = await asyncio.gather(
                summarize_conversation(self.llm_caller, self.rolling_summary, exchanges),
                summarize_tool_bodies(self.llm_caller, self.body_digest, bodies),
            )
        else:
            log("⚠️ No model available for summarization; keeping the deterministic ledger only.")

        self.tool_ledger = (self.tool_ledger + new_ledger)[-LEDGER_MAX_ENTRIES:]

        carryover = {
            "role": "user",
            "content": build_carryover(self.rolling_summary, self.tool_ledger, self.body_digest),
            "_carryover": True,
        }
        self.history = [carryover] + recent

        after = self._history_tokens()
        preamble = estimate_tokens(carryover["content"])
        log(f"   compacted ~{before:,} → ~{after:,} tokens "
            f"({100 - int(after / max(before, 1) * 100)}% saved); "
            f"preamble ~{preamble:,} tok, recent turns ~{after - preamble:,} tok")

        if after >= MAX_HISTORY_TOKENS:
            log(f"🛑 CRITICAL: still ~{after:,} tokens. The last {KEEP_RECENT_TURNS} "
                "turns alone exceed the budget. Start a new session to proceed.")
            return False

        return True

    async def orchestration_loop(self, user_prompt: str, llm_api_caller, ui_callback=None,
                                 event_cb=None, tools_enabled=True):
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        from rich.syntax import Syntax
        
        console = Console()

        def _log(text=None, panel_content=None, title=None, style=None, is_markdown=False, is_syntax=False, language="json"):
            if ui_callback:
                ui_callback(text, panel_content, title, style, is_markdown, is_syntax, language)
            else:
                if panel_content:
                    if is_markdown:
                        content = Markdown(panel_content)
                    elif is_syntax:
                        content = Syntax(panel_content, language, theme="monokai", background_color="default")
                    else:
                        content = panel_content
                    console.print(Panel(content, title=f"[{style}]{title}[/{style}]" if style else title, border_style=style or "default"))
                else:
                    console.print(text)

        """
        The master execution state machine.
        llm_api_caller is a function that takes (system_prompt, history, tools) and returns the LLM response.
        """
        def _emit(kind, **data):
            """Structured side-channel for the UI. Never allowed to break the loop."""
            if not event_cb:
                return
            try:
                event_cb(kind, **data)
            except Exception:
                pass

        # Summarization reuses the same model through the same caller.
        self.llm_caller = llm_api_caller

        self.history.append({"role": "user", "content": user_prompt})
        _emit("turn_start", prompt=user_prompt)

        # Clean tools payload for LLM (remove our internal 'server' routing key).
        # In chat mode the schema is withheld rather than mutated, so flipping
        # back to act mode needs no re-registration.
        llm_tools = [
            {"type": "function", "function": t["function"]}
            for t in self.tools_schema
        ] if tools_enabled else []

        for iteration in range(MAX_LOOP_ITERATIONS):
            # Check buffer size before hitting API
            if not await self.compact_history(log=lambda msg: _log(text=f"[dim]{msg}[/dim]")):
                break

            # Step A: Send to LLM
            _log(text=f"[dim]🔄 Loop Iteration {iteration + 1}/{MAX_LOOP_ITERATIONS}...[/dim]")
            response = await llm_api_caller(
                system_prompt=ZANI_SYSTEM_INSTRUCTIONS,
                history=self.history,
                tools=llm_tools
            )

            usage = response.get("usage") or {}
            _emit("usage", input=usage.get("input", 0), output=usage.get("output", 0))
            if response.get("error"):
                _emit("api_error", error=response["error"])

            # Step B: Intercept Response
            if not response.get("tool_calls"):
                # Raw text returned -> break loop and yield to user
                self.history.append({"role": "assistant", "content": response.get("content", "")})
                
                # Print final model response nicely
                _log(
                    panel_content=response.get("content", ""), 
                    title="🤖 Zani", 
                    style="bold magenta",
                    is_markdown=True
                )
                break

            # Step C: Execute Tools
            tool_calls = response["tool_calls"]
            self.history.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": tool_calls
            })

            # If the model had some conversational text before calling the tool, print it
            if response.get("content"):
                _log(text=f"[magenta]🤖 Zani:[/magenta] {response.get('content')}")

            for call in tool_calls:
                call_id = call.get("id", "req_unknown")
                func_name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"])
                except:
                    args = call["function"]["arguments"]

                # Verbose: Print Tool Execution Call
                args_str = json.dumps(args, indent=2)
                _log(
                    panel_content=args_str,
                    title=f"🛠️ Executing Tool: {func_name}",
                    style="bold cyan",
                    is_syntax=True,
                    language="json"
                )

                _emit("tool_start", name=func_name, args=args)
                result_text = await self.execute_tool(func_name, args)
                _emit(
                    "tool_end",
                    name=func_name,
                    ok=not result_text.startswith(("Error", "Tool Execution Error")),
                )

                # Verbose: Print Tool Execution Result
                display_text = result_text if len(result_text) < 1500 else result_text[:1500] + "\n...[TRUNCATED FOR DISPLAY]"
                
                _log(
                    panel_content=display_text,
                    title=f"📋 Result: {func_name}",
                    style="bold green"
                )

                self.history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": result_text
                })

        else:
            _log(text="[bold red]⚠️ Max iterations reached. Zani halted to prevent runaway loops.[/bold red]")

    async def shutdown(self):
        await self.exit_stack.aclose()


# ==============================================================
# EXAMPLE USAGE MOCKUP
# ==============================================================
async def mock_llm_caller(system_prompt, history, tools):
    """
    Mock LLM function. You would wire this up to OpenRouter or Gemini.
    """
    return {
        "content": "I am looking at the project now.",
        "tool_calls": [] # Example return format
    }

async def main():
    target_project = os.getcwd()
    # E.g., for Python: "pyright-langserver" or "pylsp"
    lsp_command = "pyright-langserver" 

    orchestrator = ZaniMCPOrchestrator(target_project, lsp_command)
    
    try:
        await orchestrator.initialize_servers()
        await orchestrator.orchestration_loop("Can you find where the main function is?", mock_llm_caller)
    finally:
        await orchestrator.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
