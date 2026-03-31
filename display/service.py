"""Voxel Display Service — PIL renderer with pygame preview or WhisPlay SPI output.

Usage:
    uv run python -m display.service                  # standalone demo mode
    uv run python -m display.service --url ws://localhost:8080  # connected to server
    uv run python -m display.service --scale 3        # larger preview window
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess as _subprocess
import sys
import time

from display.state import DisplayState
from display.renderer import PILRenderer
from display.led import LEDController
from hw.detect import IS_PI

log = logging.getLogger("voxel.display")

# ── Whisplay single-button polling (uses the driver's button_pressed()) ─────
#
# The Whisplay HAT has ONE button (BOARD pin 11, active-HIGH).
# The WhisPlay driver already initializes GPIO in BOARD mode and provides
# board.button_pressed() — we use that instead of raw GPIO to avoid
# mode conflicts.  Progress ring normalised to 10s (SHUTDOWN_THRESHOLD).
#
# Button interaction model (single button, no double-tap):
#
# FROM FACE VIEW (IDLE):
#   Tap   (<400ms release)        → toggle view (face/chat, fires on release)
#   Hold  >400ms (still held)     → start recording (talk) — stays in RECORDING
#                                    until release. No menu/sleep/shutdown override.
#   Release after recording       → stop recording, send to STT
#
# FROM CHAT VIEW (menu closed):
#   Tap   (<400ms release)        → toggle view (face/chat)
#   Hold  >1s   (still held)      → open menu (fires AT threshold)
#   Hold  >5s   (still held)      → sleep (fires AT threshold)
#   Hold  >10s  (still held)      → shutdown with confirm (fires AT threshold)
#
# INSIDE MENU:
#   Tap   (<500ms release)        → next item
#   Hold  >500ms (still held)     → select / enter (fires AT threshold)
#   5s idle                        → auto-close menu
#
# Key principles:
#   - No double-tap — short tap fires instantly on release, zero ambiguity
#   - Long-hold actions fire AT the threshold crossing, not on release
#   - 500ms minimum recording guard prevents accidental cancel

TAP_THRESHOLD = 0.4            # seconds — max hold for "tap" (face/chat views)
RECORD_START_THRESHOLD = 0.4   # seconds — hold to start recording
RECORD_MIN_DURATION = 0.5      # seconds — minimum recording before release accepted
MENU_OPEN_THRESHOLD = 1.0      # seconds — hold to open menu (non-face views only)
SLEEP_THRESHOLD = 5.0          # seconds — enter sleep mode
SHUTDOWN_THRESHOLD = 10.0      # seconds — shutdown Pi
MENU_TAP_THRESHOLD = 0.5       # seconds — max hold for "tap" inside menu
MENU_SELECT_THRESHOLD = 0.5    # seconds — hold to select inside menu
MENU_IDLE_TIMEOUT = 5.0        # seconds — auto-close menu after no input

# Unified button state machine — shared by hardware (Pi) and desktop (spacebar)
# States: IDLE, PRESSED, RECORDING, IN_MENU_IDLE, IN_MENU_PRESSED
_btn_state: str = "IDLE"
_btn_press_start: float = 0.0
_btn_recording_start: float = 0.0    # when recording actually started
_btn_menu_last_input: float = 0.0    # last input time for menu auto-close
_btn_fired_record: bool = False       # True once recording has been signaled
_btn_fired_menu: bool = False         # True once menu-open has been fired
_btn_fired_sleep: bool = False        # True once sleep has been fired
_btn_fired_shutdown: bool = False     # True once shutdown has been fired

# Desktop spacebar pressed state (mutable list for closure access)
_desktop_space_pressed = [False]

# Watchdog — auto-recover if stuck in THINKING or LISTENING too long
THINKING_TIMEOUT = 60.0    # seconds before auto-recovery
SPEAKING_TIMEOUT = 120.0   # seconds before auto-recovery (long TTS can be 60s+)
_thinking_since: float = 0.0
_listening_since: float = 0.0
_speaking_since: float = 0.0


def _btn_reset() -> None:
    """Reset button state machine to IDLE."""
    global _btn_state, _btn_press_start, _btn_recording_start
    global _btn_fired_record, _btn_fired_menu, _btn_fired_sleep, _btn_fired_shutdown
    _btn_state = "IDLE"
    _btn_press_start = 0.0
    _btn_recording_start = 0.0
    _btn_fired_record = False
    _btn_fired_menu = False
    _btn_fired_sleep = False
    _btn_fired_shutdown = False


def _emit_button_event(event: str, state: DisplayState) -> None:
    """Update DisplayState flash fields for a button event."""
    state.button_flash = event
    state._button_flash_until = time.time() + 0.5


def _btn_enter_menu(state: DisplayState) -> None:
    """Transition button state machine into menu mode."""
    global _btn_state, _btn_menu_last_input
    _btn_state = "IN_MENU_IDLE"
    _btn_menu_last_input = time.time()
    state.button_pressed = False
    state.button_hold = 0.0


def _btn_exit_menu() -> None:
    """Transition button state machine out of menu mode."""
    global _btn_state
    _btn_state = "IDLE"


def _poll_button_unified(pressed: bool, state: DisplayState,
                         in_menu: bool) -> list[str]:
    """Unified button state machine for both hardware and desktop.

    Args:
        pressed: True if button is currently held down
        state: DisplayState to update visual indicators
        in_menu: True if menu/overlay is currently open

    Returns list of event strings:
        "short_tap", "start_recording", "stop_recording",
        "cancel_recording", "menu_open", "menu_next", "menu_select",
        "menu_timeout", "sleep", "shutdown"
    """
    global _btn_state, _btn_press_start, _btn_recording_start
    global _btn_menu_last_input
    global _btn_fired_record, _btn_fired_menu, _btn_fired_sleep, _btn_fired_shutdown

    events: list[str] = []
    now = time.time()

    # Sync button state machine with menu state
    if in_menu and _btn_state not in ("IN_MENU_IDLE", "IN_MENU_PRESSED"):
        # Menu was opened externally (keyboard shortcut, etc.)
        _btn_enter_menu(state)
    elif not in_menu and _btn_state in ("IN_MENU_IDLE", "IN_MENU_PRESSED"):
        # Menu was closed externally
        _btn_exit_menu()

    # ── IN_MENU states ──
    if _btn_state == "IN_MENU_IDLE":
        if pressed:
            _btn_state = "IN_MENU_PRESSED"
            _btn_press_start = now
            _btn_menu_last_input = now
            _btn_fired_menu = False
            state.button_pressed = True
            state.button_hold = 0.0
        else:
            # Check auto-close timeout
            if _btn_menu_last_input > 0 and (now - _btn_menu_last_input) >= MENU_IDLE_TIMEOUT:
                events.append("menu_timeout")
                _btn_exit_menu()
        return events

    if _btn_state == "IN_MENU_PRESSED":
        hold_time = now - _btn_press_start
        if not pressed:
            # Released
            state.button_pressed = False
            state.button_hold = 0.0
            _btn_state = "IN_MENU_IDLE"
            _btn_menu_last_input = now
            if hold_time < MENU_TAP_THRESHOLD and not _btn_fired_menu:
                events.append("menu_next")
                _emit_button_event("short_press", state)
            # If >= threshold, select already fired at threshold crossing
        else:
            # Still held — check for select threshold crossing
            state.button_hold = hold_time / SHUTDOWN_THRESHOLD
            if hold_time >= MENU_SELECT_THRESHOLD and not _btn_fired_menu:
                _btn_fired_menu = True
                events.append("menu_select")
                _emit_button_event("long_press", state)
                # Stay in IN_MENU_PRESSED until release (visual feedback continues)
        return events

    # ── IDLE state ──
    if _btn_state == "IDLE":
        if pressed:
            _btn_state = "PRESSED"
            _btn_press_start = now
            _btn_fired_record = False
            _btn_fired_menu = False
            _btn_fired_sleep = False
            _btn_fired_shutdown = False
            state.button_pressed = True
            state.button_hold = 0.0
        return events

    # ── PRESSED state (waiting to see what kind of press this is) ──
    if _btn_state == "PRESSED":
        hold_time = now - _btn_press_start
        state.button_hold = hold_time / SHUTDOWN_THRESHOLD

        if not pressed:
            # Released before any threshold — short tap
            state.button_pressed = False
            state.button_hold = 0.0
            if hold_time < TAP_THRESHOLD:
                events.append("short_tap")
                _emit_button_event("short_press", state)
            _btn_reset()
        elif hold_time >= SHUTDOWN_THRESHOLD and not _btn_fired_shutdown:
            # Shutdown threshold crossed while held
            _btn_fired_shutdown = True
            events.append("shutdown")
            _emit_button_event("shutdown", state)
            state.button_pressed = False
            state.button_hold = 0.0
            _btn_reset()
        elif hold_time >= SLEEP_THRESHOLD and not _btn_fired_sleep:
            # Sleep threshold crossed while held
            _btn_fired_sleep = True
            events.append("sleep")
            _emit_button_event("sleep", state)
            state.button_pressed = False
            state.button_hold = 0.0
            _btn_reset()
        elif hold_time >= RECORD_START_THRESHOLD and not _btn_fired_record:
            # Recording threshold crossed while held.
            # Only enter RECORDING from face view in IDLE — that's where
            # talk makes sense. Otherwise fall through to menu at 1s.
            if state.view == "face" and state.state == "IDLE":
                _btn_fired_record = True
                _btn_recording_start = now
                _btn_state = "RECORDING"
                events.append("start_recording")
                _emit_button_event("start_recording", state)
            elif hold_time >= MENU_OPEN_THRESHOLD and not _btn_fired_menu:
                # Non-face view or non-idle: open menu at 1s threshold
                _btn_fired_menu = True
                events.append("menu_open")
                _emit_button_event("long_press", state)
                state.button_pressed = False
                state.button_hold = 0.0
                _btn_reset()
        return events

    # ── RECORDING state (button held, mic is recording) ──
    # Once recording, ONLY release exits. No menu/sleep/shutdown override.
    # The user is talking — don't interrupt. They release when done.
    if _btn_state == "RECORDING":
        hold_time = now - _btn_press_start
        recording_duration = now - _btn_recording_start
        state.button_hold = hold_time / SHUTDOWN_THRESHOLD

        if not pressed:
            # Released — check minimum recording guard
            if recording_duration >= RECORD_MIN_DURATION:
                state.button_pressed = False
                state.button_hold = 0.0
                events.append("stop_recording")
                _emit_button_event("start_recording", state)  # "Talk" flash
                _btn_reset()
            else:
                # Too short — likely button bounce.  Cancel the recording
                # and return to IDLE rather than waiting for a duration
                # threshold to pass after the button is already released.
                state.button_pressed = False
                state.button_hold = 0.0
                events.append("cancel_recording")
                _btn_reset()
        return events

    return events


def _poll_whisplay_button(board, state: DisplayState,
                          in_menu: bool = False) -> list[str]:
    """Poll the WhisPlay board's single button via the unified state machine."""
    if board is None:
        return []
    try:
        pressed = board.button_pressed()
    except Exception:
        return []
    return _poll_button_unified(pressed, state, in_menu=in_menu)

