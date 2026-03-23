# Architecture

## Overview

Voxel is a real-time interactive application running on a Raspberry Pi Zero 2W. It combines sprite-based animation, voice I/O, and cloud AI into a cohesive companion experience.

```
┌─────────────────────────────────────────┐
│              Main Loop (30fps)           │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │  States   │  │   Face   │  │  UI   │ │
│  │ Machine   │──│ Renderer │──│ Layer │ │
│  └────┬─────┘  └────┬─────┘  └───┬───┘ │
│       │              │            │      │
│  ┌────┴─────┐  ┌────┴─────┐  ┌──┴────┐ │
│  │  Core    │  │ Hardware │  │Config │  │
│  │ (AI/STT/ │  │ (Display/│  │(YAML) │  │
│  │  TTS)    │  │ Buttons/ │  │       │  │
│  │          │  │ LED/Bat) │  │       │  │
│  └────┬─────┘  └────┬─────┘  └───────┘ │
│       │              │                   │
└───────┼──────────────┼───────────────────┘
        │              │
   ┌────┴────┐    ┌────┴─────┐
   │ OpenClaw│    │ Whisplay │
   │ Gateway │    │   HAT    │
   │ (cloud) │    │(hardware)│
   └─────────┘    └──────────┘
```

## Layers

### 1. Hardware Abstraction (`hardware/`)

Platform-detected at startup. Same interface on desktop and Pi.

| Module | Desktop | Pi |
|--------|---------|-----|
| `platform.py` | Sets `IS_PI=False` | Sets `IS_PI=True` |
| `display.py` | Pygame window 240×280 | Pygame framebuffer → SPI LCD |
| `buttons.py` | Z/X/Space/Esc keyboard | GPIO active-low polling |
| `led.py` | Drawn circle indicator | GPIO PWM RGB LED |
| `battery.py` | Returns 100% always | PiSugar HTTP API |

### 2. Core (`core/`)

AI and audio pipelines. All cloud calls are async-safe with timeouts.

| Module | Purpose |
|--------|---------|
| `gateway.py` | OpenClaw chat completions (non-streaming). Session: `agent:{id}:companion` |
| `stt.py` | Whisper API. Records WAV → uploads → returns transcript |
| `tts.py` | ElevenLabs (primary) / edge-tts (fallback). Text → audio bytes |
| `audio.py` | PyAudio capture/playback. `get_amplitude()` for mouth sync |

### 3. Face (`face/`)

Sprite-based character rendering.

| Module | Purpose |
|--------|---------|
| `expressions.py` | 9 mood dataclasses (eye config, mouth config, body config) |
| `character.py` | Loads sprite sheets, selects frames, handles transitions |
| `renderer.py` | Composites character + overlays onto display surface |
| `mouth.py` | Maps audio amplitude (0.0-1.0) to mouth frame index |

**Rendering approach:** Pre-rendered sprite sheets (PNG sequences), not real-time 3D. The Pi Zero 2W cannot do live 3D rendering at acceptable framerates on an SPI display.

**Mood transitions:** Lerp between expression configs over ~300ms for smooth state changes.

### 4. States (`states/`)

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

### 5. UI (`ui/`)

Overlay system on top of the face renderer.

- **Status bar:** Always visible at bottom. State text, agent name, battery, connectivity.
- **Menu screens:** Full-screen replacement of face view. Button-navigated.
- **Transitions:** Slide/fade between face view and menu screens.

### 6. Config (`config/`)

YAML-based. `default.yaml` ships with the repo, `local.yaml` (gitignored) for user overrides.

Key sections: gateway connection, agent definitions (6 agents with voice assignments), display settings, audio settings, character animation parameters, power management timers.

## Data Flow: Voice Interaction

```
1. User presses button
   → State: IDLE → LISTENING
   → Eyes: wide, focused
   → LED: solid blue
   → Audio: start recording

2. User releases button
   → State: LISTENING → THINKING
   → Eyes: look up/away
   → LED: spinning amber
   → Audio: stop recording → WAV bytes

3. STT (Whisper API)
   → WAV bytes → HTTP POST → transcript text

4. Gateway (OpenClaw)
   → transcript → POST /v1/chat/completions → response text

5. TTS (ElevenLabs)
   → response text → HTTP POST → audio bytes
   → State: THINKING → SPEAKING

6. Playback
   → Audio: play through speaker
   → Mouth: amplitude → frame mapping (real-time)
   → Eyes: normal, occasional blink
   → LED: green

7. Complete
   → State: SPEAKING → IDLE
   → Eyes: gentle smile
   → LED: soft pulse
```

## Performance Budget

| Resource | Budget |
|----------|--------|
| RAM | < 100MB (of 512MB total) |
| CPU (idle) | < 10% |
| CPU (rendering) | < 30% |
| Display FPS | 30fps |
| Sprite sheet total size | < 20MB |
| Audio latency | < 200ms |

## File Conventions

- All hardware access through `hardware/` abstraction — never import RPi.GPIO directly
- Config values from YAML — no magic numbers in code
- Type hints on all public functions
- Logging via `logging.getLogger("voxel.{module}")`
- State changes always go through `StateMachine.transition()`
