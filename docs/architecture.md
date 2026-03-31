# Architecture

## Overview

Voxel uses a **PIL display service + WebSocket + Python backend** architecture with a **guardian watchdog** for reliability. Three systemd services run on the Pi. The display service (`display/service.py`) renders frames with PIL and pushes RGB565 data to the SPI LCD via the WhisPlay driver on Pi, or to a tkinter preview window on desktop. The Python backend (`server.py`) manages state, hardware I/O, and AI pipelines. They communicate over WebSocket on port 8080. The guardian (`display/guardian.py`) starts first, owns the display during boot, handles WiFi onboarding, and monitors service health.

The React app (`app/`) is a **browser-based dev tool** for rapid expression/style iteration with HMR — it is NOT the production renderer.

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Raspberry Pi Zero 2W                        │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │    Guardian      │  │    Backend       │  │   Display Service   │ │
│  │ display/         │  │   server.py      │  │ display/service.py  │ │
│  │ guardian.py      │  │                  │  │                     │ │
│  │                  │  │ State machine    │  │ PILRenderer         │ │
│  │ Boot splash      │  │ Voice pipeline   │  │ Button polling      │ │
│  │ WiFi AP mode     │  │ OpenClaw gateway │  │ Animations + moods  │ │
│  │ Crash recovery   │  │ Battery polling  │  │ Config server :8081 │ │
│  │ Service watchdog │  │ Chat history     │  │ LED patterns        │ │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬──────────┘ │
│           │                     │                        │           │
│      lock file            ws :8080                  SPI + GPIO      │
│   /tmp/voxel-display      ◄────►                        │           │
│        .lock                    │                        │           │
│                          ┌──────┴──────┐          ┌──────┴────────┐ │
│                          │  MCP Server │          │ WhisPlay HAT  │ │
│                          │   :8082     │          │ ST7789 LCD    │ │
│                          │ stdio / SSE │          │ WM8960 audio  │ │
│                          └──────┬──────┘          │ RGB LED       │ │
│                                 │                 │ Button (pin11)│ │
│                                 │                 └───────────────┘ │
│                                 │                                   │
│  ┌──────────────────────────────┼───────────────────────────────┐   │
│  │         External Services    │                               │   │
│  │                              │                               │   │
│  │  ┌───────────────────┐  ┌───┴───────────────┐               │   │
│  │  │ Whisper API (STT) │  │  OpenClaw Gateway  │               │   │
│  │  │ cloud / HTTP POST │  │  HTTP + SSE        │               │   │
│  │  └───────────────────┘  └───────────────────┘               │   │
│  │  ┌───────────────────┐  ┌───────────────────┐               │   │
│  │  │ TTS Provider      │  │  AI Agents (MCP)  │               │   │
│  │  │ edge/openai/11labs│  │  Claude, OpenClaw  │               │   │
│  │  └───────────────────┘  └───────────────────┘               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

```
┌──────────┐  UDP :41234   ┌──────────┐  ws :8080    ┌──────────────┐
│ Dev      │◄─ broadcast ──│ Display  │◄────────────►│   Backend    │
│ Machine  │  (discovery)  │ Service  │  state/cmds  │  server.py   │
│          │               │          │              │              │
│ dev-pair │─ PIN auth ───►│ Config   │              │ STT ────────►│
│ dev-push │─ SSH/rsync ──►│ Server   │              │ Gateway ────►│
│          │               │ :8081    │              │ TTS ────────►│
└──────────┘               └──────────┘              └──────────────┘
                                │                           │
                           SPI + GPIO                  HTTP / SSE
                                │                           │
                           ┌────┴────┐               ┌──────┴──────┐
                           │WhisPlay │               │  OpenClaw   │
                           │  HAT    │               │  Gateway    │
                           │ LCD/Mic │               │  + Whisper  │
                           │ Spk/LED │               │  + TTS API  │
                           └─────────┘               └─────────────┘
```

### WebSocket Message Flow

```
   Display Service                 Backend (server.py)              MCP Server
   display/service.py              ws://localhost:8080              :8082
        │                                │                            │
        │── { set_mood, set_state } ────►│                            │
        │◄── { state, mood, battery } ──│                            │
        │◄── { transcript, partial } ────│◄── chat completions ──── OpenClaw
        │◄── { reaction, emoji } ────────│                            │
        │                                │◄── { set_mood } ──────────│
        │                                │──► { state } ─────────────│
        │                                │                            │
        │── { button, press/release } ──►│                            │
        │                                │── record audio ──► STT    │
        │                                │── text ──────────► Gateway │
        │                                │◄── response ──── Gateway  │
        │                                │── text ──────────► TTS    │
        │◄── { speaking, amplitude } ────│◄── audio ──────── TTS    │
        │                                │                            │
   React App (dev)                       │                            │
   ws://localhost:8080                   │                   AI Agents
        │── { text_input, set_mood } ───►│                  (Claude,
        │◄── { state, transcript } ──────│                   OpenClaw)
```