# Demo mode: cycle through these moods
DEMO_MOODS = [
    "neutral", "happy", "curious", "thinking", "listening",
    "excited", "sleepy", "confused", "surprised", "focused",
]
# Full mood list for [/] cycling (includes all expressions)
ALL_MOODS_CYCLE = [
    "neutral", "happy", "curious", "thinking", "listening",
    "excited", "sleepy", "confused", "surprised", "focused",
    "frustrated", "sad", "working", "error",
    "low_battery", "critical_battery",
]


def _create_backend(use_pygame: bool, scale: int, backend_name: str = "auto"):
    """Create the appropriate output backend."""
    if backend_name == "framebuffer":
        from display.backends.framebuffer import FramebufferBackend
        return FramebufferBackend()
    if use_pygame:
        try:
            from display.backends.pygame import PygameBackend
            return PygameBackend(scale=scale)
        except ImportError:
            log.info("pygame not available, using tkinter backend")
            from display.backends.tkinter import TkinterBackend
            return TkinterBackend(scale=scale)
    else:
        from display.backends.spi import WhisplayBackend
        return WhisplayBackend()


# Outbound message queue — button handlers put messages here,
# the WebSocket client task sends them to server.py.
_ws_outbound: asyncio.Queue | None = None

# True when the WebSocket to server.py is open and active.
# Separate from state.connected (which may reflect gateway reachability
# in state pushes from server.py).  Button handlers use this to decide
# whether the voice pipeline is available.
_ws_connected: bool = False


