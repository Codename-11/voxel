# Voxel OpenClaw Integration

This directory contains OpenClaw integration files for the Voxel companion device.

## Prerequisites

Voxel must be in **Connected** mode (gateway URL and token configured) before MCP or webhooks can be useful. The display service (`uv run dev` or `voxel start`) must be running.

1. Configure gateway: `voxel config set gateway.url http://your-gateway:18789`
2. Configure token: `voxel config set gateway.token your-token`
3. Verify: the web UI at `http://device-ip:8081` should show "Connected"

## Skill

`SKILL.md` teaches OpenClaw agents about Voxel's capabilities and available MCP tools. Install it as a skill in your OpenClaw configuration.

## MCP Server

The Voxel MCP server exposes device tools via the Model Context Protocol.

### Available Tools (20)

**Control:** set_mood, set_style, set_character, speak_text, send_chat_message, show_reaction, set_led, set_volume, set_agent
**Query:** get_device_state, get_system_stats, get_conversation_history, get_logs, run_diagnostic, check_update
**Manage:** set_config, restart_services, install_update, reboot_device, connect_wifi

See `openclaw/SKILL.md` for full descriptions and usage guidelines.

### Starting the Server

Start it with:

```bash
# SSE transport (for OpenClaw gateway, remote agents)
uv run mcp-server --transport sse --port 8082

# Or via CLI
voxel mcp --transport sse

# stdio transport (for Claude Code, Codex CLI)
uv run python -m mcp
```

### Connecting from OpenClaw

Register the Voxel MCP server via mcporter:

```bash
mcporter config add voxel --url http://voxel.local:8082/sse
```

Or manually in `~/.openclaw/openclaw.json`:

```json
{
  "mcpServers": {
    "voxel": {
      "baseUrl": "http://voxel.local:8082/sse",
      "headers": {}
    }
  }
}
```

### Connecting from Claude Code

Add to `.claude/settings.json` or project settings:

```json
{
  "mcpServers": {
    "voxel": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp"],
      "cwd": "/path/to/voxel"
    }
  }
}
```

## Webhooks

Voxel can send events to OpenClaw's webhook endpoint. Configure in `config/local.yaml`:

```yaml
webhook:
  enabled: true
  url: "http://172.16.24.250:18789/hooks/agent"
  token: "your-gateway-token"
  events: [state_change, battery_alert, conversation_complete]
```
