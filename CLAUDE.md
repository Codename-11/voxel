# Voxel — Development Guide

## What is this?
Voxel is the character. The physical hardware is called the **Relay**.
Voxel is a pocket-sized AI companion device built on Raspberry Pi Zero 2W + PiSugar Whisplay HAT. It features an animated cube mascot character with expressive eyes/mouth, voice interaction, and connects to the Axiom-Labs AI agent team via OpenClaw.

- **Hardware:** Pi Zero 2W + PiSugar Whisplay HAT (240x280 IPS LCD, dual mics, speaker, buttons, RGB LED)
- **Repo:** ~/voxel (local, not yet on GitHub)
- **OpenClaw Gateway:** http://172.16.24.250:18789

## Architecture

**React + WebSocket + Python backend.** The React app (`app/`) is the production renderer — what you see in the browser IS what runs on the Pi via WPE/Cog. Python (`server.py`) is the backend: state machine, hardware I/O, AI pipelines. They communicate over WebSocket on port 8080.

```
  React UI (app/)              Python Backend (server.py)
  ┌─────────────────┐          ┌──────────────────────────┐
  │ Framer Motion    │◄──ws──►│ State Machine             │
  │ face animation   │  :8080  │ Hardware (buttons/LED/bat)│
  │ mood/style/mouth │         │ AI (OpenClaw, STT, TTS)   │
  └────────┬────────┘          └──────────┬───────────────┘
           │                              │
     shared/*.yaml                   shared/*.yaml
     (expressions, styles, moods)    (moods, expressions)
```

**On the Pi:** WPE WebKit renders the React app fullscreen on the LCD. Python backend runs as a systemd service. No pygame in production.

**On desktop:** `npm run dev` opens a browser window. `uv run server.py` runs the backend. Both hot-reload.

## Project Structure

```
voxel/
├── server.py                    # Python WebSocket backend (state, hardware, AI)
├── main.py                      # Legacy pygame entry point (fallback only)
├── package.json                 # Root package.json (proxies to app/)
├── app/                         # React production UI (Vite + React + Framer Motion)
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
├── core/                        # AI integration
│   ├── gateway.py               # OpenClaw API client (chat completions)
│   ├── stt.py                   # Speech-to-text (Whisper API)
│   ├── tts.py                   # Text-to-speech (ElevenLabs/edge-tts)
│   └── audio.py                 # Audio capture/playback
├── face/                        # Renderer abstraction + pygame fallback
│   ├── base.py                  # Abstract renderer interface (BaseRenderer)
│   ├── renderer.py              # Pygame implementation of BaseRenderer
│   ├── character.py             # Pygame sprite-based cube character
│   ├── expressions.py           # Python mood dataclasses (mirrors shared YAML)
│   ├── styles.py                # Python style definitions (mirrors shared YAML)
│   └── mouth.py                 # Audio amplitude → mouth frame mapping
├── hardware/                    # Platform abstraction (Pi vs desktop)
│   ├── platform.py              # Auto-detect Pi vs desktop (IS_PI flag)
│   ├── display.py               # LCD / Pygame window
│   ├── buttons.py               # GPIO / keyboard mapping
│   ├── led.py                   # RGB LED / visual indicator
│   └── battery.py               # PiSugar / mock battery
├── states/                      # Application state machine
│   └── machine.py               # IDLE → LISTENING → THINKING → SPEAKING
├── config/
│   └── default.yaml             # Settings (agents, audio, power management)
├── run_dev_windows.bat          # Windows: starts backend + frontend
├── run.sh                       # macOS/Linux: starts backend + frontend
├── assets/                      # Concept art, fonts, icons
├── voxel.service                # Systemd: Python backend (server.py)
└── voxel-ui.service             # Systemd: WPE/Cog browser (React UI on LCD)
```

## Hardware Constraints

**CRITICAL — Design everything for these limits:**
- **Display:** 240x280 pixels, SPI interface (ST7789 controller), 60fps target via WPE
- **CPU:** ARM Cortex-A53 (quad-core 1GHz) — WPE WebKit is GPU-accelerated on Pi
- **RAM:** 512MB — keep memory footprint minimal
- **Audio:** WM8960 codec, dual MEMS mics, mono speaker
- **Input:** Mouse-style buttons (left/right click), no touch screen
- **Power:** PiSugar 3 battery (1200mAh), sleep modes important

**Rendering approach:** React + Framer Motion via WPE/Cog on the Pi. CSS animations are GPU-accelerated. Pygame exists as a fallback renderer only.

## Character Design

The mascot is a **dark charcoal rounded cube** with **glowing cyan/teal accent lines** on edges. Semi-transparent glass quality. Isometric 2.5D flat style.

