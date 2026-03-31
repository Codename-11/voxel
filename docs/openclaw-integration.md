# OpenClaw Integration

## Overview

Voxel connects to an [OpenClaw](https://openclaw.ai) gateway to access AI agents. The gateway handles all model routing, session management, and tool execution — Voxel is just a voice/display client.

## Connection

```yaml
# config/default.yaml
gateway:
  url: "http://GATEWAY_HOST:18789"   # your OpenClaw gateway
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
  "stream": true,
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

**Streaming:** SSE streaming is the default mode (`stream: true`). Partial text is emitted as chunks arrive, enabling progressive display and faster perceived response time. If SSE returns empty or errors, the client automatically falls back to a single non-streaming request.

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

**Candidate:** [openWakeWord](https://github.com/dscripka/openWakeWord) — already used by the [WhisPlay reference chatbot](https://github.com/PiSugar/whisplay-ai-chatbot). Runs on Pi Zero 2W (same Cortex-A53 as Pi 3), processes 80ms audio chunks at 16 kHz. A custom "Hey Voxel" model can be trained via Google Colab in <1 hour using synthetic speech. Pre-trained model licensing is CC BY-NC-SA 4.0 (non-commercial), but custom-trained models can use any license.

Config placeholder: `audio.wake_word: null` in `config/default.yaml`. See `docs/hardware.md` § "Features to Consider" for full technical details.
