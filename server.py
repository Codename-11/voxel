"""Voxel backend server — WebSocket bridge between hardware/AI and the React UI."""

import asyncio
import json
import logging
import signal
import sys
import time
import os as _os

import websockets
from websockets.asyncio.server import serve, ServerConnection

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

_clients: set[ServerConnection] = set()

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


async def send_to(ws: ServerConnection, data: dict) -> None:
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


async def emit_reaction(emoji: str) -> None:
    """Broadcast an emoji reaction to display clients."""
    await broadcast({"type": "reaction", "emoji": emoji})


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
        loop = asyncio.get_event_loop()
        loop.create_task(push_state())
        loop.create_task(_webhook_event(
            "state_change",
            f"State: {old.name} → {new.name}",
            {"old": old.name, "new": new.name, "mood": mood},
        ))
    except RuntimeError:
        pass  # Event loop not running yet


sm.on_change(on_state_change)


def apply_runtime_settings() -> None:
    """Apply mutable runtime settings to hardware abstractions when available.

    On Pi, brightness is controlled by the display service via the WhisPlay
    driver. The server just stores the value; the display service reads it
    from config and applies it directly.
    """
    log.debug("Runtime settings applied (brightness=%d, volume=%d)",
              _ui_state["brightness"], _ui_state["volume"])


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
        # System context tells the agent how to format responses
        # (mood tags, conciseness, emoji prefixes)
        system_context = ""
        if _setting("character.system_context_enabled", True):
            system_context = _setting("character.system_context", "")
        _oclient = OpenClawClient(url, token, _ui_state["agent"],
                                  system_context=system_context)
        log.info(f"Gateway client: {url} (system_context={'yes' if system_context else 'no'})")
    else:
        log.warning("Gateway not configured (missing url or token in config)")


_webhook = None  # WebhookClient, initialized at startup


def _init_webhook() -> None:
    """Initialize the outbound webhook client from settings."""
    global _webhook
    wh_cfg = settings.get("webhook", {})
    if wh_cfg.get("enabled") and wh_cfg.get("url"):
        from core.webhook import WebhookClient
        _webhook = WebhookClient(
            url=wh_cfg["url"],
            token=wh_cfg.get("token", ""),
            enabled_events=wh_cfg.get("events"),
            debounce_seconds=wh_cfg.get("debounce_seconds", 5),
        )
        log.info("Webhook client: %s", wh_cfg["url"])


async def _webhook_event(event_type: str, message: str, data: dict | None = None) -> None:
    """Send a webhook event if the client is configured."""
    if _webhook:
        session_key = f"agent:{_ui_state['agent']}:companion"
        await _webhook.send(event_type, message, data, session_key)


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


async def _stream_to_display(text: str, history: list[dict] | None = None,
                             device_state: dict | None = None) -> tuple[str, list]:
    """Stream gateway response to the display, return final text and tool calls.

    Uses an asyncio.Queue to bridge the synchronous streaming generator
    (running in a thread) with the async event loop so we can emit partial
    transcript updates to the display as chunks arrive.
    """
    try:
        from core.gateway import TextChunk, ToolCallStart, ToolCallDone, StreamDone
    except ImportError:
        result = _oclient.send_message(text, history=history, device_state=device_state) or ""
        return result, []

    queue: asyncio.Queue = asyncio.Queue()

    def _run() -> None:
        """Run the streaming generator in a thread, pushing events to the queue."""
        try:
            for event in _oclient.send_message_stream(text, history=history, device_state=device_state):
                queue.put_nowait(event)
        except Exception as e:
            log.warning("Stream thread error: %s", e)
        finally:
            queue.put_nowait(None)  # sentinel

    # Start the streaming thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run)

    full_text = ""
    tool_calls: list[dict] = []

    # Consume events from the queue, emitting partial updates
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=130)  # slightly over gateway 120s timeout
        except asyncio.TimeoutError:
            log.warning("Stream timeout — no events received")
            break
        if event is None:
            break  # stream finished
        if isinstance(event, TextChunk):
            full_text += event.text
            # Emit partial transcript so the display updates progressively
            await emit_transcript("assistant", full_text, status="partial")
        elif isinstance(event, ToolCallStart):
            await broadcast({
                "type": "tool_call", "id": event.id,
                "name": event.name, "status": "running",
            })
        elif isinstance(event, ToolCallDone):
            tool_calls.append({
                "id": event.id, "name": event.name,
                "arguments": event.arguments,
            })
            await broadcast({
                "type": "tool_call", "id": event.id,
                "name": event.name, "status": "done",
            })
        elif isinstance(event, StreamDone):
            full_text = event.full_text
            tool_calls = [
                {"id": tc.get("id", ""), "name": tc.get("name", ""),
                 "arguments": tc.get("arguments", "")}
                for tc in (event.tool_calls or [])
            ]

    return full_text, tool_calls