**Face:** Large expressive oval eyes with glossy highlights, small mouth. The face fills most of the 240x280 screen.

## Expression System

Defined in `shared/expressions.yaml` (single source of truth). 16 moods, each with:
- `eyes` — openness, pupil size, gaze, blink rate, squint, width/height
- `mouth` — openness, smile amount, width
- `body` — bounce speed/amount, tilt, scale
- `leftEye` / `rightEye` — optional per-eye overrides for asymmetric expressions
- `eyeColorOverride` — optional color tint (used by battery moods)

3 face styles defined in `shared/styles.yaml`: **kawaii** (default), **retro**, **minimal**.

Transitions between moods are smooth (lerp via Framer Motion, ~300ms).

## State Machine

`states/machine.py` — 7 states: IDLE, LISTENING, THINKING, SPEAKING, ERROR, SLEEPING, MENU

Flow: IDLE → (button press) → LISTENING → (release) → THINKING → (response) → SPEAKING → IDLE
Any state → (button) → MENU → (button) → previous state
Long idle → SLEEPING → (button) → IDLE

State-to-mood mapping defined in `shared/moods.yaml`.

## OpenClaw Integration

`core/gateway.py` — Uses the gateway's `/v1/chat/completions` endpoint in **non-streaming mode** (streaming returns empty on this gateway version).

Session key: `agent:{agent_id}:companion` — separate from Discord and ClawPort sessions.

Supports switching between agents: Daemon, Soren, Ash, Mira, Jace, Pip.

## Audio Pipeline

```
Button press → record from dual mics (WAV)
  → Whisper API (cloud STT)
  → text to OpenClaw gateway
  → response text
  → ElevenLabs/edge-tts (cloud TTS)
  → playback through speaker
  → amplitude sent via WebSocket → React mouth animation
```

## WebSocket Protocol

`server.py` ↔ React frontend on `ws://localhost:8080`.

**Server → Client (state pushes):**
```json
{ "type": "state", "mood": "thinking", "style": "kawaii", "speaking": false,
  "amplitude": 0.0, "battery": 100, "state": "THINKING", "agent": "daemon" }
```

**Client → Server (commands):**
```json
{ "type": "set_mood", "mood": "happy" }
{ "type": "set_style", "style": "retro" }
{ "type": "cycle_state" }
{ "type": "button", "button": "press" }
```

## Key Libraries

**Frontend (React):**
- **React 19** + **Framer Motion 12** — animation
- **Tailwind CSS 4** — styling
- **Vite 8** — build/dev server
- **js-yaml** — shared YAML loading

**Backend (Python):**
- **websockets** — WebSocket server
- **pyyaml** — shared YAML loading
- **openai** — Whisper STT
- **requests** — OpenClaw gateway API
- **numpy** — audio amplitude analysis
- **edge-tts** — free fallback TTS

**Pi-only:**
- **spidev** — SPI display driver (for pygame fallback)
- **RPi.GPIO** — buttons and LED

## Configuration

`config/default.yaml` defines all settings. User overrides in `config/local.yaml` (gitignored). Key sections: gateway (URL/token/default agent), agents (6 defined with voice assignments), audio, power management.

Shared expression/style/mood data lives in `shared/*.yaml` — read by both Python and React.

## Development Workflow

Uses [uv](https://docs.astral.sh/uv/) for Python, npm for the React app. Python 3.13 pinned via `.python-version`.

### Quick start (any platform):

```bash
# Windows
run_dev_windows.bat

# macOS / Linux
./run.sh
```

This starts both processes:
- **Backend:** `uv run server.py` — WebSocket server on port 8080
- **Frontend:** `npm run dev` (proxied from root to `app/`) — Vite dev server on port 5173

### Manual start:

```bash
# Terminal 1 — backend
uv run server.py

# Terminal 2 — frontend
npm run dev
```

### Frontend only (no backend):

```bash
npm run dev
```

The React app works standalone — falls back to local state when no WebSocket connection. Dev panel auto-opens. Press backtick (`` ` ``) to toggle the dev panel.

### Editing shared data:

Changes to `shared/*.yaml` trigger HMR in the React app (Vite watches the directory). Python backend reads YAML at startup.

### Deploy to Pi:

```bash
git pull origin main
uv sync
npm run build    # Produces app/dist/
# WPE/Cog serves app/dist/ fullscreen
sudo systemctl restart voxel
```

## Conventions
- Python 3.11+, type hints everywhere
- Dataclasses for configuration/state objects
- Logging via stdlib `logging` module
- Config loaded from YAML, not hardcoded
- All hardware access behind abstraction layer (hardware/ modules)
- Shared data in `shared/*.yaml` — single source of truth for both Python and React
- State changes logged: "State: IDLE → LISTENING"
- Button input debounced in hardware/buttons.py
