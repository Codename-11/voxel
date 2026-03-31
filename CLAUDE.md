# Voxel — Development Guide

## What is this?
Voxel is the character. The physical hardware is called the **Relay**.
Voxel is a pocket-sized AI companion device built on Raspberry Pi Zero 2W + PiSugar Whisplay HAT. It features an animated cube mascot character with expressive eyes/mouth, voice interaction, and connects to the Axiom-Labs AI agent team via OpenClaw.

- **Hardware:** Pi Zero 2W + PiSugar Whisplay HAT (240x280 IPS LCD, dual mics, speaker, buttons, RGB LED)
- **Repo:** github.com/Codename-11/voxel
- **OpenClaw Gateway:** configured via `config/local.yaml` (`gateway.url`)

## Architecture

**Three services + PIL renderer + WebSocket backend.** The guardian (`display/guardian.py`) starts first, owns the display during boot, handles WiFi AP onboarding, and monitors service health. The display service (`display/service.py`) renders frames with PIL and pushes them to the SPI LCD via the WhisPlay driver on the Pi, or to a tkinter preview window on desktop. The Python backend (`server.py`) manages state, hardware I/O, and AI pipelines. They communicate over WebSocket on port 8080. The React app (`app/`) exists as a browser-based dev UI but is NOT the production renderer.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Pi Zero 2W                               │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │   Guardian    │    │   Backend    │    │  Display Service  │  │
│  │  (watchdog)   │    │  server.py   │    │  display/         │  │
│  │              │    │              │    │   service.py      │  │
│  │ Boot splash  │    │ State machine│◄ws►│ PIL renderer      │  │
│  │ WiFi AP mode │    │ Voice pipeline│:8080│ Button polling    │  │
│  │ Crash recovery│    │ Gateway/STT/ │    │ Animations/moods  │  │
│  │ LED patterns │    │  TTS/battery │    │ Config srv :8081  │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬────────────┘  │
│    lock file               │                SPI + GPIO          │
│                       ┌────┴────┐         ┌─────┴──────────┐    │
│                       │MCP :8082│         │ WhisPlay HAT   │    │
│                       │stdio+SSE│         │ LCD 240x280    │    │
│                       └────┬────┘         │ Mic/Spk/LED    │    │
│                            │              │ Button (pin 11)│    │
│                            │              └────────────────┘    │
│              ┌─────────────┼──────────────┐                     │
│              │  OpenClaw   │  Whisper API  │                     │
│              │  Gateway    │  TTS Provider │                     │
│              │  (HTTP+SSE) │  (HTTP)       │                     │
│              └─────────────┴──────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

**On the Pi:** The guardian service starts first, owns the display during boot, handles WiFi AP mode onboarding, and monitors service health. It hands off to the display service once it's ready (via lock file at `/tmp/voxel-display.lock`). The display service renders PIL frames directly to the SPI LCD via PiSugar's WhisPlay driver. A config web server runs on port 8081 with QR code access and PIN auth.

**On desktop:** `uv run dev` opens a tkinter preview window showing the 240x280 face alongside a dev panel control window for changing moods, states, and styles. `uv run dev-watch` adds auto-reload on file changes. Pass `--no-panel` to disable the dev panel.

**React app (`app/`):** Browser-based dev UI with Framer Motion animations. Not used in production on the Pi. Useful for rapid expression/style iteration in a browser with HMR. WPE/Cog rendering is a future optimization (see `docs/hardware.md`).

**Operating modes:** Standalone (face + menu + config UI) → Connected (+ AI chat via gateway) → MCP (+ external agent control) → Webhooks (+ outbound events). Each layer is additive and optional. MCP and webhooks are disabled by default.

## Project Structure