async def run_voice_pipeline() -> None:
    """Full voice conversation: record → STT → OpenClaw → TTS → playback.

    Runs as a detached asyncio.Task. Cancellable via _cancel_event.
    """
    from core import audio, stt, tts

    _init_audio()
    _cancel_event.clear()
    _release_event.clear()

    pipeline_start = time.perf_counter()
    log.info("Voice pipeline: started")

    try:
        # ── LISTENING: record mic ────────────────────────────────
        log.info("Voice pipeline: LISTENING — recording from mic")
        t_record_start = time.perf_counter()
        audio.start_recording()

        # Wait for button release (or cancellation / timeout)
        max_secs = int(_setting("pipeline.max_recording_seconds", 30))
        try:
            await asyncio.wait_for(_release_event.wait(), timeout=max_secs)
        except asyncio.TimeoutError:
            log.warning("Voice pipeline: max recording time reached (%ds)", max_secs)

        wav_bytes = await asyncio.to_thread(audio.stop_recording)
        t_record_ms = (time.perf_counter() - t_record_start) * 1000
        log.info("Voice pipeline: recording complete — %d bytes in %.0fms", len(wav_bytes), t_record_ms)

        if _cancel_event.is_set():
            log.info("Voice pipeline: cancelled during recording")
            sm.to_idle()
            return

        if len(wav_bytes) < MIN_RECORDING_BYTES:
            log.warning("Voice pipeline: recording too short (%d bytes < %d min)",
                        len(wav_bytes), MIN_RECORDING_BYTES)
            await _pipeline_error("Too short — try again")
            return

        # ── THINKING: transcribe ─────────────────────────────────
        log.info("Voice pipeline: THINKING — transcribing with STT")
        sm.to_thinking()
        await emit_transcript("user", "…", status="transcribing")

        t_stt_start = time.perf_counter()
        whisper_cfg = settings.get("stt", {}).get("whisper", {})
        user_text = await stt.transcribe(
            wav_bytes,
            api_key=whisper_cfg.get("api_key", ""),
            model=whisper_cfg.get("model", "whisper-1"),
            language=whisper_cfg.get("language", "en"),
        )
        t_stt_ms = (time.perf_counter() - t_stt_start) * 1000
        log.info("Voice pipeline: STT completed in %.0fms — %s",
                 t_stt_ms, f"'{user_text[:60]}'" if user_text else "empty")

        if _cancel_event.is_set():
            log.info("Voice pipeline: cancelled after STT")
            sm.to_idle()
            return

        if not user_text:
            await _pipeline_error("Couldn't hear that")
            return

        await emit_transcript("user", user_text, status="done")
        _append_chat("user", user_text)
        log.info("Voice pipeline: user said: '%s'", user_text)

        # ── THINKING: send to OpenClaw ───────────────────────────
        log.info("Voice pipeline: THINKING — sending to gateway (agent=%s)", _ui_state["agent"])
        await emit_transcript("assistant", "…", status="thinking")

        if _oclient is None:
            await _pipeline_error("Gateway not configured")
            return

        # Ensure gateway is using current agent
        _oclient.set_agent(_ui_state["agent"])

        # Try streaming (emits partial transcripts), fall back to blocking
        t_gw_start = time.perf_counter()
        try:
            response_text, tool_calls = await _stream_to_display(
                user_text, history=list(_chat_history), device_state=dict(_ui_state))
        except Exception as e:
            log.warning("Voice pipeline: streaming failed, falling back to non-streaming: %s", e)
            response_text = await asyncio.to_thread(
                _oclient.send_message, user_text, list(_chat_history), dict(_ui_state)) or ""
            tool_calls = []
        t_gw_ms = (time.perf_counter() - t_gw_start) * 1000
        log.info("Voice pipeline: gateway responded in %.0fms — %d chars, %d tool calls",
                 t_gw_ms, len(response_text), len(tool_calls))
        if response_text:
            log.info("Voice pipeline: agent replied: '%s'", response_text[:200])

        if _cancel_event.is_set():
            log.info("Voice pipeline: cancelled after gateway response")
            sm.to_idle()
            return

        if not response_text:
            await _pipeline_error("No response from agent")
            return

        # Extract mood hint from response
        try:
            from core.mood_parser import extract_mood
            mood, response_text = extract_mood(response_text)
            if mood:
                log.debug("Voice pipeline: extracted mood hint: %s", mood)
                set_mood(mood)
        except ImportError:
            pass

        # Extract emoji reaction (before sending to TTS)
        try:
            from display.emoji_reactions import parse_reaction
            emoji, response_text = parse_reaction(response_text)
            if emoji:
                log.debug("Voice pipeline: extracted emoji reaction: %s", emoji)
                await emit_reaction(emoji)
        except ImportError:
            pass

        await emit_transcript("assistant", response_text, status="done")
        _append_chat("assistant", response_text)

        # ── SPEAKING: synthesize and play ────────────────────────
        log.info("Voice pipeline: SPEAKING — synthesizing TTS")
        sm.to_speaking()
        _ui_state["speaking"] = True
        _ui_state["amplitude"] = 0.0  # clear residual amplitude
        await push_state()

        provider = _setting("audio.tts_provider", "edge")
        voice = _resolve_voice()
        log.debug("Voice pipeline: TTS provider=%s, voice=%s", provider, voice or "(default)")

        t_tts_start = time.perf_counter()
        audio_data = await tts.synthesize(
            response_text,
            voice=voice,
            provider=provider,
            settings=settings,
        )
        t_tts_ms = (time.perf_counter() - t_tts_start) * 1000
        log.info("Voice pipeline: TTS completed in %.0fms — %s",
                 t_tts_ms, f"{len(audio_data)} bytes" if audio_data else "no audio")

        if _cancel_event.is_set():
            log.info("Voice pipeline: cancelled after TTS")
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
                log.info("Voice pipeline: cancelled during playback")
                audio.stop_playback()
        else:
            # TTS failed — show text for a few seconds
            log.warning("Voice pipeline: TTS returned no audio, showing text only")
            await asyncio.sleep(3)

        # ── Done ─────────────────────────────────────────────────
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()

        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.info("Voice pipeline: complete in %.0fms (record=%.0f, stt=%.0f, gateway=%.0f, tts=%.0f)",
                 total_ms, t_record_ms, t_stt_ms, t_gw_ms, t_tts_ms)

        await _webhook_event("conversation_complete", "Conversation finished", {
            "user": user_text[:200],
            "agent_response": response_text[:200],
            "duration_ms": round(total_ms),
        })

    except asyncio.CancelledError:
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.info("Voice pipeline: cancelled after %.0fms", total_ms)
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
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.exception("Voice pipeline: unhandled error after %.0fms", total_ms)
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

    pipeline_start = time.perf_counter()
    log.info("Text pipeline: started with %d chars of input", len(text))

    try:
        # ── THINKING ─────────────────────────────────────────────
        log.info("Text pipeline: THINKING — sending to gateway (agent=%s)", _ui_state["agent"])
        log.info("Text pipeline: user said: '%s'", text[:200])
        sm.to_thinking()
        await emit_transcript("user", text, status="done")
        _append_chat("user", text)

        await emit_transcript("assistant", "…", status="thinking")

        if _oclient is None:
            await _pipeline_error("Gateway not configured")
            return

        _oclient.set_agent(_ui_state["agent"])

        # Try streaming (emits partial transcripts), fall back to blocking
        t_gw_start = time.perf_counter()
        try:
            response_text, tool_calls = await _stream_to_display(
                text, history=list(_chat_history), device_state=dict(_ui_state))
        except Exception as e:
            log.warning("Text pipeline: streaming failed, falling back to non-streaming: %s", e)
            response_text = await asyncio.to_thread(
                _oclient.send_message, text, list(_chat_history), dict(_ui_state)) or ""
            tool_calls = []
        t_gw_ms = (time.perf_counter() - t_gw_start) * 1000
        log.info("Text pipeline: gateway responded in %.0fms — %d chars, %d tool calls",
                 t_gw_ms, len(response_text), len(tool_calls))
        if response_text:
            log.info("Text pipeline: agent replied: '%s'", response_text[:200])

        if _cancel_event.is_set():
            log.info("Text pipeline: cancelled after gateway response")
            sm.to_idle()
            return

        if not response_text:
            await _pipeline_error("No response from agent")
            return

        # Extract mood hint from response
        try:
            from core.mood_parser import extract_mood
            mood, response_text = extract_mood(response_text)
            if mood:
                log.debug("Text pipeline: extracted mood hint: %s", mood)
                set_mood(mood)
        except ImportError:
            pass

        # Extract emoji reaction (before sending to TTS)
        try:
            from display.emoji_reactions import parse_reaction
            emoji, response_text = parse_reaction(response_text)
            if emoji:
                log.debug("Text pipeline: extracted emoji reaction: %s", emoji)
                await emit_reaction(emoji)
        except ImportError:
            pass

        await emit_transcript("assistant", response_text, status="done")
        _append_chat("assistant", response_text)

        # ── SPEAKING ─────────────────────────────────────────────
        log.info("Text pipeline: SPEAKING — synthesizing TTS")
        sm.to_speaking()
        _ui_state["speaking"] = True
        _ui_state["amplitude"] = 0.0  # clear residual amplitude
        await push_state()

        provider = _setting("audio.tts_provider", "edge")
        voice = _resolve_voice()
        log.debug("Text pipeline: TTS provider=%s, voice=%s", provider, voice or "(default)")

        t_tts_start = time.perf_counter()
        audio_data = await tts.synthesize(
            response_text,
            voice=voice,
            provider=provider,
            settings=settings,
        )
        t_tts_ms = (time.perf_counter() - t_tts_start) * 1000
        log.info("Text pipeline: TTS completed in %.0fms — %s",
                 t_tts_ms, f"{len(audio_data)} bytes" if audio_data else "no audio")

        if _cancel_event.is_set():
            log.info("Text pipeline: cancelled after TTS")
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
                log.info("Text pipeline: cancelled during playback")
                audio.stop_playback()
        else:
            log.warning("Text pipeline: TTS returned no audio, showing text only")
            await asyncio.sleep(3)

        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()

        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.info("Text pipeline: complete in %.0fms (gateway=%.0f, tts=%.0f)",
                 total_ms, t_gw_ms, t_tts_ms)

        await _webhook_event("conversation_complete", "Conversation finished", {
            "user": text[:200],
            "agent_response": response_text[:200],
            "duration_ms": round(total_ms),
        })

    except asyncio.CancelledError:
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.info("Text pipeline: cancelled after %.0fms", total_ms)
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        sm.to_idle()
    except Exception as e:
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        log.exception("Text pipeline: unhandled error after %.0fms", total_ms)
        _ui_state["speaking"] = False
        _ui_state["amplitude"] = 0.0
        await _pipeline_error(str(e)[:60])


