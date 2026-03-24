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

- **Display:** 1.69" IPS LCD, 240×280 pixels, ST7789 controller, SPI interface
- **Audio:** WM8960 codec, dual MEMS microphones, mono speaker output
- **Input:** Two mouse-style buttons (active-low, GPIO)
- **LED:** RGB LED indicator
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

### Driver Installation

```bash
# Whisplay HAT drivers (audio codec + display)
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay/Driver
sudo bash install_wm8960_drive.sh
```

This installs:
- WM8960 audio driver (ALSA device)
- ST7789 display driver (framebuffer at `/dev/fb1`)

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

### 3. Hardware Drivers

```bash
cd ~/voxel

# Install Whisplay HAT drivers + tune config.txt (gpu_mem, swap, HDMI)
./scripts/setup.sh hw

# Reboot to load drivers
sudo reboot
```

After reboot, verify:

```bash
ls /dev/fb*    # should show /dev/fb1 (ST7789 SPI LCD)
arecord -l     # should show WM8960 device
aplay -l
```

### 4. Configure & Start

```bash
cd ~/voxel

# Edit config (gateway URL, API keys)
nano config/local.yaml

# Start Voxel
./scripts/setup.sh start

# Watch logs
./scripts/setup.sh logs

# Check status
./scripts/setup.sh status
```

### Management Commands

```bash
./scripts/setup.sh install   # Full first-time setup (default)
./scripts/setup.sh update    # Pull latest, rebuild, restart services
./scripts/setup.sh hw        # Whisplay drivers + config.txt tuning
./scripts/setup.sh start     # Start services
./scripts/setup.sh stop      # Stop services
./scripts/setup.sh restart   # Restart services
./scripts/setup.sh logs      # Tail backend + UI logs
./scripts/setup.sh status    # Service status, memory, battery, display
```

---

## WPE/Cog — How It Works

WPE WebKit is an embedded browser engine built for devices like the Pi. Cog is its minimal launcher — no window decorations, no address bar, just fullscreen content. This is what renders the React + Framer Motion UI on the LCD.

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

### Two systemd services

| Service | Unit File | What it runs |
|---------|-----------|-------------|
| Backend | `voxel.service` | `uv run server.py` — WebSocket server, state machine, hardware I/O, AI pipelines |
| UI | `voxel-ui.service` | `cog file:///home/pi/voxel/app/dist/index.html` — WPE browser rendering the React app fullscreen |

The UI service waits for the backend to start (`After=voxel.service`), then opens Cog loading the pre-built React app from disk. The app connects to `ws://localhost:8080` for backend state.

### Display Routing

The Whisplay HAT's LCD is an SPI display (ST7789 controller). How WPE gets pixels to it depends on the driver:

**Scenario A — DRM connector available (preferred):**
If the Whisplay driver registers as a DRM device, Cog's DRM platform plugin renders directly to it. This is the zero-overhead path.

```bash
# Check if DRM device exists for the LCD
ls /dev/dri/card*
# If you see a card device, try:
COG_PLATFORM=drm cog file:///home/pi/voxel/app/dist/index.html
```

**Scenario B — Framebuffer only (fallback):**
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

If using fbcp, add it as a systemd service that starts before `voxel-ui`:

```bash
# /etc/systemd/system/fbcp.service
[Unit]
Description=Framebuffer copy (DRM → SPI LCD)
Before=voxel-ui.service

[Service]
ExecStart=/usr/local/bin/fbcp-ili9341
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

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
| WPE/Cog | ~120MB | WebKit renderer + React app |
| Audio pipeline | ~30MB | STT/TTS when active |
| **Total** | **~250MB** | ~260MB headroom + 256MB swap |

## Enclosure

3D printed enclosure planned (Fusion 360). Design goals:
- Minimal footprint — pocket-sized
- Access to USB-C charging port
- Speaker grille
- Mic holes
- Button access
- Display window
- Possible lanyard/clip attachment point