```
voxel/
├── server.py                    # Python WebSocket backend (state, hardware, AI)
├── AGENTS_SETUP.md              # Agent integration guide (MCP setup, decision tree)
├── package.json                 # Root package.json (proxies to app/)
├── display/                     # PIL-based display engine (production)
│   ├── guardian.py              # Display guardian — boot watchdog, WiFi AP, crash recovery (Pi only)
│   ├── service.py               # Display service entry point (uv run dev, --server for voice pipeline)
│   ├── __main__.py              # python -m display.service support
│   ├── renderer.py              # PILRenderer — composites all layers into frames
│   ├── state.py                 # DisplayState — shared state for all components
│   ├── led.py                   # LEDController — WhisPlay RGB LED patterns
│   ├── layout.py                # Screen geometry, safe areas, corner radius
│   ├── animation.py             # Lerp, easing, BreathingState, GazeDrift, BlinkState
│   ├── decorations.py           # Per-mood decorative overlays (sparkles, sweat, ZZZs, etc.)
│   ├── emoji_reactions.py        # Emoji reaction system (agent → emoji → mood + decoration)
│   ├── modifiers.py              # Data-driven animation modifiers (bounce, shake, eye_swap, etc.)
│   ├── overlay.py                # Shared RGBA overlay helpers for decoration rendering
│   ├── status_decorations.py     # Connection/battery visual indicators (WiFi arcs, battery icon)
│   ├── dev_panel.py             # Dev control window (mood/state/style controls)
│   ├── boot_animation.py         # Wake-up eye animation on startup (~3s)
│   ├── demo.py                  # DemoController — auto-cycles moods/characters/styles
│   ├── fonts.py                 # Font loading and caching
│   ├── characters/              # Character renderers (pluggable)
│   │   ├── base.py              # Abstract character interface
│   │   ├── voxel.py             # Voxel — eyes-only glowing pills (default)
│   │   ├── cube.py              # Cube — isometric charcoal cube with edge glow
│   │   └── bmo.py               # BMO character (Adventure Time)
│   ├── components/              # UI component renderers
│   │   ├── face.py              # Face compositing (eyes, mouth via character)
│   │   ├── menu.py              # Settings/menu overlay
│   │   ├── status_bar.py        # Battery, WiFi, agent indicators
│   │   ├── transcript.py        # Chat transcript overlay
│   │   ├── button_indicator.py  # Four-zone progress ring + flash pills
│   │   ├── shutdown_overlay.py  # Shutdown countdown (3... 2... 1...)
│   │   ├── qr_overlay.py        # QR code display for config URL
│   │   └── wifi_setup.py        # WiFi AP setup UI
│   ├── backends/                # Output backends (pluggable)
│   │   ├── base.py              # Abstract backend interface
│   │   ├── spi.py               # SPI LCD via WhisPlay driver (Pi production)
│   │   ├── tkinter.py           # tkinter preview window (desktop)
│   │   └── pygame.py            # pygame preview window (desktop alt)
│   ├── config_server.py         # Web config UI on port 8081 (QR + PIN auth)
│   ├── advertiser.py            # UDP broadcast for device discovery (dev-pair)
│   ├── wifi.py                  # WiFi management — AP mode onboarding, nmcli
│   └── updater.py               # Self-update system (git check + install)
├── app/                         # React browser UI (dev/iteration, not production)
│   ├── src/
│   │   ├── App.jsx              # Main app — device frame, dev panel, state
│   │   ├── components/
│   │   │   └── VoxelCube.jsx    # Animated cube face (eyes, mouth, body, moods)
│   │   ├── hooks/
│   │   │   └── useVoxelSocket.js # WebSocket client hook
│   │   ├── expressions.js       # Re-exports from shared YAML
│   │   ├── styles.js            # Re-exports from shared YAML
│   │   └── load-shared.js       # YAML loader for shared data
│   ├── vite.config.js           # Vite config (watches shared/ for HMR)
│   └── package.json             # React dependencies
├── shared/                      # Single source of truth (YAML data layer)
│   ├── expressions.yaml         # 16 mood definitions (eyes, mouth, body configs)
│   ├── styles.yaml              # 3 face styles (kawaii, retro, minimal)
│   ├── moods.yaml               # Mood icons, state-to-mood map, LED behavior
│   └── __init__.py              # Python loader for shared YAML
├── hw/                          # Hardware abstraction (Pi vs desktop)
│   ├── detect.py                # Auto-detect Pi vs desktop (IS_PI, probe_hardware)
│   ├── buttons.py               # GPIO / keyboard mapping
│   └── battery.py               # PiSugar / mock battery
├── cli/                         # Voxel CLI (`uv run voxel <command>`)
│   ├── app.py                   # Argument parsing, all commands
│   ├── doctor.py                # System health diagnostics
│   ├── display.py               # Terminal colors, tables, status icons
│   ├── dev_push.py              # Sync full runtime to Pi over SSH
│   └── setup_wizard.py          # Interactive TUI config wizard (gateway, voice, display, MCP, etc.)
├── core/                        # AI integration
│   ├── gateway.py               # OpenClaw API client (chat completions)
│   ├── stt.py                   # Speech-to-text (Whisper API)
│   ├── tts.py                   # Text-to-speech (OpenAI, edge-tts, ElevenLabs)
│   └── audio.py                 # Audio capture/playback + amplitude
├── states/                      # Application state machine
│   └── machine.py               # IDLE → LISTENING → THINKING → SPEAKING
├── config/
│   └── default.yaml             # Settings (agents, audio, power management)
├── mcp/                         # MCP server (AI agent integration)
│   ├── __init__.py
│   ├── __main__.py              # Entry point (python -m mcp)
│   ├── server.py                # JSON-RPC 2.0 protocol handler (stdio + SSE)
│   └── tools.py                 # Tool definitions and handlers
├── openclaw/                    # OpenClaw integration files
│   ├── SKILL.md                 # Skill definition for OpenClaw agents
│   └── README.md                # Integration guide
├── native/                      # Native C programs
│   ├── boot_splash/             # Early boot LCD splash (~3s after power-on)
│   │   ├── splash.c             # C program: SPI init, ST7789 init, frame push
│   │   ├── generate_splash.py   # Python script to generate RGB565 splash frame
│   │   ├── Makefile             # Build, generate, and install targets
│   │   ├── splash.rgb565        # Pre-rendered frame (134,400 bytes, generated)
│   │   └── splash.png           # PNG preview (generated)
│   └── lvgl_poc/                # Pre-renders RGB565 frames on workstation
├── services/                    # Systemd unit files
│   ├── voxel-splash.service     # Boot splash (C, runs before guardian)
│   ├── voxel-guardian.service   # Guardian watchdog (boot, WiFi, crash recovery)
│   ├── voxel.service            # Backend (server.py)
│   └── voxel-display.service    # Display service (display/service.py)
├── .github/workflows/           # CI/CD
│   ├── ci.yml                   # Lint, import checks, React build
│   └── build-pi-image.yml       # Pre-built Pi image (on release/manual)
├── tests/                       # pytest test suite
│   ├── test_mood_pipeline.py    # Mood transitions, battery, lockout, connection, demo
│   ├── test_state_lifecycle.py  # DisplayState defaults, transcripts, blink/gaze/breathing
│   ├── test_characters.py       # All characters x all moods rendering, tilt, accents
│   └── test_guardian.py         # Guardian screens, lock files, WiFi flag, menu integration
├── _legacy/                     # Archived code (not imported by active code)
│   ├── main.py                  # Old pygame entry point
│   ├── face/                    # Pygame renderer + sprites
│   ├── ui/                      # Old UI screens
│   └── services/                # Archived service files (voxel-ui, voxel-web)
├── user-docs/                   # VitePress documentation site
├── scripts/
│   └── setup.sh                 # Bootstrap script (curl-able, idempotent)
├── run_dev_windows.bat          # Windows: starts backend + frontend
├── run.sh                       # macOS/Linux: starts backend + frontend
└── assets/                      # Concept art, fonts, icons
```

