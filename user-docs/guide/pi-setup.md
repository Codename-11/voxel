# Pi Setup

Detailed walkthrough for setting up Voxel on a Raspberry Pi Zero 2W from scratch.

## SD Card Preparation

1. Download and install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Select **Raspberry Pi Zero 2W** as the device.
3. Choose **Raspberry Pi OS Lite (64-bit)** — Bookworm or later. The Lite image is required; the desktop image wastes RAM on a 512MB device.
4. Click the gear icon to open advanced settings:
   - **Hostname:** `voxel`
   - **Enable SSH:** Yes, with password authentication
   - **Username:** `pi` (the setup scripts expect this)
   - **WiFi:** Enter your network SSID and password
   - **Locale:** Set your timezone and keyboard layout
5. Flash the image to a 16GB+ microSD card.
6. Insert the card into the Pi and power on.

::: tip
If you plan to use WiFi onboarding instead of pre-configuring WiFi, you can skip the WiFi field in the imager. The device will start in AP mode on first boot. See [WiFi Setup](/guide/wifi-setup).
:::

## First SSH Connection

Wait about 60 seconds for the Pi to boot, then connect:

```bash
ssh pi@voxel.local
```

If `voxel.local` does not resolve, find the Pi's IP address from your router's admin page and use that instead.

## Bootstrap

Run the one-line installer:

```bash
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

The bootstrap script performs these steps:

1. **Installs git** if not present
2. **Clones the repository** to `/home/pi/voxel`
3. **Installs uv** (Astral's Python package manager)
4. **Installs Python dependencies** via `uv sync --extra pi`
5. **Creates the `voxel` CLI** at `/usr/local/bin/voxel`
6. **Runs `voxel setup`** automatically

## What `voxel setup` Does

The setup command performs a full first-time installation:

### System Packages

Installs required system dependencies via `apt`:

- `git`, `curl`, `wget`
- `portaudio19-dev` (audio capture)
- `ffmpeg` (audio conversion)
- `nodejs`, `npm` (for React app build)
- `python3-dev` (native extensions)

### Whisplay HAT Drivers

Clones the PiSugar Whisplay driver repository and installs:

- **WM8960 audio codec driver** — enables the dual MEMS mics and mono speaker as an ALSA device
- **Whisplay Python driver** — SPI display, RGB LED, and button access

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay/Driver
sudo bash install_wm8960_drive.sh
```

### Python Dependencies

Installs all Python packages via uv, including Pi-specific extras (spidev, RPi.GPIO).

### React App Build

Runs `npm install` and `npm run build` in the `app/` directory to produce the static React build used by the remote browser UI.

### Configuration

Creates `config/local.yaml` from defaults. This is where you set API keys and customize settings. The file is gitignored.

### Systemd Services

Installs and enables:

| Service | Unit File | Purpose |
|---------|-----------|---------|
| `voxel-splash` | `voxel-splash.service` | C boot splash (instant LCD image ~3s after power-on) |
| `voxel-guardian` | `voxel-guardian.service` | Display guardian (wake-up animation, WiFi AP onboarding, crash recovery watchdog) |
| `voxel` | `voxel.service` | Python backend (state machine, hardware, AI) |
| `voxel-display` | `voxel-display.service` | PIL display service (renders face to LCD, config UI on port 8081) |

### System Tuning

Applies performance tweaks to `/boot/config.txt`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `gpu_mem` | `128` | Allocate GPU memory for compositing |
| `hdmi_blanking` | `2` | Disable HDMI output to save ~25mA |

Increases swap from the default 100MB to 256MB as a safety net for the 512MB RAM.

## Post-Setup Reboot

A reboot is required for the Whisplay drivers to load:

```bash
sudo reboot
```

## Verify Installation

After reboot, SSH back in and run diagnostics:

```bash
voxel doctor
```

This checks:

- Required tools are installed (git, uv, node, ffmpeg)
- Configuration files exist and are valid
- API keys are set (gateway, STT, TTS)
- OpenClaw gateway is reachable
- Whisplay hardware is detected (audio codec, display, button)
- Services are running

::: warning
If `voxel doctor` reports missing Whisplay hardware, run `voxel hw` and reboot again. Some driver installations require two reboots.
:::

## Hardware Assembly

The physical stack order (bottom to top):

1. **PiSugar 3 battery** (bottom)
2. **Raspberry Pi Zero 2W** (middle) — pogo pins connect to battery
3. **PiSugar Whisplay HAT** (top) — connects via 40-pin GPIO header

No soldering required. Total thickness is approximately 15mm.

## Next Steps

- [Configure API keys and settings](/guide/configuration)
- [WiFi onboarding for headless devices](/guide/wifi-setup)
- [Hardware reference and pin mapping](/guide/hardware)
