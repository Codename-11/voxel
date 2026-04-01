# Troubleshooting

Common issues and how to resolve them.

## Diagnostic Tool

Always start with the built-in diagnostics:

```bash
voxel doctor
```

This checks tools, configuration, API keys, gateway connectivity, hardware detection, and service status. Most issues will be identified here.

## Service Logs

View real-time logs from all Voxel services:

```bash
voxel logs
```

For a specific service:

```bash
journalctl -u voxel-guardian -f   # Boot watchdog, WiFi AP, crash recovery
journalctl -u voxel-display -f    # Display renderer
journalctl -u voxel -f            # Backend (AI, voice)
```

## Common Issues

### Device does not boot

**Symptoms:** No activity on the LCD, cannot SSH in.

- Verify the microSD card is fully inserted
- Check that the power supply provides at least 5V/1A
- Try re-flashing the SD card with Raspberry Pi Imager
- If using the PiSugar battery, ensure it is charged (connect USB-C to charge)
- Remove the Whisplay HAT and try booting the Pi alone to isolate the issue

### No display output

**Symptoms:** Pi boots and is reachable via SSH, but the LCD stays blank.

```bash
# Install/reinstall Whisplay drivers
voxel hw
sudo reboot
```

After reboot, verify:

```bash
# Test the display directly
voxel display-test

# Check if the display service is running
voxel status

# Check doctor for hardware issues
voxel doctor
```

::: warning
Some driver installations require two reboots. If `voxel hw` followed by one reboot does not work, reboot a second time.
:::

### Display flickering

**Cause:** The backlight is set below 100%. The Whisplay HAT uses software PWM for backlight control, which causes visible brightness pulsing due to Linux scheduler jitter.

**Fix:** Set brightness to 100%:

```bash
voxel config set display.brightness 100
voxel restart
```

This is a hardware limitation. Future firmware may support panel-level brightness commands to avoid this issue.

### WiFi will not connect

- Ensure you are connecting to a 2.4GHz network (Pi Zero 2W does not support 5GHz)
- Double-check the WiFi password
- See the [WiFi Setup](/guide/wifi-setup) troubleshooting section for AP mode issues

To re-enter AP mode:

```bash
sudo nmcli connection delete <network-name>
sudo reboot
```

### Cannot reach the config UI

The web config server runs on port 8081.

```bash
# Verify the device IP
hostname -I

# Check if the config server is running
voxel status

# Test locally
curl http://localhost:8081
```

Ensure your computer is on the same network as the device. If connecting via AP mode, you must be connected to the Voxel-Setup hotspot.

### Voice interaction not working

**No audio recording:**

```bash
# Check if the WM8960 audio codec is detected
arecord -l
```

If no WM8960 device appears, reinstall drivers:

```bash
voxel hw
sudo reboot
```

**STT (speech-to-text) fails:**

- Verify your OpenAI API key is set: `voxel config get stt.whisper.api_key`
- Or check the environment variable: `echo $OPENAI_API_KEY`
- Test gateway connectivity: `voxel doctor`

**TTS (text-to-speech) fails:**

- `edge-tts` (default) requires internet but no API key
- OpenAI TTS shares the same API key as Whisper STT (`stt.whisper.api_key` or `OPENAI_API_KEY`). Falls back to edge-tts on failure.
- ElevenLabs requires a valid API key: `voxel config get tts.elevenlabs.api_key`
- Check audio output: `aplay -l` should show WM8960

**No response from AI agent:**

- Check gateway connectivity: `voxel doctor`
- Verify the gateway URL: `voxel config get gateway.url`
- Verify the gateway token: `voxel config get gateway.token`

### Services fail to start

```bash
# Check service status
voxel status

# Check for errors in logs
voxel logs

# Restart services
voxel restart
```

If services consistently fail:

```bash
# Rebuild everything
voxel build

# Reinstall services
voxel setup
```

### Out of memory

The Pi Zero 2W has 512MB RAM. If processes are being killed:

```bash
# Check memory usage
free -h

# Ensure swap is enabled (should be 256MB)
swapon --show
```

If swap is missing or too small:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=256/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### `voxel` command not found

The CLI wrapper is installed at `/usr/local/bin/voxel`. If it is missing:

```bash
# Reinstall from the repo directory
cd ~/voxel
sudo tee /usr/local/bin/voxel > /dev/null <<'WRAPPER'
#!/bin/bash
exec $HOME/.local/bin/uv run --project /home/pi/voxel voxel "$@"
WRAPPER
sudo chmod +x /usr/local/bin/voxel
```

### How do I access settings?

From the face view, tap the button to switch to the chat view. Then hold the button for more than 1 second to open the settings menu. Inside the menu, tap to move between items and hold to select.

If you are unsure about gestures, open the settings menu and select "Help" to replay the gesture tutorial that ran on first boot.

You can also access settings from a browser: scan the QR code shown on the device LCD, or navigate to `http://<device-ip>:8081` and enter the 6-digit PIN.

### `dev-pair` cannot find the device

- Ensure the device and your workstation are on the same network
- Check that `dev.advertise` is `true` in the device config
- The device broadcasts on UDP port 41234 — some networks block broadcast traffic
- Use `--host <ip>` to skip auto-discovery

### `dev-push` connection refused

- Run `voxel dev-pair` first to save SSH credentials
- Verify the device IP has not changed (DHCP lease may have expired)
- Test SSH manually: `ssh pi@<device-ip>`
