import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("bash-server")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="run_bash_command",
            description="Run a bash command on the host system. Use this to execute tests, compile code, or inspect the environment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command string to execute"}
                },
                "required": ["command"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "run_bash_command":
        cmd = arguments.get("command")
        if not cmd:
            raise ValueError("Missing command")
            
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            out = stdout.decode()
            err = stderr.decode()
            
            result = ""
            if out: result += f"STDOUT:\n{out}\n"
            if err: result += f"STDERR:\n{err}\n"
            if not result: result = "Command completed silently."
            
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Execution error: {str(e)}")]
            
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