## Layers

### 1. PIL Display Service (`display/service.py`)

The **production renderer**. Renders frames with Pillow (PIL), compositing characters, menus, overlays, and status indicators into 240x280 images. On Pi, frames are pushed as RGB565 to the SPI LCD via the WhisPlay driver (`display/backends/spi.py`). On desktop, frames display in a tkinter window (`display/backends/tkinter.py`).

| Path | Purpose |
|------|---------|
| `display/ambient.py` | Ambient audio monitor (mic RMS for deterministic face reactions) |
| `display/animation.py` | Lerp, easing, transition helpers |
| `display/emoji_reactions.py` | Emoji reaction parser, mood mapping, and floating decoration |
| `display/fonts.py` | Font loading and caching |
| `display/layout.py` | Screen geometry, safe areas, corner radius |
| `display/modifiers.py` | Data-driven expression modifier registry (bounce, shake, eye_swap, etc.) |
| `display/overlay.py` | Shared RGBA overlay compositing helpers |
| `display/renderer.py` | PILRenderer — composites all layers into frames |
| `display/state.py` | DisplayState — shared state for all components |
| `display/characters/` | Pluggable character renderers (cube, bmo) |
| `display/components/` | UI components: face, menu, status_bar, transcript, button_indicator, shutdown_overlay, qr_overlay, wifi_setup, onboarding |
| `display/backends/spi.py` | WhisPlay SPI driver (Pi) |
| `display/backends/tkinter.py` | tkinter preview window (desktop) |
| `display/backends/pygame.py` | pygame preview window (desktop alt) |
| `display/config_server.py` | Web config UI on port 8081 (QR + PIN auth) |
| `display/led.py` | LEDController — WhisPlay RGB LED |
| `display/wifi.py` | WiFi management — AP mode onboarding, nmcli |
| `display/dev_panel.py` | Dev control window (mood/state/style GUI) |
| `display/status_decorations.py` | Connection/battery visual indicators (WiFi arcs, disconnect X, draining icon) |
| `display/updater.py` | Self-update system (git check + install) |

**Status decorations** (`display/status_decorations.py`) are separate from mood decorations (`display/decorations.py`). They visualize device events: WiFi arcs on connect, an X on disconnect, and a draining battery icon for low power warnings. Status decorations layer on top of mood decorations (both can render simultaneously) and are configurable via `display.status_animations` in config.

#### Modifier System

Expression modifiers (`display/modifiers.py`) replace hardcoded per-mood animation logic with a data-driven registry. Each modifier is a function that adjusts rendering parameters (bounce, tilt, gaze, shake) and is configured per-expression in `shared/expressions.yaml`:

```yaml
thinking:
  modifiers:
    - type: eye_swap
      cycle: 7.0
      gaze_influence: 0.1
    - type: tilt_oscillation
      speed: 0.8
      amount: 2.5
```

Available modifiers: `bounce_boost`, `tilt_oscillation`, `eye_swap`, `shake`, `squint_pulse`, `gaze_wander`. Characters call `apply_modifiers()` once per frame and read the returned overrides dict. Expressions also support `extends` (inheritance) and `blend` (weighted composition).

#### Emoji Reactions

Agents can include leading emoji in responses (e.g. "😊 That sounds great!"). The emoji reaction system (`display/emoji_reactions.py`) parses the emoji, maps it to a mood if known (31 emoji covering 11 moods), and displays a floating emoji decoration above the face that auto-dismisses after 3 seconds. Unmapped emoji still display visually without a mood change.

System events (tool calls, ambient spikes, connection changes, battery warnings) also trigger emoji reactions automatically. For example, a loud ambient noise shows ❗ alongside the surprised mood, and a gateway connection loss shows ❌ with the sad mood. These reinforce state changes with personality.

#### Ambient Monitor

`display/ambient.py` monitors mic input in a background thread (no audio recording — just RMS amplitude). Deterministic reactions without any LLM call: loud spike → surprised, sustained sound → curious, extended silence → sleepy. Beat detection tracks rhythm for body bounce sync. Configurable via `audio.ambient_react`, `audio.ambient_sensitivity`, and `audio.ambient_silence_timeout`.

