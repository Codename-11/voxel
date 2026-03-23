# Changelog

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
- Local dev preview via Pygame window (240×280)
- Character concept art (3 variants)
- CLAUDE.md developer guide
- Default config with all 6 agents + voice assignments
- `run.sh` for quick local setup
