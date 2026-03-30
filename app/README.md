# Voxel — React Dev UI

Browser-based development UI for iterating on expressions, styles, and animations. **This is not the production renderer** — the Pi uses the PIL display service (`display/`).

## Quick Start

```bash
# From repo root
npm run dev        # Vite dev server on :5173
```

Or with the backend for live WebSocket state:

```bash
# Terminal 1
uv run server.py

# Terminal 2
npm run dev
```

## What's Here

- **VoxelCube** — Animated cube face with Framer Motion (eyes, mouth, body, moods)
- **StatusBar** — Battery, WiFi, agent indicator
- **ChatPanel** — Conversation UI
- **Dev Panel** — Toggle with backtick (`` ` ``) — mood/style/state controls

## Relationship to Production

The PIL renderer (`display/`) is the production display path. This React app is useful for:
- Rapid expression/style iteration with HMR
- Prototyping new animations before porting to PIL
- Testing WebSocket protocol changes

Changes to `shared/*.yaml` trigger HMR automatically.
