"""Voxel backend server — WebSocket bridge between hardware/AI and the React UI."""

import asyncio
import json
import logging
import signal
import sys
import time

import websockets
from websockets.server import serve

from config.settings import load_settings, save_local_settings
from core.log import setup as setup_logging, boot_message, ready_message, shutdown_message
from states.machine import StateMachine, State
from shared import load_moods

setup_logging(level=logging.INFO)
log = logging.getLogger("voxel.server")

# ── State ────────────────────────────────────────────────────────────────────

moods_config = load_moods()
STATE_MOOD_MAP: dict[str, str] = moods_config.get("state_map", {})
LED_MAP: dict = moods_config.get("led_map", {})
settings = load_settings()


def _setting(path: str, default=None):
    current = settings
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _clamp_percent(value: int | float) -> int:
    return max(0, min(100, int(value)))


def _agent_ids() -> set[str]:
    return {agent.get("id", "") for agent in settings.get("agents", [])}


sm = StateMachine()

# Current UI state pushed to frontend
_ui_state = {
    "mood": "neutral",
    "style": "kawaii",
    "speaking": False,
    "amplitude": 0.0,
    "battery": 100,
    "state": "IDLE",
    "agent": _setting("gateway.default_agent", "daemon"),
    "connected": False,
    "brightness": _clamp_percent(_setting("display.brightness", 80)),
    "volume": _clamp_percent(_setting("audio.volume", 80)),
    "displayMode": _setting("display.mode", "auto"),
    "inputMode": _setting("input.mode", "auto"),
    "agents": settings.get("agents", []),
}

_clients: set[websockets.WebSocketServerProtocol] = set()

# ── Conversation pipeline state ──────────────────────────────────────────────

_pipeline_task: asyncio.Task | None = None
_release_event: asyncio.Event = asyncio.Event()
_cancel_event: asyncio.Event = asyncio.Event()
_chat_history: list[dict] = []
_oclient = None  # OpenClawClient, initialized at startup
_audio_initialized = False

CHAT_LIMIT = int(_setting("pipeline.chat_history_limit", 50))
ERROR_SECONDS = int(_setting("pipeline.error_display_seconds", 3))
MIN_RECORDING_BYTES = int(_setting("pipeline.min_recording_bytes", 1000))


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


async def send_to(ws: websockets.WebSocketServerProtocol, data: dict) -> None:
    """Send to a specific client."""
    try:
        await ws.send(json.dumps(data))
    except Exception:
        pass


async def push_state() -> None:
    """Push full UI state to all clients."""
    await broadcast({"type": "state", **_ui_state})


async def emit_button(button: str) -> None:
    """Broadcast a button event to connected frontends."""
    await broadcast({"type": "button", "button": button})


async def emit_transcript(role: str, text: str, status: str = "done") -> None:
    """Broadcast a transcript update to all clients."""
    await broadcast({
        "type": "transcript",
        "role": role,
        "text": text,
        "status": status,
        "timestamp": time.time(),
    })


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


def apply_runtime_settings() -> None:
    """Apply mutable runtime settings to hardware abstractions when available."""
    try:
        from hardware import display
        display.set_brightness(_ui_state["brightness"] / 100)
    except Exception as exc:
        log.debug(f"Brightness apply skipped: {exc}")


def persist_settings(update: dict) -> None:
    """Persist selected mutable settings to config/local.yaml."""
    global settings
    settings = save_local_settings(update)
    _ui_state["brightness"] = _clamp_percent(_setting("display.brightness", _ui_state["brightness"]))
    _ui_state["volume"] = _clamp_percent(_setting("audio.volume", _ui_state["volume"]))
    _ui_state["agent"] = _setting("gateway.default_agent", _ui_state["agent"])
    _ui_state["displayMode"] = _setting("display.mode", _ui_state["displayMode"])
    _ui_state["inputMode"] = _setting("input.mode", _ui_state["inputMode"])
    _ui_state["agents"] = settings.get("agents", [])
    apply_runtime_settings()


# ── Conversation pipeline ────────────────────────────────────────────────────

