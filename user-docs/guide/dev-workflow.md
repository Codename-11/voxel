# Development Workflow

Voxel can be developed on any platform — Windows, macOS, or Linux. The PIL display service renders in a local tkinter window that shows the exact 240x280 face as it appears on the device's LCD.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Pinned to 3.13 via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | Latest | Python package manager |
| Node.js | 18+ | For React browser UI (optional) |
| npm | 9+ | Comes with Node.js |

Install uv if you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Clone the repo and install dependencies:

```bash
git clone https://github.com/Codename-11/voxel.git
cd voxel
uv sync
```

## Local Preview (PIL Renderer)

The primary development tool. Opens a tkinter window rendering the 240x280 face using the same PIL renderer that runs on the Pi.

```bash
# Start the preview
uv run dev

# With auto-reload on file changes
uv run dev-watch

# With full voice pipeline (spawns server.py as a child process)
uv run dev --server
```

The preview window simulates the hardware button with the **spacebar** — same timing patterns as the physical button (short press, double-tap, long press).

::: tip
The `--server` flag spawns `server.py` as a child process and auto-connects via WebSocket, enabling the full voice pipeline (STT, gateway, TTS) in the preview. No need to run the backend separately.
:::

::: tip
`dev-watch` uses `watchfiles` to monitor for changes and automatically restarts the display service. This is the recommended mode during active development.
:::

## React Browser UI

A browser-based UI with Framer Motion animations. Useful for rapid expression and style iteration with hot module replacement (HMR). This is a development tool, not the production renderer.

```bash
# macOS / Linux
./run.sh

# Windows
run_dev_windows.bat
```

This starts two processes:

- **Backend:** `uv run server.py` on port 8080 (WebSocket server)
- **Frontend:** `npm run dev` on port 5173 (Vite dev server)

Open `http://localhost:5173` in your browser. The React app works standalone and falls back to local state when no WebSocket connection is available. Press backtick (`` ` ``) to toggle the dev panel.

## Pairing with a Device

To push code to a physical Voxel device, first pair with it:

```bash
uv run voxel dev-pair
```

This discovers the device on your LAN via UDP broadcast, prompts for the 6-digit PIN shown on the device's LCD, and saves SSH credentials locally.

To skip discovery and specify an IP:

```bash
uv run voxel dev-pair --host 192.168.1.42
```

## Pushing to the Pi

After pairing, use `display-push` to sync and run your local display service on the device:

```bash
# Sync + run, show remote logs
uv run voxel display-push --logs

# Watch for changes and auto-push
uv run voxel display-push --watch

# Update Pi code (git pull + uv sync) before pushing
uv run voxel display-push --update
```

This is the core dev loop for hardware iteration: edit locally, push to Pi, see results on the LCD.

## Editing Expressions

Expression data lives in `shared/expressions.yaml` — the single source of truth for all 16 moods. Each mood defines eye openness, pupil size, mouth shape, body bounce, and more.

When you edit `shared/expressions.yaml`:

- **React browser UI:** Changes trigger HMR instantly via Vite (which watches the `shared/` directory)
- **PIL preview (`dev-watch`):** Restarts the display service automatically
- **Pi (`display-push --watch`):** Syncs and restarts on the device

Face styles are in `shared/styles.yaml` (kawaii, retro, minimal). Mood-to-state mapping and LED behavior are in `shared/moods.yaml`.

### Emoji Reactions

Agents can prefix their responses with an emoji (e.g. "😊 That's great!") to trigger a mood change and a floating emoji decoration on the display. 31 emoji are mapped to 11 moods — for example, 😊 triggers `happy`, 🤔 triggers `thinking`, and 😮 triggers `surprised`. Unmapped emoji still appear as a visual decoration but do not change the mood.

To test emoji reactions during development, use the **Emoji Reactions** buttons in the dev panel. This sends a simulated `reaction` message so you can see the pop-in, hold, and fade-out animation without needing a live agent connection.

## Adding a Character

Characters are pluggable renderers in `display/characters/`. Each implements the abstract `Character` base class and interprets the same `Expression` data in its own visual style.

See the [Display Architecture — Creating a New Character](/guide/display-architecture#creating-a-new-character) guide for the full tutorial with code examples, interface contract, and tips.

**Quick summary:**

1. Create `display/characters/mychar.py`, extend `Character` from `base.py`
2. Implement `draw()` — render eyes, mouth, body using the expression parameters
3. Update `_last_face_cx`, `_last_left_eye`, etc. so decorations position correctly
4. Register in `display/characters/__init__.py`
5. Set active via `config/local.yaml` or the settings menu

Existing characters to reference:

| Character | File | Style |
|-----------|------|-------|
| **Voxel** | `voxel.py` | Minimal glowing pill eyes (default) |
| **Cube** | `cube.py` | Isometric 3D cube with edge glow, detailed face |
| **BMO** | `bmo.py` | Adventure Time console, pixel-art style |

Set the active character in `config/local.yaml`:

```yaml
character:
  default: mychar
```

## Local vs Device Development

There are two main ways to develop — choose based on what you are working on:

| What | Where | Command | Best for |
|------|-------|---------|----------|
| PIL preview | Local machine | `uv run dev` | Face rendering, expressions, layout |
| React browser UI | Local machine | `./run.sh` | Animation prototyping with HMR |
| Push to Pi | Pi hardware | `uv run voxel display-push --logs` | Hardware testing, SPI display, button, LED |
| Watch + push | Both | `uv run voxel display-push --watch` | Iterating on Pi with fast feedback |

The PIL preview on your local machine renders **the exact same frames** that display on the Pi's LCD. The tkinter window is pixel-identical to the SPI output (240x280, same corner radius). This means most development can happen locally without touching the hardware.

Push to Pi when you need to test:
- SPI display rendering performance
- Physical button interaction
- LED patterns
- Audio input/output
- WiFi/AP mode behavior
- Boot sequence and systemd service lifecycle

## Project Structure Overview

```
display/
  service.py                # Display service entry point (uv run dev)
  renderer.py               # PILRenderer — composites all layers
  state.py                  # Shared display state
  characters/               # Pluggable character renderers
  components/               # UI components (face, menu, onboarding...)
  backends/                 # Output backends (spi.py, tkinter.py, pygame.py)
  led.py                    # LEDController — WhisPlay RGB LED patterns
server.py                   # Python backend (state machine, AI, hardware)
hw/                         # Hardware abstraction (detect.py, buttons.py, battery.py)
shared/                     # YAML data (expressions, styles, moods)
app/                        # React browser UI (dev tool)
services/                   # Systemd unit files
```

## Tips

- The display is 240x280 pixels with ~40px corner radius. Content near corners gets clipped by the physical bezel.
- Target 20 FPS. PIL rendering is CPU-bound on the Pi's ARM Cortex-A53.
- Backlight must stay at 100% — dimming below that causes visible flicker due to software PWM.
- Keep memory usage low. The Pi has 512MB RAM total.
- Use `voxel doctor` on the Pi to diagnose issues after pushing changes.

## MCP Server Development

The MCP server (`mcp/`) can be tested locally:

```bash
# Start in stdio mode (for testing with Claude Code)
uv run python -m mcp

# Start in SSE mode (for testing with OpenClaw or remote agents)
uv run python -m mcp --transport sse --port 8082

# The MCP server needs server.py running on :8080 for tool execution
# In another terminal:
uv run server.py
```

MCP tools are defined in `mcp/tools.py`. To add a new tool, add an entry to the `TOOLS` list with a name, description, and JSON Schema input, then add a handler case in `handle_tool()`.