### 1b. React Browser UI (`app/`) — Dev Tool Only

Browser-based dev UI for rapid expression/style iteration. Built with React 19, Framer Motion 12, Tailwind CSS 4, Vite 8. **Not used in production on the Pi.**

| File | Purpose |
|------|---------|
| `App.jsx` | Main app — device frame, status bar, dev panel overlay |
| `components/VoxelCube.jsx` | Animated cube face — eyes, mouth, body, mood icons. All 16 moods, 3 styles. |
| `hooks/useVoxelSocket.js` | WebSocket client — auto-reconnect, state sync, command methods |
| `expressions.js` / `styles.js` | Re-export expression and style data from shared YAML |
| `load-shared.js` | YAML import helper (loads `shared/*.yaml` via Vite raw imports + js-yaml) |

**Standalone mode:** When the backend isn't connected, the app runs entirely client-side with local state and a dev panel for testing moods, styles, and speaking animation.

### 2. Python WebSocket Backend (`server.py`)

Manages application state and bridges hardware/AI to the frontend.

| Concern | Implementation |
|---------|---------------|
| WebSocket server | `websockets` library, port 8080 |
| State machine | `states/machine.py` (7 states) |
| State broadcasting | Push full UI state to all connected clients on change |
| Runtime settings | `config/settings.py` loads `default.yaml` + `local.yaml`, persists mutable user settings |
| Hardware polling | 20Hz loop — battery (on Pi only; display service handles button input) |
| Mood mapping | `shared/moods.yaml` defines state-to-mood map |

### 3. Shared YAML Data Layer (`shared/`)

Single source of truth for expression, style, and mood data. Both Python and React read from these files.

| File | Contents |
|------|----------|
| `expressions.yaml` | 16 mood definitions (eyes, mouth, body, per-eye overrides, color overrides) |
| `styles.yaml` | 3 face styles (kawaii, retro, minimal) with eye/mouth rendering config |
| `moods.yaml` | Mood icons, state-to-mood map, LED behavior per state, status bar colors |
| `__init__.py` | Python loader functions (`load_expressions()`, `load_styles()`, `load_moods()`) |

**React reads YAML** via Vite raw imports + js-yaml parsing at build time. **Python reads YAML** via PyYAML at startup.

Vite watches `shared/` and triggers HMR on YAML changes, so edits to expressions or styles are reflected instantly in the browser.

### 4. Core — AI Pipelines (`core/`)

| Module | Purpose |
|--------|---------|
| `gateway.py` | OpenClaw chat completions (SSE streaming, fallback to non-streaming). Session: `agent:{id}:companion` |
| `stt.py` | Whisper API. Records WAV → uploads → returns transcript |
| `tts.py` | OpenAI TTS / ElevenLabs / edge-tts (fallback). Text → audio bytes |
| `audio.py` | Audio capture/playback. `get_amplitude()` for mouth sync |

### 5. Hardware Abstraction (`hw/`)

Platform-detected at startup. Same interface on desktop and Pi.

| Module | Desktop | Pi |
|--------|---------|-----|
| `detect.py` | Sets `IS_PI=False` | Sets `IS_PI=True`, `probe_hardware()` |
| `buttons.py` | Keyboard mapping (Z/X/Space/Esc) | GPIO active-low polling |
| `battery.py` | Returns 100% always | PiSugar HTTP API |

LED control is handled by `display/led.py` (`LEDController`) which drives the WhisPlay RGB LED based on device state.

> **Legacy:** The old pygame renderer (`face/`) and hardware display/LED modules are archived in `_legacy/`.

### 6. States (`states/`)

Finite state machine driving application behavior.

```
         ┌─────────┐
         │  IDLE   │◄──────────────────┐
         └────┬────┘                   │
              │ hold >400ms (face view)│ response done
         ┌────▼────┐            ┌──────┴──────┐
         │LISTENING│            │  SPEAKING   │
         └────┬────┘            └──────▲──────┘
              │ button release         │ TTS ready
         ┌────▼────┐            ┌──────┴──────┐
         │THINKING │────────────│  (gateway)  │
         └────┬────┘ response   └─────────────┘
              │ error
         ┌────▼────┐
         │  ERROR  │──── timeout ──► IDLE
         └─────────┘

Any state ──── long idle ──► SLEEPING
Chat view ──── hold >1s ──► MENU ──► previous state
```