def _append_chat(role: str, text: str) -> None:
    """Append a message to chat history (capped)."""
    _chat_history.append({
        "role": role,
        "text": text,
        "timestamp": time.time(),
        "agent": _ui_state["agent"] if role == "assistant" else None,
    })
    if len(_chat_history) > CHAT_LIMIT:
        _chat_history.pop(0)


def _resolve_voice() -> str:
    """Get the TTS voice for the current agent."""
    agent_id = _ui_state["agent"]
    for agent in settings.get("agents", []):
        if agent.get("id") == agent_id:
            return agent.get("voice", "")
    return ""


def _init_gateway() -> None:
    """Initialize the OpenClaw client from settings."""
    global _oclient
    url = _setting("gateway.url", "")
    token = _setting("gateway.token", "")
    if url and token:
        from core.gateway import OpenClawClient
        _oclient = OpenClawClient(url, token, _ui_state["agent"])
        log.info(f"Gateway client: {url}")
    else:
        log.warning("Gateway not configured (missing url or token in config)")


def _init_audio() -> None:
    """Initialize audio subsystem once."""
    global _audio_initialized
    if not _audio_initialized:
        try:
            from core.audio import init
            init()
            _audio_initialized = True
        except Exception as e:
            log.warning(f"Audio init failed: {e}")


async def _pipeline_error(msg: str) -> None:
    """Transition to ERROR, broadcast, recover to IDLE after delay."""
    log.error(f"Pipeline error: {msg}")
    sm.to_error(msg)
    await emit_transcript("system", msg, status="error")
    await asyncio.sleep(ERROR_SECONDS)
    sm.to_idle()


async def run_voice_pipeline() -> None:
    """Full voice conversation: record → STT → OpenClaw → TTS → playback.

    Runs as a detached asyncio.Task. Cancellable via _cancel_event.
    """
    from core import audio, stt, tts

    _init_audio()
    _cancel_event.clear()
    _release_event.clear()

    try:
        # ── LISTENING: record mic ────────────────────────────────
        audio.start_recording()

        # Wait for button release (or cancellation / timeout)
        max_secs = int(_setting("pipeline.max_recording_seconds", 30))
        try:
            await asyncio.wait_for(_release_event.wait(), timeout=max_secs)
        except asyncio.TimeoutError:
            log.warning("Max recording time reached")

        wav_bytes = await asyncio.to_thread(audio.stop_recording)

        if _cancel_event.is_set():
            sm.to_idle()
            return

        if len(wav_bytes) < MIN_RECORDING_BYTES:
            await _pipeline_error("Too short — try again")
            return

        # ── THINKING: transcribe ─────────────────────────────────
        sm.to_thinking()
        await emit_transcript("user", "…", status="transcribing")

        whisper_cfg = settings.get("stt", {}).get("whisper", {})
        user_text = await stt.transcribe(
            wav_bytes,
            api_key=whisper_cfg.get("api_key", ""),
            model=whisper_cfg.get("model", "whisper-1"),
            language=whisper_cfg.get("language", "en"),
        )

        if _cancel_event.is_set():
            sm.to_idle()
            return

        if not user_text:
            await _pipeline_error("Couldn't hear that")
            return

        await emit_transcript("user", user_text, status="done")
        _append_chat("user", user_text)

        # ── THINKING: send to OpenClaw ───────────────────────────
        await emit_transcript("assistant", "…", status="thinking")

        if _oclient is None:
            await _pipeline_error("Gateway not configured")
            return

        # Ensure gateway is using current agent
        _oclient.set_agent(_ui_state["agent"])

        response_text = await asyncio.to_thread(_oclient.send_message, user_text)

        if _cancel_event.is_set():
            sm.to_idle()
            return

        if not response_text:
            await _pipeline_error("No response from agent")
            return

        await emit_transcript("assistant", response_text, status="done")
        _append_chat("assistant", response_text)

        # ── SPEAKING: synthesize and play ────────────────────────
        sm.to_speaking()
        _ui_state["speaking"] = True
        await push_state()

        provider = _setting("audio.tts_provider", "edge")
        voice = _resolve_voice()

        audio_data = await tts.synthesize(
            response_text,
            voice=voice,
            provider=provider,
            settings=settings,
        )

        if _cancel_event.is_set():
            _ui_state["speaking"] = False
            sm.to_idle()
            return

        if audio_data:
            audio.play_audio(audio_data)

            # Amplitude broadcast loop — 20Hz
            while audio.is_playing() and not _cancel_event.is_set():
                _ui_state["amplitude"] = audio.get_amplitude()
                await push_state()
                await asyncio.sleep(0.05)

            if _cancel_event.is_set():
                audio.stop_playback()
        else:
            # TTS failed — show text for a few seconds
            log.warning("TTS returned no audio, showing text only")
            await asyncio.sleep(3)

        # ── Done ─────────────────────────────────────────────────
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()

    except asyncio.CancelledError:
        log.info("Pipeline cancelled")
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        try:
            from core.audio import stop_recording, stop_playback
            stop_recording()
            stop_playback()
        except Exception:
            pass
        sm.to_idle()
    except Exception as e:
        log.exception("Pipeline unhandled error")
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        await _pipeline_error(str(e)[:60])


