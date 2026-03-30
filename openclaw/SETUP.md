# Voxel MCP — Quick Setup for AI Agents

> This file is served at `http://<device-ip>:8081/setup` and can be fetched by any agent.

## What is Voxel?

Voxel is a pocket AI companion device (Raspberry Pi Zero 2W + 240x280 LCD). It exposes **20 MCP tools** for device control, monitoring, and management.

## Connect in 3 Steps

### Step 1: Choose your transport

**OpenClaw (SSE — network):**
```bash
mcporter config add voxel --url http://DEVICE_IP:8082/sse
```

**Claude Code (stdio — local):**
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

**Manual config (OpenClaw `~/.openclaw/openclaw.json`):**
```json
{
  "mcpServers": {
    "voxel": {
      "baseUrl": "http://DEVICE_IP:8082/sse",
      "headers": {}
    }
  }
}
```

### Step 2: Install the skill (OpenClaw only)

```bash
mkdir -p ~/.openclaw/workspace/skills/voxel-device
curl -o ~/.openclaw/workspace/skills/voxel-device/SKILL.md http://DEVICE_IP:8081/skill
```

### Step 3: Verify

```bash
# Check MCP discovery
curl http://DEVICE_IP:8081/.well-known/mcp

# Check skill is served
curl http://DEVICE_IP:8081/skill | head -5
```

## Available Tools (20)

| Category | Tools |
|----------|-------|
| **Control** | `set_mood`, `set_style`, `set_character`, `speak_text`, `send_chat_message`, `show_reaction`, `set_led`, `set_volume`, `set_agent` |
| **Query** | `get_device_state`, `get_system_stats`, `get_conversation_history`, `get_logs`, `run_diagnostic`, `check_update` |
| **Manage** | `set_config`, `restart_services`, `install_update`, `reboot_device`, `connect_wifi` |

## Discovery Endpoints (no auth required)

| Endpoint | Returns | Purpose |
|----------|---------|---------|
| `GET /setup` | This guide (text/markdown) | Agent self-setup instructions |
| `GET /skill` | SKILL.md (text/markdown) | Tool descriptions for agent context |
| `GET /.well-known/mcp` | JSON | MCP server status, URL, tool count |
| `GET /api/stats` | JSON | Live system stats |
| `GET /api/health` | JSON | Health check |

## Ports

| Port | Service | Protocol |
|------|---------|----------|
| 8080 | Backend (server.py) | WebSocket |
| 8081 | Config web server | HTTP (settings, chat, discovery) |
| 8082 | MCP server | SSE (when running) |

## Example: First interaction

```
1. get_device_state()          → see battery, mood, WiFi status
2. set_mood("happy")           → face shows happy expression
3. speak_text("Hello world")   → device speaks aloud
4. get_system_stats()          → CPU temp, RAM, disk usage
5. get_logs(service="display") → recent display service logs
```