def ws_send(msg: dict) -> None:
    """Queue a message to send to server.py via WebSocket.

    Thread-safe — can be called from the render loop or button handlers.
    No-op if the WebSocket is not connected.
    """
    if _ws_outbound is not None:
        try:
            _ws_outbound.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # drop if queue is backed up


async def _ws_client(state: DisplayState, url: str, stop: asyncio.Event) -> None:
    """WebSocket client loop — bidirectional connection to server.py.

    Receives state updates and pushes outbound messages (button events,
    mood commands) from the _ws_outbound queue.
    """
    global _ws_outbound, _ws_connected

    try:
        import websockets
        log.info(f"websockets version: {websockets.__version__}")
    except ImportError:
        log.error("websockets package not installed")
        return

    _ws_outbound = asyncio.Queue(maxsize=32)

    # Build connect kwargs — proxy param only exists in websockets >= 14
    connect_kwargs = {
        "open_timeout": 5,
        "ping_interval": 20,
        "ping_timeout": 10,
    }
    try:
        import inspect
        sig = inspect.signature(websockets.connect)
        if "proxy" in sig.parameters:
            connect_kwargs["proxy"] = None
    except Exception:
        pass

    while not stop.is_set():
        try:
            log.info(f"WebSocket: connecting to {url}...")
            ws = await asyncio.wait_for(
                websockets.connect(url, **connect_kwargs).__aenter__(),
                timeout=10,
            )
            log.info("WebSocket: connected!")
            try:
                _ws_connected = True
                state.connected = True

                async def _receive():
                    async for raw in ws:
                        if stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type")

                        if msg_type == "state":
                            state.mood = msg.get("mood", state.mood)
                            state.style = msg.get("style", state.style)
                            state.state = msg.get("state", state.state)
                            state.speaking = msg.get("speaking", state.speaking)
                            state.amplitude = msg.get("amplitude", state.amplitude)
                            state.battery = msg.get("battery", state.battery)
                            state.agent = msg.get("agent", state.agent)

                        elif msg_type == "transcript":
                            role = msg.get("role", "")
                            text = msg.get("text", "")
                            status = msg.get("status", "done")
                            if role and text:
                                state.push_transcript(role, text, status)

                        elif msg_type == "reaction":
                            emoji = msg.get("emoji", "")
                            if emoji:
                                state.reaction_emoji = emoji
                                state.reaction_time = time.time()

                        elif msg_type == "greeting":
                            text = msg.get("text", "")
                            if text:
                                state.greeting_text = text
                                state.greeting_time = time.time()
                                log.info("Gateway greeting: %s", text[:60])

                        elif msg_type == "tool_call":
                            name = msg.get("name", "")
                            status = msg.get("status", "running")
                            result = msg.get("result", "")
                            if status == "running":
                                state.push_transcript("tool", f"Running {name}...", status="tool_running",
                                                      tool_name=name)
                                # Visual feedback: working mood + gear emoji
                                state.mood = "working"
                                from display.emoji_reactions import apply_reaction
                                apply_reaction(state, "\u2699", time.time(),
                                               duration=10.0, set_mood=False)
                            elif status == "done":
                                if state.transcripts and state.transcripts[-1].role == "tool":
                                    state.transcripts[-1].text = f"{name}: {result}" if result else f"{name} done"
                                    state.transcripts[-1].status = "tool_done"
                                # Restore thinking mood and clear gear emoji
                                state.reaction_emoji = ""
                                if state.mood == "working":
                                    state.mood = "thinking"

                async def _send():
                    while not stop.is_set():
                        try:
                            msg = await asyncio.wait_for(
                                _ws_outbound.get(), timeout=0.5,
                            )
                            await ws.send(json.dumps(msg))
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            break

                # Run receive and send concurrently
                await asyncio.gather(
                    _receive(),
                    _send(),
                    return_exceptions=True,
                )
            finally:
                _ws_connected = False
                await ws.close()

        except Exception as e:
            _ws_connected = False
            state.connected = False
            if not stop.is_set():
                log.warning(f"WebSocket connection failed: {e} — retrying in 2s")
                await asyncio.sleep(2.0)

    _ws_connected = False
    state.connected = False


def _check_wifi() -> bool:
    """Quick check if wifi is connected (called periodically, not every frame)."""
    import subprocess
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=2,
        )
        return bool(result.stdout.strip())
    except Exception:
        return True  # assume connected on desktop / error


