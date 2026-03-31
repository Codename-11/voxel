# Voxel — Agent Setup Guide

> **For AI agents.** This file helps you connect to and control a Voxel companion device. It works whether you're reading this from GitHub or from a local clone.

## What is Voxel?

Voxel is a pocket AI companion device (Raspberry Pi Zero 2W) with a 240x280 animated face, speaker, RGB LED, and single button. You can control it via **20 MCP tools** — set moods, speak text, manage services, view logs, and more.

## Quick Decision Tree

### Do you have the device IP?

**Yes → Connect directly:**
```bash
# Check if the device is reachable and MCP is running
curl http://DEVICE_IP:8081/.well-known/mcp
```
If that returns JSON with `"running": true`, skip to [Connect MCP](#connect-mcp).
If `"running": false`, tell the user: "The Voxel MCP server isn't running. Run `voxel mcp` on the device or enable it in the web settings at http://DEVICE_IP:8081 under Integration."

**No → Ask the user:**
"What's the IP address of your Voxel device? Check the device's LCD screen, or try `voxel.local` if you're on the same network."

Common IPs:
- `voxel.local` (mDNS, if on same LAN)
- `10.42.0.1` (if device is in AP/setup mode)
- Check router DHCP lease list

### Is this a new device (no Voxel software yet)?

Tell the user:
```bash
# One-line Pi setup
ssh pi@DEVICE_IP
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

After setup completes and the device reboots, the face appears on the LCD and the config server starts on port 8081.

---

## Connect MCP

All clients get the same 20 tools. Device discovery at `http://DEVICE_IP:8081/.well-known/mcp`.

| Client | Transport | Config | Setup |
|--------|-----------|--------|-------|
| Claude Code | SSE (remote) or stdio (local) | `.mcp.json` + `VOXEL_DEVICE_IP` env var | Auto via project `.mcp.json` |
| Codex CLI | stdio | Manual config | `uv run python -m mcp` |
| OpenClaw | SSE via mcporter | `mcporter config add voxel --url http://DEVICE_IP:8082/sse` | + skill install |
| Any MCP client | SSE | `http://DEVICE_IP:8082/sse` | Standard MCP SSE |

### Option A: OpenClaw (SSE transport — network)

**Quickest — one command each:**
```bash
# 1. Register MCP server via mcporter (syncs to cursor, claude-code, codex too)
mcporter config add voxel --url http://DEVICE_IP:8082/sse

# 2. Install skill (teaches agents about Voxel's tools)
mkdir -p ~/.openclaw/workspace/skills/voxel-device
curl -o ~/.openclaw/workspace/skills/voxel-device/SKILL.md http://DEVICE_IP:8081/skill
```

**Install skill from GitHub** (works without a running device):
```bash
mkdir -p ~/.openclaw/workspace/skills/voxel-device
curl -o ~/.openclaw/workspace/skills/voxel-device/SKILL.md \
  https://raw.githubusercontent.com/Codename-11/voxel/main/openclaw/SKILL.md
```

**Manual config** (if mcporter CLI isn't available):

Add to mcporter's config file (location varies — typically `~/.npm-global/lib/node_modules/mcporter/config/mcporter.json`):
```json
{
  "mcpServers": {
    "voxel": {
      "description": "Voxel AI companion device — 20 tools for mood, speech, LED, logs, config, services.",
      "baseUrl": "http://DEVICE_IP:8082/sse"
    }
  }
}
```
mcporter syncs to: cursor, claude-code, claude-desktop, codex (configured via its `imports` array).

> **Note:** Do NOT add `mcpServers` to `~/.openclaw/openclaw.json` — that key is invalid there and will break the gateway. MCP servers are managed by mcporter, not the gateway config.

### Option B: Claude Code (stdio transport — local)

Add to your Claude Code MCP settings:
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

This runs the MCP server locally as a subprocess. Requires the Voxel repo cloned and `uv sync` completed. The MCP server connects to the backend via WebSocket on `ws://localhost:8080` (start `server.py` first).

### Option C: Any MCP client (SSE)

Point your MCP client to:
```
http://DEVICE_IP:8082/sse
```

Standard MCP protocol over Server-Sent Events. Endpoints:
- `GET /sse` — event stream (server → client)
- `POST /message` — JSON-RPC requests (client → server)
- `GET /health` — health check

---

## Available Tools (20)

| Category | Tools | Description |
|----------|-------|-------------|
| **Control** | `set_mood` | Change face expression (13 moods) |
| | `set_style` | Switch face style (kawaii/retro/minimal) |
| | `set_character` | Switch mascot (voxel/cube/bmo) |
| | `speak_text` | TTS speech through speaker |
| | `send_chat_message` | Send message to AI agent |
| | `show_reaction` | Float emoji above face |
| | `set_led` | Set RGB LED color |
| | `set_volume` | Set speaker volume (0-100) |
| | `set_agent` | Switch AI agent |
| **Query** | `get_device_state` | Battery, WiFi, mood, state, agent |
| | `get_system_stats` | CPU temp, RAM, disk, WiFi signal |
| | `get_conversation_history` | Recent chat messages |
| | `get_logs` | Service log output (up to 200 lines) |
| | `run_diagnostic` | Full health check (voxel doctor) |
| | `check_update` | Check for new version |
| **Manage** | `set_config` | Change config value (dotted key) |
| | `restart_services` | Restart display/backend services |
| | `install_update` | Git pull + rebuild (requires confirm) |
| | `reboot_device` | Reboot Pi (requires confirm) |
| | `connect_wifi` | Connect to WiFi network |

## Discovery Endpoints

These are served by the config web server on port 8081 — **no authentication required**:

| Endpoint | Content | Use |
|----------|---------|-----|
| `GET /setup` | Setup guide (this content, with IPs resolved) | Agent self-setup |
| `GET /skill` | SKILL.md (tool descriptions) | Agent context |
| `GET /.well-known/mcp` | JSON (MCP status, URLs, tool count) | Programmatic discovery |
| `GET /api/health` | JSON health check | Availability check |
| `GET /api/stats` | JSON system stats | Device monitoring |

## GitHub Raw URLs (always available)

These work even when the device is offline:

| File | Raw URL |
|------|---------|
| This guide | `https://raw.githubusercontent.com/Codename-11/voxel/main/AGENTS_SETUP.md` |
| Skill (SKILL.md) | `https://raw.githubusercontent.com/Codename-11/voxel/main/openclaw/SKILL.md` |
| Setup guide | `https://raw.githubusercontent.com/Codename-11/voxel/main/openclaw/SETUP.md` |
| Full integration docs | `https://raw.githubusercontent.com/Codename-11/voxel/main/openclaw/README.md` |

## Ports Reference

| Port | Service | Protocol |
|------|---------|----------|
| 8080 | Backend (server.py) | WebSocket |
| 8081 | Config web server | HTTP |
| 8082 | MCP server (when running) | SSE |

## Troubleshooting

**"Connection refused" on port 8082:**
The MCP server isn't running. Ask the user to run `voxel mcp` on the device, or enable it in the web UI at `http://DEVICE_IP:8081` under the Integration section.

**"Connection refused" on port 8081:**
The display service isn't running. Ask the user to run `voxel start` or check with `voxel status`.

**"Connection refused" on port 8080:**
The backend server isn't running. Ask the user to run `uv run server.py` on the device.

**Can't reach the device at all:**
Ask the user to verify the device is powered on and on the same network. Try `ping voxel.local` or check the router's DHCP lease list.
