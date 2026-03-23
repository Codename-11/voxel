# Voxel

Pocket AI companion. Animated cube mascot on Raspberry Pi Zero 2W + PiSugar Whisplay HAT.

Animated cube mascot with personality, connected to your AI agent team via OpenClaw.

## Hardware (The Relay)

- **Raspberry Pi Zero 2W** — brain
- **PiSugar Whisplay HAT** — 1.69" IPS LCD (240x280), dual mics, speaker, buttons, RGB LED
- **PiSugar 3 Battery** — portable power (1200mAh)

## Features

- **Animated Companion** — custom cube mascot with expressive eyes, mouth animation synced to speech, idle behaviors, and mood states
- **Voice Interaction** — push-to-talk or wake word, Whisper STT, ElevenLabs/edge TTS
- **OpenClaw Integration** — talks directly to your AI agent team (Daemon, Soren, Ash, etc.)
- **Settings UI** — agent selection, voice config, WiFi, battery status, brightness
- **State Machine** — idle → listening → thinking → speaking → error, each with unique animations

## Architecture

```
voxel/
├── core/              # OpenClaw gateway client, STT/TTS pipelines
│   ├── gateway.py     # OpenClaw API integration
│   ├── stt.py         # Speech-to-text (Whisper API)
│   ├── tts.py         # Text-to-speech (ElevenLabs/edge)
│   └── audio.py       # Audio capture/playback via Whisplay
├── face/              # Animated companion face engine
│   ├── renderer.py    # Pygame framebuffer renderer
│   ├── character.py   # Cube mascot sprite controller
│   ├── expressions.py # Mood/expression state definitions
│   ├── mouth.py       # Audio-reactive mouth animation
│   └── sprites/       # Sprite sheets (idle, listen, think, speak, etc.)
├── ui/                # Menu system and overlays
│   ├── menu.py        # Settings/navigation menu
│   ├── statusbar.py   # Bottom status bar (state, transcript, battery)
│   ├── screens.py     # Screen definitions (home, settings, agent select)
│   └── transitions.py # Screen transition animations
├── hardware/          # Whisplay HAT drivers and hardware abstraction
│   ├── display.py     # SPI LCD driver (ST7789)
│   ├── buttons.py     # Button input handler
│   ├── led.py         # RGB LED control
│   └── battery.py     # PiSugar battery monitor
├── states/            # Application state machine
│   ├── machine.py     # State machine core
│   ├── idle.py        # Idle state (ambient animations)
│   ├── listening.py   # Listening state (recording audio)
│   ├── thinking.py    # Thinking state (waiting for AI)
│   ├── speaking.py    # Speaking state (TTS + mouth sync)
│   └── error.py       # Error state (X_X face)
├── config/            # Configuration
│   ├── settings.py    # Runtime settings manager
│   ├── default.yaml   # Default configuration
│   └── agents.yaml    # Agent definitions (name, voice, personality)
├── assets/            # Design assets
│   ├── character/     # Character design source files
│   ├── icons/         # UI icons
│   └── fonts/         # Display fonts
├── scripts/           # Setup and utility scripts
│   ├── setup.sh       # First-time setup (drivers, deps, config)
│   ├── install-drivers.sh  # Whisplay HAT audio/display drivers
│   └── service.sh     # Systemd service installer
├── main.py            # Application entry point
├── requirements.txt   # Python dependencies
└── voxel.service  # Systemd unit file
```

## Tech Stack

- **Python 3.11+** — primary language
- **Pygame** — framebuffer rendering for sprite animations
- **OpenClaw Gateway API** — AI agent communication
- **OpenAI Whisper** — speech-to-text
- **ElevenLabs / Edge TTS** — text-to-speech
- **PiSugar Whisplay drivers** — hardware abstraction
- **YAML** — configuration

## States

| State | Eyes | Mouth | LED | Animation |
|-------|------|-------|-----|-----------|
| Idle | Slow blinks, gaze drift | Neutral/smile | Soft pulse | Gentle breathing/bounce |
| Listening | Wide open, focused | Slightly open | Solid blue | Lean forward, attentive |
| Thinking | Look up/away, squint | Neutral | Spinning amber | Processing indicator |
| Speaking | Normal, occasional blink | Synced to audio | Green | Subtle head bob |
| Error | X_X | Flat line | Red flash | Shake/vibrate |
| Sleeping | Closed, zzz | Closed | Off | Slow breathing |

## Setup

```bash
# Clone and setup
git clone https://github.com/Codename-11/voxel.git
cd voxel
./scripts/setup.sh

# Configure
cp config/default.yaml config/local.yaml
# Edit config/local.yaml with your OpenClaw gateway URL and API keys

# Run
python main.py

# Install as service (auto-start on boot)
./scripts/service.sh install
```

## License

MIT