## Hardware Constraints

**CRITICAL — Design everything for these limits:**
- **Display:** 240x280 pixels, SPI interface (ST7789 controller), 30 FPS config target (~20 actual on Pi)
- **CPU:** ARM Cortex-A53 (quad-core 1GHz) — PIL rendering is CPU-bound
- **RAM:** 512MB — keep memory footprint minimal
- **Audio:** WM8960 codec, dual MEMS mics, mono speaker
- **Input:** Single push button (BOARD pin 11, active-HIGH), no touch screen
- **Power:** PiSugar 3 battery (1200mAh), sleep modes important

**Rendering approach:** PIL renders frames in Python, pushed to SPI LCD via WhisPlay driver. Backlight must run at 100% to avoid flicker (software PWM limitation). Corner radius ~40px — content in corners gets clipped by the physical bezel. WPE/Cog is a future optimization (see `docs/hardware.md`).

## Character Design

The mascot is a **dark charcoal rounded cube** with **glowing cyan/teal accent lines** on edges. Semi-transparent glass quality. Isometric 2.5D flat style.

**Face:** Large expressive oval eyes with glossy highlights, small mouth. The face fills most of the 240x280 screen.

**Animation layers:** Characters have idle quirks (cube: edge shimmer, BMO: pixel game/cursor blink), speaking reactions (scale pulse, eye glow), and mood-specific tweaks (excited=extra bounce, thinking=tilt oscillation, error=screen shake). A global BreathingState modulates body scale organically for all characters. GazeDrift uses saccadic eye movement (fast jumps + slow drifts) with pink noise microsaccadic jitter during fixation. BlinkState uses delta-time based animation (frame-rate independent, 150ms wall-clock duration) with asymmetric timing (28% close / 72% open, per Disney research) and blink clustering (35% cluster probability, 1-2 extra blinks per cluster). Width-only perspective (no height perspective -- removed to fix twitching). Float precision positioning with round() only at final draw. `state.dt` tracks actual elapsed time, capped at 3x interval.

**Mood-specific eye shapes:**
- **Happy:** Curved bottom cutout on eyes (smile-shaped, inspired by FluxGarage RoboEyes)
- **Sleepy / low-battery:** Bar-shaped eyes with filleted ends (not elliptical)
- **Closed eyes:** Flat horizontal bars with small fillet radius (not capsules)
- **Sad:** Curved arc eyelid overlay (softer than triangle), tilt increased to +/-15 degrees, openness 0.6
- **Frustrated/angry:** Tilt increased to +/-16 degrees

**Mood decorations:** Per-mood overlays drawn via RGBA compositing (`display/decorations.py`): sparkles (happy/excited), sweat drops (frustrated), ZZZs (sleepy), tears (sad), "!" (surprised), blush circles (happy), thinking dots. Positioned relative to each character's actual face center (stored during `draw()`).