def _cancel_pipeline() -> None:
    """Cancel any running pipeline."""
    global _pipeline_task
    if _pipeline_task and not _pipeline_task.done():
        log.info("Pipeline: cancelling active pipeline task")
        _cancel_event.set()
        _pipeline_task.cancel()
        _pipeline_task = None


# ── WebSocket handler ────────────────────────────────────────────────────────

async def handler(websocket: ServerConnection) -> None:
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


async def handle_message(data: dict, ws: ServerConnection) -> None:
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

        elif button == "cancel":
            # Cancel active pipeline (tap during THINKING or SPEAKING)
            if sm.state in (State.THINKING, State.SPEAKING):
                _cancel_pipeline()
                sm.to_idle()

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
    """Poll hardware state (battery only).

    Button input is handled by the display service, which forwards
    button events to us via WebSocket. This avoids double-polling
    the same GPIO pins.
    """
    from hw.detect import IS_PI

    if IS_PI:
        from hw.battery import get_level, init as battery_init
        battery_init()

        while True:
            batt = get_level()
            if batt >= 0 and batt != _ui_state["battery"]:
                _ui_state["battery"] = batt
                if batt <= 5:
                    set_mood("critical_battery")
                    await _webhook_event("battery_alert", f"Battery critical: {batt}%", {"level": batt})
                elif batt <= 20:
                    set_mood("low_battery")
                    await _webhook_event("battery_alert", f"Battery low: {batt}%", {"level": batt})
                await push_state()

            await asyncio.sleep(1.0)  # Battery changes slowly
    else:
        # Desktop — no hardware to poll, just keep alive
        while True:
            await asyncio.sleep(1)


