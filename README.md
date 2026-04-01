<p align="center">
  <img src="assets/Logo-3D.SVG" width="160" alt="Voxel" />
</p>

<h1 align="center">Voxel</h1>

<p align="center">
  Pocket AI companion device — animated cube mascot with voice interaction
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/platform-Pi%20Zero%202W-c51a4a?logo=raspberrypi&logoColor=white" alt="Pi Zero 2W" />
  <img src="https://img.shields.io/badge/display-240%C3%97280%20SPI-00d4d2" alt="240x280 SPI LCD" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
</p>

---

**Voxel** is the character — an animated cube mascot with expressive eyes, a mouth, and body language. The physical device is called the **Relay**. Press a button, talk, and Voxel responds with voice, animated expressions, and the intelligence of your cloud AI agents via [OpenClaw](https://github.com/openclaw/openclaw).

<p align="center">
  <img src="assets/character/concept-03-ui-mockup.png" width="240" alt="Voxel on the Relay device" />
</p>

## What is Voxel?

Voxel is a pocket-sized AI companion that runs on a Raspberry Pi Zero 2W with a PiSugar Whisplay HAT. It gives your AI agents a physical presence — an animated face on a tiny LCD, a speaker, a microphone, and a button. Talk to it, and it talks back. Connect it to OpenClaw to chat with different AI agents. Give those agents control over the device via MCP so they can set moods, speak text, and react to the world.

## Quick Start

### Hardware (The Relay)

| Component | Product | Purpose |
|-----------|---------|---------|
| Brain | Raspberry Pi Zero 2W | Compute |
| Display + Audio | PiSugar Whisplay HAT | 1.69" IPS LCD, dual mics, speaker, button, RGB LED |
| Battery | PiSugar 3 (1200mAh) | Portable power via USB-C charging |
| Storage | MicroSD card (16GB+) | OS + software |
| **Total** | | **~$65** |

See [docs/hardware.md](docs/hardware.md) for detailed specs, pin mapping, and assembly.

### Setup

Flash [Raspberry Pi OS Lite (64-bit)](https://www.raspberrypi.com/software/) to the SD card, enable SSH, boot, then:

```bash
ssh pi@voxel.local
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

First-time setup takes ~15-20 minutes on a Pi Zero 2W (compiling drivers, installing dependencies). After the reboot, the configuration wizard runs automatically on the LCD — it walks you through WiFi, gateway token, voice settings, and more.

For the full walkthrough, see the [Quick Start guide](user-docs/guide/quick-start.md).

### Button Controls

Single button (Whisplay HAT). All interaction encoded through hold duration -- no double-tap:

**Face view (IDLE):**

| Gesture | Action | Timing |
|---------|--------|--------|
| **Tap** | Toggle view (face / chat) | < 400ms, fires on release |
| **Hold** | Push-to-talk (start recording) | > 400ms (still held), stays recording until release |

**Chat view:**

| Gesture | Action | Timing |
|---------|--------|--------|
| **Tap** | Toggle view (face / chat) | < 400ms, fires on release |
| **Hold** | Open menu | > 1s (fires at threshold) |
| **Hold** | Sleep | > 5s (fires at threshold) |
| **Hold** | Shutdown (with 3s confirm) | > 10s (fires at threshold) |

Inside menus: tap = next item, hold > 500ms = select.

On first boot, a gesture tutorial walks through all three interactions. After 45 seconds idle on the face view, a hint appears: "Hold to talk · Tap for more". The settings menu includes a "Help" item to replay the tutorial.

## Features

- **Animated face** on 240x280 IPS LCD -- 16 mood states, 3 visual styles, smooth transitions
- **Multiple characters** -- Voxel (default), Cube (isometric), BMO (Adventure Time)
- **Voice interaction** -- push-to-talk via single button, Whisper STT, OpenAI TTS/ElevenLabs/edge-tts
- **Multiple AI agents** -- switch between Daemon, Soren, Ash, Mira, Jace, Pip via OpenClaw
- **MCP integration** -- 20 device tools for AI agents: control mood, speech, LED; query stats, logs, diagnostics; manage config, services, updates
- **Web-based settings** -- config UI on port 8081 with QR code access and PIN auth
- **WiFi onboarding** -- AP mode captive portal on first boot ("Voxel-Setup" hotspot)
- **Self-update** -- check for and install updates from the device menu
- **Streaming chat** -- SSE streaming with progressive display, tool call indicators, emoji reactions
- **Cross-platform dev preview** -- develop on Windows, macOS, or Linux with tkinter preview

### Operating Modes

Voxel works in layers — each mode adds capabilities on top of the previous:

| Mode | What it does | Requires |
|------|-------------|----------|
| **Standalone** | Animated face, button interaction, on-device menu, config web UI | Nothing (works out of the box) |
| **Connected** | + Chat with AI agents, voice interaction, mood reactions | Gateway URL + token in config |
| **MCP Enabled** | + External agents can control device (mood, speech, LED, etc.) | `voxel mcp` running |
| **Webhooks** | + Device pushes events to gateway (battery alerts, state changes) | Webhook URL in config |

All modes are additive. MCP and webhooks are disabled by default — enable in `config/local.yaml` or the web settings page under "Integration".

## Agent Integration (MCP)

AI agents can control Voxel via MCP — set moods, speak text, query device state, manage configuration, and more. 20 tools are exposed over stdio or SSE transport.

### Connect an agent

The device serves setup instructions at a public URL — no auth required:

```bash
# Fetch the setup guide (replace IP with your device)
curl http://voxel.local:8081/setup

# Install the skill (teaches agents about Voxel's 20 tools)
curl http://voxel.local:8081/skill
```

### Client configuration

All clients get the same 20 tools. Device discovery at `http://DEVICE_IP:8081/.well-known/mcp`.

| Client | Transport | Config |
|--------|-----------|--------|
| Claude Code | SSE (remote) or stdio (local) | `.mcp.json` + `VOXEL_DEVICE_IP` env var |
| Codex CLI | stdio | `uv run python -m mcp` |
| OpenClaw | SSE via mcporter | `mcporter config add voxel --url http://DEVICE_IP:8082/sse` |
| Any MCP client | SSE | `http://DEVICE_IP:8082/sse` |

**OpenClaw:**
```bash
mcporter config add voxel --url http://voxel.local:8082/sse
mkdir -p ~/.openclaw/workspace/skills/voxel-device
curl -o ~/.openclaw/workspace/skills/voxel-device/SKILL.md http://voxel.local:8081/skill
```

**Claude Code:**
```json
{ "mcpServers": { "voxel": { "command": "uv", "args": ["run", "python", "-m", "mcp"], "cwd": "/path/to/voxel" } } }
```

**Discovery endpoints** (public, no auth):

| URL | What |
|-----|------|
| `/setup` | Agent setup guide with copy-paste commands |
| `/skill` | Full tool reference (SKILL.md) |
| `/.well-known/mcp` | MCP server status + connection URL (JSON) |

Full agent integration guide: [`AGENTS_SETUP.md`](AGENTS_SETUP.md)

## CLI Commands

After bootstrap, the `voxel` command is available globally on the Pi:

| Command | Description |
|---------|-------------|
| `voxel setup` | First-time install (deps, build, services, wizard) |
| `voxel configure` | Interactive configuration wizard |
| `voxel doctor` | Full system health diagnostics |
| `voxel update` | Pull latest, rebuild, restart services |
| `voxel start` / `stop` / `restart` | Manage services |
| `voxel logs` | Tail service logs |
| `voxel status` | Service/system/hardware status |
| `voxel config` | Show config (`config set`/`config get` for changes) |
| `voxel mcp` | Start MCP server (AI agent integration) |
| `voxel version` | Show version |

See the [CLI reference](user-docs/guide/cli-reference.md) for the full command list including dev commands.

## Configuration

- **Interactive wizard:** `voxel configure` -- guided setup for gateway, voice, display, MCP, webhooks, and power. Runs automatically after `voxel setup`.
- **Web UI:** Settings menu on device, or scan QR code to open `http://<device-ip>:8081`
- **Config files:** `config/default.yaml` (defaults) + `config/local.yaml` (overrides, gitignored)
- **Required keys:** Gateway token (`gateway.token`), OpenAI API key (`stt.whisper.api_key` -- also used by OpenAI TTS)

```bash
voxel configure                                   # interactive wizard
voxel config set gateway.token <your-token>        # or set individual keys
voxel config set stt.whisper.api_key <your-key>
```

See [Configuration guide](user-docs/guide/configuration.md) for all available settings.

## Development

For contributors and people building on Voxel. Uses [uv](https://docs.astral.sh/uv/) for all Python tooling (3.11-3.13).

### Desktop preview

The preview window renders 1:1 with the Pi LCD (240x280, same PIL renderer, corner mask, all components). Spacebar simulates the hardware button.

```bash
git clone https://github.com/Codename-11/voxel.git
cd voxel

uv run dev                        # PIL preview window (1:1 with Pi LCD)
uv run dev --scale 3              # larger preview
uv run dev --server               # with full voice pipeline (spawns server.py)
uv run dev-watch                  # auto-restart on file changes
```

> **`uv run dev`** = PIL display preview (what runs on the Pi). This is the primary dev command.
> **`npm run dev`** = React browser UI (design tool for expression iteration only, NOT the production renderer).

### Dev pairing and push to Pi

```bash
uv run voxel dev-pair                       # auto-discover + pair with device
uv run voxel dev-push --logs                # sync runtime to Pi + tail logs
uv run voxel dev-push --watch               # watch for changes, auto-push
uv run voxel dev-push --install-service     # set up systemd auto-start
```

### Testing

```bash
uv run pytest                     # run all tests
uv run pytest tests/ -v           # verbose output
```

See the [Development workflow guide](user-docs/guide/dev-workflow.md) for the full dev setup, keyboard shortcuts, and remote development details.

## Architecture

Three services run on the Pi. The **guardian** starts first, owns the display during boot, handles WiFi onboarding, and monitors health. The **backend** (`server.py`) manages state, AI pipelines, and hardware I/O over WebSocket. The **display service** renders PIL frames to the SPI LCD, handles button input, and runs the config web server. On desktop, frames display in a tkinter window.

```
┌──────────────────────────────────────────────────────────────┐
│                       Pi Zero 2W                             │
│                                                              │
│  ┌──────────────┐   ┌───────────────┐   ┌────────────────┐  │
│  │   Guardian    │   │   Backend     │   │ Display Service│  │
│  │              │   │  server.py    │   │ display/       │  │
│  │ Boot splash  │   │              │   │  service.py    │  │
│  │ WiFi AP mode │   │ State machine│◄──►│ PIL renderer  │  │
│  │ Crash recovery│   │ Voice pipeline│ws  │ Button polling│  │
│  │ Watchdog     │   │ Gateway/STT/ │:8080│ Config :8081  │  │
│  │              │   │  TTS/battery │   │ LED patterns  │  │
│  └──────┬───────┘   └──────┬───────┘   └──────┬─────────┘  │
│    lock file               │               SPI + GPIO       │
│                       ┌────┴─────┐      ┌──────┴─────────┐  │
│                       │MCP :8082 │      │ WhisPlay HAT   │  │
│                       │stdio+SSE │      │ LCD/Mic/Spk/LED│  │
│                       └────┬─────┘      └────────────────┘  │
│                            │                                 │
│              ┌─────────────┼──────────────┐                  │
│              │  OpenClaw   │  Whisper API  │                  │
│              │  Gateway    │  TTS Provider │                  │
│              │  (HTTP+SSE) │  (HTTP)       │                  │
│              └─────────────┴──────────────┘                  │
└──────────────────────────────────────────────────────────────┘
```

For full architecture details, see [Display architecture](user-docs/guide/display-architecture.md).

## Documentation

Full documentation is available in the [user-docs/](user-docs/) directory:

- [Quick Start](user-docs/guide/quick-start.md) -- getting Voxel running on a Pi
- [Configuration](user-docs/guide/configuration.md) -- all settings and config options
- [CLI Reference](user-docs/guide/cli-reference.md) -- every command explained
- [Development Workflow](user-docs/guide/dev-workflow.md) -- contributing and dev setup
- [Hardware](user-docs/guide/hardware.md) -- specs, pin mapping, assembly
- [WiFi Setup](user-docs/guide/wifi-setup.md) -- AP mode and network configuration
- [Troubleshooting](user-docs/guide/troubleshooting.md) -- common issues and fixes

## License

MIT

---

*Built by [Axiom-Labs](https://axiom-labs.dev)*