State transitions trigger mood changes (via `shared/moods.yaml` state_map) and WebSocket broadcasts to the frontend.

## WebSocket Protocol

**Server → Client (state pushes):**
```json
{ "type": "state", "mood": "thinking", "style": "kawaii", "speaking": false,
  "amplitude": 0.0, "battery": 100, "state": "THINKING", "agent": "daemon",
  "brightness": 80, "volume": 80, "displayMode": "auto", "inputMode": "auto",
  "agents": [...], "connected": false }
```

**Server → Client (conversation):**
```json
{ "type": "transcript", "role": "user|assistant", "text": "...", "status": "transcribing|thinking|done|error", "timestamp": 1234 }
{ "type": "chat_history", "messages": [...] }
{ "type": "button", "button": "left|right|press|release|menu" }
```

**Client → Server:**
```json
{ "type": "set_mood", "mood": "happy" }
{ "type": "set_style", "style": "retro" }
{ "type": "set_state", "state": "THINKING" }
{ "type": "set_agent", "agent": "soren" }
{ "type": "set_setting", "section": "display", "key": "brightness", "value": 70 }
{ "type": "text_input", "text": "hello voxel" }
{ "type": "get_chat_history" }
{ "type": "cycle_state" }
{ "type": "button", "button": "left|right|press|release|menu" }
{ "type": "ping" }
```

## Data Flow: Voice Interaction

### Voice Pipeline Flow

```
  User holds button >400ms (face view only)
  │
  ▼
IDLE ──────────────────────────────────────────────────────┐
  │  hold >400ms                                           │
  ▼                                                        │
LISTENING ──► Record audio from dual mics (16kHz WAV)      │
  │              │                                         │
  │         Button release                                 │
  │         (or tap to cancel ──► IDLE)                    │
  │              │                                         │
  ▼              ▼                                         │
THINKING ──► Whisper API ──► OpenClaw Gateway              │
  │            (STT)           (SSE streaming)              │
  │            ~1-3s           ~2-15s                       │
  │              │                │                         │
  │              │         Response text                    │
  │              │         + emoji prefix?                  │
  │              │                │                         │
  │   (tap to cancel ──► IDLE)   │                         │
  │                              ▼                         │
SPEAKING ◄───────────── TTS (edge/openai/11labs)           │
  │                        ~1-3s                           │
  │                                                        │
  │  Playback through speaker                              │
  │  Amplitude ──► ws ──► mouth animation                  │
  │  (tap to cancel ──► IDLE)                              │
  │                                                        │
  ▼                                                        │
IDLE ◄─────────────── playback complete ───────────────────┘
```

### Detailed Step-by-Step

```
1. User holds button >400ms from face view (hardware GPIO or spacebar)
   -> server.py: State IDLE -> LISTENING
   -> WebSocket push: { mood: "listening", state: "LISTENING" }
   -> Display: eyes widen, lean forward, sound wave icon

2. User releases button
   -> server.py: State LISTENING -> THINKING (immediate, no frame flash)
   -> Audio: stop recording -> WAV bytes
   -> WebSocket push: { mood: "thinking", state: "THINKING" }
   -> Display: asymmetric brow raise, gaze up, brain+cog icon

3. STT (Whisper API)
   -> WAV bytes -> HTTP POST -> transcript text

4. Gateway (OpenClaw)
   -> transcript -> POST /v1/chat/completions -> response text (SSE stream)
   -> Partial text emitted as { transcript, status: "partial" }
   -> Leading emoji parsed -> { reaction } message + mood change

5. TTS (OpenAI TTS / ElevenLabs / edge-tts)
   -> response text -> HTTP POST -> audio bytes
   -> server.py: State THINKING -> SPEAKING
   -> WebSocket push: { mood: "neutral", state: "SPEAKING", speaking: true }

6. Playback
   -> Audio: play through speaker
   -> server.py: stream amplitude via WebSocket
   -> Display: mouth animation synced to amplitude

7. Complete
   -> server.py: State SPEAKING -> IDLE
   -> WebSocket push: { mood: "neutral", state: "IDLE", speaking: false }
```

## Button Interaction State Diagram