**Status decorations:** Separate from mood decorations, `display/status_decorations.py` renders device event overlays — WiFi arcs on connect, X on disconnect, draining battery icon. These layer on top of mood decorations and are toggled via `display.status_animations` in config.

**Demo mode:** Config-driven showcase mode (`display/demo.py`) auto-cycles through moods, characters, and styles. Enabled via `character.demo_mode` in config. Forces IDLE state and face view.

## Expression System

Defined in `shared/expressions.yaml` (single source of truth). 16 moods, each with:
- `eyes` — openness, pupil size, gaze, blink rate, squint, width/height
- `mouth` — openness, smile amount, width
- `body` — bounce speed/amount, tilt, scale
- `leftEye` / `rightEye` — optional per-eye overrides for asymmetric expressions
- `eyeColorOverride` — optional color tint (used by battery moods)

3 face styles defined in `shared/styles.yaml`: **kawaii** (default), **retro**, **minimal**.

Transitions between moods are smooth (lerp via Framer Motion, ~300ms).

Expressions support data-driven **modifiers** — animation behaviors defined per-mood in YAML and applied at render time by `display/modifiers.py`. Available modifiers: `bounce_boost`, `tilt_oscillation`, `eye_swap`, `shake`, `squint_pulse`, `gaze_wander`. See `shared/expressions.yaml` for usage.

**Composition:** Expressions can inherit via `extends: <mood>` and blend with `blend: {<mood>: <weight>}`. Example: `surprised_by_sound` extends `surprised` with 35% `curious` influence.

**Emoji reactions:** Agents can send leading emoji in responses (e.g. "😊 That's great!"). The display service parses the emoji, maps it to a mood if known (31 emoji → 11 moods), and shows a floating emoji decoration above the face. See `display/emoji_reactions.py`.

## State Machine

`states/machine.py` — 7 states: IDLE, LISTENING, THINKING, SPEAKING, ERROR, SLEEPING, MENU

Flow: IDLE → (hold >400ms) → LISTENING → (release) → THINKING → (response) → SPEAKING → IDLE
Cancel: THINKING → (tap) → IDLE, SPEAKING → (tap) → IDLE
Other views → (hold >1s) → MENU → (tap/hold) → previous state
Long idle → SLEEPING → (button) → IDLE

State-to-mood mapping defined in `shared/moods.yaml`.

## Button Interaction Patterns

Single button (Whisplay HAT BOARD pin 11). All interaction encoded through hold duration. No double-tap.

**From face view (IDLE):**

| Gesture | Action | Timing |
|---------|--------|--------|
| Tap | Toggle view (face / chat) | < 400ms, fires instantly on release |
| Hold | Start recording (push-to-talk) | > 400ms (still held), stays in RECORDING until release |

Once recording starts, the button stays in RECORDING state until release. There is no menu/sleep/shutdown override while recording.

**From chat view:**

| Gesture | Action | Timing |
|---------|--------|--------|
| Tap | Toggle view (face / chat) | < 400ms, fires instantly on release |
| Hold | Open menu | > 1s (fires AT threshold, not on release) |
| Hold | Sleep | > 5s (fires AT threshold) |
| Hold | Shutdown with confirm | > 10s (fires AT threshold) |

**Inside menu:**

| Gesture | Action | Timing |
|---------|--------|--------|
| Tap | Move to next item | < 500ms |
| Hold | Select / enter | > 500ms (fires AT threshold) |
| Idle | Auto-close menu | 5s with no input |

"Back" is the last item in every menu/submenu. For value items (volume, brightness), taps cycle preset values (0/25/50/75/100), hold confirms.

**Talk mode rules:** Push-to-talk activates when the button is held past 400ms, from the face view only (not from menu or chat views). While LISTENING, a tap stops recording. While THINKING, a tap cancels the pipeline and returns to IDLE. While SPEAKING, a tap cancels playback and returns to IDLE. A 500ms minimum recording guard prevents accidental cancel.

Implementation in `display/service.py` (`_poll_button_unified` -- shared by Pi GPIO and desktop spacebar). Visual feedback in `display/components/button_indicator.py` (four-zone progress ring + flash pills). Shutdown shows a 3s countdown overlay (`display/components/shutdown_overlay.py`) -- any press cancels.

## OpenClaw Integration

`core/gateway.py` — Uses the gateway's `/v1/chat/completions` endpoint with **SSE streaming** (falls back to non-streaming if the gateway returns empty or errors).

Session key: `agent:{agent_id}:companion` — separate from Discord and ClawPort sessions.

Supports switching between agents: Daemon, Soren, Ash, Mira, Jace, Pip.

**System context:** Configurable in `config/default.yaml` (`character.system_context`). Tells the agent to be concise, use mood tags (`[happy]`, `[curious]`, etc.), and format for the tiny screen. Sent as a system message with every request. Disable with `character.system_context_enabled: false`.

