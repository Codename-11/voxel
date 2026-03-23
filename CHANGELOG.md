# Changelog

## [0.2.0] - 2026-03-23

### Added
- React + Framer Motion production renderer (`app/`) — animated cube face with eyes, mouth, body language, and mood icons
- 16 mood expressions: neutral, happy, curious, thinking, confused, excited, sleepy, error, listening, sad, surprised, focused, frustrated, working, lowBattery, criticalBattery
- 3 face styles: kawaii (default), retro (iris + teeth), minimal (dots + arcs)
- Per-eye overrides for asymmetric expressions (thinking, confused, sad, frustrated)
- Eye color overrides for tinted moods (lowBattery, criticalBattery)
- Shared YAML data layer (`shared/`) — expressions.yaml, styles.yaml, moods.yaml as single source of truth for Python and React
- Python WebSocket backend (`server.py`) — state broadcasting, button handling, mood/style commands, hardware polling
- WebSocket frontend hook (`useVoxelSocket.js`) — auto-reconnect, state sync, convenience methods
- Abstract renderer interface (`face/base.py`) — pluggable backend (React primary, pygame fallback)
- Root `package.json` proxying npm commands to `app/`
- `run_dev_windows.bat` and updated `run.sh` — start both backend and frontend
- Vite config watches `shared/` for HMR on YAML changes
- Dev panel with offline/standalone mode (toggle with backtick key)

### Changed
- Renamed `design/` to `app/` — it is the production UI, not a design tool
- Architecture pivoted from pygame to React/Framer Motion as primary renderer
- Expanded from 9 moods to 16 moods
- Development workflow: `npm run dev` + `uv run server.py` instead of `uv run main.py`
- Pygame moved to optional dependency (`[project.optional-dependencies] pygame`)

## [0.1.0] - 2026-03-23

### Added
- Initial project scaffold — core, face, UI, hardware, states, config
- Platform abstraction layer — auto-detects Pi vs desktop
- Display abstraction — Pygame window (desktop) / framebuffer (Pi)
- Button abstraction — keyboard mapping (desktop) / GPIO (Pi)
- LED abstraction — visual indicator (desktop) / RGB LED (Pi)
- Audio abstraction — laptop mic/speakers (desktop) / Whisplay HAT (Pi)
- Battery abstraction — mock 100% (desktop) / PiSugar API (Pi)
- Expression system — 9 mood states with eye/mouth/body configs
- State machine — 7 states (idle, listening, thinking, speaking, error, sleeping, menu)
- OpenClaw gateway client — non-streaming chat completions
- Basic main loop with placeholder face at 30fps
- Local dev preview via Pygame window (240x280)
- Character concept art (3 variants)
- CLAUDE.md developer guide
- Default config with all 6 agents + voice assignments
- `run.sh` for quick local setup