```
                 ┌─────── FACE VIEW ───────┐    ┌──── CHAT VIEW ────┐
                 │                         │    │                    │
                 │  IDLE                   │    │  IDLE              │
                 │    │                    │    │    │               │
                 │    ├─ tap ──► cycle     │    │    ├─ tap ► cycle  │
                 │    │         view       │    │    │       view    │
                 │    │                    │    │    │               │
                 │    └─ hold >400ms       │    │    └─ hold >1s    │
                 │         │               │    │         │          │
                 │         ▼               │    │         ▼          │
                 │    LISTENING             │    │    MENU opened    │
                 │    (recording)           │    │    │     │        │
                 │         │               │    │    │ tap: next     │
                 │    ┌────┤               │    │    │ hold: select  │
                 │    │    │               │    │    │ idle: close   │
                 │    │  release           │    │    │               │
                 │    │    │               │    │    └─ hold >5s    │
                 │  tap    ▼               │    │         │          │
                 │  (cancel) THINKING      │    │    SLEEPING        │
                 │    │    │               │    │                    │
                 │    │    ├─ tap ► IDLE   │    │    └─ hold >10s   │
                 │    │    │  (cancel)     │    │         │          │
                 │    │    │               │    │    SHUTDOWN        │
                 │    ▼    ▼               │    │    (3s confirm)    │
                 │    IDLE  SPEAKING       │    │                    │
                 │         │               │    └────────────────────┘
                 │         ├─ tap ► IDLE   │
                 │         │  (cancel)     │
                 │         │               │
                 │         └─ done ► IDLE  │
                 │                         │
                 └─────────────────────────┘
```

### Hold Indicator Zones

```
 Time:  0s      0.4s        1s              5s              10s
        │────────│───────────│───────────────│───────────────│
        │        │           │               │               │
 Face:  │ wait   │ RECORDING │               │               │
        │        │ (until    │               │               │
        │        │  release) │               │               │
        │        │           │               │               │
 Chat:  │ wait   │           │ MENU          │ SLEEP         │ SHUTDOWN
        │        │           │ (fires at     │ (fires at     │ (fires at
        │        │           │  threshold)   │  threshold)   │  threshold)
        │        │           │               │               │
 Ring:  │ dot    │ cyan fill │ bright cyan   │ orange ► red  │ full red
 Label: │ (none) │ "Talk"    │ "Menu"        │ "Sleep"       │ "Shutdown"
```

## Display Rendering Pipeline

```
  DisplayState (mood, style, view, battery, ...)
  + shared/*.yaml (expressions, styles, moods)
  + Animation state (blink, gaze, breathing, dt)
           │
           ▼
  ┌─ PILRenderer.render() ─────────────────────────┐
  │                                                 │
  │  Which view?                                    │
  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐  │
  │  │   Face   │  │ Chat Drawer  │  │Chat Full │  │
  │  └────┬─────┘  └──────┬───────┘  └────┬─────┘  │
  │       │               │               │         │
  │       ▼               ▼               ▼         │
  │  Character.draw()  Face (small)   draw_chat()   │
  │       │            + chat list    (transcript)   │
  │       │               │               │         │
  │       ▼               │               │         │
  │  ┌─ Face layers ──┐   │               │         │
  │  │ Eyes (pills,   │   │               │         │
  │  │   perspective, │   │               │         │
  │  │   blink, gaze) │   │               │         │
  │  │ Mouth (smile,  │   │               │         │
  │  │   openness)    │   │               │         │
  │  │ Body (scale,   │   │               │         │
  │  │   tilt, bounce)│   │               │         │
  │  └────────────────┘   │               │         │
  │       │               │               │         │
  │       ▼               ▼               ▼         │
  │  ┌─ Overlay layers (composited in order) ────┐  │
  │  │ Mood decorations (sparkles, tears, ZZZs)  │  │
  │  │ Status decorations (WiFi arcs, battery)   │  │
  │  │ Emoji reactions (floating emoji)          │  │
  │  │ Greeting overlay                          │  │
  │  │ Peek bubble (chat preview on face view)   │  │
  │  └───────────────────────────────────────────┘  │
  │       │                                         │
  │       ▼                                         │
  │  Status bar (battery %, WiFi, agent name)       │
  │       │                                         │
  │       ▼                                         │
  │  Button indicator / speaking pill               │
  │       │                                         │
  │       ▼                                         │
  │  Menu overlay (if MENU state)                   │
  │       │                                         │
  │       ▼                                         │
  │  Shutdown overlay (if shutting down)             │
  │       │                                         │
  │       ▼                                         │
  │  Corner mask (rounded rect, ~40px radius)       │
  │                                                 │
  └──────────────────┬──────────────────────────────┘
                     │
                     ▼
           ┌─── Backend ───┐
           │               │
     ┌─────┴─────┐  ┌─────┴──────┐
     │  Pi: SPI  │  │  Desktop:  │
     │  RGB565   │  │  tkinter   │
     │  134KB/   │  │  window    │
     │  frame    │  │  (or       │
     │  ~20 FPS  │  │  pygame)   │
     └───────────┘  └────────────┘
```

