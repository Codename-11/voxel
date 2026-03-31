# Voxel Plugin Roadmap

## Goal

Package Voxel's MCP server as a **Claude Code plugin** for one-click installation, replacing the current manual `.mcp.json` + env var setup.

## Current State

Voxel exposes 20 MCP tools via a JSON-RPC server supporting stdio and SSE transports. Integration requires manual config:
- Claude Code: `.mcp.json` with `VOXEL_DEVICE_IP` env var
- OpenClaw: mcporter + skill install
- Codex: manual stdio config

## Plugin Scope

### Single plugin vs multiple

One plugin is preferred — all 20 tools share the same WS bridge and device context. Splitting by category (control vs query vs manage) would add complexity with no real benefit since the bridge is shared.

### What the plugin would provide

- **MCP server** — same `mcp/server.py`, bundled as a plugin module
- **Agent/skill** — `openclaw/SKILL.md` content as a Claude agent definition
- **Auto-discovery** — plugin config UI asks for device IP (or discovers via UDP broadcast)
- **User config** — `VOXEL_DEVICE_IP` as a plugin option (no env var needed)
- **Marketplace** — published to a marketplace for `claude plugin install voxel`

### Plugin manifest structure

```
.claude-plugin/
  manifest.json        # name, version, description, MCP servers, user config
  agents/
    voxel.md           # skill/agent definition (from SKILL.md)
  mcp/
    server.py          # or reference to the existing mcp/ module
```

### User config schema

```json
{
  "userConfig": {
    "device_ip": {
      "type": "string",
      "description": "Voxel device IP address",
      "required": true
    },
    "transport": {
      "type": "string",
      "enum": ["sse", "stdio"],
      "default": "sse"
    }
  }
}
```

## Blockers

- Claude Code plugin marketplace is relatively new — need to evaluate stability
- Plugin distribution for OpenClaw/Codex would need separate packaging
- UDP auto-discovery requires network access from the plugin runtime

## When

After the current MCP server is stable and tested across Claude Code + OpenClaw. Plugin is a packaging improvement, not a capability change.
