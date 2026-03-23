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
curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash
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

### Flash OS
1. Use Raspberry Pi Imager
2. Select "Raspberry Pi OS Lite (64-bit)"
3. Configure WiFi, SSH, hostname in imager settings
4. Flash to microSD

### First Boot
```bash
# SSH in
ssh pi@voxel.local

# Update
sudo apt update && sudo apt upgrade -y

# Install Whisplay drivers
curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash

# Reboot for drivers
sudo reboot

# Clone Voxel
git clone https://github.com/Codename-11/voxel.git
cd voxel
./scripts/setup.sh

# Configure
cp config/default.yaml config/local.yaml
nano config/local.yaml  # Add gateway URL and token

# Test
python main.py

# Install as service
sudo cp voxel.service /etc/systemd/system/
sudo systemctl enable --now voxel
```

## Enclosure

3D printed enclosure planned (Fusion 360). Design goals:
- Minimal footprint — pocket-sized
- Access to USB-C charging port
- Speaker grille
- Mic holes
- Button access
- Display window
- Possible lanyard/clip attachment point