## Pi Deployment

On the Raspberry Pi, three systemd services run in boot order:

| # | Service | Unit File | What it runs |
|---|---------|-----------|-------------|
| 1 | Guardian | `voxel-guardian.service` | `python -m display.guardian` -- boot splash, WiFi AP mode, crash recovery watchdog |
| 2 | Backend | `voxel.service` | `uv run server.py` -- WebSocket :8080, state machine, AI pipelines, battery |
| 3 | Display | `voxel-display.service` | `uv run display/service.py --url ws://localhost:8080` -- PIL renderer, SPI LCD, buttons, config :8081 |

The guardian hands off display ownership to the display service via a lock file at `/tmp/voxel-display.lock`. If the display service crashes, the guardian reclaims the display and shows an error screen.

Hardware drivers: WhisPlay HAT (SPI display, audio codec, button, RGB LED), PiSugar (battery) when attached.

> **Legacy:** `voxel-ui.service` (WPE/Cog) and `voxel-web.service` (HTTP server for remote browser) are archived in `_legacy/`.

## Performance Budget

| Resource | Budget |
|----------|--------|
| RAM (total) | < 200MB (of 512MB) |
| CPU (idle) | < 15% |
| CPU (animating) | < 40% |
| WebSocket latency | < 50ms |
| Audio latency | < 200ms |

## Setup & Onboarding

First-boot flow on Pi:
1. `setup.sh` bootstraps: clones repo, installs uv, runs `voxel setup` (includes `voxel hw`)
2. User reboots (required for Whisplay kernel modules)
3. `voxel-guardian.service` starts first -- boot splash, WiFi check
4. If no WiFi: guardian starts AP mode ("Voxel-Setup") with config portal on LCD
5. `voxel.service` and `voxel-display.service` start after guardian
6. If no gateway token: shows "scan to configure" QR screen
7. After config: normal face mode

Setup state tracked in `config/.setup-state` (YAML checkpoints).

Three production services: `voxel-guardian.service` (watchdog) + `voxel.service` (backend) + `voxel-display.service` (display).

## Dev Panel

On desktop, `uv run dev` opens a dev panel control window (`display/dev_panel.py`) alongside the preview window. The panel provides GUI controls for changing moods, states, styles, and triggering test actions without keyboard shortcuts. Pass `--no-panel` to disable it.

Keyboard shortcuts are also available in the preview window itself: number keys `1`-`9`/`0` for moods, `m` for menu, `c` for cycling views, `t` for transcript, `p` for demo mode, `n` for noise spike simulation, and spacebar for hardware button simulation.

## Logging

All logging goes through `core/log.py`, which provides colored console output (stderr) and optional file output.

**Configuration:**
- `--verbose` / `-v` CLI flag sets DEBUG level
- `VOXEL_LOG_LEVEL` env var: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`
- `VOXEL_LOG_FILE` env var: path to an additional log file (always captures DEBUG, appended)

**Log levels:**
- `DEBUG` — per-frame details, animation parameters, protocol messages
- `INFO` — state transitions, mood changes, service lifecycle, config
- `WARNING` — fallbacks, degraded functionality, missing optional config
- `ERROR` — failures affecting user experience
- `CRITICAL` — service cannot start

All loggers use the `voxel.*` namespace (e.g., `voxel.display`, `voxel.core`). Module prefixes are shortened in output for readability.

## Testing

Test suite in `tests/` using pytest (config in `pyproject.toml`). Run with `uv run pytest`.

| Test file | Coverage |
|-----------|----------|
| `test_mood_pipeline.py` | Mood transitions, battery reactions, manual lockout (5s), connection changes, demo mode blocking |
| `test_state_lifecycle.py` | DisplayState defaults, transcript management, blink/gaze/breathing animation state, idle prompts |
| `test_characters.py` | All characters x all moods render without error, tilt cuts, accent color correctness |

Tests have a 10-second timeout. No hardware or network access required.

## File Conventions

- All hardware access through `hw/` abstraction — never import RPi.GPIO directly
- Config values from YAML — no magic numbers in code
- Shared data in `shared/*.yaml` — never duplicate expression/style/mood definitions
- Type hints on all public Python functions
- Logging via `logging.getLogger("voxel.{module}")`
- State changes always go through `StateMachine.transition()`
