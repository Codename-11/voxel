# TODO — Voxel

## Priority: High

- [ ] **Voice pipeline wiring** — Wire STT/TTS through the WebSocket backend. Button press → record → Whisper → OpenClaw gateway → ElevenLabs/edge-tts → playback + amplitude over WebSocket for mouth sync.
- [ ] **WPE/Cog deployment** — Set up WPE WebKit on Pi OS Lite to render `app/dist/` fullscreen on the LCD. Configure Cog to auto-launch on boot pointing at the React build.
- [ ] **Production build serving** — `server.py` should serve `app/dist/` as static files in production mode (when WPE loads from localhost). Or configure Cog to load directly from filesystem.
- [ ] **Pi setup script update** — Update `scripts/setup.sh` to install Node.js, build the React app, install WPE/Cog, and configure both systemd services (backend + browser).

## Priority: Medium

- [ ] **Settings menu UI** — React-based settings screens. Agent selection, voice picker, brightness, battery, about. Navigated via hardware buttons (WebSocket button events).
- [ ] **Status bar integration** — Show agent name, battery level, connectivity in the React status bar. Data already flows via WebSocket state.
- [ ] **Full voice interaction loop** — End-to-end: button press → record → STT → gateway → TTS → speak with mouth sync → return to idle. All state transitions via WebSocket.
- [ ] **Audio amplitude streaming** — Stream real-time audio RMS amplitude from Python backend to React frontend via WebSocket for live mouth animation during TTS playback.
- [ ] **Wake word** — Optional "Hey Voxel" wake word for hands-free activation. Porcupine or Vosk for on-device detection.
- [ ] **CLI interface** — Argument parsing for `server.py` (`--verbose`, `--port`, `--log-level`, `--no-hardware`).

## Priority: Low

- [ ] **Conversation memory** — Keep last N exchanges in context for follow-up conversations. Store locally or via gateway session.
- [ ] **Notification display** — Show brief text notifications on screen (Discord mentions, cron alerts, etc.) with Voxel reacting to them.
- [ ] **Power management** — Dim display after idle timeout, sleep mode, battery warnings, graceful shutdown on low battery. Battery data already flows via WebSocket.
- [ ] **OTA updates** — Pull latest from GitHub, rebuild React app, restart services — from the menu UI.
- [ ] **3D printed case** — Fusion 360 enclosure design for Pi Zero 2W + Whisplay HAT + PiSugar battery stack.
- [ ] **Custom boot splash** — Voxel logo/animation on boot before WPE starts.
- [ ] **Pygame renderer parity** — Keep pygame fallback updated with all 16 moods and 3 styles (currently has 9 moods, no per-eye overrides).

## Ideas / Exploration

- [ ] Multiple character skins (swap the cube for other shapes/characters)
- [ ] Emoji reactions on the LED (flash patterns for different events)
- [ ] Camera add-on (Pi Camera Zero) for visual awareness
- [ ] Local LLM option (Ollama on Pi 5 version)
- [ ] Companion app (phone) for remote config and conversation history
- [ ] Offline mode — cache recent agent responses, show cached personality when no network

## Completed

- [x] **React face renderer** — Framer Motion-based animated cube with eyes, mouth, body, mood icons. 16 moods, 3 styles.
- [x] **Shared YAML data layer** — `shared/expressions.yaml`, `shared/styles.yaml`, `shared/moods.yaml`. Both Python and React read from them.
- [x] **WebSocket backend** — `server.py` with state broadcasting, button handling, mood/style commands, hardware polling loop.
- [x] **WebSocket frontend hook** — `useVoxelSocket.js` with auto-reconnect, state sync, command methods.
- [x] **Pluggable renderer interface** — `face/base.py` abstract base class. Pygame implements it; React is primary.
- [x] **Dev workflow** — `run_dev_windows.bat` / `run.sh` start both backend and frontend. Root `package.json` proxies npm commands.
- [x] **Platform abstraction** — auto-detects Pi vs desktop for buttons, LED, battery, display.
- [x] **State machine** — 7 states with transition callbacks.
- [x] **OpenClaw gateway client** — non-streaming chat completions.
- [x] **Expression system** — 16 moods with per-eye overrides and eye color overrides.
- [x] **Style system** — kawaii, retro, minimal face styles.
- [x] **Character design** — concept art, UI mockups.
