# Hardware Reference

## Bill of Materials

| Component | Product | ~Price | Purpose |
|-----------|---------|--------|---------|
| Brain | Raspberry Pi Zero 2W | $15 | Compute (quad-core ARM Cortex-A53, 512MB RAM) |
| Display + Audio | PiSugar Whisplay HAT | $25 | LCD, mics, speaker, button, LED |
| Battery | PiSugar 3 1200mAh | $20 | Portable power via USB-C charging |
| Storage | MicroSD card (16GB+) | $5 | OS and software |
| **Total** | | **~$65** | |

No soldering required. The components stack together using the GPIO header and pogo pins.

## Assembly

Stack order (bottom to top):

1. **PiSugar 3 battery** — pogo pins face up
2. **Raspberry Pi Zero 2W** — pogo pins align automatically
3. **PiSugar Whisplay HAT** — connects via 40-pin GPIO header

Total thickness: approximately 15mm. A 3D-printable enclosure is planned.

## PiSugar Whisplay HAT

The Whisplay HAT integrates display, audio, and input onto a single board matching the Pi Zero footprint.

### Display

- **Type:** 1.69" IPS LCD
- **Resolution:** 240 x 280 pixels
- **Controller:** ST7789
- **Interface:** SPI at 100MHz
- **Corner radius:** ~40px rounded bezel (content in corners gets clipped)
- **Backlight:** Software PWM — must use 100% to avoid flicker
- **No VSYNC pin** — cannot sync SPI writes to panel refresh; full-frame writes at 20 FPS are acceptable

::: warning
Dimming the backlight below 100% causes visible brightness pulsing. This is a software PWM limitation caused by Linux scheduler jitter. Use 100% brightness for now. Future options include ST7789 panel-level brightness commands (registers 0x51/0x53) or hardware PWM via `pigpio`.
:::

### Audio

- **Codec:** WM8960
- **Microphones:** Dual MEMS mics
- **Speaker:** Mono output
- **Driver:** ALSA device installed via Whisplay driver package

### Input

- **Button:** Single push button (BOARD pin 11, active-HIGH with external pull-down)
- **LED:** RGB LED indicator (active-LOW, software PWM)

## Pin Mapping

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

::: info
Pin mapping may vary by Whisplay HAT revision. Verify with the PiSugar documentation for your specific board.
:::

## Button Interaction Patterns

All interaction is encoded through a single button using hold duration. There is no double-tap.

### From Face View (IDLE)

| Gesture | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| Tap | Toggle view (face / chat) | < 400ms, fires instantly on release | "Tap" pill (cyan) |
| Hold | Start recording (push-to-talk) | > 400ms (still held), stays recording until release | Pulsing ring + "Talk" label (green) |

Once recording starts at 400ms, the button stays in recording state until release. There is no menu/sleep/shutdown override while recording -- the hold is exclusively for voice input.

### From Chat View

| Gesture | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| Tap | Toggle view (face / chat) | < 400ms, fires instantly on release | "Tap" pill (cyan) |
| Hold | Open menu | > 1s (fires at threshold) | Ring fills to 1/10, "Menu" pill |
| Hold | Sleep | > 5s (fires at threshold) | Ring continues to 5/10, "Sleep" pill |
| Hold | Shutdown with confirm | > 10s (fires at threshold) | Orange-to-red ring fills to full, "Shutdown" pill |

### Inside Menu

| Gesture | Action | Timing |
|---------|--------|--------|
| Tap | Move to next item | < 500ms |
| Hold | Select / enter | > 500ms (fires at threshold) |
| Idle | Auto-close menu | 5s with no input |

"Back" is the last item in every menu/submenu. For value items (volume, brightness), taps cycle preset values (0/25/50/75/100), hold confirms.

### Hold Indicator

While the button is held (from non-face views), a four-zone progress ring appears at the bottom of the screen:

- **Zone 0 (0-0.4s):** Subtle pulsing dot. No label (waiting to determine tap vs hold).
- **Zone 1 (0.4-1s):** Cyan ring fills with pulsing center dot. "Talk" label (face view only: recording active).
- **Zone 2 (1-5s):** Brighter cyan continues. "Menu" label (menu opened at 1s threshold).
- **Zone 3 (5-10s):** Orange-to-red. "Sleep" then "Shutdown" labels.

Tick marks at 1s and 5s zone boundaries. Center dot changes color at each zone.

Long-hold actions (menu, sleep, shutdown) fire the moment the threshold is crossed while the button is still held. They do not wait for release. From the face view, the hold is reserved exclusively for recording.

### Shutdown Confirmation

When the 10s threshold is crossed, a full-screen countdown overlay appears:

- 3... 2... 1... with a pulsing "SHUTTING DOWN" warning
- Any button press during the countdown cancels the shutdown
- After reaching 0, the device executes `sudo shutdown -h now`

### Talk Mode Rules

Push-to-talk activates when the button is held past 400ms, from the face view only (not menu or chat views). While LISTENING, a tap stops recording. While SPEAKING, a tap cancels playback. A 500ms minimum recording guard prevents accidental cancellation from button bounce.

### Desktop Simulation

In the tkinter or pygame preview window, the **spacebar** feeds into the exact same button state machine as the Pi GPIO hardware.

## LED Patterns

The RGB LED provides status feedback:

| State | LED Behavior |
|-------|-------------|
| Idle | Slow cyan breathe |
| Listening | Solid green |
| Thinking | Pulsing yellow |
| Speaking | Pulsing blue |
| Error | Red flash |
| Sleeping | Off or very dim pulse |

LED brightness and animation speed are configurable:

```yaml
led:
  enabled: true
  brightness: 80
  breathe_speed: 1.0
```

## PiSugar 3 Battery

- **Capacity:** 1200mAh
- **Output:** 5V via pogo pins to the Pi Zero
- **Charging:** USB-C
- **Monitoring:** I2C or HTTP API at `localhost:8421`

### Battery API

```bash
curl http://localhost:8421/api/battery
# {"battery": 78, "charging": false}
```

Battery level is displayed in the status bar on the LCD and accessible via the WebSocket state.

## Display Constraints Summary

| Constraint | Value | Impact |
|------------|-------|--------|
| Resolution | 240 x 280 px | Design all UI for this exact size |
| Corner radius | ~40px | Avoid placing content in corners |
| Safe area | 20px+ inset from top/bottom edges | Status bar and indicators only in margins |
| Frame rate | ~20 FPS (target 30, limited by CPU/SPI) | Keep rendering simple |
| Backlight | 100% only | No dimming without flicker |
| Interface | SPI at 100MHz | Full-frame writes, no partial updates |
| No VSYNC | Cannot sync to panel refresh | Occasional tearing is normal |

## Performance Tuning

Applied automatically by `voxel setup`, but can be manually configured in `/boot/config.txt`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `gpu_mem` | `128` | GPU memory for compositing |
| `hdmi_blanking` | `2` | Disable HDMI to save ~25mA |
| Swap | 256MB | Safety net for 512MB RAM |

### Memory Budget

| Process | ~RAM | Notes |
|---------|------|-------|
| Kernel + drivers | ~60MB | Pi OS Lite baseline |
| Display service | ~40MB | PIL renderer + components |
| server.py | ~40MB | Python + websockets + numpy |
| Audio pipeline | ~30MB | Active during STT/TTS |
| **Total** | **~170MB** | ~340MB headroom + 256MB swap |