async def run_text_pipeline(text: str) -> None:
    """Text-input conversation: skip recording/STT, go straight to gateway.

    Used for remote browser text input fallback.
    """
    from core import audio, tts

    _init_audio()
    _cancel_event.clear()

    try:
        # ── THINKING ─────────────────────────────────────────────
        sm.to_thinking()
        await emit_transcript("user", text, status="done")
        _append_chat("user", text)

        await emit_transcript("assistant", "…", status="thinking")

        if _oclient is None:
            await _pipeline_error("Gateway not configured")
            return

        _oclient.set_agent(_ui_state["agent"])
        response_text = await asyncio.to_thread(_oclient.send_message, text)

        if _cancel_event.is_set():
            sm.to_idle()
            return

        if not response_text:
            await _pipeline_error("No response from agent")
            return

        await emit_transcript("assistant", response_text, status="done")
        _append_chat("assistant", response_text)

        # ── SPEAKING ─────────────────────────────────────────────
        sm.to_speaking()
        _ui_state["speaking"] = True
        await push_state()

        provider = _setting("audio.tts_provider", "edge")
        voice = _resolve_voice()

        audio_data = await tts.synthesize(
            response_text,
            voice=voice,
            provider=provider,
            settings=settings,
        )

        if _cancel_event.is_set():
            _ui_state["speaking"] = False
            sm.to_idle()
            return

        if audio_data:
            audio.play_audio(audio_data)

            while audio.is_playing() and not _cancel_event.is_set():
                _ui_state["amplitude"] = audio.get_amplitude()
                await push_state()
                await asyncio.sleep(0.05)

            if _cancel_event.is_set():
                audio.stop_playback()
        else:
            await asyncio.sleep(3)

        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()

    except asyncio.CancelledError:
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()
    except Exception as e:
        log.exception("Text pipeline error")
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        await _pipeline_error(str(e)[:60])


def _cancel_pipeline() -> None:
    """Cancel any running pipeline."""
    global _pipeline_task
    if _pipeline_task and not _pipeline_task.done():
        _cancel_event.set()
        _pipeline_task.cancel()
        _pipeline_task = None


# ── WebSocket handler ────────────────────────────────────────────────────────

async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
    """Handle a single WebSocket client connection."""
    _clients.add(websocket)
    log.info(f"Client connected ({len(_clients)} total)")

    # Send current state + chat history immediately
    try:
        await websocket.send(json.dumps({"type": "state", **_ui_state}))
        if _chat_history:
            await send_to(websocket, {"type": "chat_history", "messages": _chat_history})

        async for message in websocket:
            try:
                data = json.loads(message)
                await handle_message(data, websocket)
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON from client: {message}")
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(websocket)
        log.info(f"Client disconnected ({len(_clients)} total)")


