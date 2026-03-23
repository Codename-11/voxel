# OpenClaw Integration

## Overview

Voxel connects to an [OpenClaw](https://openclaw.ai) gateway to access AI agents. The gateway handles all model routing, session management, and tool execution — Voxel is just a voice/display client.

## Connection

```yaml
# config/default.yaml
gateway:
  url: "http://172.16.24.250:18789"  # Docker-Server LAN IP
  token: ""                           # Set in local.yaml
  default_agent: "daemon"
```

## Session Keys

Each agent gets its own companion session, separate from Discord, ClawPort, or any other surface:

```
agent:daemon:companion
agent:soren:companion
agent:ash:companion
agent:mira:companion
agent:jace:companion
agent:pip:companion
```

**Architecture rule:** Never share sessions across surfaces. Each client (Discord, ClawPort, Voxel) maintains independent sessions per agent.

## API Usage

### Chat Completions

```python
POST {gateway_url}/v1/chat/completions
Headers:
  Authorization: Bearer {token}
  Content-Type: application/json
  x-openclaw-session-key: agent:{agent_id}:companion

Body:
{
  "model": "openclaw:{agent_id}",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

**Important:** Use `stream: false`. The gateway's streaming endpoint currently returns empty responses. Non-streaming works correctly and returns the full response in one shot.

### Health Check

```python
GET {gateway_url}/v1/models
Headers:
  Authorization: Bearer {token}
```

Returns 200 if gateway is reachable and authenticated.

## Available Agents

| ID | Name | Role | Default Voice |
|----|------|------|---------------|
| daemon | Daemon | Lead agent — coordinator | Charlie |
| soren | Soren | Senior architect | Adam |
| ash | Ash | Builder/executor | Josh |
| mira | Mira | Business operator | Rachel |
| jace | Jace | Flex agent | Sam |
| pip | Pip | Intern | Charlie |

## Agent Switching

The settings menu lets users switch agents. `core/gateway.py` handles this:

```python
client = OpenClawClient(url, token, agent_id="daemon")
client.set_agent("soren")  # Switches session key + model
```

## Error Handling

| Error | Voxel Behavior |
|-------|----------------|
| Gateway unreachable | X_X face, red LED, "Can't reach gateway" status |
| Auth failure (401) | X_X face, "Auth failed" status |
| Timeout (>120s) | Thinking → Error, "Response timed out" |
| Empty response | Confused face, retry once, then error |

## Future: Wake Word

When "Hey Voxel" wake word is implemented, the interaction becomes hands-free:

```
Wake word detected → LISTENING (auto-record)
Silence detected → THINKING (send to gateway)
Response received → SPEAKING (TTS + mouth sync)
Done → IDLE (back to ambient)
```