**Conversation history:** Up to 50 messages (configurable via `pipeline.chat_limit`) are maintained per session and sent with each request so the agent has context from prior turns. History is also served to new WebSocket clients on connect.

**Streaming:** Responses arrive as Server-Sent Events (SSE). Partial text is emitted as `transcript` messages with `status: "partial"` during streaming, then `status: "done"` on completion. If SSE fails, the gateway client falls back to a single non-streaming request.

**Tool calls:** The gateway may include tool call chunks in streamed responses. These are parsed and forwarded to clients as `tool_call` messages with `status: "running"` when started and `status: "done"` when the result is available.

**Emoji reactions:** Agent responses may begin with an emoji prefix (e.g. "\ud83d\ude0a That's great!"). The backend strips the leading emoji, maps it to a mood if recognized (31 emoji mapped to 11 moods), and sends a `reaction` message to clients. Unmapped emoji are still forwarded as visual decorations.

## MCP Server

`mcp/` — Model Context Protocol server exposing Voxel device tools to AI agents. Supports two transports:

- **stdio** — for Claude Code, Codex CLI (local subprocess, `python -m mcp`)
- **SSE** — for OpenClaw gateway, remote agents (HTTP on port 8082, `voxel mcp`)

20 tools exposed:
- **Control:** `set_mood`, `set_style`, `set_character`, `speak_text`, `send_chat_message`, `show_reaction`, `set_led`, `set_volume`, `set_agent`
- **Query:** `get_device_state`, `get_system_stats`, `get_conversation_history`, `get_logs`, `run_diagnostic`, `check_update`
- **Manage:** `set_config`, `restart_services`, `install_update`, `reboot_device`, `connect_wifi`

3 resources: `voxel://state`, `voxel://config`, `voxel://history`.

The MCP server connects to server.py via WebSocket on port 8080 (same protocol as the display service and React app). No additional dependencies required. When `mcp.enabled: true` in config, the display service auto-starts the MCP server as a subprocess and stops it on shutdown. Can also be started manually via `voxel mcp` or the web UI Integration toggle.

OpenClaw skill definition at `openclaw/SKILL.md` teaches agents about Voxel's capabilities.

