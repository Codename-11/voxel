# TODO — Voxel

## Priority: High

- [ ] **Character sprite sheets** — Design final cube mascot sprites based on concept-03. Export PNG sequences for each mood state (idle, listening, thinking, speaking, happy, error, sleeping). Target: 24-frame idle loop, 8-frame transitions.
- [ ] **Face renderer** — Pygame sprite animation engine. Load sprite sheets, animate at 30fps, smooth transitions between moods (lerp over ~300ms).
- [ ] **Mouth audio sync** — Real-time amplitude detection (RMS) from TTS audio output → mapped to mouth openness frames. `core/audio.py` already has `get_amplitude()`.
- [ ] **STT pipeline** — Whisper API integration. Record from mic on button press, send to Whisper, return transcript. `core/stt.py`.
- [ ] **TTS pipeline** — ElevenLabs (primary) / edge-tts (fallback). Receive text from gateway, generate audio, play through speaker while syncing mouth. `core/tts.py`.

## Priority: Medium

- [ ] **Full voice interaction loop** — Button press → record → STT → gateway → response → TTS → speak with mouth sync → return to idle. Wire all components together.
- [ ] **Settings menu UI** — Button-navigated menu screens. Agent selection, voice picker, brightness slider, WiFi status, battery, about screen. `ui/menu.py`, `ui/screens.py`.
- [ ] **Status bar** — Bottom bar overlay showing current state text, agent name, battery icon, connectivity indicator. `ui/statusbar.py`.
- [ ] **Screen transitions** — Smooth transitions between face view and menu screens. Slide, fade, or iris effects. `ui/transitions.py`.
- [ ] **Wake word** — Optional "Hey Voxel" wake word for hands-free activation. Porcupine or Vosk for on-device detection.

## Priority: Low

- [ ] **Conversation memory** — Keep last N exchanges in context for follow-up conversations. Store locally or via gateway session.
- [ ] **Notification display** — Show brief text notifications on screen (Discord mentions, cron alerts, etc.) with Voxel reacting to them.
- [ ] **Idle behaviors** — Random gaze drift patterns, occasional curious head tilts, sleepy mode after timeout. Make Voxel feel alive when not in conversation.
- [ ] **Power management** — Dim display after idle timeout, sleep mode, battery warnings, graceful shutdown on low battery.
- [ ] **OTA updates** — Pull latest from GitHub and restart service from the menu UI.
- [ ] **3D printed case** — Fusion 360 enclosure design for Pi Zero 2W + Whisplay HAT + PiSugar battery stack.
- [ ] **Custom boot splash** — Voxel logo/animation on boot before main app starts.

## Ideas / Exploration

- [ ] Multiple character skins (swap the cube for other shapes/characters)
- [ ] Emoji reactions on the LED (flash patterns for different events)
- [ ] Camera add-on (Pi Camera Zero) for visual awareness
- [ ] Local LLM option (Ollama on Pi 5 version)
- [ ] Companion app (phone) for remote config and conversation history
