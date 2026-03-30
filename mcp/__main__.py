"""Run the Voxel MCP server.

Usage:
    python -m mcp                                  # stdio transport (Claude Code / Codex)
    python -m mcp --transport sse                   # SSE transport (OpenClaw / remote)
    python -m mcp --transport sse --port 8082       # SSE on custom port
    python -m mcp --ws-url ws://pi.local:8080       # connect to remote backend
"""

from mcp.server import main

if __name__ == "__main__":
    main()
