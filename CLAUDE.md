# Voxel — Development Guide

## What is this?
Voxel is the character. The physical hardware is called the **Relay**.
Voxel is a pocket-sized AI companion device built on Raspberry Pi Zero 2W + PiSugar Whisplay HAT. It features an animated cube mascot character with expressive eyes/mouth, voice interaction, and connects to the Axiom-Labs AI agent team via OpenClaw.

- **Hardware:** Pi Zero 2W + PiSugar Whisplay HAT (240x280 IPS LCD, dual mics, speaker, buttons, RGB LED)
- **Repo:** ~/voxel (local, not yet on GitHub)
- **OpenClaw Gateway:** http://172.16.24.250:18789

## Project Structure

```
voxel/
├── main.py                      # Application entry point
├── core/                        # OpenClaw gateway client, STT/TTS pipelines
│   ├── gateway.py               # OpenClaw API integration (chat completions)
│   ├── stt.py                   # Speech-to-text (Whisper API)
│   ├── tts.py                   # Text-to-speech (ElevenLabs/edge-tts)
│   └── audio.py                 # Audio capture/playback via Whisplay HAT
├── face/                        # Animated companion face engine
│   ├── renderer.py              # Pygame framebuffer renderer for SPI LCD
│   ├── character.py             # Cube mascot sprite controller
│   ├── expressions.py           # Mood/expression definitions (9 moods)
│   ├── mouth.py                 # Audio-reactive mouth animation (RMS amplitude)
│   └── sprites/                 # Sprite sheets per state/expression
├── ui/                          # Menu system and overlays
│   ├── menu.py                  # Settings/navigation menu (button-driven)
│   ├── statusbar.py             # Bottom status bar (state, transcript, battery)
│   ├── screens.py               # Screen definitions (home, settings, agent select)
│   └── transitions.py           # Screen transition animations
├── hardware/                    # Whisplay HAT drivers and hardware abstraction
│   ├── display.py               # SPI LCD driver (ST7789, 240x280)
│   ├── buttons.py               # Button input handler (mouse buttons on HAT)
│   ├── led.py                   # RGB LED control
│   └── battery.py               # PiSugar battery monitor
├── states/                      # Application state machine
│   ├── machine.py               # State machine core (7 states)
│   ├── idle.py                  # Idle state (ambient animations)
│   ├── listening.py             # Listening state (recording audio)
│   ├── thinking.py              # Thinking state (waiting for AI response)
│   ├── speaking.py              # Speaking state (TTS + mouth sync)
│   └── error.py                 # Error state (X_X face)
├── config/                      # Configuration
│   ├── settings.py              # Runtime settings manager
│   └── default.yaml             # Default configuration (agents, display, audio, etc.)
├── assets/                      # Design assets
│   ├── character/               # Character concept art and sprite sources
│   ├── icons/                   # UI icons
│   └── fonts/                   # Display fonts
├── scripts/                     # Setup and utility scripts
│   └── setup.sh                 # First-time setup (drivers, deps, config)
├── requirements.txt             # Python dependencies
└── voxel.service      # Systemd unit file for auto-start
```

## Hardware Constraints

**CRITICAL — Design everything for these limits:**
- **Display:** 240x280 pixels, SPI interface (ST7789 controller), 30fps target
- **CPU:** ARM Cortex-A53 (quad-core 1GHz) — no real-time 3D, use sprite sheets
- **RAM:** 512MB — keep memory footprint minimal
- **Audio:** WM8960 codec, dual MEMS mics, mono speaker
- **Input:** Mouse-style buttons (left/right click), no touch screen
- **Power:** PiSugar 3 battery (1200mAh), sleep modes important

**Rendering approach:** Pre-rendered sprite sheets, NOT real-time 3D. Pygame on framebuffer. Design sprites in external tools, export as PNG sequences.

## Character Design

The mascot is a **dark charcoal rounded cube** with **glowing cyan/teal accent lines** on edges. Semi-transparent glass quality. Isometric 2.5D flat style.

**Face:** Large expressive oval eyes with glossy highlights, small mouth. The face fills most of the 240x280 screen.

**States and expressions:**
| State | Eyes | Mouth | LED | Body |
|-------|------|-------|-----|------|
| Idle | Slow blinks, gaze drift | Gentle smile | Soft pulse | Breathing bounce |
| Listening | Wide, focused | Slightly open | Solid blue | Lean forward |
| Thinking | Look up/away, squint | Neutral | Spinning amber | Processing dot |
| Speaking | Normal, blinks | Audio-synced | Green | Subtle bob |
| Error | X_X | Flat line | Red flash | Shake |
| Sleeping | Closed, zzz | Closed | Off | Slow breath |
| Happy | Squint-smile | Wide smile | Warm pulse | Bouncy |

## Expression System

`face/expressions.py` defines 9 moods as dataclasses:
- Each mood has `EyeConfig` (openness, pupil size, gaze, blink rate, squint)
- `MouthConfig` (openness, smile amount, width)
- `BodyConfig` (bounce speed/amount, tilt, scale)

Transitions between moods should be smooth (lerp over ~300ms).

## State Machine

`states/machine.py` — 7 states: IDLE, LISTENING, THINKING, SPEAKING, ERROR, SLEEPING, MENU

Flow: IDLE → (button press) → LISTENING → (release) → THINKING → (response) → SPEAKING → IDLE
Any state → (button) → MENU → (button) → previous state
Long idle → SLEEPING → (button) → IDLE

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
  → mouth animation synced to audio amplitude (RMS)
```

## UI Architecture

**Default view:** Character face fills screen, small status bar at bottom.
**Menu:** Button-navigated (left/right buttons on Whisplay HAT). Settings: agent select, voice, WiFi, brightness, battery, about.
**Status bar:** State text ("Listening...", "Connected to Daemon"), battery icon, connectivity dot.

## Key Libraries
- **pygame** — framebuffer rendering, sprite animation
- **Pillow** — image manipulation
- **openai** — Whisper STT
- **requests** — OpenClaw gateway API
- **numpy** — audio amplitude analysis (RMS for mouth sync)
- **edge-tts** — free fallback TTS
- **spidev** — SPI display driver
- **RPi.GPIO** — buttons and LED

## Configuration

`config/default.yaml` defines all settings. User overrides in `config/local.yaml` (gitignored). Key sections: gateway (URL/token/default agent), agents (6 defined with voice assignments), display, audio, character animation params, power management.

## Development Workflow

### On the Pi:
```bash
cd ~/voxel
source .venv/bin/activate
python main.py
```

### Testing without hardware (desktop):
Pygame can render to a window instead of framebuffer. Use `SDL_VIDEODRIVER=x11` or mock the hardware modules.

### Deploy:
```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart voxel
```

## Conventions
- Python 3.11+, type hints everywhere
- Dataclasses for configuration/state objects
- Logging via stdlib `logging` module
- Config loaded from YAML, not hardcoded
- All hardware access behind abstraction layer (hardware/ modules)
- Sprite sheets as PNG sequences in face/sprites/
- State changes logged: "State: IDLE → LISTENING"
- Button input debounced in hardware/buttons.py