async def handle_message(data: dict, ws: websockets.WebSocketServerProtocol) -> None:
    """Handle incoming messages from the frontend."""
    global _pipeline_task
    msg_type = data.get("type", "")

    if msg_type == "set_mood":
        set_mood(data.get("mood", "neutral"))

    elif msg_type == "set_style":
        _ui_state["style"] = data.get("style", "kawaii")
        await push_state()

    elif msg_type == "set_state":
        state_name = str(data.get("state", "IDLE")).upper()
        try:
            sm.transition(State[state_name])
        except KeyError:
            log.warning(f"Unknown state requested: {state_name}")

    elif msg_type == "cycle_state":
        cycle = [State.IDLE, State.LISTENING, State.THINKING, State.SPEAKING]
        cur_idx = next((i for i, s in enumerate(cycle) if s == sm.state), 0)
        nxt = cycle[(cur_idx + 1) % len(cycle)]
        sm.transition(nxt)

    elif msg_type == "set_agent":
        agent_id = data.get("agent", "")
        if agent_id not in _agent_ids():
            log.warning(f"Unknown agent requested: {agent_id}")
            return
        _ui_state["agent"] = agent_id
        persist_settings({"gateway": {"default_agent": agent_id}})
        await push_state()

    elif msg_type == "set_setting":
        section = data.get("section", "")
        key = data.get("key", "")
        value = data.get("value")
        if section == "display" and key == "brightness":
            persist_settings({"display": {"brightness": _clamp_percent(value)}})
            await push_state()
        elif section == "audio" and key == "volume":
            persist_settings({"audio": {"volume": _clamp_percent(value)}})
            await push_state()
        else:
            log.warning(f"Unsupported setting update: {section}.{key}")

    elif msg_type == "button":
        button = data.get("button", "")
        log.info(f"Button: {button}")

        if button.startswith("agent:"):
            agent_id = button.split(":", 1)[1]
            if agent_id in _agent_ids():
                _ui_state["agent"] = agent_id
                persist_settings({"gateway": {"default_agent": agent_id}})
                await push_state()

        elif button == "press":
            if sm.state == State.SPEAKING:
                # Cancel current conversation
                _cancel_pipeline()
                sm.to_idle()
            elif sm.state == State.IDLE:
                sm.to_listening()
                _pipeline_task = asyncio.create_task(run_voice_pipeline())

        elif button == "release":
            if sm.state == State.LISTENING:
                sm.to_thinking()
                _release_event.set()

        elif button == "menu":
            sm.to_menu() if sm.state != State.MENU else sm.to_idle()

        elif button in {"left", "right"}:
            await emit_button(button)

    elif msg_type == "text_input":
        text = data.get("text", "").strip()
        if text and sm.state == State.IDLE:
            _pipeline_task = asyncio.create_task(run_text_pipeline(text))

    elif msg_type == "get_chat_history":
        await send_to(ws, {"type": "chat_history", "messages": _chat_history})

    elif msg_type == "ping":
        await broadcast({"type": "pong"})


# ── Hardware polling ─────────────────────────────────────────────────────────

async def hardware_loop() -> None:
    """Poll hardware inputs and push state changes."""
    from hardware.platform import IS_PI

    if IS_PI:
        from hardware import buttons, led, battery
        buttons.init()
        led.init()
        battery.init()

        while True:
            btn_events = buttons.poll()
            for evt in btn_events:
                from hardware.buttons import ButtonEvent
                if evt == ButtonEvent.BUTTON_PRESS:
                    await emit_button("press")
                    # Trigger pipeline via the same path as WebSocket button
                    await handle_message({"type": "button", "button": "press"}, None)
                elif evt == ButtonEvent.BUTTON_RELEASE:
                    await emit_button("release")
                    await handle_message({"type": "button", "button": "release"}, None)
                elif evt == ButtonEvent.BUTTON_LEFT:
                    await emit_button("left")
                elif evt == ButtonEvent.BUTTON_RIGHT:
                    await emit_button("right")
                elif evt == ButtonEvent.BUTTON_MENU:
                    await emit_button("menu")
                    sm.to_menu() if sm.state != State.MENU else sm.to_idle()

            # Battery level
            batt = battery.get_level()
            if batt >= 0 and batt != _ui_state["battery"]:
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
    apply_runtime_settings()
    _init_gateway()

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
