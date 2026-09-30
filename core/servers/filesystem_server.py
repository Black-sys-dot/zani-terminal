import sys
import os
import asyncio
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Allow imports from package root when spawned as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.harness_secrets import (  # noqa: E402
    secret_kind,
    should_hide_from_listing,
    should_skip_in_search,
)

app = Server("filesystem-server")
sandbox_dir = None
harness_mode = False


def _resolve_path(path_str):
    p = Path(sandbox_dir) / path_str
    if not os.path.abspath(p).startswith(os.path.abspath(sandbox_dir)):
        raise ValueError("Security violation: Path is outside the sandbox directory.")
    kind = secret_kind(path_str)
    if kind == "always_blocked":
        raise ValueError(
            "Security violation: `.zani.env` is blocked and not accessible to tools."
        )
    if kind == "env_gated" and not harness_mode:
        raise ValueError("Security violation: Access to `.env` files is prohibited.")
    return p

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_file",
            description="Read the contents of a file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"}
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="write_file",
            description="Write content to a file (overwrites existing).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "The full content to write"}
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="list_directory",
            description="List contents of a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (use '.' for root project dir)"}
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="zani_global_search",
            description="[SELF-MADE LSP ALTERNATIVE] Performs a fast lexical global search across the entire project workspace for a specific symbol or text. Use this to find definitions instead of the LSP.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The exact string or symbol to search for"}
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "read_file":
            path = _resolve_path(arguments["path"])
            if not path.is_file():
                return [TextContent(type="text", text="Error: File not found or is a directory.")]
            content = path.read_text(encoding="utf-8")
            return [TextContent(type="text", text=content)]
            
        elif name == "write_file":
            path = _resolve_path(arguments["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(arguments["content"], encoding="utf-8")
            return [TextContent(type="text", text="File written successfully.")]
            
        elif name == "list_directory":
            path = _resolve_path(arguments["path"])
            if not path.is_dir():
                return [TextContent(type="text", text="Error: Directory not found.")]
            items = []
            for item in path.iterdir():
                if item.name == ".env" or should_hide_from_listing(
                    item.name, harness=harness_mode
                ):
                    continue
                items.append(f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}")
            return [TextContent(type="text", text="\n".join(items) if items else "Directory is empty.")]
            
        elif name == "zani_global_search":
            query = arguments["query"]
            results = []
            
            IGNORE_DIRS = {'__pycache__', 'node_modules', 'vendor', 'target', 'build', 'dist', 'out', 'bin', 'obj'}
            
            for root, dirs, files in os.walk(sandbox_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in IGNORE_DIRS]
                for file in files:
                    if should_skip_in_search(file, harness=harness_mode):
                        continue
                    if file.startswith('.') and file not in (".gitignore",):
                        continue
                        
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, sandbox_dir)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            for i, line in enumerate(f, 1):
                                if query in line:
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                    except (UnicodeDecodeError, IOError):
                        pass
                        
            if not results:
                return [TextContent(type="text", text=f"Symbol '{query}' not found in the workspace.")]
            
            if len(results) > 100:
                results = results[:100] + [f"... and {len(results)-100} more matches."]
                
            return [TextContent(type="text", text="\n".join(results))]
            
        raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

async def main():
    global sandbox_dir, harness_mode
    if len(sys.argv) > 1:
        sandbox_dir = sys.argv[1]
    else:
        sandbox_dir = os.getcwd()
    harness_mode = "--harness" in sys.argv[2:]
        
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
