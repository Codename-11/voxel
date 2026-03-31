# CLI Reference

The `voxel` command is the primary interface for managing a Voxel device. It is installed globally at `/usr/local/bin/voxel` during bootstrap.

On a development machine (not on the Pi), run CLI commands through uv:

```bash
uv run voxel <command>
```

## Setup and Maintenance

### `voxel setup`

Full first-time installation. Installs system packages, Whisplay drivers, Python and Node dependencies, builds the React app, creates config files, installs systemd services, and tunes system settings. At the end, launches the interactive configuration wizard (`voxel configure`).

```bash
voxel setup
```

To skip the wizard (e.g. in automated/CI environments):

```bash
voxel setup --no-configure
```

Typically called automatically by the bootstrap script. Safe to re-run.

### `voxel configure`

Interactive TUI wizard for post-setup configuration. Walks through gateway connection, voice/TTS settings, display/character preferences, MCP server, webhooks, and power management. Each section is optional -- press Enter to accept defaults or skip.

```bash
voxel configure
```

Settings are saved to `config/local.yaml`. This wizard runs automatically at the end of `voxel setup` unless `--no-configure` is passed. Can be re-run at any time to change settings.

### `voxel doctor`

Runs full system health diagnostics. Checks installed tools, configuration, API keys, gateway connectivity, and hardware detection.

```bash
voxel doctor
```

### `voxel update`

Pulls the latest code from git, rebuilds dependencies, and restarts services.

```bash
voxel update
```

### `voxel build`

Rebuilds only — installs Python dependencies via uv and rebuilds the React app. Does not restart services.

```bash
voxel build
```

### `voxel hw`

Installs or reinstalls Whisplay HAT drivers and applies `/boot/config.txt` tuning (GPU memory, HDMI blanking, swap). Requires a reboot afterward.

```bash
voxel hw
sudo reboot
```

## Service Management

Voxel runs as systemd services on the Pi. These commands control them.

### `voxel start`

Starts all Voxel services.

```bash
voxel start
```

### `voxel stop`

Stops all Voxel services.

```bash
voxel stop
```

### `voxel restart`

Restarts all Voxel services.

```bash
voxel restart
```

### `voxel logs`

Tails the combined service logs in real time.

```bash
voxel logs
```

### `voxel status`

Shows the current status of all services, system info, and hardware state.

```bash
voxel status
```

## Configuration

### `voxel config`

Displays the current merged configuration (defaults + local overrides).

```bash
voxel config
```

### `voxel config get <key>`

Gets a specific configuration value using dot notation.

```bash
voxel config get gateway.url
voxel config get audio.volume
voxel config get character.default
```

### `voxel config set <key> <value>`

Sets a configuration value. Writes to `config/local.yaml`.

```bash
voxel config set gateway.token "your-token"
voxel config set audio.tts_provider openai     # or: edge, elevenlabs
voxel config set display.brightness 90
voxel config set character.default bmo
```

## Development and Pairing

These commands are used from a development workstation to interact with a Voxel device on the local network.

### `voxel dev-pair`

Auto-discovers a Voxel device on the LAN via UDP broadcast and pairs with it using the PIN shown on the device's LCD. Saves SSH credentials to `config/local.yaml`.

```bash
uv run voxel dev-pair
```

To skip auto-discovery and specify a device directly:

```bash
uv run voxel dev-pair --host 192.168.1.42
```

After pairing, all dev commands (`dev-push`, `dev-ssh`, `dev-logs`, `dev-restart`) work without re-entering credentials.

### `voxel dev-setup`

One-time setup: saves SSH credentials locally and enables dev mode on the Pi (skips PIN auth for the config server).

```bash
uv run voxel dev-setup --host 192.168.1.42 --user pi --password voxel
```

### `voxel dev-ssh`

Opens an SSH session to the paired Pi using saved credentials.

```bash
uv run voxel dev-ssh
```

### `voxel dev-logs`

Tails the display service logs on the Pi remotely via SSH (uses `journalctl` if available, falls back to `/tmp/voxel-display.log`).

```bash
uv run voxel dev-logs
```

### `voxel dev-restart`

Restarts the display service on the Pi remotely — kills the existing process and starts a fresh one.

```bash
uv run voxel dev-restart
```

### `voxel dev-push`

Syncs the full runtime (display, backend, state machine, MCP, CLI, config, shared data) to the Pi over SSH and runs the display service. This is the primary dev loop for iterating on device code.

```bash
# Sync and run, showing remote logs
uv run voxel dev-push --logs

# Watch for local file changes and auto-push
uv run voxel dev-push --watch

# Pull latest code and sync deps on Pi before pushing
uv run voxel dev-push --update

# Specify host manually (first time, before pairing)
uv run voxel dev-push --host 192.168.1.42

# Save SSH config for future use
uv run voxel dev-push --save-ssh
```

### `voxel display-test`

Runs a direct display sanity test on the Pi, bypassing the full display service. Tests the Whisplay SPI driver directly.

```bash
voxel display-test
```

## LVGL (Experimental)

Native C renderer proof of concept. Pre-renders RGB565 frames on a workstation and plays them back on the Pi's LCD.

### `voxel lvgl-build`

Compiles the LVGL renderer binary.

```bash
uv run voxel lvgl-build
```

### `voxel lvgl-render`

Renders RGB565 frames to a local directory.

```bash
uv run voxel lvgl-render --frames-dir ./out/lvgl-frames
```

### `voxel lvgl-sync`

Syncs rendered frames to the Pi over SSH.

```bash
uv run voxel lvgl-sync --frames-dir ./out/lvgl-frames --host <pi-ip> --user pi
```

### `voxel lvgl-play`

Plays pre-rendered frames on the Pi's LCD.

```bash
voxel lvgl-play --frames-dir ~/voxel/.cache/lvgl-poc-frames
```

### `voxel lvgl-deploy`

Renders, syncs, and plays in one command.

```bash
uv run voxel lvgl-deploy --frames-dir ./out/lvgl-frames --host <pi-ip> --user pi
```

### `voxel lvgl-dev`

Opinionated dev loop: renders frames, syncs to Pi, and opens an interactive preview.

```bash
uv run voxel lvgl-dev
```

## Other

### `voxel version`

Shows the current Voxel version.

```bash
voxel version
```

### `voxel uninstall`

Removes systemd services and caches. Does not delete the repository or config files.

```bash
voxel uninstall
```