**Agent setup guide:** `AGENTS_SETUP.md` (repo root) — decision-tree setup for any AI agent. Also served at `GET /setup` on the device (port 8081, no auth) and available via [GitHub raw URL](https://raw.githubusercontent.com/Codename-11/voxel/main/AGENTS_SETUP.md).

**Discovery endpoints (no auth):** `GET /setup` (agent guide), `GET /skill` (tool definitions), `GET /.well-known/mcp` (MCP status JSON). The web UI Integration section has a "Human / Agent" tab with copyable URLs for each.

## Audio Pipeline

```
  Hold button >400ms (face view)
  │
  ▼
LISTENING ──► Record from dual mics (16kHz WAV)
  │              │
  │         Button release
  │              │
  ▼              ▼
THINKING ──► Whisper API (STT) ──► OpenClaw Gateway (SSE)
  │              ~1-3s                  ~2-15s
  │                                      │
  │                              Response text + emoji?
  │                                      │
  ▼                                      ▼
SPEAKING ──► TTS (edge/openai/11labs) ──► Playback + amplitude
  │              ~1-3s                     mouth animation
  │                                        │
  ▼                                        ▼
IDLE ◄──────────────── done ◄───────────── done
```

**TTS providers:** Three providers available via `audio.tts_provider` config:
- **`edge`** (default) — free Microsoft Edge TTS, no API key needed
- **`openai`** — OpenAI TTS API (10 voices, 3 models: `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`). Returns WAV directly. Shares API key with STT (`stt.whisper.api_key` or `OPENAI_API_KEY`). Falls back to edge-tts on failure.
- **`elevenlabs`** — ElevenLabs TTS, highest quality, requires separate API key

## WebSocket Protocol

`server.py` ↔ React frontend on `ws://localhost:8080`.

MCP tools use the same WebSocket protocol on port 8080. The MCP server translates MCP tool calls into WS commands.

**Server → Client (state pushes):**
```json
{ "type": "state", "mood": "thinking", "style": "kawaii", "speaking": false,
  "amplitude": 0.0, "battery": 100, "state": "THINKING", "agent": "daemon",
  "brightness": 80, "volume": 80, "displayMode": "auto", "inputMode": "auto",
  "agents": [...], "connected": false }
```

**Server → Client (conversation):**
```json
{ "type": "transcript", "role": "user", "text": "hello", "status": "done", "timestamp": 1234 }
{ "type": "transcript", "role": "assistant", "text": "hi!", "status": "done", "timestamp": 1234 }
{ "type": "chat_history", "messages": [...] }
{ "type": "button", "button": "left" }
```

**Server → Client (streaming):**
```json
// Partial response (streamed via SSE)
{ "type": "transcript", "role": "assistant", "text": "Hello wo", "status": "partial", "timestamp": 1234 }
// Final response
{ "type": "transcript", "role": "assistant", "text": "Hello world!", "status": "done", "timestamp": 1234 }
```

**Server → Client (emoji reactions):**
```json
// Emoji reaction (agent response had leading emoji)
{ "type": "reaction", "emoji": "\ud83d\ude0a" }
```

**Server → Client (tool calls):**
```json
// Tool call started
{ "type": "tool_call", "id": "call_123", "name": "search_web", "status": "running" }
// Tool call completed
{ "type": "tool_call", "id": "call_123", "name": "search_web", "status": "done", "result": "..." }
```

**Client → Server (commands):**
```json
{ "type": "set_mood", "mood": "happy" }
{ "type": "set_style", "style": "retro" }
{ "type": "set_state", "state": "IDLE" }
{ "type": "set_agent", "agent": "soren" }
{ "type": "set_setting", "section": "audio", "key": "volume", "value": 80 }
{ "type": "button", "button": "press|release|menu|left|right" }
{ "type": "text_input", "text": "hello voxel" }
{ "type": "get_chat_history" }
{ "type": "cycle_state" }
```

## Key Libraries

**Display Service (Python):**
- **Pillow (PIL)** — frame rendering (characters, menus, overlays)
- **qrcode** — QR code generation for config URL
- **watchfiles** — file watching for dev-watch auto-reload

**Backend (Python):**
- **websockets** — WebSocket server
- **pyyaml** — shared YAML loading
- **openai** — Whisper STT + OpenAI TTS
- **requests** — OpenClaw gateway API
- **numpy** — audio amplitude analysis
- **edge-tts** — free fallback TTS
- **paramiko** — SSH for dev-push to Pi
- **rich** — CLI output formatting

**React browser UI (dev/iteration):**
- **React 19** + **Framer Motion 12** — animation
- **Tailwind CSS 4** — styling
- **Vite 8** — build/dev server
- **js-yaml** — shared YAML loading

**Pi-only:**
- **spidev** — SPI display driver
- **RPi.GPIO** — buttons and LED

## Configuration

`config/default.yaml` defines all settings. User overrides in `config/local.yaml` (gitignored). Key sections: gateway (URL/token/default agent), agents (6 defined with voice assignments), audio (including `wake_word: null` placeholder), stt (Whisper), tts (OpenAI/edge-tts/ElevenLabs), pipeline (recording/chat limits), display, power management, character selection (includes `boot_animation`, `greeting_enabled`, `greeting_prompt`, demo mode settings: `demo_mode`, `demo_cycle_speed`, `demo_include_characters`, `demo_include_styles`), dev mode.

**Web config UI:** The display service runs a web server on port 8081 (`display/config_server.py`). A 6-digit PIN is generated on each boot and shown on the LCD. The device also displays a QR code for quick access from a phone or laptop. Auth can be disabled via `web.auth_enabled: false` in `local.yaml`. Features include an eye favicon/logo, browser-based STT (mic button for voice input), and browser TTS (speaker toggle to read responses aloud).

**WiFi onboarding:** On first boot with no known WiFi, the display service starts AP mode ("Voxel-Setup" hotspot at `10.42.0.1`) and serves a config portal. Uses `nmcli` (NetworkManager). See `display/wifi.py`.

Shared expression/style/mood data lives in `shared/*.yaml` — read by both Python and React.

## Voxel CLI

After bootstrap, all Pi management goes through the `voxel` command:

```bash
# Setup & maintenance
voxel setup          # First-time install (apt deps, Node, build, services, wizard)
voxel setup --no-configure  # Skip the interactive wizard after setup
voxel configure      # Interactive TUI wizard (gateway, voice, display, MCP, webhooks, power)
voxel doctor         # Full system health diagnostics
voxel update         # Pull latest, rebuild, restart services
voxel build          # Just rebuild (Python deps + React app)
voxel hw             # Whisplay HAT drivers + config.txt tuning

# Service management
voxel start          # Start services
voxel stop           # Stop services
voxel restart        # Restart services
voxel logs           # Tail service logs
voxel status         # Service/system/hardware status

# Configuration
voxel config         # Show config
voxel config set <section.key> <value>
voxel config get <section.key>

# Dev pairing & remote development (from workstation)
voxel dev-pair                  # Auto-discover device + pair via PIN
voxel dev-pair --host <ip>      # Pair with specific device IP
voxel dev-push                  # Sync full runtime to Pi and run it
voxel dev-push --watch          # Watch for changes, auto-push
voxel dev-push --logs           # Push and tail remote logs
voxel dev-push --update         # git pull + uv sync on Pi first
voxel dev-push --save-ssh       # Save SSH config to local.yaml

# Display testing (on Pi)
voxel display-test              # Direct Whisplay display sanity test

# LVGL PoC (native renderer experiment)
voxel lvgl-build     # Build the LVGL PoC once
voxel lvgl-render    # Render LVGL RGB565 frames locally
voxel lvgl-sync      # Sync rendered LVGL frames to a Pi
voxel lvgl-play      # Play pre-rendered LVGL frames on the Pi
voxel lvgl-deploy    # Render, sync, and play in one command
voxel lvgl-dev       # Opinionated dev loop (render + sync + interactive preview)

# MCP server (AI agent integration)
voxel mcp                       # Start MCP server (SSE on :8082)

# Other
voxel version        # Show version
voxel uninstall      # Remove services + caches
```

## Setup & Onboarding

**One-line Pi setup:**
```bash
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

This runs `voxel setup` which includes hardware driver installation (`voxel hw`) and launches an interactive configuration wizard at the end (`voxel configure`). The wizard walks through gateway, voice, display, MCP, webhooks, and power settings. Skip with `--no-configure`. After completion, reboot. The device auto-starts and guides the user through WiFi + config on the LCD.

**Setup state tracking:** `config/.setup-state` (YAML) tracks: `system_deps`, `drivers_installed`, `build_complete`, `config_created`, `services_installed`, `wifi_configured`, `gateway_configured`. The display service reads this to decide what to show (onboarding screens vs face).

**Five production services (boot order):**
1. `voxel-splash.service` — C boot splash (native/boot_splash/splash.c): runs ~3s after power-on, drives ST7789 LCD via SPI directly from C, shows closed-eye bars on dark background. Type=oneshot, exits after pushing frame (image persists on LCD).
2. `voxel-guardian.service` — display guardian (display/guardian.py): starts after splash, boot animation (wake-up sequence), WiFi AP mode onboarding, service health watchdog, crash recovery screens. Hands off display to voxel-display via lock file.
3. `voxel.service` — backend (server.py): state machine, AI pipelines, battery polling. Starts after guardian.
4. `voxel-display.service` — display service (display/service.py `--url ws://localhost:8080`, PIL→SPI): button input, rendering, config server. Starts after guardian and backend.
5. `voxel-first-boot.service` — one-shot service that runs `voxel hw` on first boot to compile Whisplay HAT drivers. Disables itself after completion. Only used in the pre-built Pi image.

WPE/Cog (`voxel-ui.service`) and static HTTP (`voxel-web.service`) are archived in `_legacy/services/`.

**Pre-built Pi image:** GitHub Actions workflow (`build-pi-image.yml`) builds a flashable `.img` with everything pre-installed. All 5 services are installed and enabled. System packages include `build-essential` (for first-boot driver compilation) and `libportaudio2`. The splash frame (`splash.rgb565`) is pre-copied to `/boot/`. User experience: flash → boot → configure WiFi from phone → done.

## Development Workflow

Uses [uv](https://docs.astral.sh/uv/) for Python, npm for the React app. Python 3.13 pinned via `.python-version`.

### Quick start — PIL display preview (any platform):

```bash
# Local preview (PIL renderer in tkinter window + dev panel)
uv run dev

# Auto-reload on file changes
uv run dev-watch

# Without dev panel
uv run dev --no-panel

# With full voice pipeline (spawns server.py, connects via WebSocket)
uv run dev --server

# Verbose logging (DEBUG level)
uv run dev --verbose
```

These run `display/service.py` which opens a tkinter window showing the 240x280 face exactly as it renders on the Pi's LCD, plus a dev panel control window (`display/dev_panel.py`) for changing moods, states, styles, and triggering actions.

The `--server` flag spawns `server.py` as a child process and auto-connects via WebSocket, enabling the full voice pipeline (STT, gateway, TTS) without running the backend separately.

#### Keyboard shortcuts (in preview window):

| Key | Action |
|-----|--------|
| `1`-`9`, `0` | Set mood (neutral, happy, curious, thinking, listening, excited, sleepy, confused, surprised, focused) |
| `[` / `]` | Cycle through all 16 moods (prev / next) |
| `m` | Toggle settings menu |
| `c` | Toggle view (face / chat) |
| `t` | Toggle transcript overlay |
| `p` | Toggle demo mode |
| `n` | Simulate ambient noise spike |
| `Spacebar` | Simulate hardware button (hold/release) |
| `Escape` | Close preview |

When the menu is open, keys switch to menu navigation: `w`/`s` = up/down, `a`/`d` = adjust, `Enter`/`Space` = select, `m`/`Escape` = back.

#### Logging:

Logging is configured via `core/log.py`. Colored output to stderr, optional file output.

| Control | Description |
|---------|-------------|
| `--verbose` / `-v` | Enable DEBUG level logging |
| `VOXEL_LOG_LEVEL` env | Set level: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |
| `VOXEL_LOG_FILE` env | Path to additional log file (appended, always DEBUG level) |

Log levels used: `DEBUG` (per-frame details, protocol messages), `INFO` (state transitions, mood changes, lifecycle), `WARNING` (fallbacks, degraded functionality), `ERROR` (failures affecting UX).

### Pair with device (first time):

```bash
# Auto-discover device on LAN + pair via PIN
uv run voxel dev-pair

# Or specify IP manually
uv run voxel dev-pair --host <pi-ip>
```

The device broadcasts its presence via UDP on port 41234. `dev-pair` discovers it, prompts for the 6-digit PIN shown on the LCD, then saves SSH credentials locally. After pairing, all `dev-*` commands (dev-push, dev-ssh, dev-logs, dev-restart) work without re-entering credentials.

### Push to Pi hardware:

```bash
# Sync full runtime + run on Pi (fast dev loop)
uv run voxel dev-push --logs

# Watch for local changes and auto-push
uv run voxel dev-push --watch

# First time (if not using dev-pair) — save SSH credentials
uv run voxel dev-push --host <pi-ip> --save-ssh
```

### React browser UI (for expression iteration):

```bash
# Windows
run_dev_windows.bat

# macOS / Linux
./run.sh
```

This starts both processes:
- **Backend:** `uv run server.py` — WebSocket server on port 8080
- **Frontend:** `npm run dev` (proxied from root to `app/`) — Vite dev server on port 5173

The React app works standalone — falls back to local state when no WebSocket connection. Dev panel auto-opens. Press backtick (`` ` ``) to toggle the dev panel.

### Testing:

```bash
# Run all tests
uv run pytest

# Verbose output
uv run pytest tests/ -v
```

pytest config is in `pyproject.toml` (`[tool.pytest.ini_options]`): test paths set to `tests/`, 10s timeout per test. Tests cover the mood pipeline (transitions, battery reactions, manual lockout, connection changes, demo mode), display state lifecycle (defaults, transcripts, blink/gaze/breathing, idle prompts), and character rendering (all characters x all moods, tilt cuts, accent colors).

### Editing shared data:

Changes to `shared/*.yaml` trigger HMR in the React app (Vite watches the directory). `dev-watch` also reloads on shared YAML changes.

### Deploy to Pi:

```bash
# First-time (curl bootstrap):
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash

# After that, update with:
voxel update    # git pull + rebuild + restart services
```

## Mood Pipeline

The idle personality system (`display/idle.py`) returns `(mood, urgent)` via `update_ex()`. Urgent moods (battery warnings, connection status) bypass the 5-second manual lockout that protects dev panel / WebSocket mood changes from being overwritten. Demo mode blocks idle personality entirely. Connection changes fire immediately (no shared cooldown). The `button_flash` flag auto-clears in the render loop. The ambient monitor checks `not state.demo_mode`.

## Standardised Indicators

Activity indicators are coordinated across screen, LED, and state:

| Activity | Screen | LED |
|----------|--------|-----|
| Ambient hearing | Pulsing mic dot (bottom-right) | Cyan flash on spike |
| Listening (talk) | Pulse ring + "Talk" label | Solid cyan |
| Speaking | Waveform pill | Green blink |
| Button held | Progress ring with zones | White solid |

Status decorations (`display/status_decorations.py`) show connection events (WiFi arcs/X) and battery warnings (draining battery icon) independently from mood decorations, at `STATUS_ICON_Y` to avoid visual overlap. Configurable via `display.status_animations` and `display.ambient_indicator`.

## Event Integration

System events trigger coordinated visual responses across mood, emoji reactions, decorations, and LED:

| Event | Mood | Emoji | Decoration | LED |
|-------|------|-------|------------|-----|
| Agent tool call running | working | ⚙ (10s) | Working dots | Via state |
| Agent tool call done | (restored) | (cleared) | — | Via state |
| Ambient noise spike | surprised | ❗ (1.5s) | Surprised "!" | Cyan flash |
| Connection lost | sad | ❌ (2s) | WiFi X slash | — |
| Connection restored | happy | ✅ (2s) | WiFi arcs | — |
| Low battery (<20%) | low_battery | 🔋 (2.5s) | Battery drain | — |
| Critical battery (<10%) | critical_battery | 🚨 (3s) | Battery pulse | — |
| Agent response emoji | (mapped) | (from text) | — | — |

Agent responses are parsed for leading emoji (e.g. "😊 That sounds great!") which triggers both a mood change and a floating emoji decoration. Emoji parsing happens in both `server.py` (voice/text pipeline) and `config_server.py` (web chat).

## Conventions
- Python 3.11+, type hints everywhere
- Dataclasses for configuration/state objects
- Logging via stdlib `logging` module
- Config loaded from YAML, not hardcoded
- All hardware access behind abstraction layer (hw/ modules)
- Shared data in `shared/*.yaml` — single source of truth for both Python and React
- State changes logged: "State: IDLE → LISTENING"
- Button input debounced in hw/buttons.py
