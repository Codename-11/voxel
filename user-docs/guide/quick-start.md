# Quick Start

Get Voxel running on a Raspberry Pi Zero 2W in under 15 minutes.

## Prerequisites

| Item | Notes |
|------|-------|
| Raspberry Pi Zero 2W | With GPIO header soldered |
| PiSugar Whisplay HAT | Display, audio, button, LED |
| MicroSD card (16GB+) | Flashed with Raspberry Pi OS Lite (64-bit) |
| PiSugar 3 battery (optional) | 1200mAh for portable use |
| USB-C power supply | For initial setup |

## Option A: Pre-built Image (Easiest)

If a pre-built Voxel image is available from the [releases page](https://github.com/Codename-11/voxel/releases):

1. Download the `.img.xz` file
2. Flash it to your SD card with [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (select "Use custom")
3. Insert the card, power on
4. The LCD shows "Connect to Voxel-Setup WiFi" — follow the prompts
5. Done. No SSH required.

Skip to [First Boot](#_4-first-boot) below.

## Option B: Manual Install

### 1. Flash the SD Card

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite (64-bit)** (Bookworm or later).

In the imager settings, configure:

- **Hostname:** `voxel`
- **Enable SSH** with password authentication
- **Username:** `pi`
- **WiFi:** Enter your network SSID and password

Insert the card and power on the Pi.

### 2. Install Voxel

SSH into the Pi and run the bootstrap script:

```bash
ssh pi@voxel.local
curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash
```

This single command handles everything:

1. Clones the Voxel repository to `~/voxel`
2. Installs [uv](https://docs.astral.sh/uv/) (Python package manager)
3. Installs Python dependencies
4. Creates the global `voxel` CLI command
5. Hands off to `voxel setup`, which:
   - Installs system packages (git, portaudio, ffmpeg, Node.js)
   - Installs Whisplay HAT drivers (WM8960 audio, SPI display)
   - Builds the React dev UI
   - Creates `config/local.yaml`
   - Installs and enables systemd services
   - Tunes `/boot/config.txt` (GPU memory, HDMI blanking)
   - Increases swap to 256MB
   - Launches an interactive configuration wizard (gateway, voice, display, MCP, power)

### 3. Reboot

A reboot is required for the Whisplay drivers to load:

```bash
sudo reboot
```

## 4. First Boot

After reboot, the Voxel display service starts automatically.

- If your Pi connected to WiFi during setup, the animated face appears on the LCD.
- If no WiFi is available, the device enters AP mode and shows a WiFi setup screen. See [WiFi Setup](/guide/wifi-setup) for details.

On first boot, a short gesture tutorial walks you through the three main interactions: hold the button to talk, tap to switch views, and hold from the chat view to open settings. The tutorial only shows once -- you can replay it later from the "Help" item in the settings menu.

## 5. Verify

SSH back in and check system health:

```bash
voxel doctor
```

This runs diagnostics on tools, configuration, gateway connectivity, and hardware.

## Next Steps

- [Configure API keys and agents](/guide/configuration)
- [Set up WiFi on a headless device](/guide/wifi-setup)
- [Full Pi setup details](/guide/pi-setup)
- [CLI command reference](/guide/cli-reference)
