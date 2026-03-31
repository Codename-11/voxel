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

## Features

- **Animated face** on 240x280 IPS LCD -- 16 mood states, 3 visual styles, smooth transitions
- **Multiple characters** -- Voxel (default), Cube (isometric), BMO (Adventure Time)
- **Voice interaction** -- push-to-talk via single button, Whisper STT, OpenAI TTS/ElevenLabs/edge-tts
- **Multiple AI agents** -- switch between Daemon, Soren, Ash, Mira, Jace, Pip via OpenClaw
- **Web-based settings** -- config UI on port 8081 with QR code access and PIN auth
- **WiFi onboarding** -- AP mode captive portal on first boot ("Voxel-Setup" hotspot)
- **Self-update** -- check for and install updates via git from the device menu
- **MCP integration** -- expose 20 device tools to AI agents: control (mood, speech, LED), query (stats, logs, diagnostics), manage (config, services, updates, WiFi)
- **Webhook events** -- notify OpenClaw gateway on state changes, battery alerts, conversations
- **Streaming chat** -- SSE streaming with progressive display, tool call indicators, emoji reactions
- **System stats** -- CPU temp, RAM, disk, WiFi signal via `/api/stats` endpoint
- **Light/dark mode** -- web config server supports both themes with auto-detection
- **Cross-platform dev preview** -- develop on Windows, macOS, or Linux with tkinter preview

## Hardware (The Relay)

| Component | Product | Purpose |
|-----------|---------|---------|
| Brain | Raspberry Pi Zero 2W | Compute |
| Display + Audio | PiSugar Whisplay HAT | 1.69" IPS LCD, dual mics, speaker, button, RGB LED |
| Battery | PiSugar 3 (1200mAh) | Portable power via USB-C charging |
| Storage | MicroSD card (16GB+) | OS + software |
| **Total** | | **~$65** |

See [docs/hardware.md](docs/hardware.md) for detailed specs, pin mapping, and assembly.

## Quick Start

### On the Pi (first time)

```bash
ssh pi@voxel.local
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

### Development (any platform)

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager).

```bash
git clone https://github.com/Codename-11/voxel.git
cd voxel

# Local preview (PIL renderer in a tkinter window — same as Pi LCD)
uv run dev

# Auto-reload on file changes
uv run dev-watch

# Push to Pi hardware
uv run voxel dev-push --logs
```

The preview window renders 1:1 with the Pi LCD (240x280, same PIL renderer, corner mask, all components). Spacebar simulates the hardware button.

> Voxel works standalone with just the display service. Add a gateway token for AI chat, enable MCP for remote agent control, or enable webhooks for event notifications. See [Operating Modes](#operating-modes).

> **`uv run dev`** = PIL display preview (what runs on the Pi). This is the primary dev command.
> **`npm run dev`** = React browser UI (design tool only, NOT the production renderer).

## Button Controls

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

Inside menus: tap = next item, hold > 500ms = select. Desktop: spacebar simulates the button.

## Configuration

- **Interactive wizard:** `voxel configure` -- guided setup for gateway, voice, display, MCP, webhooks, and power. Runs automatically after `voxel setup`.
- **Web UI:** Settings menu on device, or scan QR code to open `http://<device-ip>:8081`
- **Config files:** `config/default.yaml` (defaults) + `config/local.yaml` (overrides, gitignored)
- **Required keys:** Gateway token (`gateway.token`), OpenAI API key (`stt.whisper.api_key` — also used by OpenAI TTS)

```bash
voxel configure                                   # interactive wizard
voxel config set gateway.token <your-token>        # or set individual keys
voxel config set stt.whisper.api_key <your-key>
```

## Characters

<p align="center">
  <img src="assets/Logo.SVG" width="64" alt="Voxel flat" />
  &nbsp;&nbsp;
  <img src="assets/Logo-3D.SVG" width="64" alt="Voxel 3D" />
</p>

| Character | Description |
|-----------|-------------|
| **Voxel** (default) | Glowing cyan pill eyes — minimal, expressive |
| **Cube** | Dark charcoal isometric cube with neon edge glow |
| **BMO** | Adventure Time game console with face |

16 moods defined in `shared/expressions.yaml`, 3 face styles in `shared/styles.yaml` (kawaii, retro, minimal). Smooth lerp transitions between moods.

Characters are defined in `display/characters/` and selected via `config/default.yaml` (`character.default`).

## Operating Modes

Voxel works in layers — each mode adds capabilities on top of the previous:

| Mode | What it does | Requires |
|------|-------------|----------|
| **Standalone** | Animated face, button interaction, on-device menu, config web UI | Nothing (works out of the box) |
| **Connected** | + Chat with AI agents, voice interaction, mood reactions | Gateway URL + token in config |
| **MCP Enabled** | + External agents can control device (mood, speech, LED, etc.) | `voxel mcp` running |
| **Webhooks** | + Device pushes events to gateway (battery alerts, state changes) | Webhook URL in config |

All modes are additive. MCP and webhooks are disabled by default — enable in `config/local.yaml` or the web settings page under "Integration".

### MCP Client Integration

All clients get the same 20 tools. Device discovery at `http://DEVICE_IP:8081/.well-known/mcp`.

