# Voxel

> A pocket AI companion with personality.

Voxel is an animated AI companion that lives on a tiny screen in your pocket. A dark cube mascot with glowing cyan accents, expressive eyes, and a voice — connected to your AI agent team through [OpenClaw](https://github.com/openclaw/openclaw).

Press a button, talk, and Voxel responds — with animated expressions, voice, and the full intelligence of your cloud AI agents behind it.

**Voxel** is the character. The physical device is called the **Relay**.

![Concept Art](assets/character/concept-03-ui-mockup.png)

## Why

Most AI assistants are apps on a phone or text in a terminal. Voxel is something different — a dedicated physical companion with a face, emotions, and presence. It's always there, always listening (when you want it to), and always connected to your AI team.

Think Wall-E meets a modern AI assistant, running on $30 of hardware.

## What It Does

- 🎭 **Animated character** — expressive cube mascot with eyes, mouth, and body language. 9 mood states that react to conversation.
- 🎤 **Voice interaction** — push-to-talk or wake word ("Hey Voxel"). Whisper for speech-to-text, ElevenLabs for voice.
- 🤖 **Agent switching** — talk to any agent on your team (Daemon, Soren, Ash, Mira, Jace, Pip) by selecting from the menu.
- 💬 **Mouth sync** — mouth animation driven by audio amplitude in real-time.
- 😴 **Idle behaviors** — slow blinks, gaze drift, gentle breathing animation. Voxel feels alive even when idle.
- ⚙️ **Settings UI** — agent selection, voice config, brightness, battery status. Button-navigated menus.

## Hardware (The Relay)

| Component | Details |
|-----------|---------|
| **Brain** | Raspberry Pi Zero 2W |
| **Display** | 1.69" IPS LCD, 240×280px (PiSugar Whisplay HAT) |
| **Audio** | Dual MEMS microphones + mono speaker |
| **Input** | Mouse-style buttons (left/right click) |
| **Feedback** | RGB LED indicator |
| **Power** | PiSugar 3 battery (1200mAh portable) |

Total hardware cost: ~$50-60

## Current Status

🟢 **Foundation complete** — platform abstraction layer, expression system, state machine, OpenClaw gateway client, local desktop preview.

| Component | Status |
|-----------|--------|
| Platform abstraction (desktop/Pi) | ✅ Done |
| Display, buttons, LED, audio, battery | ✅ Abstracted |
| Expression system (9 moods) | ✅ Defined |
| State machine (7 states) | ✅ Built |
| OpenClaw gateway client | ✅ Built |
| Local dev preview (Pygame window) | ✅ Working |
| Character sprite sheets | 🔲 Next |
| Face renderer (sprite animation) | 🔲 Next |
| Mouth audio sync | 🔲 Next |
| STT pipeline (Whisper) | 🔲 Planned |
| TTS pipeline (ElevenLabs/edge) | 🔲 Planned |
| Settings/menu UI | 🔲 Planned |
| Wake word detection | 🔲 Planned |
| Pi deployment + testing | 🔲 Planned |

## Local Development

Develop and preview Voxel on your desktop — no Pi hardware needed. The same code runs on both. Uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

**Prerequisites:** Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Windows

```cmd
git clone https://github.com/Codename-11/voxel.git
cd voxel
run_dev_windows.bat
```

Or directly:
```cmd
uv run main.py
```

### macOS / Linux

```bash
git clone https://github.com/Codename-11/voxel.git
cd voxel
./run.sh
```

`uv run` auto-creates a `.venv`, installs the pinned Python version (3.13) and all dependencies on first run.

This opens a 240×280 pixel window — exact match of the Relay's LCD. Keyboard simulates hardware buttons:

| Key | Action |
|-----|--------|
| Space | Push-to-talk |
| Z | Left button |
| X | Right button |
| Escape | Menu / Quit |

## Architecture

```
voxel/
├── main.py              # Entry point + main loop (30fps)
├── core/                # AI integration
│   ├── gateway.py       # OpenClaw API client
│   ├── stt.py           # Speech-to-text (Whisper)
│   ├── tts.py           # Text-to-speech (ElevenLabs/edge)
│   └── audio.py         # Audio capture/playback
├── face/                # Character animation
│   ├── renderer.py      # Pygame sprite renderer
│   ├── character.py     # Cube mascot controller
│   ├── expressions.py   # 9 mood definitions (dataclass-based)
│   ├── mouth.py         # Audio-reactive mouth sync
│   └── sprites/         # Pre-rendered sprite sheets
├── ui/                  # Menu system
│   ├── menu.py          # Button-navigated settings
│   ├── statusbar.py     # Bottom bar (state, battery, connectivity)
│   ├── screens.py       # Screen definitions
│   └── transitions.py   # Transition animations
├── hardware/            # Platform abstraction
│   ├── platform.py      # Auto-detect Pi vs desktop
│   ├── display.py       # LCD / Pygame window
│   ├── buttons.py       # GPIO / keyboard mapping
│   ├── led.py           # RGB LED / visual indicator
│   └── battery.py       # PiSugar / mock battery
├── states/              # State machine
│   └── machine.py       # IDLE → LISTENING → THINKING → SPEAKING
├── config/
│   └── default.yaml     # All settings (agents, display, audio, character)
└── assets/              # Sprites, fonts, icons, concept art
```

## Expression States

| State | Eyes | Mouth | LED | Body |
|-------|------|-------|-----|------|
| Idle | Slow blinks, gaze drift | Gentle smile | Soft cyan pulse | Breathing bounce |
| Listening | Wide, focused | Slightly open | Solid blue | Lean forward |
| Thinking | Look up/away | Neutral | Spinning amber | Processing dot |
| Speaking | Normal blinks | Audio-synced | Green | Subtle bob |
| Error | X_X | Flat line | Red flash | Shake |
| Sleeping | Closed | Closed | Off | Slow breath |
| Happy | Squint-smile | Wide grin | Warm pulse | Bouncy |

## Tech Stack

- **Python 3.11–3.13** with type hints (managed by [uv](https://docs.astral.sh/uv/))
- **Pygame** for rendering (sprite sheets, not real-time 3D)
- **OpenClaw** gateway API for AI agent communication
- **Whisper** (OpenAI) for speech-to-text
- **ElevenLabs / edge-tts** for text-to-speech
- **YAML** for configuration

## Pi Setup

```bash
# On the Raspberry Pi Zero 2W:
git clone https://github.com/Codename-11/voxel.git
cd voxel
./scripts/setup.sh    # Installs uv, system deps, and Python packages (including Pi extras)

# Configure
cp config/default.yaml config/local.yaml
# Edit config/local.yaml with your OpenClaw gateway URL and API keys

# Run
uv run main.py

# Auto-start on boot
sudo cp voxel.service /etc/systemd/system/
sudo systemctl enable --now voxel
```

## OpenClaw Integration

Voxel connects to an [OpenClaw](https://openclaw.ai) gateway to access your AI agent team. Each agent gets its own session (`agent:{id}:companion`) — separate from Discord, ClawPort, or any other surface.

Switch agents from the settings menu. Default: Daemon.

## License

MIT

---

*Built by [Axiom-Labs](https://axiom-labs.dev)*
