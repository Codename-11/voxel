---
name: voxel-device
description: Control and monitor the Voxel companion device (LCD face, speaker, LED, mood, chat)
version: 0.1.0
metadata:
  openclaw:
    emoji: "VX"
    requires:
      anyBins: ["python3", "python"]
    homepage: "https://github.com/Codename-11/voxel"
---

# Voxel Device Control

You have access to a Voxel companion device — a pocket-sized AI companion with an animated face on a 240x280 LCD, speaker, RGB LED, and single button.

## Available Tools (via MCP)

When the Voxel MCP server is connected, you can use these tools:

### State & Information
- **get_device_state** — Returns battery %, WiFi status, current mood, speaking state, active agent, system stats (CPU temp, RAM, uptime)
- **get_conversation_history** — Recent chat messages between user and agent
- **get_system_stats** — CPU usage/temperature, RAM, disk space, WiFi signal strength, uptime, display FPS
- **run_diagnostic** — Run a full system health check (service status, hardware checks, config validation)
- **get_logs** — Get recent log output from display or backend services (up to 200 lines)
- **check_update** — Check if a new version is available

### Display & Expression
- **set_mood** — Change the animated face expression. Available moods: neutral, happy, curious, thinking, listening, excited, sleepy, confused, surprised, focused, frustrated, sad, error
- **set_style** — Change face rendering style: kawaii (default, rounded), retro (pixelated), minimal (simplified)
- **set_character** — Switch mascot: voxel (glowing eyes, default), cube (isometric 3D), bmo (Adventure Time)
- **show_reaction** — Show a floating emoji decoration above the face (e.g. "😊", "🎉", "💡"). Auto-dismisses after 3s.

### Audio & Communication
- **speak_text** — Make Voxel speak text aloud through the speaker via TTS
- **send_chat_message** — Send a message to the current AI agent as if the user typed it
- **set_volume** — Set speaker volume (0-100)

### Hardware
- **set_led** — Set the RGB LED color (r, g, b values 0-255)
- **set_agent** — Switch the active AI agent (daemon, soren, ash, mira, jace, pip)

### Device Management
- **restart_services** — Restart display and/or backend services (use after config changes)
- **set_config** — Change a configuration value (dotted key path, e.g. 'audio.volume', 'character.default')
- **install_update** — Pull latest code and rebuild (requires confirmation)
- **reboot_device** — Reboot the device (requires confirmation, ~30s downtime)
- **connect_wifi** — Connect to a WiFi network (SSID + password)

## Guidelines

- **Be expressive**: Use set_mood and show_reaction to convey emotion naturally during conversation
- **Keep it brief**: The device has a tiny screen and speaker — short responses work best
- **Check state first**: Call get_device_state before making assumptions about battery, connectivity, etc.
- **Don't spam**: Avoid rapid-fire tool calls — the device renders at 20 FPS
- **Mood tags**: Begin responses with [mood] tags (e.g. [happy] That's great!) — Voxel's display service parses these for face expression changes
- **Confirm destructive actions**: reboot_device and install_update require `confirm: true` — always explain what you're about to do before confirming
- **Check before changing**: Call get_device_state or run_diagnostic before making config changes or restarts
- **Logs for debugging**: Use get_logs when something isn't working — check both display and backend services