# ── Main ─────────────────────────────────────────────────────────────────────

def _time_of_day() -> str:
    """Return a time-of-day string based on the current local hour."""
    import datetime
    hour = datetime.datetime.now().hour
    if hour < 6:
        return "late night"
    elif hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    elif hour < 21:
        return "evening"
    else:
        return "night"


async def _startup_greeting() -> None:
    """Request a short greeting from the gateway agent on startup.

    Waits for a client to connect, then asks the agent for a brief
    wake-up greeting. The response is broadcast as a 'greeting' message
    that the display service renders as a fade-in/fade-out text overlay.
    Skips silently if the gateway is unreachable or greeting is disabled.
    """
    greeting_enabled = _setting("character.greeting_enabled", True)
    if not greeting_enabled:
        log.debug("Startup greeting: disabled by config")
        return

    if _oclient is None:
        log.debug("Startup greeting: no gateway client configured")
        return

    # Wait briefly for a display client to connect
    for _ in range(30):  # up to 15s
        if _clients:
            break
        await asyncio.sleep(0.5)
    else:
        log.info("Startup greeting: no display client connected after 15s, skipping")
        return

    # Brief delay after client connects — boot animation is ~3s,
    # but we start the gateway request early so the response is
    # ready by the time the animation finishes.
    await asyncio.sleep(1.0)
    log.info("Startup greeting: client connected, requesting from gateway...")

    prompt = _setting(
        "character.greeting_prompt",
        "You just woke up. Give a very brief greeting (under 10 words) "
        "appropriate for {time_of_day}. Be in character.",
    )
    prompt = prompt.replace("{time_of_day}", _time_of_day())

    try:
        log.info("Startup greeting: requesting from gateway (agent=%s)", _ui_state["agent"])
        _oclient.set_agent(_ui_state["agent"])
        response = await asyncio.to_thread(
            _oclient.send_message, prompt, device_state=dict(_ui_state),
        )

        if not response:
            log.debug("Startup greeting: empty response from gateway")
            return

        # Strip mood tags like [happy] etc.
        import re
        clean = re.sub(r'^\s*\[\w+\]\s*', '', response).strip()
        # Strip leading emoji
        try:
            from display.emoji_reactions import parse_reaction
            _emoji, clean = parse_reaction(clean)
        except ImportError:
            pass

        if clean:
            clean = clean.strip('"').strip()
            log.info("Startup greeting: %s", clean[:60])
            await broadcast({"type": "greeting", "text": clean})
    except Exception as e:
        log.warning("Startup greeting: failed — %s", e)


async def main() -> None:
    # Suppress websockets' noisy handshake failure logs (e.g. port-check probes)
    logging.getLogger("websockets").setLevel(logging.ERROR)

    boot_message()
    apply_runtime_settings()
    _init_gateway()
    _init_webhook()

    host = "0.0.0.0"
    port = 8080

    async with serve(handler, host, port):
        log.info(f"WebSocket server: ws://{host}:{port}")
        ready_message()
        log.info("Frontend: open app/index.html or run 'npm run dev' in app/")

        # Fire-and-forget startup greeting (non-blocking)
        asyncio.create_task(_startup_greeting())

        await hardware_loop()


def shutdown(signum, frame) -> None:
    shutdown_message()
    # Silence stderr before exit — asyncio's Task.__del__ writes "Task was
    # destroyed but it is pending" via loop.call_exception_handler() during
    # GC teardown. These are harmless but noisy. Redirect stderr to devnull
    # for the final moments of the process.
    try:
        sys.stderr = open(_os.devnull, "w")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass  # shutdown() already logged the message
