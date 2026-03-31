# Hardware Guide

## Bill of Materials

| Component | Product | ~Price | Purpose |
|-----------|---------|--------|---------|
| Brain | Raspberry Pi Zero 2W | $15 | Compute |
| Display + Audio | PiSugar Whisplay HAT | $25 | LCD, mics, speaker, buttons, LED |
| Battery | PiSugar 3 1200mAh | $20 | Portable power |
| Storage | MicroSD card (16GB+) | $5 | OS + software |
| **Total** | | **~$65** | |

## PiSugar Whisplay HAT

The Whisplay HAT integrates everything onto a single board that matches the Pi Zero footprint:

- **Display:** 1.69" IPS LCD, 240×280 pixels, ST7789 controller, SPI at 100MHz
  - **Corner radius:** ~20px at top corners (`CornerHeight = 20` in the WhisPlay driver), ~40px effective with bezel — content in corners gets clipped
  - **Safe area:** Inset text/icons ≥20px from edges at top/bottom rows (see `display/layout.py`)
  - **Backlight:** Software PWM via Python thread — **must use 100% to avoid visible flicker**. Dimming below 100% causes brightness pulsing from scheduler jitter. Future: use ST7789 panel-level brightness commands (0x51/0x53) or hardware PWM via `pigpio`.
  - **Y offset:** The ST7789 panel has a 20px vertical offset in the driver's `set_window()` — accounted for in the WhisPlay driver, transparent to our code.
  - **No TE/VSYNC pin** — cannot sync SPI writes to panel refresh. Full-frame writes at 20 FPS are acceptable.