async def _render_loop(state: DisplayState, renderer: PILRenderer,
                       backend, stop: asyncio.Event,
                       button_handler=None, led: LEDController | None = None,
                       ambient=None, dev_panel=None) -> None:
    """Main render loop — FPS from config (default 30)."""
    try:
        from config.settings import load_settings as _load_fps
        fps = _load_fps().get("display", {}).get("fps", 30)
    except Exception:
        fps = 30
    interval = 1.0 / fps
    log.info("Render loop: %d FPS (%.1fms interval)", fps, interval * 1000)

    # Greeting is handled by the gateway greeting system (server.py)
    # which sends a personality-driven overlay, not a chat bubble.

    start_time = time.time()
    last_wifi_check = 0.0
    frame_count = 0
    prev_frame_time = start_time

    while not stop.is_set():
        frame_start = time.time()
        state.time = frame_start
        # Use actual elapsed time so animations compensate for frame drops
        state.dt = min(frame_start - prev_frame_time, interval * 3)  # cap at 3x to avoid jumps
        prev_frame_time = frame_start
        frame_count += 1

        # Poll hardware button (Whisplay single button on Pi)
        if hasattr(backend, '_board') and backend._board is not None:
            _in_menu = (renderer.menu.open or state.pairing_mode or
                        state.shutdown_confirm)
            for btn in _poll_whisplay_button(backend._board, state, in_menu=_in_menu):
                if button_handler:
                    button_handler(btn)

        # Poll desktop spacebar via the same unified state machine
        # (desktop press/release callbacks feed _desktop_space_pressed)
        if not (hasattr(backend, '_board') and backend._board is not None):
            _in_menu = (renderer.menu.open or state.pairing_mode or
                        state.shutdown_confirm)
            for btn in _poll_button_unified(_desktop_space_pressed[0], state,
                                            in_menu=_in_menu):
                if button_handler:
                    button_handler(btn)

        # Periodic wifi check (every 10s)
        if frame_start - last_wifi_check > 10.0:
            was_connected = state.wifi_connected
            state.wifi_connected = _check_wifi()
            last_wifi_check = frame_start
            # Exit AP mode when WiFi connects
            if state.wifi_ap_mode and state.wifi_connected and not was_connected:
                state.wifi_ap_mode = False
                log.info("WiFi connected — exiting AP mode")
                try:
                    from display.components.onboarding import save_setup_flag
                    save_setup_flag("wifi_configured")
                except Exception:
                    pass

        # Clear expired button flash (don't rely on drawing code to clean state)
        if state.button_flash and state._button_flash_until > 0 and frame_start >= state._button_flash_until:
            state.button_flash = ""
            state._button_flash_until = 0.0

        # Watchdog — auto-recover from stuck states
        global _thinking_since, _listening_since, _speaking_since

        def _watchdog_recover(label: str, msg: str):
            """Show error face briefly, then recover to IDLE."""
            log.warning("Watchdog: %s timeout — recovering", label)
            state.state = "ERROR"
            state.mood = "error"
            state.speaking = False
            state.amplitude = 0.0
            state.push_transcript("system", msg)
            # Error face shows for ~3s via the render loop,
            # then _watchdog_error_until triggers IDLE recovery
            state._watchdog_error_until = frame_start + 3.0

        # Recover from watchdog error state after 3s
        if hasattr(state, '_watchdog_error_until') and state._watchdog_error_until > 0:
            if state.state == "ERROR" and frame_start >= state._watchdog_error_until:
                state.state = "IDLE"
                state.mood = "neutral"
                state._watchdog_error_until = 0.0

        if state.state == "THINKING":
            if _thinking_since == 0.0:
                _thinking_since = frame_start
            elif frame_start - _thinking_since > THINKING_TIMEOUT:
                _watchdog_recover("THINKING", "Request timed out")
                _thinking_since = 0.0
        else:
            _thinking_since = 0.0

        if state.state == "LISTENING":
            if _listening_since == 0.0:
                _listening_since = frame_start
            elif frame_start - _listening_since > THINKING_TIMEOUT:
                _watchdog_recover("LISTENING", "Recording timed out")
                _listening_since = 0.0
        else:
            _listening_since = 0.0

        if state.state == "SPEAKING":
            if _speaking_since == 0.0:
                _speaking_since = frame_start
            elif frame_start - _speaking_since > SPEAKING_TIMEOUT:
                _watchdog_recover("SPEAKING", "Playback timed out")
                try:
                    from core.audio import stop_playback
                    stop_playback()
                except Exception:
                    pass
                _speaking_since = 0.0
        else:
            _speaking_since = 0.0

        # Check shutdown countdown
        if state.shutdown_confirm and state._shutdown_at > 0 and frame_start >= state._shutdown_at:
            state.shutdown_confirm = False
            state._shutdown_at = 0.0
            log.warning("Shutdown countdown complete — executing shutdown")
            try:
                _subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
            except Exception as e:
                log.error(f"Shutdown command failed: {e}")

        # Check menu WiFi setup trigger
        if renderer.menu._wifi_setup_triggered:
            renderer.menu._wifi_setup_triggered = False
            if IS_PI:
                log.info("WiFi setup requested via menu — signalling guardian")
                try:
                    from pathlib import Path
                    Path("/tmp/voxel-wifi-setup").touch()
                except Exception as e:
                    log.error(f"WiFi setup signal failed: {e}")
            else:
                log.info("WiFi setup requested on desktop — ignoring")

        # Check menu reboot confirmation
        if renderer.menu._reboot_confirmed:
            renderer.menu._reboot_confirmed = False
            if IS_PI:
                log.warning("Reboot confirmed via menu — executing reboot")
                try:
                    _subprocess.Popen(["sudo", "reboot"])
                except Exception as e:
                    log.error(f"Reboot command failed: {e}")
            else:
                log.info("Reboot requested on desktop — ignoring")

        # Persist menu config changes (agent, character, brightness, volume, accent)
        if renderer.menu._pending_config is not None:
            _cfg_update = renderer.menu._pending_config
            renderer.menu._pending_config = None
            try:
                from config.settings import save_local_settings
                save_local_settings(_cfg_update)
                log.info("Menu: persisted config %s", list(_cfg_update.keys()))
                # Forward to backend via WebSocket if connected
                if _ws_connected:
                    for section, values in _cfg_update.items():
                        if isinstance(values, dict):
                            for key, val in values.items():
                                ws_send({"type": "set_setting", "section": section,
                                         "key": key, "value": val})
            except Exception as e:
                log.warning("Menu: failed to persist config: %s", e)

        # Ambient audio reactivity (deterministic, no LLM)
        # Only runs during IDLE, not connected, and not in demo mode
        if (ambient and ambient.enabled and state.state == "IDLE"
                and not state.connected and not state.demo_mode):
            reaction = ambient.get_reaction()
            if reaction:
                state.mood = reaction
                # Reinforce spike reactions with a brief emoji
                if reaction == "surprised" and not state.reaction_emoji:
                    from display.emoji_reactions import apply_reaction
                    apply_reaction(state, "\u2757", time.time(),
                                   duration=1.5, set_mood=False)
            # Subtle mouth movement from ambient sound (30% of full speaking amplitude)
            state.amplitude = ambient.amplitude * 0.3
        elif ambient and state.state != "IDLE":
            # Don't let ambient amplitude leak into speaking/listening states
            pass  # amplitude is driven by server or dev panel

        # Ambient activity indicator — always track if monitor is running
        if ambient and ambient.enabled and ambient._running:
            state.ambient_active = ambient.amplitude > 0.05
            state.ambient_amplitude = ambient.amplitude
        else:
            state.ambient_active = False
            state.ambient_amplitude = 0.0

        # Render
        img = renderer.render(state)
        backend.push_frame(img)

        # Update LED color/pattern based on current state
        if led is not None:
            led.update(state, state.time)
            # Simulate LED on desktop preview (tkinter backend)
            if hasattr(backend, 'set_led'):
                backend.set_led(*led._compute_color(state, state.time))

        # Update dev panel — every 2nd frame for responsive mic level,
        # UI button highlights only refresh every 10th frame
        if dev_panel and not dev_panel.closed and frame_count % 2 == 0:
            try:
                dev_panel.update()
            except Exception:
                pass  # panel may have been closed

        if backend.should_quit():
            stop.set()
            break

        # Frame timing — always yield to event loop so background tasks
        # (WebSocket client, etc.) get CPU time even when rendering is slow
        elapsed = time.time() - frame_start
        sleep_time = max(0, interval - elapsed)
        await asyncio.sleep(sleep_time)


