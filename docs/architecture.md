# Architecture

## Overview

Voxel uses a **React + WebSocket + Python** architecture. The React app (`app/`) renders the animated companion face. The Python backend (`server.py`) manages state, hardware, and AI pipelines. They communicate over WebSocket.

On the Pi, WPE/Cog (embedded WebKit) renders the React app fullscreen on the LCD. On desktop, Vite's dev server runs in a browser window.

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

## Layers

### 1. React Frontend (`app/`)

The production face renderer. Built with React 19, Framer Motion 12, Tailwind CSS 4, Vite 8.

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
| Hardware polling | 20Hz loop — buttons, battery, LED (on Pi only) |
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
| `gateway.py` | OpenClaw chat completions (non-streaming). Session: `agent:{id}:companion` |
| `stt.py` | Whisper API. Records WAV → uploads → returns transcript |
| `tts.py` | ElevenLabs (primary) / edge-tts (fallback). Text → audio bytes |
| `audio.py` | Audio capture/playback. `get_amplitude()` for mouth sync |

### 5. Face — Renderer Abstraction (`face/`)

| Module | Purpose |
|--------|---------|
| `base.py` | `BaseRenderer` abstract class — defines mood/style/audio/frame interface |
| `renderer.py` | `FaceRenderer` — pygame implementation of BaseRenderer (fallback only) |
| `character.py` | `VoxelCharacter` — pygame sprite-based cube with all animation logic |
| `expressions.py` | Python mood dataclasses (mirrors `shared/expressions.yaml`) |
| `styles.py` | Python style definitions (mirrors `shared/styles.yaml`) |
| `mouth.py` | Audio amplitude → mouth frame mapping |

**React is the primary renderer.** Pygame exists as a fallback for headless/legacy use. The `BaseRenderer` interface ensures any backend can be swapped in.

### 6. Hardware Abstraction (`hardware/`)

Platform-detected at startup. Same interface on desktop and Pi.

| Module | Desktop | Pi |
|--------|---------|-----|
| `platform.py` | Sets `IS_PI=False` | Sets `IS_PI=True` |
| `buttons.py` | Keyboard mapping (Z/X/Space/Esc) | GPIO active-low polling |
| `led.py` | Visual indicator (logged) | GPIO PWM RGB LED |
| `battery.py` | Returns 100% always | PiSugar HTTP API |

On the Pi, `server.py` polls hardware at 20Hz and broadcasts state changes to the React frontend via WebSocket.

### 7. States (`states/`)

Finite state machine driving application behavior.

```
         ┌─────────┐
         │  IDLE   │◄──────────────────┐
         └────┬────┘                   │
              │ button press           │ response done
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
Any state ──── menu button ──► MENU ──► previous state
```

State transitions trigger mood changes (via `shared/moods.yaml` state_map) and WebSocket broadcasts to the frontend.

## WebSocket Protocol

**Server → Client:**
```json
{ "type": "state", "mood": "thinking", "style": "kawaii", "speaking": false,
  "amplitude": 0.0, "battery": 100, "state": "THINKING", "agent": "daemon", "connected": false }
```

**Client → Server:**
```json
{ "type": "set_mood", "mood": "happy" }
{ "type": "set_style", "style": "retro" }
{ "type": "cycle_state" }
{ "type": "button", "button": "press|release|menu" }
{ "type": "ping" }
```

## Data Flow: Voice Interaction

```
1. User presses button (hardware GPIO or WebSocket "button" event)
   → server.py: State IDLE → LISTENING
   → WebSocket push: { mood: "listening", state: "LISTENING" }
   → React: eyes widen, lean forward, sound wave icon

2. User releases button
   → server.py: State LISTENING → THINKING
   → Audio: stop recording → WAV bytes
   → WebSocket push: { mood: "thinking", state: "THINKING" }
   → React: asymmetric brow raise, gaze up, brain+cog icon

3. STT (Whisper API)
   → WAV bytes → HTTP POST → transcript text

4. Gateway (OpenClaw)
   → transcript → POST /v1/chat/completions → response text

5. TTS (ElevenLabs)
   → response text → HTTP POST → audio bytes
   → server.py: State THINKING → SPEAKING
   → WebSocket push: { mood: "neutral", state: "SPEAKING", speaking: true }

6. Playback
   → Audio: play through speaker
   → server.py: stream amplitude via WebSocket
   → React: mouth animation synced to amplitude

7. Complete
   → server.py: State SPEAKING → IDLE
   → WebSocket push: { mood: "neutral", state: "IDLE", speaking: false }
```

## Pi Deployment

On the Raspberry Pi, the stack is:

1. **WPE/Cog** — lightweight embedded WebKit browser, renders `app/dist/` fullscreen on the LCD
2. **server.py** — Python WebSocket backend as a systemd service
3. **Hardware drivers** — Whisplay HAT (display, audio, buttons, LED), PiSugar (battery)

WPE is GPU-accelerated on the Pi, so CSS/Framer Motion animations perform well even on the Zero 2W.

## Performance Budget

| Resource | Budget |
|----------|--------|
| RAM (total) | < 200MB (of 512MB) |
| CPU (idle) | < 15% |
| CPU (animating) | < 40% |
| WebSocket latency | < 50ms |
| Audio latency | < 200ms |

## File Conventions

- All hardware access through `hardware/` abstraction — never import RPi.GPIO directly
- Config values from YAML — no magic numbers in code
- Shared data in `shared/*.yaml` — never duplicate expression/style/mood definitions
- Type hints on all public Python functions
- Logging via `logging.getLogger("voxel.{module}")`
- State changes always go through `StateMachine.transition()`
