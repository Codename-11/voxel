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
  - **Corner radius:** ~40px rounded bevel — content in corners gets clipped by the physical bezel
  - **Safe area:** Inset text/icons ≥20px from edges at top/bottom rows (see `display/layout.py`)
  - **Backlight:** Software PWM via Python thread — **must use 100% to avoid visible flicker**. Dimming below 100% causes brightness pulsing from scheduler jitter. Future: use ST7789 panel-level brightness commands (0x51/0x53) or hardware PWM via `pigpio`.
  - **No TE/VSYNC pin** — cannot sync SPI writes to panel refresh. Full-frame writes at 20 FPS are acceptable.
- **Audio:** WM8960 codec, dual MEMS microphones, mono speaker output
- **Input:** Single push button (BOARD pin 11, active-HIGH with external pull-down). See [Button Interaction Patterns](#button-interaction-patterns) below.
- **WiFi:** Single radio (CYW43436) — AP and client modes are mutually exclusive. On first boot with no known WiFi, the display service starts AP mode ("Voxel-Setup" hotspot) and serves a config portal at `http://10.42.0.1:8081`. Uses `nmcli` (NetworkManager) for all WiFi operations — no extra packages needed.
- **LED:** RGB LED indicator (active-LOW, software PWM)
- **Connector:** 40-pin GPIO header (stacks on Pi Zero)

### Pin Mapping

| Function | GPIO Pin | Notes |
|----------|----------|-------|
| LCD SPI MOSI | GPIO 10 | SPI0 |
| LCD SPI SCLK | GPIO 11 | SPI0 |
| LCD CS | GPIO 8 | SPI CE0 |
| LCD DC | GPIO 25 | Data/Command |
| LCD RST | GPIO 27 | Reset |
| LCD BL | GPIO 18 | Backlight (PWM) |
| Button Left | GPIO 26 | Active-low, internal pull-up |
| Button Right | GPIO 13 | Active-low, internal pull-up |
| RGB LED | GPIO 12 | WS2812-style or PWM |
| I2S BCLK | GPIO 18 | WM8960 audio |
| I2S LRCLK | GPIO 19 | WM8960 audio |
| I2S DIN | GPIO 20 | WM8960 audio |
| I2S DOUT | GPIO 21 | WM8960 audio |
| I2C SDA | GPIO 2 | WM8960 control |
| I2C SCL | GPIO 3 | WM8960 control |

*Note: Pin mapping may vary by Whisplay HAT revision. Verify with PiSugar docs.*

### Button Interaction Patterns

The Whisplay HAT has a single push button (BOARD pin 11). All interaction is encoded through timing patterns:

| Pattern | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| **Short press** | Cycle views (face / drawer / chat) | < 400ms hold, no second press within 400ms | "Tap" pill (cyan) |
| **Double-tap** | Push-to-talk (start recording) | Two presses within 400ms, face view only | "Talk" pill (bright green) |
| **Long press** | Menu open / select | Hold > 1s | Cyan ring fills to 1/10, "Menu" pill (bright cyan) |
| **Sleep** | Enter sleep mode | Hold > 5s | Blue/indigo ring continues to 5/10, "Sleep" pill (indigo) |
| **Shutdown** | Shutdown Pi (with confirm) | Hold > 10s | Orange→red ring fills to full, "Shutdown" pill (red) |

**Hold indicator:** While the button is held, a three-zone progress ring appears at the bottom of the screen:
- **Zone 1 (0-1s):** Cyan arc fills the first 1/10 of the ring, label shows "menu"
- **Zone 2 (1-5s):** Blue/indigo arc continues filling to 5/10, label shows "sleep"
- **Zone 3 (5-10s):** Orange→red arc fills the remaining half, label shows "shutdown"
- Two zone boundary ticks mark the 1s and 5s transition points
- Center dot changes color at each zone boundary

**Shutdown confirmation:** After releasing at >10s, a full-screen countdown overlay appears (3... 2... 1...) with a pulsing "SHUTTING DOWN" warning. Any button press during the countdown cancels. After the countdown reaches 0, `sudo shutdown -h now` executes.

**Talk mode rules:** Push-to-talk only triggers from the face view (not menu or chat views). While LISTENING, any short press or double-tap stops recording. While SPEAKING, any short press or double-tap cancels playback.

**Desktop simulation:** The spacebar in the tkinter/pygame preview window mimics the hardware button with identical timing logic.

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

4. **Credentials saved:** SSH host/user/password are saved to `config/local.yaml` so all `dev-*` commands (ssh, logs, restart, display-push) work without re-entering credentials.

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
voxel display-push     # sync + run display on device
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

## Enclosure

3D printed enclosure planned (Fusion 360). Design goals:
- Minimal footprint — pocket-sized
- Access to USB-C charging port
- Speaker grille
- Mic holes
- Button access
- Display window
- Possible lanyard/clip attachment point
