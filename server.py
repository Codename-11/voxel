"""Voxel backend server — WebSocket bridge between hardware/AI and the React UI."""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

import websockets
from websockets.server import serve

from core.log import setup as setup_logging, boot_message, ready_message, shutdown_message
from states.machine import StateMachine, State
from shared import load_moods

setup_logging(level=logging.INFO)
log = logging.getLogger("voxel.server")

# ── State ────────────────────────────────────────────────────────────────────

moods_config = load_moods()
STATE_MOOD_MAP: dict[str, str] = moods_config.get("state_map", {})
LED_MAP: dict = moods_config.get("led_map", {})

sm = StateMachine()

# Current UI state pushed to frontend
_ui_state = {
    "mood": "neutral",
    "style": "kawaii",
    "speaking": False,
    "amplitude": 0.0,
    "battery": 100,
    "state": "IDLE",
    "agent": "daemon",
    "connected": False,
}

_clients: set[websockets.WebSocketServerProtocol] = set()


# ── Broadcasting ─────────────────────────────────────────────────────────────

async def broadcast(data: dict) -> None:
    """Send state update to all connected frontends."""
    if not _clients:
        return
    msg = json.dumps(data)
    await asyncio.gather(
        *(client.send(msg) for client in _clients),
        return_exceptions=True,
    )


async def push_state() -> None:
    """Push full UI state to all clients."""
    await broadcast({"type": "state", **_ui_state})


def set_mood(mood: str) -> None:
    """Update mood and schedule broadcast."""
    _ui_state["mood"] = mood
    log.info(f"Mood: {mood}")
    asyncio.get_event_loop().create_task(push_state())


def on_state_change(old: State, new: State) -> None:
    """Handle state machine transitions."""
    mood = STATE_MOOD_MAP.get(new.name, "neutral")
    _ui_state["state"] = new.name
    _ui_state["mood"] = mood
    log.info(f"State: {old.name} → {new.name} (mood: {mood})")
    try:
        asyncio.get_event_loop().create_task(push_state())
    except RuntimeError:
        pass  # Event loop not running yet


sm.on_change(on_state_change)


# ── WebSocket handler ────────────────────────────────────────────────────────

async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
    """Handle a single WebSocket client connection."""
    _clients.add(websocket)
    log.info(f"Client connected ({len(_clients)} total)")

    # Send current state immediately
    try:
        await websocket.send(json.dumps({"type": "state", **_ui_state}))

        async for message in websocket:
            try:
                data = json.loads(message)
                await handle_message(data)
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON from client: {message}")
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(websocket)
        log.info(f"Client disconnected ({len(_clients)} total)")


async def handle_message(data: dict) -> None:
    """Handle incoming messages from the frontend."""
    msg_type = data.get("type", "")

    if msg_type == "set_mood":
        set_mood(data.get("mood", "neutral"))

    elif msg_type == "set_style":
        _ui_state["style"] = data.get("style", "kawaii")
        await push_state()

    elif msg_type == "cycle_state":
        # Cycle through states for testing
        cycle = [State.IDLE, State.LISTENING, State.THINKING, State.SPEAKING]
        cur_idx = next((i for i, s in enumerate(cycle) if s == sm.state), 0)
        nxt = cycle[(cur_idx + 1) % len(cycle)]
        sm.transition(nxt)

    elif msg_type == "button":
        button = data.get("button", "")
        log.info(f"Button: {button}")
        if button == "press":
            sm.to_listening()
        elif button == "release":
            sm.to_thinking()
        elif button == "menu":
            sm.to_menu() if sm.state != State.MENU else sm.to_idle()

    elif msg_type == "ping":
        await broadcast({"type": "pong"})


# ── Hardware polling (placeholder — wired when on Pi) ────────────────────────

async def hardware_loop() -> None:
    """Poll hardware inputs and push state changes. Placeholder for desktop."""
    from hardware.platform import IS_PI

    if IS_PI:
        from hardware import buttons, led, battery
        buttons.init()
        led.init()
        battery.init()

        while True:
            # Poll buttons
            btn_events = buttons.poll()
            for evt in btn_events:
                from hardware.buttons import ButtonEvent
                if evt == ButtonEvent.BUTTON_PRESS:
                    sm.to_listening()
                elif evt == ButtonEvent.BUTTON_MENU:
                    sm.to_menu() if sm.state != State.MENU else sm.to_idle()

            # Battery level
            batt = battery.get_level()
            if batt != _ui_state["battery"]:
                _ui_state["battery"] = batt
                if batt <= 5:
                    set_mood("critical_battery")
                elif batt <= 20:
                    set_mood("low_battery")
                await push_state()

            await asyncio.sleep(0.05)  # 20Hz polling
    else:
        # Desktop — no hardware to poll, just keep alive
        while True:
            await asyncio.sleep(1)


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    boot_message()

    host = "0.0.0.0"
    port = 8080

    async with serve(handler, host, port):
        log.info(f"WebSocket server: ws://{host}:{port}")
        ready_message()
        log.info("Frontend: open app/index.html or run 'npm run dev' in app/")

        await hardware_loop()


def shutdown(signum, frame) -> None:
    shutdown_message()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        shutdown_message()
