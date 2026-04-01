# Voxel — Running TODO

Items for Claude to pick up. Checked items are done but kept for context.

## Critical / Blocking

- [x] **WiFi AP mode not auto-starting** — Fixed: moved WiFi check to `display/guardian.py` (voxel-guardian service) which starts before all other services and handles AP mode onboarding with a dedicated recovery screen. Guardian checks WiFi via nmcli before voxel-display starts.
- [ ] **WebSocket event loop starvation** — render loop wasn't yielding to async tasks on Pi (fix: `await asyncio.sleep(0)` always). Push and verify voice pipeline works end-to-end.
- [x] **dev-push overwrote local.yaml** — caused WiFi loss. Fix merged (skip `local.yaml` in sync). Verified working with `uninstall --nuke` + fresh `setup.sh` end-to-end test.

## Voice Pipeline

- [ ] **Streaming TTS per-sentence** — current pipeline waits for full gateway response (13s) + full TTS (2s) before playback. Stream gateway SSE → detect sentence boundaries → TTS per sentence → queue playback. Target: first audio in ~5s instead of ~19s.
- [ ] **Startup greeting timing** — server waits for display client but display takes ~25s to boot. Greeting request should fire after WS connects, not on a timer.

### Completed (this session)
- [x] **PortAudio rescan for recording** — recording uses device index 0 with `sd._terminate()` + `sd._initialize()` after ambient monitor pause
- [x] **Ambient monitor pause/resume** — `ambient_control` WebSocket messages coordinate pause/resume between backend and display service
- [x] **ALSA capture PCM auto-repair** — `dsnoop` config auto-repaired in `core/audio.py` and `voxel hw`
- [x] **Pipeline error toasts** — human-readable error messages on LCD (red pill): "No API key", "Didn't catch that", "Too short", "Can't reach server"

## UI / UX

- [x] **WiFi recovery screen** — Implemented in `display/guardian.py`. Guardian shows WiFi setup screen (AP SSID, password, PIN, QR code, config server URL) when no WiFi is detected at boot. Also accessible from the LCD settings menu via "WiFi Setup" option.
- [x] **Button UX discoverability** — Decision: keep current button model (face view: hold>400ms=talk, tap=switch; chat view: hold>1s=menu, tap=switch). Added discoverability layer: first-boot gesture tutorial (3-phase), idle hint after 45s on face view ("Hold to talk · Tap for more"), chat entry hint on first visit ("Hold for settings"), Help menu item to replay tutorial, view-aware button indicator labels. New components: `display/components/tutorial.py`, `display/components/idle_hint.py`. Config keys: `display.gesture_tutorial`, `display.idle_hint_enabled`, `display.idle_hint_delay`.
- [ ] **USB gadget mode** — enable `dtoverlay=dwc2` in `voxel hw` setup so USB recovery always works
- [ ] **Thinking cancel animation** — tap-to-cancel during THINKING implemented but needs a visual spinner/indicator showing "processing" that's clearly cancellable
- [ ] **npm run dev** — experimental React app, expected to have full capability with flags to disable features. Config handles naturally otherwise.

## Bugs / Edge Cases

- [ ] **No THINKING cancel propagation** — cancel signal sent to server but doesn't interrupt mid-flight gateway request (waits for 60s watchdog)
- [ ] **config_server sessions** — `_sessions` cleanup is lazy (every 60s on auth check). No issue in practice but could add periodic timer.
- [ ] **Boot animation → render loop spacing snap** — lerp added during settle phase but verify visually on Pi

## Completed (2026-03-31 session)

### Button UX
- [x] **Shutdown/sleep from long hold** — menu open no longer resets button state, so sleep (5s) and shutdown (10s) thresholds fire correctly even when menu was opened during hold
- [x] **Clean recording indicator** — button indicator shows pulsing cyan ring during recording (no menu/sleep/shutdown zone markers)
- [x] **View-aware labels** — "Talk" label only on face view, suppressed on chat view

### Web UI
- [x] **OpenAI TTS provider** — voice selection with 9 OpenAI voices
- [x] **Help links** — API key pages link to OpenAI, ElevenLabs, OpenClaw docs
- [x] **Test Connection** — gateway test button with dynamic agent fetching
- [x] **Restart Services** — button (without full reboot)
- [x] **Shutdown** — button in web UI
- [x] **Replay Gesture Tutorial** — button in web UI
- [x] **Diagnostics audio fix** — audio backend detection corrected
- [x] **Integration cleanup** — MCP auto-start toggle, endpoints with copy buttons
- [x] **Quick reference** — button gesture guide in Help section

### LCD Menu
- [x] **Restart Services** — menu item
- [x] **Shutdown** — menu item
- [x] **Gesture Help** — menu item (replays tutorial)

### Testing
- [x] **97 new tests** — 286 total: test_button.py, test_websocket.py, test_audio_detect.py, test_cli.py
- [x] **Pre-push git hook** — validates syntax, imports, tests before push

### CLI
- [x] **Grouped sections** — Setup, Services, Config, Dev, Experimental
- [x] **LVGL hidden** — experimental commands shown with `--all` flag
- [x] **uninstall --nuke** — complete removal for clean re-install
- [x] **Block ASCII logo** — matching Pi logs style

### Setup
- [x] **voxel hw Trixie support** — pipes 'y' to interactive driver installer, installs kernel headers for Debian 13
- [x] **End-to-end tested** — uninstall --nuke + setup.sh fresh install verified
- [x] **WhisPlay.py vendored** — at hw/WhisPlay.py (no longer cloned from GitHub)

## Early Boot Display

- [x] **Phase 1: config.txt GPIO (zero code)** — `voxel hw` now appends early boot GPIO directives to config.txt: cyan LED at ~1.5s (`gpio=24=op,dl; gpio=23=op,dl; gpio=25=op,dh`), backlight OFF until splash (`gpio=22=op,dh`). Eliminates blue screen flash.
- [x] **Phase 2: C boot splash binary** — Implemented in `native/boot_splash/splash.c`. Runs as `voxel-splash.service` (Type=oneshot). Pre-rendered RGB565 frame is pre-copied in the pi-gen image build. Ref: [CNflysky/st7789_rpi](https://github.com/CNflysky/st7789_rpi).
- [x] **Phase 3: fbtft framebuffer (optional, experimental)** — `mipi-dbi-spi` kernel overlay for boot console on LCD. Config snippet, framebuffer backend (`display/backends/framebuffer.py`), `voxel hw --fbtft` flag, and docs added. Needs hardware validation on Pi.

## Future / Research

- [ ] **Wake word (openWakeWord)** — on-device wake word detection. Custom "Hey Voxel" model trainable via Colab. Config placeholder exists (`audio.wake_word: null`).
- [ ] **Local STT/TTS fallback** — faster-whisper (tiny model), Piper TTS for offline mode when gateway unreachable
- [ ] **Partial display updates** — `set_window()` for sub-region SPI writes to reduce bandwidth
- [ ] **Gateway WebSocket migration** — switch from HTTP REST to WS protocol (needs device pairing)
