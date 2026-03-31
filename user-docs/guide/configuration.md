# Configuration

Voxel uses a layered YAML configuration system with environment variable overrides.

## Interactive Wizard

The easiest way to configure Voxel is with the interactive wizard:

```bash
voxel configure
```

This walks through gateway connection, voice/TTS providers, display/character settings, MCP server, webhooks, and power management. Each section is optional -- press Enter to accept defaults or skip. All changes are saved to `config/local.yaml`.

The wizard runs automatically at the end of `voxel setup`. To re-run it later or change settings, use `voxel configure` directly.

## Config Files

| File | Purpose | Tracked in git |
|------|---------|----------------|
| `config/default.yaml` | Default values for all settings | Yes |
| `config/local.yaml` | Your overrides (API keys, preferences) | No (gitignored) |

Settings in `local.yaml` override `default.yaml`. You only need to add the keys you want to change.

### Example `local.yaml`

```yaml
gateway:
  token: "your-openclaw-token"

stt:
  whisper:
    api_key: "your-openai-api-key"

tts:
  elevenlabs:
    api_key: "your-elevenlabs-api-key"

audio:
  tts_provider: elevenlabs  # upgrade from free edge-tts
  volume: 90

character:
  default: cube
```

## Environment Variables

API keys can also be set via environment variables. These take priority over YAML values:

| Variable | Purpose |
|----------|---------|
| `OPENCLAW_TOKEN` | OpenClaw gateway authentication |
| `OPENAI_API_KEY` | Whisper speech-to-text |
| `ELEVENLABS_API_KEY` | ElevenLabs text-to-speech |

## Web Config UI

The display service runs a web configuration server on **port 8081**. On boot, the device LCD shows a QR code you can scan to open the config page in a browser.

### Access

1. Scan the QR code on the device screen, or navigate to `http://<device-ip>:8081`
2. Enter the 6-digit PIN displayed on the LCD
3. Change settings through the web interface

::: tip
Auth can be disabled for development by setting `web.auth_enabled: false` in `local.yaml`.
:::

## CLI Config Commands

View and modify settings from the command line:

```bash
# Show all config
voxel config

# Get a specific value
voxel config get gateway.url
voxel config get audio.volume

# Set a value
voxel config set gateway.token "your-token"
voxel config set audio.tts_provider elevenlabs
voxel config set display.brightness 90
```

Changes made via `voxel config set` are written to `config/local.yaml`.

## Settings Reference

### Gateway

```yaml
gateway:
  url: "http://GATEWAY_HOST:18789"   # OpenClaw gateway URL
  token: ""                           # Auth token
  default_agent: "daemon"             # Agent to use on startup
```

### Agents

Six AI agents are available, each with a distinct personality and assigned voice:

| Agent | Role | Default Voice |
|-------|------|---------------|
| Daemon | Lead coordinator | charlie |
| Soren | Senior architect | adam |
| Ash | Builder/executor | josh |
| Mira | Business operator | rachel |
| Jace | Flex agent | sam |
| Pip | Intern | charlie |

Switch agents at runtime via the menu, web config, or WebSocket command.

### Audio

```yaml
audio:
  stt_provider: whisper    # whisper (cloud) or local
  tts_provider: edge       # edge (free), openai, elevenlabs
  wake_word: null           # null = push-to-talk only
  volume: 80                # 0-100
  device: default           # default, wm8960, usb, or ALSA device string
```

### Speech-to-Text

```yaml
stt:
  whisper:
    model: whisper-1
    language: en
    api_key: ""  # or set OPENAI_API_KEY env var
```

### Text-to-Speech

```yaml
tts:
  openai:
    model: tts-1               # tts-1 (fast), tts-1-hd (quality), gpt-4o-mini-tts (newest)
    voice: nova                # alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer
    api_key: ""                # falls back to stt.whisper.api_key / OPENAI_API_KEY
  elevenlabs:
    api_key: ""                        # or set ELEVENLABS_API_KEY env var
    model: eleven_turbo_v2_5
  edge:
    voice: en-US-ChristopherNeural     # free fallback, no API key needed
```

::: info
`edge-tts` is the default TTS provider and requires no API key. It uses Microsoft Edge's online TTS service. Quality is good but OpenAI TTS and ElevenLabs sound more natural. OpenAI TTS shares the same API key as Whisper STT, so if you already have an OpenAI key configured for STT, just set `audio.tts_provider: openai` to use it. All providers fall back to `edge-tts` on failure.
:::

### Display

```yaml
display:
  mode: auto          # auto or whisplay (PIL->SPI on Pi, tkinter on desktop)
  width: 240
  height: 280
  fps: 30
  brightness: 80      # 0-100
  orientation: 0      # 0, 90, 180, 270
  remote_port: 8081
```

### Character

```yaml
character:
  default: voxel                # voxel (default), cube, or bmo
  idle_blink_interval: 3.5      # seconds between random blinks
  gaze_drift_speed: 0.5         # eye wander speed when idle
  mouth_sensitivity: 0.6        # audio amplitude to mouth mapping
  breathing_speed: 0.3          # idle bounce speed
  system_context_enabled: true  # send system prompt to AI
  boot_animation: true          # play wake-up eye animation on startup (~3s)
  greeting_enabled: true        # request a greeting from the gateway agent on startup
  greeting_prompt: "You just woke up. Give a very brief greeting..."
```

### Power Management

```yaml
power:
  sleep_after_idle: 300    # seconds until sleep mode (5 min)
  dim_after_idle: 60       # seconds until display dims (1 min)
  dim_brightness: 20       # brightness when dimmed (0-100)
```

### LED

```yaml
led:
  enabled: true
  brightness: 80          # 0-100 max brightness cap
  breathe_speed: 1.0      # animation speed multiplier
```

### Development

```yaml
dev:
  enabled: false           # show dev indicators, skip web auth
  advertise: true          # broadcast presence on LAN (UDP 41234)
  ssh:
    host: ""               # Pi SSH host (set by dev-pair or dev-push)
    user: pi
    password: ""
```
