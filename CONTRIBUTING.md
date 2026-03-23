# Contributing to Voxel

Thanks for your interest in Voxel! This project is in early development.

## Getting Started

1. Fork the repo and clone locally
2. Run `./run.sh` to set up the dev environment and preview
3. Make your changes
4. Test locally (the Pygame window should reflect your changes at 240×280)
5. Submit a PR

## Development Setup

```bash
git clone https://github.com/YOUR-USERNAME/voxel.git
cd voxel
./run.sh
```

No Pi hardware needed — the platform abstraction layer runs on desktop.

## Project Structure

See [CLAUDE.md](CLAUDE.md) for the full developer guide, and [docs/architecture.md](docs/architecture.md) for system design.

## Code Style

- Python 3.11+, type hints on all public functions
- Dataclasses for config/state objects
- Hardware access behind abstraction layer (`hardware/` modules)
- Logging via stdlib `logging` module
- Config in YAML, not hardcoded values

## Key Constraints

- **240×280 pixels** — everything must look good at this resolution
- **Pi Zero 2W** — 512MB RAM, quad-core 1GHz ARM. No heavy processing.
- **Sprite-based rendering** — no real-time 3D. Pre-rendered sprite sheets.
- **30fps target** — keep the main loop lean

## Areas for Contribution

- **Character design** — sprite sheets, expressions, animations
- **Face renderer** — Pygame sprite animation engine
- **Audio pipeline** — STT/TTS integration, mouth sync
- **UI** — menu system, settings screens
- **Pi testing** — hardware integration on actual Relay hardware

## Reporting Issues

Open an issue on GitHub with:
- What you expected
- What happened
- Platform (desktop OS or Pi model)
- Screenshots/video if UI-related
