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

All interaction is encoded through a single button using timing patterns:

| Pattern | Action | Timing | Visual Feedback |
|---------|--------|--------|-----------------|
| Short press | Cycle views (face / drawer / chat) | < 400ms hold, no second press within 400ms | "Tap" pill (cyan) |
| Double-tap | Push-to-talk (start recording) | Two presses within 400ms, face view only | "Talk" pill (bright green) |
| Long press | Menu open / select | Hold > 1s | Cyan ring fills to 1/10, "Menu" pill |
| Sleep | Enter sleep mode | Hold > 5s | Blue/indigo ring continues to 5/10, "Sleep" pill |
| Shutdown | Shutdown Pi (with confirm) | Hold > 10s | Orange-to-red ring fills to full, "Shutdown" pill |

### Hold Indicator

While the button is held, a three-zone progress ring appears at the bottom of the screen:

- **Zone 1 (0-1s):** Cyan arc fills the first 1/10 of the ring. Label shows "menu".
- **Zone 2 (1-5s):** Blue/indigo arc continues filling to 5/10. Label shows "sleep".
- **Zone 3 (5-10s):** Orange-to-red arc fills the remaining half. Label shows "shutdown".

Two zone boundary ticks mark the 1s and 5s transitions. The center dot changes color at each zone boundary.

### Shutdown Confirmation

After releasing the button at >10s, a full-screen countdown overlay appears:

- 3... 2... 1... with a pulsing "SHUTTING DOWN" warning
- Any button press during the countdown cancels the shutdown
- After reaching 0, the device executes `sudo shutdown -h now`

### Talk Mode Rules

Push-to-talk only triggers from the face view — not from menu or chat views. While LISTENING, any short press or double-tap stops recording. While SPEAKING, any short press or double-tap cancels playback.

### Desktop Simulation

In the tkinter or pygame preview window, the **spacebar** simulates the hardware button with identical timing logic.

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