| Client | Transport | Config | Setup |
|--------|-----------|--------|-------|
| Claude Code | SSE (remote) or stdio (local) | `.mcp.json` + `VOXEL_DEVICE_IP` env var | Auto via project `.mcp.json` |
| Codex CLI | stdio | Manual config | `uv run python -m mcp` |
| OpenClaw | SSE via mcporter | `mcporter config add voxel --url http://DEVICE_IP:8082/sse` | + skill install |
| Any MCP client | SSE | `http://DEVICE_IP:8082/sse` | Standard MCP SSE |

> A Claude Code plugin is planned to simplify installation to one click — see project roadmap.

## Agent Setup (MCP)

Connect any AI agent to Voxel in seconds. The device serves setup instructions at a public URL — no auth required.

```bash
# Fetch the setup guide (replace IP with your device)
curl http://voxel.local:8081/setup

# Install the skill (teaches agents about Voxel's 20 tools)
curl http://voxel.local:8081/skill
```

**OpenClaw:**
```bash
# Register MCP server
mcporter config add voxel --url http://voxel.local:8082/sse

# Install skill (one-time)
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

Full agent integration guide: [`AGENTS_SETUP.md`](AGENTS_SETUP.md) (also available at [raw GitHub URL](https://raw.githubusercontent.com/Codename-11/voxel/main/AGENTS_SETUP.md) — works without a running device).

## Architecture

Three services run on the Pi. The **guardian** starts first, owns the display during boot, handles WiFi onboarding, and monitors health. The **backend** (`server.py`) manages state, AI pipelines, and hardware I/O over WebSocket. The **display service** renders PIL frames to the SPI LCD, handles button input, and runs the config web server. On desktop, frames display in a tkinter window. React app (`app/`) exists as a browser-based dev UI, not the production renderer.

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

For full architecture details, protocol docs, and data flow diagrams, see [docs/architecture.md](docs/architecture.md).

## CLI Commands

After bootstrap, the `voxel` command is available globally on the Pi:

| Command | Description |
|---------|-------------|
| `voxel setup` | First-time install (deps, build, services, wizard) |
| `voxel configure` | Interactive configuration wizard |
| `voxel doctor` | Full system health diagnostics |
| `voxel update` | Pull latest, rebuild, restart services |
| `voxel build` | Rebuild Python deps + React app |
| `voxel hw` | Install Whisplay HAT drivers + tune config.txt |
| `voxel start` | Start services |
| `voxel stop` | Stop services |
| `voxel restart` | Restart services |
| `voxel logs` | Tail service logs |
| `voxel status` | Service/system/hardware status |
| `voxel config` | Show config (`config set`/`config get` for changes) |
| `voxel mcp` | Start MCP server (AI agent integration) |
| `voxel display-test` | Direct Whisplay display sanity test |
| `voxel dev-push` | Sync full runtime to Pi over SSH and run it |
| `voxel version` | Show version |
| `voxel uninstall` | Remove services + caches |

### Development commands (from workstation, all via `uv`)

| Command | Description |
|---------|-------------|
| `uv run dev` | Local PIL preview (tkinter window, 1:1 with Pi LCD) |
| `uv run dev --scale 3` | Larger preview window |
| `uv run dev-watch` | Local preview with auto-reload on file changes |
| `uv run voxel dev-push` | Sync full runtime to Pi and run it |
| `uv run voxel dev-push --logs` | Push and tail remote logs |
| `uv run voxel dev-push --watch` | Watch for changes, auto-push to Pi |
| `uv run voxel dev-push --install-service` | Set up systemd auto-start on boot |
| `uv run voxel dev-pair` | Auto-discover and pair with device |
| `uv run voxel dev-ssh` | SSH into Pi (uses saved creds) |
| `uv run voxel dev-logs` | Tail Pi logs remotely |
| `uv run voxel dev-restart` | Restart display service on Pi |
| `uv run voxel dev-setup` | One-time setup (save SSH + enable dev mode) |

## Development

Uses [uv](https://docs.astral.sh/uv/) for all Python tooling (3.11-3.13). uv manages the venv, dependencies, and script entry points.

```bash
# Primary dev commands (all use uv)
uv run dev                                  # PIL preview window (1:1 with Pi LCD)
uv run dev --scale 3                        # larger preview
uv run dev --server                         # with full voice pipeline (spawns server.py)
uv run dev-watch                            # auto-restart on file changes

# Deploy to Pi
uv run voxel dev-push --host <pi-ip>        # first time (saves SSH config)
uv run voxel dev-push --logs                # push + tail logs
uv run voxel dev-push --install-service     # set up systemd auto-start

# Dev convenience
uv run voxel dev-pair                       # auto-discover + pair with device
uv run voxel dev-ssh                        # SSH into Pi (uses saved creds)
uv run voxel dev-logs                       # tail Pi logs remotely
uv run voxel dev-restart                    # restart display service on Pi

# Start MCP server (for AI agent integration)
uv run mcp-server                           # SSE on :8082
uv run python -m mcp                        # stdio (for Claude Code)
voxel mcp                                   # via CLI on Pi
```

> **Note:** `npm run dev` starts the React browser UI (design tool for expression iteration). It is NOT the production display renderer. Use `uv run dev` for the actual Pi-equivalent preview.

Editing `display/` or `shared/*.yaml` files triggers hot-reload with `dev-watch` or `dev-push --watch`.

## License

MIT

---

*Built by [Axiom-Labs](https://axiom-labs.dev)*