- **Audio:** WM8960 codec, dual MEMS microphones, mono speaker output
- **Input:** Single push button (BOARD pin 11, active-HIGH with external pull-down). See [Button Interaction Patterns](#button-interaction-patterns) below.
- **WiFi:** Single radio (CYW43436) — AP and client modes are mutually exclusive. On first boot with no known WiFi, the display service starts AP mode ("Voxel-Setup" hotspot) and serves a config portal at `http://10.42.0.1:8081`. Uses `nmcli` (NetworkManager) for all WiFi operations — no extra packages needed.
- **LED:** RGB LED indicator (active-LOW, software PWM)
- **Connector:** 40-pin GPIO header (stacks on Pi Zero)
- **Supported platforms:** All Raspberry Pi with 40-pin header (Zero, Zero 2W, 3, 4, 5), Radxa ZERO 3W (RK3566), Radxa Cubie A7Z (Allwinner A733). Voxel targets Pi Zero 2W.

### Pin Mapping

Pin assignments from the [WhisPlay driver](https://github.com/PiSugar/Whisplay):

| Function | BOARD Pin | BCM GPIO | Notes |
|----------|-----------|----------|-------|
| LCD SPI MOSI | 19 | GPIO 10 | SPI0 |
| LCD SPI SCLK | 23 | GPIO 11 | SPI0 |
| LCD CS | 24 | GPIO 8 | SPI0 CE0 |
| LCD DC | 13 | GPIO 27 | Data/Command select |
| LCD RST | 7 | GPIO 4 | Reset (active-LOW) |
| LCD Backlight | 15 | GPIO 22 | Active-LOW; software PWM at 1000 Hz |
| Button | 11 | GPIO 17 | Active-HIGH, external pull-down on HAT |
| RGB LED Red | 22 | GPIO 25 | Common-anode, active-LOW (inverted PWM) |
| RGB LED Green | 18 | GPIO 24 | Common-anode, active-LOW (inverted PWM) |
| RGB LED Blue | 16 | GPIO 23 | Common-anode, active-LOW (inverted PWM) |
| I2S BCLK | 12 | GPIO 18 | WM8960 bit clock |
| I2S LRCLK | 35 | GPIO 19 | WM8960 left/right clock |
| I2S DIN | 38 | GPIO 20 | WM8960 data in (record) |
| I2S DOUT | 40 | GPIO 21 | WM8960 data out (playback) |
| I2C SDA | 3 | GPIO 2 | WM8960 control |
| I2C SCL | 5 | GPIO 3 | WM8960 control |

### Audio Codec Details (WM8960)

The WM8960 is a Wolfson/Cirrus Logic low-power stereo codec connected via I2S (data) and I2C (control).

- **ALSA sound card:** `wm8960soundcard` (device `hw:wm8960soundcard` or `hw:<card_number>,0`)
- **Recording:** 16-bit signed LE, 16 kHz, 2 channels (dual MEMS mics). Downmix to mono for STT.
  ```bash
  arecord -D hw:wm8960soundcard -f S16_LE -r 16000 -c 2 -d 5 test.wav
  ```
- **Playback:** Via ALSA or PyAudio to `hw:wm8960soundcard`
- **Volume controls (ALSA):**
  ```bash
  amixer sset Speaker 121          # Speaker output (max 127, ~80% at 121)
  amixer sset Playback 230         # Playback DAC level
  amixer sset Capture 45           # Capture ADC level
  # Mic boost (+20dB):
  amixer sset 'Left Input Boost Mixer LINPUT1' 2
  amixer sset 'Right Input Boost Mixer RINPUT1' 2
  ```
- **Speaker output:** Class D, up to 1W into 8 ohm load (mono)

### Button Interaction Patterns

The Whisplay HAT has a single push button (BOARD pin 11). All interaction is encoded through hold duration. There is no double-tap -- every gesture resolves from a single press.

#### From Face View (IDLE)

| Gesture | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| **Tap** | Toggle view (face / chat) | < 400ms, fires instantly on release | "Tap" pill (cyan) |
| **Hold** | Start recording (push-to-talk) | > 400ms (still held), stays in RECORDING until release | Pulsing ring + "Talk" label (green) |

Once recording starts at 400ms, the button stays in RECORDING state until release. There is **no menu/sleep/shutdown override** while recording -- the hold is exclusively for voice input.

**Recording guard:** Once recording starts (at 400ms), releases within the first 500ms of recording are ignored to prevent accidental cancellation from button bounce.

#### From Chat View

| Gesture | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| **Tap** | Toggle view (face / chat) | < 400ms, fires instantly on release | "Tap" pill (cyan) |
| **Hold** | Open menu | > 1s (fires AT threshold, not on release) | Ring fills to 1/10, "Menu" pill (bright cyan) |
| **Hold** | Enter sleep mode | > 5s (fires AT threshold) | Ring continues to 5/10, "Sleep" pill (indigo) |
| **Hold** | Shutdown with confirm | > 10s (fires AT threshold) | Orange/red ring fills full, "Shutdown" pill (red) |

#### Inside Menu

| Gesture | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| **Tap** | Move to next item | < 500ms | Highlight advances |
| **Hold** | Select / enter current item | > 500ms (fires AT threshold) | Brief fill animation |
| **Idle** | Auto-close menu, return to face | 5s with no input | Fade out |

**Menu structure:** Every menu and submenu has "Back" as the last item. Tap to reach it, hold to select = go back one level. For value adjustment items (volume, brightness), taps cycle through preset values (0, 25, 50, 75, 100) and hold confirms.

#### Hold Indicator

While the button is held (from non-face views), a four-zone progress ring appears at the bottom of the screen:
- **Zone 0 (0-0.4s):** Subtle pulsing dot -- no label (waiting to see if this is a tap)
- **Zone 1 (0.4-1s):** Cyan ring fills with pulsing center dot, "Talk" label (face view only: recording active)
- **Zone 2 (1-5s):** Brighter cyan continues, "Menu" label (menu opened at 1s threshold)
- **Zone 3 (5-10s):** Orange to red, "Sleep" then "Shutdown" labels
- Tick marks at 1s and 5s zone boundaries
- Center dot changes color at each zone boundary

**Key design:** Long-hold actions (menu, sleep, shutdown) fire the moment the threshold is crossed while the button is still held. They do not wait for release. This makes the interaction feel immediate and predictable. From the face view, the hold is reserved exclusively for recording.

**Shutdown confirmation:** When the 10s threshold is crossed, a full-screen countdown overlay appears (3... 2... 1...) with a pulsing "SHUTTING DOWN" warning. Any button press during the countdown cancels. After the countdown reaches 0, `sudo shutdown -h now` executes.

**Talk mode rules:** Push-to-talk activates when the button is held past 400ms, from the face view only (not menu or chat views). While LISTENING, a tap stops recording and sends audio to STT. While THINKING, a tap cancels the pipeline (STT/gateway) and returns to IDLE. While SPEAKING, a tap cancels playback and returns to IDLE.

**Desktop simulation:** The spacebar in the tkinter/pygame preview window feeds into the exact same button state machine as the Pi GPIO hardware.

### Driver Installation

```bash
# Whisplay HAT drivers (audio codec + display)
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay/Driver
sudo bash install_wm8960_drive.sh
```

This installs:
- WM8960 audio driver (ALSA device)
- Whisplay display/LED/button Python driver

Notes from current Pi Zero 2W validation:
- WM8960 audio detection works after install.
- The Whisplay Python display path works via PiSugar's `WhisPlayBoard` driver.
- `/dev/fb1` is not a reliable sole detection signal on all Pi images.

## PiSugar 3 Battery

- Capacity: 1200mAh
- Output: 5V via pogo pins to Pi Zero
- Charging: USB-C
- Monitoring: I2C or HTTP API at `localhost:8421`

### Battery API

```bash
# Check battery level
curl http://localhost:8421/api/battery

# Response:
# {"battery": 78, "charging": false}
```

## Assembly

1. Stack: PiSugar 3 battery → Pi Zero 2W → Whisplay HAT
2. The pogo pins align automatically
3. No soldering required
4. Total thickness: ~15mm

## Pi Zero 2W Setup

### 1. Flash OS

1. Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select **"Raspberry Pi OS Lite (64-bit)"** (Bookworm or later)
3. Click the gear icon and configure:
   - Hostname: `voxel`
   - Enable SSH (password or key)
   - WiFi SSID and password
   - Username: `pi`
4. Flash to microSD, insert into Pi, power on

### 2. Install & Setup (one command)

```bash
# SSH in
ssh pi@voxel.local

# Update system
sudo apt update && sudo apt upgrade -y

# Install everything (clones repo, installs deps, builds React app, configures services)
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

### 3. Web Config UI

The display service runs a web config server on port 8081 with a 6-digit PIN shown on the LCD. Open it from your laptop or phone:

```text
http://<pi-ip>:8081
```

This lets you configure settings, check connectivity, and manage the device remotely.

```bash
# Edit config (gateway URL, API keys)
voxel config                    # show current config
nano ~/voxel/config/local.yaml  # or edit directly

# Start and check
voxel start
voxel status
```

### 4. Whisplay Hardware Drivers

```bash
# Install Whisplay HAT drivers + tune config.txt (gpu_mem, swap, HDMI)
voxel hw

# Reboot to load drivers
sudo reboot
```

After reboot, verify:

```bash
arecord -l     # should show WM8960 device
aplay -l
voxel display-test
```

`voxel display-test` is the preferred sanity check because it talks to the Whisplay driver directly.

### 4b. LVGL Native Renderer PoC

We also have a native LVGL proof of concept that renders RGB565 frames and plays them back on the Whisplay panel using the same direct Python driver path.

Typical workflow:

```bash
# WSL / Linux workstation
uv run voxel lvgl-build
uv run voxel lvgl-render --frames-dir ./out/lvgl-frames
uv run voxel lvgl-sync --frames-dir ./out/lvgl-frames --host <pi-ip> --user pi

# Raspberry Pi
voxel lvgl-play --frames-dir ~/voxel/.cache/lvgl-poc-frames
```

One-command variant from the workstation:

```bash
uv run voxel lvgl-deploy --frames-dir ./out/lvgl-frames --host <pi-ip> --user pi
```

This path exists specifically to avoid recompiling on the Pi during visual iteration.

### 5. Configure & Start

```bash
# Edit config (gateway URL, API keys)
nano ~/voxel/config/local.yaml

# Check system health
voxel doctor

# Start Voxel
voxel start

# Watch logs
voxel logs

# Check status
voxel status
```

### Voxel CLI Commands

```bash
voxel setup       # Full first-time setup (deps, build, services)
voxel doctor      # Diagnose system health (tools, config, gateway, hardware)
voxel update      # Pull latest, rebuild, restart services
voxel build       # Just rebuild (Python deps + React app)
voxel hw          # Whisplay drivers + config.txt tuning
voxel display-test # Direct Whisplay display sanity test
voxel lvgl-build  # Build the LVGL PoC once
voxel lvgl-render # Render LVGL RGB565 frames without playback
voxel lvgl-sync   # Sync rendered LVGL frames to the Pi
voxel lvgl-play   # Replay pre-rendered LVGL frames on the Pi
voxel lvgl-deploy # Render, sync, and play in one command
voxel dev-pair    # Auto-discover device + pair via PIN
voxel start       # Start services
voxel stop        # Stop services
voxel restart     # Restart services
voxel logs        # Tail service logs
voxel status      # Service/system/hardware status
voxel config      # Show config
voxel config set gateway.token <value>  # Set a config value
voxel config get gateway.url            # Get a config value
voxel uninstall   # Remove services + caches
voxel version     # Show version
```

---

## Services on the Pi

The production deployment uses two systemd services:

| Service | Unit File | What it runs |
|---------|-----------|-------------|
| Backend | `voxel.service` | `uv run server.py` — WebSocket server, state machine, battery polling, AI pipelines |
| Display | `voxel-display.service` | `uv run display/service.py --url ws://localhost:8080` — PIL renderer → SPI LCD, button input, config server on port 8081. Depends on and starts after `voxel.service`. |

> **Archived services:** `voxel-ui.service` (WPE/Cog browser) and `voxel-web.service` (static HTTP server for remote browser UI) are no longer used. They were from an earlier architecture where the React app was the production renderer. The PIL display service replaced both.

## WPE/Cog — Future Optimization (Not Currently Used)

> **Current approach:** The display service (`display/service.py`) renders with
> Python PIL and pushes frames directly to the SPI LCD via the WhisPlay driver —
> the same proven approach used by PiSugar's reference chatbot. WPE/Cog is a
> future optimization that would allow the React app to render directly on the Pi
> LCD, eliminating the need for the PIL renderer. It requires a working
> framebuffer driver (fbtft or fbcp-ili9341) which has not been validated yet.

WPE WebKit is an embedded browser engine built for devices like the Pi. Cog is its minimal launcher — no window decorations, no address bar, just fullscreen content. If enabled, it would render the React + Framer Motion UI on the LCD.

<details>
<summary>WPE/Cog architecture and setup notes (expand for future reference)</summary>

### Architecture on the Pi

```
┌─────────────────────────────────────┐
│  Cog (WPE launcher)                │
│  └── loads app/dist/index.html     │
│      └── React app (Framer Motion) │
│          └── ws://localhost:8080   │
├─────────────────────────────────────┤
│  WPE WebKit (GPU-accelerated)      │
│  └── CSS transforms, animations    │
│      are hardware-accelerated via   │
│      the VideoCore IV GPU           │
├─────────────────────────────────────┤
│  DRM/KMS display backend           │
│  └── renders to the display output │
├─────────────────────────────────────┤
│  ST7789 SPI LCD (/dev/fb1)         │
│  240×280 pixels                     │
└─────────────────────────────────────┘
```

### Display Routing

The Whisplay HAT's LCD is an SPI display (ST7789 controller). How WPE gets pixels to it depends on the driver:

**Scenario A — DRM connector available (preferred):**
If the Whisplay driver registers as a DRM device, Cog's DRM platform plugin renders directly to it. This is the zero-overhead path.

Status notes from earlier testing:
- On the validated Pi Zero 2W + Whisplay hardware, direct driver rendering works.
- Direct `cog` DRM startup currently fails on the tested Pi OS image with DRM/session initialization errors.
- Weston can acquire DRM successfully when `seatd` is running, but `cog -P wl` still aborts on the tested package set because it cannot load `libWPEBackend-default.so`.
- That means hardware is healthy, but the browser backend path still needs work.
- LVGL frame generation and Whisplay playback both work, which makes the native renderer path the most credible route for matching the device UI today.

```bash
# Check if DRM device exists for the LCD
ls /dev/dri/card*
# If you see a card device, try:
COG_PLATFORM=drm cog file:///home/pi/voxel/app/dist/index.html
```

**Scenario B - Framebuffer only (fallback):**
If the driver only provides `/dev/fb1`, use `fbcp` to mirror the primary DRM output to the SPI framebuffer:

```bash
# Install fbcp
sudo apt install cmake
git clone https://github.com/nickeltin/fbcp-ili9341.git
cd fbcp-ili9341
mkdir build && cd build
cmake -DSPI_BUS_CLOCK_DIVISOR=6 -DST7789VW=ON -DGPIO_TFT_DATA_CONTROL=25 \
      -DGPIO_TFT_RESET_PIN=27 -DSTATISTICS=0 ..
make -j$(nproc)
sudo cp fbcp-ili9341 /usr/local/bin/

# Test — should mirror the DRM output to the LCD
fbcp-ili9341 &
COG_PLATFORM=drm cog file:///home/pi/voxel/app/dist/index.html
```

If using fbcp, add it as a systemd service that starts before the display service:

```bash
# /etc/systemd/system/fbcp.service
[Unit]
Description=Framebuffer copy (DRM → SPI LCD)
Before=voxel-display.service

[Service]
ExecStart=/usr/local/bin/fbcp-ili9341
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Scenario C - FreeDesktop backend (`fdo`) via Weston:**
If direct Cog DRM is not viable, run Cog against the FreeDesktop backend on top of a Wayland compositor such as Weston. This adds a compositor layer, but is often more tolerant than raw DRM startup.

In short:
- `cog` is the launcher.
- `drm` is the direct kernel graphics path.
- `wl` is Cog's Wayland platform module, typically used under Weston.
- `fdo` is the WPE backend library family used underneath that path.

</details>

### Performance Tuning

| Setting | Value | Why |
|---------|-------|-----|
| GPU memory | 128MB | `gpu_mem=128` in `/boot/config.txt` — WPE needs GPU RAM for compositing |
| Disable HDMI | Yes | `hdmi_blanking=2` — saves ~25mA power |
| Overclock | Optional | `arm_freq=1200` (Pi Zero 2W default is 1000MHz) |
| Swap | 256MB | `CONF_SWAPSIZE=256` in `/etc/dphys-swapfile` — safety net for 512MB RAM |

Add to `/boot/config.txt`:

```ini
# Voxel display settings
gpu_mem=128
hdmi_blanking=2

# Optional: mild overclock
# arm_freq=1200
# over_voltage=2
```

### Memory Budget (512MB target)

| Process | ~RAM | Notes |
|---------|------|-------|
| Kernel + drivers | ~60MB | Pi OS Lite baseline |
| server.py | ~40MB | Python + websockets + numpy |
| display/service.py | ~50MB | PIL renderer + config server |
| Audio pipeline | ~30MB | STT/TTS when active |
| **Total** | **~180MB** | ~330MB headroom + 256MB swap |

## Device Discovery & Dev Pairing

The display service broadcasts the device's presence on the LAN via UDP so dev machines can auto-discover it.

### How it works

1. **Advertiser (Pi side):** The display service starts a background thread that sends a small JSON heartbeat every 5 seconds via UDP broadcast on port **41234**. The payload includes the device name, IP, config server port, and firmware version.

2. **Discovery (dev side):** `voxel dev-pair` listens on port 41234 for these broadcasts. If multiple devices are found, the user picks one.

3. **Pairing:** The dev machine sends the 6-digit PIN (shown on the device LCD) to the config server's `POST /api/dev/pair` endpoint. On success, the device enables dev mode and returns SSH credentials.

4. **Credentials saved:** SSH host/user/password are saved to `config/local.yaml` so all `dev-*` commands (dev-push, dev-ssh, dev-logs, dev-restart) work without re-entering credentials.

### Usage

```bash
# Auto-discover and pair (interactive)
voxel dev-pair

# Skip discovery — specify IP directly
voxel dev-pair --host 192.168.1.42

# Specify a non-default config server port
voxel dev-pair --host 192.168.1.42 --port 8082
```

After pairing:
```bash
voxel dev-push         # sync full runtime to device
voxel dev-logs         # tail device logs
voxel dev-ssh          # SSH into device
voxel dev-restart      # restart display service remotely
```

### Protocol details

- **Transport:** UDP broadcast to `255.255.255.255:41234`
- **Interval:** Every 5 seconds
- **Payload:** JSON `{"service":"voxel","name":"voxel","ip":"...","port":8081,"version":"0.1.0","time":...}`
- **Pairing endpoint:** `POST /api/dev/pair` with `{"pin":"123456","dev_host":"..."}` — returns SSH creds and device info
- **No extra dependencies:** Uses only Python stdlib (`socket`, `json`, `threading`)

## WhisPlay Reference Repos

PiSugar maintains several repos useful as reference implementations:

| Repo | Description |
|------|-------------|
| [PiSugar/Whisplay](https://github.com/PiSugar/Whisplay) | Hardware driver — ST7789 SPI, WM8960 audio, RGB LED, button GPIO. Source of truth for pin mapping and init sequences. |
| [PiSugar/whisplay-ai-chatbot](https://github.com/PiSugar/whisplay-ai-chatbot) | Reference AI chatbot (TypeScript + Python). Full voice pipeline: wake word, STT, LLM, TTS. Display rendering via PIL → RGB565. |
| [PiSugar/whisplay-lumon-mdr-ui](https://github.com/PiSugar/whisplay-lumon-mdr-ui) | Lumon MDR-themed UI (Severance). Example of custom PIL-rendered display apps. |

### Font Sizes from Reference Chatbot

The reference chatbot uses these font sizes on the 240×280 display — useful guidelines for our transcript/menu/overlay rendering:

| Element | Size (px) | Notes |
|---------|-----------|-------|
| Header status text | 20 | Top-left label |
| Emoji display | 40 | Center header emoji |
| Body text (chat) | 20 | ~12-15 chars/line at 240px width |
| Battery/status label | 13 | Small indicator text |
| Large title | 28 | DejaVuSans-Bold |
| Subtitle | 18 | Secondary text |

Font selection: Custom font path via env var, fallback chain: DejaVuSans-Bold → FreeSansBold → PIL default. Emoji rendered from SVG via cairosvg.

### RGB565 Rendering Notes

Both Voxel and the reference chatbot use the same approach:
- PIL renders RGBA/RGB frames
- Numpy-accelerated conversion to RGB565 big-endian: `((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)`
- Full-frame push via SPI: 240×280×2 = 134,400 bytes per frame
- Partial updates via `set_window(x0, y0, x1, y1)` are supported by the driver but not currently used
- Line-level image caching in the chatbot avoids re-rendering unchanged text lines — worth considering for our transcript overlay

## Features to Consider

Capabilities available on the WhisPlay platform that we could adopt:

### Wake Word Detection (openWakeWord)

[openWakeWord](https://github.com/dscripka/openWakeWord) — on-device wake word detection used by the reference chatbot.

**How it works:**
1. Mel-spectrogram computation from raw 16 kHz mono audio (ONNX model)
2. Feature extraction via shared speech embedding backbone (derived from Google's model)
3. Per-keyword classification via small FC or RNN head

**Resource usage:**
- Pi 3 (same Cortex-A53 as Pi Zero 2W at 1.4 vs 1.0 GHz): 15-20 models simultaneously per core
- Pi Zero 2W estimate: 1-2 models comfortably with CPU headroom for rendering + audio
- Minimal incremental RAM per additional model (shared backbone)

**Integration pattern** (from reference chatbot):
```python
from openwakeword.model import Model

model = Model(wakeword_models=["hey_jarvis"])
# Read 1280-sample (80ms) chunks from mic at 16 kHz
prediction = model.predict(audio_frame)
for keyword, score in prediction.items():
    if score >= threshold:  # default 0.5
        trigger_listening()
```

The reference chatbot runs it as a Python subprocess, printing `WAKE <keyword> <score>` to stdout. Config via env vars: `WAKE_WORD_ENABLED`, `WAKE_WORDS`, `WAKE_WORD_THRESHOLD` (default 0.5), `WAKE_WORD_COOLDOWN_SEC` (default 1.5).

**Pre-trained models:** `alexa`, `hey_mycroft`, `hey_jarvis`, `hey_rhasspy`, `current_weather`, `timers` (<5% false-reject, <0.5/hr false-accept).

**Custom wake words:** Google Colab notebook trains a basic model in <1 hour using synthetic speech (TTS) — no manual recording needed. Recommended: ~30k hours negative audio for robust models.

**Extras:**
- Speex noise suppression (ARM64 Linux): `Model(..., enable_speex_noise_suppression=True)`
- Built-in Silero VAD: `Model(..., vad_threshold=0.5)` — suppresses predictions during non-speech
- Dual runtime: ONNX Runtime (all platforms) or TensorFlow Lite (Linux)

**Licensing:** Code is Apache 2.0, but pre-trained models are **CC BY-NC-SA 4.0** (non-commercial). Custom-trained models can use any license.

**Our config placeholder:** `audio.wake_word: null` in `config/default.yaml`. Future flow: Wake word → LISTENING → silence detect → THINKING → SPEAKING → IDLE (see `docs/openclaw-integration.md`).

### Voice Activity Detection (Dynamic)

The reference chatbot uses sox-based dynamic VAD that recalibrates to ambient noise:
- Measures ambient RMS amplitude via `sox ... stat` every 30 seconds
- Voice detection level = ambient noise % + 8% margin, clamped to 10-60%
- Exponential moving average smoothing (factor 0.7)
- Recording stops after 700ms of silence below threshold

We already have `display/ambient.py` which does deterministic amplitude-based reactions (spike detection, sustained sound, silence timeout) but doesn't gate STT recording. This pattern could be extended to auto-stop recording based on silence detection rather than requiring a button release.

### Local STT/TTS (On-Device)

The reference chatbot supports several local (no-cloud) providers:

| Provider | Type | Notes |
|----------|------|-------|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | STT | INT8 quantized, runs on Pi CPU (port 8803). `tiny` model fits in RAM. |
| [Piper](https://github.com/rhasspy/piper) | TTS | Fast local neural TTS, multiple voices, low latency on ARM. |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) | TTS | Robotic but zero-latency, zero-bandwidth fallback. |
| [Vosk](https://alphacephei.com/vosk/) | STT | Offline speech recognition, small models available. |

These could serve as offline fallbacks when the gateway is unreachable.

### Video Playback

The reference chatbot can play MP4 video directly to the display:
- `ffmpeg` decodes to raw RGB565 big-endian frames piped to stdout
- Pi Zero 2W: 4-thread CPU mode
- Original Pi Zero: hardware H.264 decoder (`h264_v4l2m2m`)
- GC disabled during playback for consistent frame rate

Could be useful for boot animations, easter eggs, or notification effects.

### Display Partial Updates

The WhisPlay driver supports `set_window(x0, y0, x1, y1)` for updating rectangular sub-regions without a full-frame push. This could reduce SPI bandwidth for UI elements that change independently (status bar, transcript text) while the face remains static.

### Camera Support

The reference chatbot supports image capture via a connected camera:
- Button double-click triggers capture
- Image sent to vision-capable LLMs (GPT-4o, Gemini, Qwen-VL)
- Web browser camera also supported

Not currently planned for Voxel but worth noting as the platform supports it.

### Hardware Acceleration

Supported by the WhisPlay ecosystem (not Pi Zero 2W):
- **Hailo-10H** (Pi AI HAT+): NPU-accelerated Whisper STT, Qwen3 LLM, vision models
- **LLM8850**: On-device Whisper + MeloTTS + LCM image generation

Relevant if Voxel expands to Pi 4/5 targets.

### Community Projects

Other projects building on WhisPlay that may have useful patterns:

- [whisplay-im-openclaw-plugin](https://github.com/JdaieLin/whisplay-im-openclaw-plugin) — OpenClaw integration (closest to our use case)
- [whisplay-openclaw-integration](https://github.com/MasteraSnackin/whisplay-openclaw-integration) — Another OpenClaw bridge
- [WhisplayChatbot](https://github.com/mklements/WhisplayChatbot) — Chatbot variant
- [chatbot-whisplay-rag](https://github.com/goldenlife-tome/chatbot-whisplay-rag) — RAG-enhanced chatbot

## Enclosure

3D printed enclosure planned (Fusion 360). Design goals:
- Minimal footprint — pocket-sized
- Access to USB-C charging port
- Speaker grille
- Mic holes
- Button access
- Display window
- Possible lanyard/clip attachment point