async def _main(args: argparse.Namespace) -> None:
    use_pygame = not IS_PI
    if args.backend == "pygame":
        use_pygame = True
    elif args.backend in ("whisplay", "framebuffer"):
        use_pygame = False

    backend = _create_backend(use_pygame, args.scale, backend_name=args.backend)
    backend.init()
    log.info("Display backend: %s", type(backend).__name__)

    # ── Boot splash ───────────────────────────────────────────────────
    from display.boot_splash import BootSplash

    _splash_version = "0.1.0"
    try:
        from importlib.metadata import version as _pkg_version
        _splash_version = _pkg_version("voxel")
    except Exception:
        pass
    splash = BootSplash(backend)
    splash.show_title(version=_splash_version)

    state = DisplayState()

    # Demo mode: CLI flag or config
    if args.demo:
        state.demo_mode = True
    else:
        try:
            from config.settings import load_settings as _load_demo_cfg
            state.demo_mode = _load_demo_cfg().get("character", {}).get("demo_mode", False)
        except Exception:
            pass

    renderer = PILRenderer()

    # Boot splash: Display + Expressions ready
    splash.add_line("Display", "OK")
    splash.add_line("Expressions", "OK")

    stop = asyncio.Event()

    # LED controller — uses WhisPlay board if available, no-op on desktop
    led_board = getattr(backend, '_board', None)
    led_brightness = 80
    led_speed = 1.0
    led_enabled = True
    try:
        from config.settings import load_settings as _load_led_cfg
        _led_cfg = _load_led_cfg().get("led", {})
        led_brightness = _led_cfg.get("brightness", 80)
        led_speed = _led_cfg.get("breathe_speed", 1.0)
        led_enabled = _led_cfg.get("enabled", True)
    except Exception:
        pass
    led = LEDController(led_board, brightness=led_brightness, speed_mult=led_speed)
    led.enabled = led_enabled

    # Ambient audio monitor — deterministic face reactivity from mic input
    ambient = None
    _audio_status = "SKIP"
    try:
        from config.settings import load_settings as _load_ambient_cfg
        _ambient_cfg = _load_ambient_cfg().get("audio", {})
        _ambient_enabled = _ambient_cfg.get("ambient_react", True)
        _ambient_sensitivity = _ambient_cfg.get("ambient_sensitivity", 0.6)
        _ambient_silence = _ambient_cfg.get("ambient_silence_timeout", 180)
        if _ambient_enabled:
            from display.ambient import AmbientMonitor
            ambient = AmbientMonitor(
                sensitivity=_ambient_sensitivity,
                silence_timeout=_ambient_silence,
            )
            ambient.start()
            _audio_status = "OK"
    except Exception as e:
        log.debug(f"Ambient monitor not available: {e}")
    splash.add_line("Audio", _audio_status)

    # Check gateway configuration
    _gateway_status = "SKIP"
    try:
        from config.settings import load_settings as _load_gw_cfg
        _gw_token = _load_gw_cfg().get("gateway", {}).get("token", "")
        if _gw_token:
            _gateway_status = "OK"
    except Exception:
        pass
    splash.add_line("Gateway", _gateway_status)

    # Boot splash: Ready!
    splash.show_ready(hold=0.5)
    del splash  # free splash resources

    # ── Boot animation (wake-up sequence) ────────────────────────────
    _boot_anim_enabled = True
    try:
        from config.settings import load_settings as _load_boot_cfg
        _boot_cfg = _load_boot_cfg()
        _boot_anim_enabled = _boot_cfg.get("character", {}).get("boot_animation", True)
    except Exception:
        _boot_cfg = {}

    if _boot_anim_enabled:
        try:
            from display.boot_animation import play_boot_animation
            play_boot_animation(backend, config=_boot_cfg)
        except Exception as e:
            log.warning("Boot animation failed: %s", e)
    else:
        log.info("Boot animation: disabled by config")

    # Check WiFi and start AP mode if not connected (Pi only)
    if IS_PI:
        try:
            from display.wifi import is_nmcli_available, is_wifi_connected, start_ap, AP_SSID, AP_PASSWORD, AP_IP
            if is_nmcli_available() and not is_wifi_connected():
                log.info("No WiFi — starting AP mode for onboarding")
                if start_ap():
                    state.wifi_ap_mode = True
                    state.wifi_ap_ssid = AP_SSID
                    state.wifi_ap_password = AP_PASSWORD
                    state.wifi_connected = False
        except Exception as e:
            log.warning(f"WiFi check failed: {e}")

    # Start config web server (serves on AP IP in AP mode, or LAN IP otherwise)
    try:
        from display.config_server import start_config_server
        config_url = start_config_server(state=state)
        renderer.config_url = config_url
    except Exception as e:
        log.warning(f"Config server failed to start: {e}")
        config_url = ""

    # Auto-start MCP server if enabled in config
    mcp_proc = None
    try:
        from config.settings import load_settings as _load_mcp_cfg
        _mcp_cfg = _load_mcp_cfg().get("mcp", {})
        if _mcp_cfg.get("enabled", False):
            import sys, subprocess
            from pathlib import Path
            _mcp_port = _mcp_cfg.get("port", 8082)
            _mcp_ws = _mcp_cfg.get("ws_url", "ws://localhost:8080")
            mcp_proc = subprocess.Popen(
                [sys.executable, "-m", "mcp",
                 "--transport", "sse", "--port", str(_mcp_port),
                 "--ws-url", _mcp_ws],
                cwd=str(Path(__file__).parent.parent),
            )
            log.info("MCP server auto-started on :%d (PID %d)", _mcp_port, mcp_proc.pid)
    except Exception as e:
        log.debug(f"MCP auto-start failed: {e}")

    # Dev mode + accent color
    try:
        from display.config_server import _load_settings
        settings = _load_settings()
        dev_enabled = settings.get("dev", {}).get("enabled", False)
        if dev_enabled:
            log.info("Dev mode ENABLED")
            state.dev_mode = True
        char_settings = settings.get("character", {})
        state.character = char_settings.get("default", "voxel")
        state.accent_color = char_settings.get("accent_color", "#00d4d2")
        log.info("Character: %s, accent: %s, demo: %s",
                 state.character, state.accent_color, state.demo_mode)
    except Exception:
        pass

    # Start device advertiser for dev-pair discovery (if enabled in config)
    try:
        from config.settings import load_settings as _load_cfg
        _cfg = _load_cfg()
        should_advertise = _cfg.get("dev", {}).get("advertise", True)
        if should_advertise:
            from display.advertiser import start_advertiser
            from display.updater import get_current_version
            adv_port = int(config_url.split(":")[-1]) if config_url else 8081
            start_advertiser(config_port=adv_port, version=get_current_version())
    except Exception as e:
        log.debug(f"Advertiser failed: {e}")

    # Check for updates on boot (non-blocking)
    if IS_PI:
        try:
            from display.updater import check_for_update
            update_info = check_for_update()
            if update_info.get("available"):
                state.update_available = True
                state.update_behind = update_info.get("behind", 0)
                log.info(f"Update available: {update_info['behind']} commits behind")
        except Exception as e:
            log.debug(f"Update check failed: {e}")

    # Keyboard controls for dev preview
    menu = renderer.menu

    def _on_key(key: str) -> None:
        # Menu navigation takes priority when open
        if menu.open:
            if key == "m" or key == "\x1b":  # m or Escape
                menu.back()
            elif key == "w":
                menu.navigate(-1)
            elif key == "s":
                menu.navigate(1)
            elif key == "\r" or key == " ":
                menu.select(state)
            elif key == "a":
                menu.adjust(state, -10)
            elif key == "d":
                menu.adjust(state, 10)
            return

        if key == "m":
            menu.open = True
            log.info("Menu opened")
        elif key == "c":
            # Toggle between face and chat
            state.view = "chat" if state.view == "face" else "face"
            log.info(f"View: {state.view}")
        elif key == "t":
            # Toggle transcript overlay visibility (for testing)
            state.transcript_visible = not state.transcript_visible
            if state.transcript_visible and not state.transcript_user:
                state.transcript_user = "hello voxel"
                state.transcript_voxel = "hey! how can I help?"
            log.info(f"Transcript: {'visible' if state.transcript_visible else 'hidden'}")
        elif key == "p":
            # Toggle demo mode at runtime
            state.demo_mode = not state.demo_mode
            log.info(f"Demo mode: {'ON' if state.demo_mode else 'OFF'}")
        elif key == "n":
            # Simulate ambient noise spike (for desktop testing)
            if ambient:
                ambient.simulate_spike()
                log.info("Simulated ambient noise spike")
        elif key == "[":
            # Cycle mood previous
            try:
                idx = ALL_MOODS_CYCLE.index(state.mood)
            except ValueError:
                idx = 0
            state.mood = ALL_MOODS_CYCLE[(idx - 1) % len(ALL_MOODS_CYCLE)]
            log.info(f"Mood: {state.mood}")
        elif key == "]":
            # Cycle mood next
            try:
                idx = ALL_MOODS_CYCLE.index(state.mood)
            except ValueError:
                idx = -1
            state.mood = ALL_MOODS_CYCLE[(idx + 1) % len(ALL_MOODS_CYCLE)]
            log.info(f"Mood: {state.mood}")
        elif key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
            idx = int(key) - 1 if key != "0" else 9
            if idx < len(DEMO_MOODS):
                state.mood = DEMO_MOODS[idx]
                log.info(f"Mood: {state.mood}")

    if hasattr(backend, "set_key_callback"):
        backend.set_key_callback(_on_key)

    # Desktop spacebar — unified state machine via _poll_button_unified
    # The render loop polls _desktop_space_pressed[0] each frame.
    def _on_space_press():
        _desktop_space_pressed[0] = True

    def _on_space_release():
        _desktop_space_pressed[0] = False

    if hasattr(backend, "set_button_callbacks"):
        backend.set_button_callbacks(_on_space_press, _on_space_release)

    # Button event handler — processes events from the unified state machine.
    # Events: "short_tap", "start_recording", "stop_recording",
    #         "cancel_recording", "menu_open", "menu_next", "menu_select",
    #         "menu_timeout", "sleep", "shutdown"
    def _on_button(btn: str) -> None:
        # Any button event during sleep wakes the device
        if state.state == "SLEEPING" and btn not in ("sleep", "shutdown"):
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Wake from sleep (button press)")
            return

        # Any button event during shutdown countdown cancels it
        if state.shutdown_confirm and btn != "shutdown":
            state.shutdown_confirm = False
            state._shutdown_at = 0.0
            log.info("Shutdown cancelled (button press)")
            return

        # Pairing request: tap = approve (show PIN), menu_select = deny
        if state.pairing_request:
            if btn in ("short_tap", "menu_next"):
                state.pairing_request = False
                state.pairing_approved = True
                state.pairing_mode = True  # show the PIN
                log.info(f"Pairing approved for {state.pairing_request_from}")
            elif btn in ("menu_select", "menu_open"):
                state.pairing_request = False
                state.pairing_denied = True
                log.info(f"Pairing denied for {state.pairing_request_from}")
            return

        # Dismiss pairing overlay on any button press
        if state.pairing_mode:
            state.pairing_mode = False
            log.info("Pairing mode dismissed")
            return

        # Menu events (handled by the unified state machine's menu mode)
        if menu.open:
            if btn == "menu_next":
                menu.navigate(1)   # tap = next item
            elif btn == "menu_select":
                menu.select(state) # hold = select/enter
            elif btn == "menu_timeout":
                menu.open = False
                log.info("Menu auto-closed (idle timeout)")
            elif btn in ("sleep", "shutdown"):
                menu.open = False
                log.info(f"Menu force-closed ({btn})")
            return

        # While actively listening, tap or stop_recording ends it
        if state.state == "LISTENING" and btn in ("short_tap", "stop_recording"):
            ws_send({"type": "button", "button": "release"})
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Push-to-talk: stop recording (%s)", btn)
            return

        # Cancel recording (menu open override while recording)
        if state.state == "LISTENING" and btn == "cancel_recording":
            ws_send({"type": "button", "button": "release"})
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Push-to-talk: cancelled recording (menu override)")
            return

        # While thinking, tap cancels the pipeline and returns to IDLE
        if state.state == "THINKING" and btn == "short_tap":
            ws_send({"type": "button", "button": "cancel"})
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Push-to-talk: cancelled (tap during THINKING)")
            return

        # While speaking, tap cancels playback
        if state.state == "SPEAKING" and btn == "short_tap":
            ws_send({"type": "button", "button": "cancel"})
            try:
                from core.audio import stop_playback
                stop_playback()
            except Exception:
                pass
            state.speaking = False
            state.amplitude = 0.0
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Push-to-talk: cancelled (tap during SPEAKING)")
            return

        # ── Face/Chat view events ──
        if btn == "short_tap":
            # Toggle between face and chat
            state.view = "chat" if state.view == "face" else "face"
            log.info(f"View: {state.view}")
        elif btn == "start_recording":
            # Hold >400ms starts recording — only from face view in IDLE
            if state.view != "face":
                log.debug("Talk ignored — not on face view (view=%s)", state.view)
            elif state.state != "IDLE":
                log.debug("Talk ignored — not idle (state=%s)", state.state)
            else:
                if _ws_connected:
                    ws_send({"type": "button", "button": "press"})
                else:
                    log.warning("No backend connected — voice pipeline unavailable. "
                                "Run with --server for full voice support.")
                state.state = "LISTENING"
                state.mood = "listening"
                state.view = "face"
                log.info("Push-to-talk: start recording (hold >400ms)")
        elif btn == "stop_recording":
            # Release after recording — send to STT.
            if state.state == "LISTENING":
                if _ws_connected:
                    # Immediately transition to THINKING locally so there's no
                    # 1-2 frame flash to IDLE before the server pushes THINKING.
                    ws_send({"type": "button", "button": "release"})
                    state.state = "THINKING"
                    state.mood = "thinking"
                    log.info("Push-to-talk: stop recording (release) → THINKING")
                else:
                    # No backend — go back to IDLE since there's nothing to process
                    state.state = "IDLE"
                    state.mood = "neutral"
                    log.info("Push-to-talk: stop recording (release) → IDLE (no backend)")
        elif btn == "cancel_recording":
            # Recording cancelled by menu open or other override
            if state.state == "LISTENING":
                ws_send({"type": "button", "button": "release"})
                state.state = "IDLE"
                state.mood = "neutral"
                log.info("Push-to-talk: cancelled recording")
        elif btn == "menu_open":
            menu.open = True
            _btn_enter_menu(state)
            log.info("Menu opened (hold >1s)")
        elif btn == "sleep":
            state.state = "SLEEPING"
            state.mood = "sleepy"
            state.speaking = False
            state.amplitude = 0.0
            log.info("Sleep mode entered (hold >5s)")
        elif btn == "shutdown":
            # Start shutdown confirmation countdown (3s)
            state.shutdown_confirm = True
            state._shutdown_at = time.time() + 3.0
            log.info("Shutdown countdown started (hold >10s) — press to cancel")

    # Dev panel — secondary control window (desktop only, disable with --no-panel)
    dev_panel = None
    if not IS_PI and not args.no_panel and hasattr(backend, '_root') and backend._root:
        try:
            from display.dev_panel import DevPanel
            dev_panel = DevPanel(
                root=backend._root, state=state, backend=backend,
                on_mood=lambda m: log.info("Dev panel mood: %s", m),
            )
        except Exception as e:
            log.debug("Dev panel not available: %s", e)

    # Handle signals
    def _signal_handler(*_):
        stop.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    tasks = []

    # WebSocket client (if URL provided)
    ws_task = None
    if args.url:
        ws_task = asyncio.create_task(_ws_client(state, args.url, stop))
        tasks.append(ws_task)

    # Render loop (demo mode handled by DemoController in renderer)
    render_task = asyncio.create_task(
        _render_loop(state, renderer, backend, stop, button_handler=_on_button,
                     led=led, ambient=ambient, dev_panel=dev_panel)
    )
    tasks.append(render_task)

    try:
        # Wait for render loop to finish (window close, signal, etc.)
        # Then cancel the WS client so we don't hang.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
    except asyncio.CancelledError:
        pass
    finally:
        if ambient:
            ambient.stop()
        if mcp_proc and mcp_proc.poll() is None:
            mcp_proc.terminate()
            log.info("MCP server stopped")
        led.off()
        backend.cleanup()
        log.info("Display service stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Voxel PIL Display Service")
    parser.add_argument("--url", type=str, default=None,
                        help="WebSocket server URL (e.g. ws://localhost:8080)")
    parser.add_argument("--scale", type=int, default=1,
                        help="Preview window scale factor (default: 1, true 1:1 with Pi LCD)")
    parser.add_argument("--backend", choices=["auto", "pygame", "whisplay", "framebuffer"],
                        default="auto",
                        help="Output backend (default: auto-detect; framebuffer for fbtft/mipi-dbi-spi)")
    parser.add_argument("--demo", action="store_true",
                        help="Enable demo mode (auto-cycle moods/characters/styles)")
    parser.add_argument("--no-panel", action="store_true",
                        help="Disable the dev control panel window")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--server", action="store_true",
                        help="Auto-start server.py and connect (full voice pipeline)")
    args = parser.parse_args()

    from core.log import setup as setup_logging
    level = logging.DEBUG if args.verbose else None  # None = auto from env
    setup_logging(level=level, show_banner=True)

    server_proc = None
    if args.server:
        import shutil
        import socket
        from pathlib import Path

        # Kill any zombie server.py on port 8080 before starting fresh
        _port_in_use = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
                _s.settimeout(0.5)
                _s.connect(("127.0.0.1", 8080))
                _port_in_use = True
        except OSError:
            pass  # Connection refused = port is free

        if _port_in_use:
            log.info("Port 8080 in use — killing old server.py")
            try:
                if sys.platform == "win32":
                    # Find and kill the process listening on 8080
                    result = _subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True, text=True, timeout=5,
                    )
                    for line in result.stdout.splitlines():
                        if ":8080" in line and "LISTENING" in line:
                            pid = line.strip().split()[-1]
                            _subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                capture_output=True, timeout=5,
                            )
                            log.info("Killed old server (PID %s)", pid)
                            break
                else:
                    # Unix: use fuser to kill whatever's on the port
                    _subprocess.run(
                        ["fuser", "-k", "8080/tcp"],
                        capture_output=True, timeout=5,
                    )
                import time as _t
                _t.sleep(0.5)  # let port release
            except Exception as e:
                log.warning("Could not kill old server: %s", e)

        server_py = Path(__file__).resolve().parent.parent / "server.py"
        uv_bin = shutil.which("uv")
        if uv_bin:
            cmd = [uv_bin, "run", str(server_py)]
        else:
            cmd = [sys.executable, str(server_py)]

        log.info("Starting server.py: %s", " ".join(cmd))
        env = {**os.environ, "VOXEL_NO_BANNER": "1"}
        server_proc = _subprocess.Popen(cmd, env=env)
        # Give server a moment to bind
        import time as _t
        _t.sleep(1.5)

        # Auto-set WebSocket URL regardless (connect to existing or new server)
        if not args.url:
            args.url = "ws://localhost:8080"

    def _kill_server():
        """Kill server.py and its entire process tree."""
        if not server_proc:
            return
        pid = server_proc.pid
        log.info("Stopping server.py (pid %d)", pid)
        try:
            if sys.platform == "win32":
                # taskkill /T kills the process tree (uv → python → server.py)
                _subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
            else:
                # Unix: kill process group
                import signal as _sig
                os.killpg(os.getpgid(pid), _sig.SIGKILL)
        except Exception:
            try:
                server_proc.kill()
            except Exception:
                pass

    def _force_exit(*_):
        """Second Ctrl+C forces immediate exit."""
        _kill_server()
        os._exit(1)

    try:
        asyncio.run(_main(args))
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, _force_exit)  # second Ctrl+C = force
    finally:
        _kill_server()


def main_watch() -> None:
    """Run with file-watching auto-restart (like Vite HMR for Python).

    Usage: uv run dev-watch
    """
    import subprocess
    import sys
    from pathlib import Path

    from watchfiles import run_process

    watch_dirs = [
        str(Path(__file__).parent),
        str(Path(__file__).parent.parent / "shared"),
    ]

    print("Starting display service with auto-reload...")
    print(f"  Watching: display/, shared/")
    print(f"  Press Ctrl+C to stop\n")

    run_process(
        *watch_dirs,
        target=_run_subprocess,
        args=(sys.argv[1:],),
    )


def _run_subprocess(args: list[str]) -> None:
    """Target function for watchfiles — runs main() in-process."""
    import sys
    # Re-parse args for the subprocess
    sys.argv = ["dev"] + list(args)
    main()


if __name__ == "__main__":
    main()
