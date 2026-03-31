"""MCP tool definitions and handlers for Voxel device control.

Each tool maps to a WebSocket command understood by the Voxel backend (server.py).
Tools are returned by ``tools/list`` and executed via ``tools/call``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server import VoxelBridge

log = logging.getLogger("voxel.mcp.tools")

# ---------------------------------------------------------------------------
# Tool definitions (MCP schema)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "get_device_state",
        "description": (
            "Get current Voxel device state including battery, WiFi, mood, "
            "speaking state, active agent, and connectivity status. "
            "CALL THIS FIRST to check if the device is reachable. "
            "If '_connected' is false, control tools will fail."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
    },
    {
        "name": "set_mood",
        "description": "Set Voxel's facial expression/mood. Changes the animated face on the LCD.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "enum": [
                        "neutral", "happy", "curious", "thinking", "listening",
                        "excited", "sleepy", "confused", "surprised", "focused",
                        "frustrated", "sad", "error",
                    ],
                    "description": "The mood/expression to display",
                },
            },
            "required": ["mood"],
        },
    },
    {
        "name": "set_style",
        "description": "Set the face rendering style.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "enum": ["kawaii", "retro", "minimal"],
                },
            },
            "required": ["style"],
        },
    },
    {
        "name": "set_character",
        "description": "Switch the active character (mascot appearance).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "enum": ["voxel", "cube", "bmo"],
                },
            },
            "required": ["character"],
        },
    },
    {
        "name": "speak_text",
        "description": "Make Voxel speak text aloud via TTS through the device speaker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to speak aloud",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "send_chat_message",
        "description": (
            "Send a text message to the current AI agent through Voxel, "
            "as if the user typed it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message to send to the agent",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "show_reaction",
        "description": "Show a floating emoji reaction on the Voxel display.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emoji": {
                    "type": "string",
                    "description": "Emoji to display (e.g. '\U0001f60a', '\U0001f389', '\U0001f4a1')",
                },
            },
            "required": ["emoji"],
        },
    },
    {
        "name": "set_led",
        "description": "Set the RGB LED color on the Voxel device.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "r": {"type": "integer", "minimum": 0, "maximum": 255},
                "g": {"type": "integer", "minimum": 0, "maximum": 255},
                "b": {"type": "integer", "minimum": 0, "maximum": 255},
            },
            "required": ["r", "g", "b"],
        },
    },
    {
        "name": "set_volume",
        "description": "Set speaker volume level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["volume"],
        },
    },
    {
        "name": "get_conversation_history",
        "description": "Get recent conversation messages between the user and AI agent.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "set_agent",
        "description": "Switch the active AI agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["daemon", "soren", "ash", "mira", "jace", "pip"],
                    "description": "Agent ID to switch to",
                },
            },
            "required": ["agent"],
        },
    },
    # --- Device management tools ---
    {
        "name": "get_system_stats",
        "description": "Get system health stats: CPU usage/temp, RAM, disk, WiFi signal, uptime, display FPS. Works without backend connection if running on Pi.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "reboot_device",
        "description": "Reboot the Voxel device. Takes ~30 seconds to come back online.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Must be true to confirm reboot"}
            },
            "required": ["confirm"],
        },
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "restart_services",
        "description": "Restart the Voxel display and backend services (systemd). Use after config changes or to recover from errors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["all", "display", "backend"],
                    "description": "Which service to restart. 'all' restarts both.",
                }
            },
            "required": ["service"],
        },
    },
    {
        "name": "get_logs",
        "description": "Get recent log output from Voxel services. Useful for diagnosing errors. Works without backend connection if running on Pi.",
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["display", "backend", "all"], "description": "Which service logs"},
                "lines": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Number of log lines (default 50)"},
            },
        },
    },
    {
        "name": "run_diagnostic",
        "description": "Run system health diagnostics (voxel doctor). Returns a health report with service status, hardware checks, and config validation. Works without backend connection if running on Pi.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "check_update",
        "description": "Check if a new version of Voxel is available (compares local git to remote).",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "install_update",
        "description": "Pull the latest code from git and rebuild. Services will restart automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Must be true to confirm update"}
            },
            "required": ["confirm"],
        },
        "annotations": {"destructiveHint": True},
    },
    {
        "name": "set_config",
        "description": "Change a Voxel configuration value. Use dotted key paths (e.g. 'audio.volume', 'gateway.default_agent', 'character.default').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config key (dotted path, e.g. 'audio.volume')"},
                "value": {"description": "New value (string, number, or boolean)"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "connect_wifi",
        "description": "Connect the device to a WiFi network. Only works on the Pi.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ssid": {"type": "string", "description": "WiFi network name"},
                "password": {"type": "string", "description": "WiFi password"},
            },
            "required": ["ssid", "password"],
        },
    },
]

# ---------------------------------------------------------------------------
# Resource definitions (read-only data clients can browse)
# ---------------------------------------------------------------------------

RESOURCES: list[dict] = [
    {
        "uri": "voxel://state",
        "name": "Device State",
        "description": "Current Voxel device state (battery, mood, WiFi, etc.)",
        "mimeType": "application/json",
    },
    {
        "uri": "voxel://config",
        "name": "Configuration",
        "description": "Current device configuration",
        "mimeType": "application/json",
    },
    {
        "uri": "voxel://history",
        "name": "Conversation History",
        "description": "Recent chat messages",
        "mimeType": "application/json",
    },
]

# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def handle_tool(name: str, arguments: dict, bridge: "VoxelBridge") -> list[dict]:
    """Execute a tool and return MCP content blocks.

    Tools that use the WebSocket bridge catch ConnectionError and return
    a helpful message so the calling agent knows the device is unreachable.
    """

    # --- State query (always works, includes connectivity info) ---

    if name == "get_device_state":
        state = dict(await bridge.get_state())
        return [{"type": "text", "text": json.dumps(state, indent=2)}]

    # --- WebSocket-bridged tools (require backend connection) ---

    try:
        result = await _handle_ws_tool(name, arguments, bridge)
        if result is not None:
            return result
    except ConnectionError as e:
        return [{"type": "text", "text": f"[DEVICE OFFLINE] {e}"}]

    # --- Device management tools (direct system calls, no WS bridge) ---

    return await _handle_system_tool(name, arguments, bridge)


async def _handle_ws_tool(name: str, arguments: dict, bridge: "VoxelBridge") -> list[dict] | None:
    """Handle tools that require the WebSocket bridge. Returns None if not matched."""

    if name == "set_mood":
        await bridge.send_command({"type": "set_mood", "mood": arguments["mood"]})
        return [{"type": "text", "text": f"Mood set to {arguments['mood']}"}]

    if name == "set_style":
        await bridge.send_command({"type": "set_style", "style": arguments["style"]})
        return [{"type": "text", "text": f"Style set to {arguments['style']}"}]

    if name == "set_character":
        await bridge.send_command({
            "type": "set_setting",
            "section": "character",
            "key": "default",
            "value": arguments["character"],
        })
        return [{"type": "text", "text": f"Character set to {arguments['character']}"}]

    if name == "speak_text":
        await bridge.send_command({
            "type": "text_input",
            "text": f"[SPEAK]{arguments['text']}",
        })
        return [{"type": "text", "text": f"Speaking: {arguments['text']}"}]

    if name == "send_chat_message":
        await bridge.send_command({"type": "text_input", "text": arguments["text"]})
        return [{"type": "text", "text": f"Message sent: {arguments['text']}"}]

    if name == "show_reaction":
        await bridge.send_command({"type": "reaction", "emoji": arguments["emoji"]})
        return [{"type": "text", "text": f"Showing {arguments['emoji']}"}]

    if name == "set_led":
        await bridge.send_command({
            "type": "set_setting",
            "section": "led",
            "key": "color",
            "value": [arguments["r"], arguments["g"], arguments["b"]],
        })
        return [{"type": "text", "text": f"LED set to ({arguments['r']}, {arguments['g']}, {arguments['b']})"}]

    if name == "set_volume":
        await bridge.send_command({
            "type": "set_setting",
            "section": "audio",
            "key": "volume",
            "value": arguments["volume"],
        })
        return [{"type": "text", "text": f"Volume set to {arguments['volume']}%"}]

    if name == "get_conversation_history":
        await bridge.send_command({"type": "get_chat_history"})
        await asyncio.sleep(0.5)
        history = bridge.history
        return [{"type": "text", "text": json.dumps(history, indent=2)}]

    if name == "set_agent":
        await bridge.send_command({"type": "set_agent", "agent": arguments["agent"]})
        return [{"type": "text", "text": f"Agent switched to {arguments['agent']}"}]

    return None  # not a WS tool


async def _handle_system_tool(name: str, arguments: dict, bridge: "VoxelBridge") -> list[dict]:
    """Handle tools that use direct system calls (no WS bridge needed)."""

    # --- Device management handlers (direct system calls, no WS bridge) ---

    if name == "get_system_stats":
        try:
            from display.system_stats import get_system_stats
            stats = get_system_stats()
            return [{"type": "text", "text": json.dumps(stats, indent=2)}]
        except ImportError:
            return [{"type": "text", "text": "System stats module not available"}]

    if name == "reboot_device":
        if not arguments.get("confirm"):
            return [{"type": "text", "text": "Reboot cancelled — confirm must be true"}]
        import subprocess
        import sys
        if sys.platform == "linux":
            subprocess.Popen(["sudo", "reboot"])
            return [{"type": "text", "text": "Rebooting device..."}]
        return [{"type": "text", "text": "Reboot only available on Pi (Linux)"}]

    if name == "restart_services":
        import subprocess
        import sys
        if sys.platform != "linux":
            return [{"type": "text", "text": "Service restart only available on Pi"}]
        svc = arguments.get("service", "all")
        services = []
        if svc in ("all", "display"):
            services.append("voxel-display")
        if svc in ("all", "backend"):
            services.append("voxel")
        try:
            for s in services:
                subprocess.run(["sudo", "systemctl", "restart", s], capture_output=True, timeout=15)
            return [{"type": "text", "text": f"Restarted: {', '.join(services)}"}]
        except Exception as e:
            return [{"type": "text", "text": f"Restart failed: {e}"}]

    if name == "get_logs":
        import subprocess
        import sys
        if sys.platform != "linux":
            return [{"type": "text", "text": "Logs only available on Pi"}]
        svc = arguments.get("service", "all")
        lines = min(arguments.get("lines", 50), 200)
        units = []
        if svc in ("all", "display"):
            units.extend(["-u", "voxel-display"])
        if svc in ("all", "backend"):
            units.extend(["-u", "voxel"])
        try:
            result = subprocess.run(
                ["journalctl"] + units + ["--no-pager", "-n", str(lines), "--output", "short-iso"],
                capture_output=True, text=True, timeout=10,
            )
            return [{"type": "text", "text": result.stdout or "(no logs)"}]
        except Exception as e:
            return [{"type": "text", "text": f"Failed to get logs: {e}"}]

    if name == "run_diagnostic":
        import subprocess
        import sys
        try:
            result = subprocess.run(
                [sys.executable, "-m", "cli", "doctor"],
                capture_output=True, text=True, timeout=30,
                cwd=str(Path(__file__).parent.parent),
            )
            output = result.stdout + result.stderr
            return [{"type": "text", "text": output or "(no output)"}]
        except Exception as e:
            return [{"type": "text", "text": f"Diagnostic failed: {e}"}]

    if name == "check_update":
        import subprocess
        try:
            subprocess.run(
                ["git", "fetch", "--dry-run"],
                capture_output=True, text=True, timeout=15,
                cwd=str(Path(__file__).parent.parent),
            )
            result2 = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..@{upstream}"],
                capture_output=True, text=True, timeout=10,
                cwd=str(Path(__file__).parent.parent),
            )
            behind = int(result2.stdout.strip()) if result2.stdout.strip() else 0
            if behind > 0:
                return [{"type": "text", "text": f"Update available: {behind} commit(s) behind remote"}]
            return [{"type": "text", "text": "Up to date"}]
        except Exception as e:
            return [{"type": "text", "text": f"Update check failed: {e}"}]

    if name == "install_update":
        if not arguments.get("confirm"):
            return [{"type": "text", "text": "Update cancelled — confirm must be true"}]
        import subprocess
        import sys
        try:
            cwd = str(Path(__file__).parent.parent)
            subprocess.run(["git", "pull"], capture_output=True, timeout=30, cwd=cwd)
            subprocess.run([sys.executable, "-m", "uv", "sync"], capture_output=True, timeout=60, cwd=cwd)
            return [{"type": "text", "text": "Update installed. Restart services to apply."}]
        except Exception as e:
            return [{"type": "text", "text": f"Update failed: {e}"}]

    if name == "set_config":
        key = arguments.get("key", "")
        value = arguments.get("value")
        if not key:
            return [{"type": "text", "text": "Error: key is required"}]
        import subprocess
        import sys
        try:
            result = subprocess.run(
                [sys.executable, "-m", "cli", "config", "set", key, str(value)],
                capture_output=True, text=True, timeout=10,
                cwd=str(Path(__file__).parent.parent),
            )
            return [{"type": "text", "text": result.stdout.strip() or f"Config set: {key} = {value}"}]
        except Exception as e:
            return [{"type": "text", "text": f"Config set failed: {e}"}]

    if name == "connect_wifi":
        import subprocess
        import sys
        if sys.platform != "linux":
            return [{"type": "text", "text": "WiFi control only available on Pi"}]
        ssid = arguments["ssid"]
        password = arguments["password"]
        try:
            result = subprocess.run(
                ["nmcli", "device", "wifi", "connect", ssid, "password", password],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return [{"type": "text", "text": f"Connected to {ssid}"}]
            return [{"type": "text", "text": f"Failed: {result.stderr.strip()}"}]
        except Exception as e:
            return [{"type": "text", "text": f"WiFi connect failed: {e}"}]

    log.warning("Unknown tool requested: %s", name)
    return [{"type": "text", "text": f"Unknown tool: {name}"}]


# ---------------------------------------------------------------------------
# Resource handler
# ---------------------------------------------------------------------------


async def handle_resource(uri: str, bridge: "VoxelBridge") -> list[dict]:
    """Read a resource and return MCP content blocks."""

    if uri == "voxel://state":
        state = dict(await bridge.get_state())
        return [{"type": "text", "text": json.dumps(state, indent=2)}]

    if uri == "voxel://config":
        try:
            from config.settings import load_settings
            cfg = load_settings()
            # Strip sensitive keys before exposing
            sanitized = {k: v for k, v in cfg.items() if k not in ("gateway",)}
            return [{"type": "text", "text": json.dumps(sanitized, indent=2)}]
        except Exception as exc:
            return [{"type": "text", "text": json.dumps({"error": str(exc)})}]

    if uri == "voxel://history":
        await bridge.send_command({"type": "get_chat_history"})
        await asyncio.sleep(0.5)
        return [{"type": "text", "text": json.dumps(bridge.history, indent=2)}]

    return [{"type": "text", "text": json.dumps({"error": f"Unknown resource: {uri}"})}]
