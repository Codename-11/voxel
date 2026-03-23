# Contributing to Voxel

Thanks for your interest in Voxel! This project is in early development.

## Getting Started

1. Fork the repo and clone locally
2. Run `run_dev_windows.bat` (Windows) or `./run.sh` (macOS/Linux) to start the dev environment
3. Make your changes
4. Test in the browser (240x280 device frame at http://localhost:5173)
5. Submit a PR

## Development Setup

```bash
git clone https://github.com/YOUR-USERNAME/voxel.git
cd voxel

# Full stack (backend + frontend)
run_dev_windows.bat   # Windows
./run.sh              # macOS / Linux

# Frontend only (no backend needed)
npm run dev
```

No Pi hardware needed — the React app runs in any browser.

## Project Structure

See [CLAUDE.md](CLAUDE.md) for the full developer guide, and [docs/architecture.md](docs/architecture.md) for system design.

## Code Style

**Frontend (React):**
- React functional components with hooks
- Framer Motion for all animation
- Tailwind CSS for styling
- Expression/style data in `shared/*.yaml`, not hardcoded in components

**Backend (Python):**
- Python 3.11+, type hints on all public functions
- Dataclasses for config/state objects
- Hardware access behind abstraction layer (`hardware/` modules)
- Logging via stdlib `logging` module
- Config in YAML, not hardcoded values

## Key Constraints

- **240x280 pixels** — everything must look good at this resolution
- **Pi Zero 2W** — 512MB RAM, quad-core 1GHz ARM. Keep animations efficient.
- **WebSocket bridge** — all hardware/AI state flows through `server.py`
- **Shared YAML** — expression and style data lives in `shared/`, not duplicated

## Areas for Contribution

- **Face expressions** — new moods, refine existing animations in `shared/expressions.yaml`
- **Face styles** — new visual styles in `shared/styles.yaml` + rendering in `VoxelCube.jsx`
- **Audio pipeline** — STT/TTS integration, mouth sync via WebSocket
- **Settings UI** — React-based menu screens for agent selection, voice, settings
- **Pi deployment** — WPE/Cog setup, systemd services, production build optimization
- **Pi testing** — hardware integration on actual Relay hardware

## Reporting Issues

Open an issue on GitHub with:
- What you expected
- What happened
- Platform (desktop browser or Pi model)
- Screenshots/video if UI-related
