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

log = logging.getLogger("voxel.display")

# ── Whisplay single-button polling (uses the driver's button_pressed()) ─────
#
# The Whisplay HAT has ONE button (BOARD pin 11, active-HIGH).
# The WhisPlay driver already initializes GPIO in BOARD mode and provides
# board.button_pressed() — we use that instead of raw GPIO to avoid
# mode conflicts.  Progress ring normalised to 10s (SHUTDOWN_THRESHOLD).
#
# Button interaction patterns (single button):
#   Short press (<400ms, no 2nd press within 400ms) → cycle views
#   Double-tap  (two presses within 400ms)          → push-to-talk
#   Long press  (hold >1s)                           → menu open/select
#   Medium hold (0.4-1s, menu only)                  → navigate up (previous)
#   Sleep       (hold >5s)                           → enter sleep mode
#   Shutdown    (hold >10s)                          → shutdown Pi (with confirm)

SHORT_PRESS_THRESHOLD = 0.55  # seconds — max hold for "short" / double-tap window (0.4 too tight for hardware)
MEDIUM_PRESS_THRESHOLD = 0.55 # seconds — lower bound for "medium hold" (= SHORT)
LONG_PRESS_THRESHOLD = 1.0    # seconds — menu open (from face view)
MENU_LONG_PRESS = 0.9         # seconds — menu select (wider window for reliable medium press)
SLEEP_THRESHOLD = 5.0         # seconds — enter sleep mode
SHUTDOWN_THRESHOLD = 10.0     # seconds — shutdown Pi

# Hardware button state machine
_btn_was_pressed = False
_btn_press_start = 0.0
_btn_waiting_double: bool = False      # True while waiting to see if a second tap comes
_btn_first_release_time: float = 0.0   # when the first short press was released

# Desktop spacebar state machine (mirrors hardware)
_desktop_press_time = [0.0]            # mutable for closure access from render loop
_desktop_waiting_double = [False]
_desktop_first_release_time = [0.0]

# Watchdog — auto-recover if stuck in THINKING or LISTENING too long
THINKING_TIMEOUT = 60.0    # seconds before auto-recovery
SPEAKING_TIMEOUT = 120.0   # seconds before auto-recovery (long TTS can be 60s+)
_thinking_since: float = 0.0
_listening_since: float = 0.0
_speaking_since: float = 0.0


def _classify_release(hold_time: float, instant_tap: bool = False) -> str | None:
    """Classify a button release into an event based on hold duration.

    Returns the event name or None if the press was short and needs to
    wait for a possible second tap (double-tap detection).

    When instant_tap is True (menu/overlay context):
      - long_press threshold is shorter (0.7s vs 1.0s) for snappier select
      - medium_press zone (0.4-0.9s) used for "navigate up/previous"
    """
    long_threshold = MENU_LONG_PRESS if instant_tap else LONG_PRESS_THRESHOLD

    if hold_time >= SHUTDOWN_THRESHOLD:
        return "shutdown"
    elif hold_time >= SLEEP_THRESHOLD:
        return "sleep"
    elif hold_time >= long_threshold:
        return "long_press"
    elif instant_tap and hold_time >= MEDIUM_PRESS_THRESHOLD:
        return "medium_press"
    # Short press — caller must wait for double-tap window
    return None


def _emit_button_event(event: str, state: DisplayState) -> None:
    """Update DisplayState flash fields for a button event."""
    state.button_flash = event
    state._button_flash_until = time.time() + 0.5


def _poll_whisplay_button(board, state: DisplayState,
                          instant_tap: bool = False) -> list[str]:
    """Poll the WhisPlay board's single button. Returns event list.

    Updates state.button_hold / button_pressed for the visual indicator.
    Events: "short_press", "double_tap", "long_press", "sleep", "shutdown".

    When instant_tap is True (e.g. menu is open), short presses fire
    immediately on release without waiting for the double-tap window.
    This makes menu navigation feel responsive.
    """
    global _btn_was_pressed, _btn_press_start
    global _btn_waiting_double, _btn_first_release_time

    if board is None:
        return []

    events: list[str] = []
    try:
        pressed = board.button_pressed()
    except Exception:
        return []

    now = time.time()

    if pressed and not _btn_was_pressed:
        # Button just pressed
        if _btn_waiting_double and not instant_tap:
            # Second press within the double-tap window
            _btn_waiting_double = False
            _btn_first_release_time = 0.0
            events.append("double_tap")
            _emit_button_event("double_tap", state)
            _btn_press_start = now
            _btn_was_pressed = True
            state.button_pressed = False
            state.button_hold = 0.0
        else:
            _btn_waiting_double = False
            _btn_first_release_time = 0.0
            _btn_press_start = now
            _btn_was_pressed = True
            state.button_pressed = True
            state.button_hold = 0.0
    elif pressed and _btn_was_pressed:
        # Button held — update progress (normalised to 10s full scale)
        hold_time = now - _btn_press_start
        state.button_hold = hold_time / SHUTDOWN_THRESHOLD
    elif not pressed and _btn_was_pressed:
        # Button just released
        hold_time = now - _btn_press_start
        state.button_pressed = False
        state.button_hold = 0.0
        _btn_was_pressed = False

        event = _classify_release(hold_time, instant_tap=instant_tap)
        if event:
            events.append(event)
            _emit_button_event(event, state)
        elif instant_tap:
            # In menu/overlay: fire short_press immediately, no double-tap wait
            events.append("short_press")
            _emit_button_event("short_press", state)
        else:
            # Normal: start double-tap timer
            _btn_waiting_double = True
            _btn_first_release_time = now
    else:
        # Not pressed — check double-tap timer expiry
        state.button_pressed = False
        state.button_hold = 0.0
        if _btn_waiting_double and (now - _btn_first_release_time) >= SHORT_PRESS_THRESHOLD:
            _btn_waiting_double = False
            _btn_first_release_time = 0.0
            events.append("short_press")
            _emit_button_event("short_press", state)

    return events

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
DEMO_CYCLE_INTERVAL = 4.0  # seconds per mood


def _create_backend(use_pygame: bool, scale: int):
    """Create the appropriate output backend."""
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
    global _ws_outbound

    try:
        import websockets
    except ImportError:
        log.error("websockets package not installed")
        return

    _ws_outbound = asyncio.Queue(maxsize=32)

    while not stop.is_set():
        try:
            log.info(f"Connecting to {url}")
            async with websockets.connect(url) as ws:
                state.connected = True
                log.info("WebSocket connected")

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

        except Exception as e:
            state.connected = False
            if not stop.is_set():
                log.debug(f"WebSocket disconnected: {e}")
                await asyncio.sleep(2.0)

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

    # Initial greeting (first boot with empty chat)
    if not state.transcripts:
        try:
            from config.settings import load_settings as _load_greeting
            _gcfg = _load_greeting().get("character", {})
            if _gcfg.get("greeting_enabled", True) and _gcfg.get("greeting"):
                state.push_transcript("assistant", _gcfg["greeting"])
                state.trigger_chat_peek(time.time(), duration=6.0)  # longer for greeting
                log.info("Greeting shown: %s", _gcfg["greeting"][:40])
        except Exception:
            pass

    start_time = time.time()
    last_wifi_check = 0.0
    frame_count = 0

    while not stop.is_set():
        frame_start = time.time()
        state.time = frame_start
        state.dt = interval
        frame_count += 1

        # Poll hardware button (Whisplay single button on Pi)
        # When menu/overlay is open, skip double-tap detection for instant response
        if hasattr(backend, '_board') and backend._board is not None:
            _instant = (renderer.menu.open or state.pairing_mode or
                        state.shutdown_confirm)
            for btn in _poll_whisplay_button(backend._board, state, instant_tap=_instant):
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

        # Update spacebar hold progress for desktop simulation
        if state.button_pressed and _desktop_press_time[0] > 0:
            state.button_hold = (time.time() - _desktop_press_time[0]) / SHUTDOWN_THRESHOLD

        # Check desktop double-tap timer expiry
        if _desktop_waiting_double[0] and (frame_start - _desktop_first_release_time[0]) >= SHORT_PRESS_THRESHOLD:
            _desktop_waiting_double[0] = False
            _desktop_first_release_time[0] = 0.0
            _emit_button_event("short_press", state)
            if button_handler:
                button_handler("short_press")

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

        global _thinking_since, _listening_since, _speaking_since

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

        # Frame timing
        elapsed = time.time() - frame_start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


async def _main(args: argparse.Namespace) -> None:
    # Detect platform
    try:
        from hw.detect import IS_PI
    except ImportError:
        IS_PI = False

    use_pygame = not IS_PI
    if args.backend == "pygame":
        use_pygame = True
    elif args.backend == "whisplay":
        use_pygame = False

    backend = _create_backend(use_pygame, args.scale)
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
            # Cycle: face -> chat_drawer -> chat_full -> face
            views = ["face", "chat_drawer", "chat_full"]
            idx = views.index(state.view) if state.view in views else 0
            state.view = views[(idx + 1) % len(views)]
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

    # Spacebar hold simulation for desktop (mimics hardware button state machine)
    def _on_space_press():
        now = time.time()
        if _desktop_waiting_double[0]:
            # Second press within double-tap window
            _desktop_waiting_double[0] = False
            _desktop_first_release_time[0] = 0.0
            _desktop_press_time[0] = 0.0
            state.button_pressed = False
            state.button_hold = 0.0
            _emit_button_event("double_tap", state)
            _on_button("double_tap")
            return
        if not state.button_pressed:
            _desktop_press_time[0] = now
            state.button_pressed = True
            state.button_hold = 0.0

    def _on_space_release():
        if state.button_pressed:
            hold = time.time() - _desktop_press_time[0]
            state.button_pressed = False
            state.button_hold = 0.0
            _in_menu = menu.open or state.pairing_mode or state.shutdown_confirm
            event = _classify_release(hold, instant_tap=_in_menu)
            if event:
                _desktop_press_time[0] = 0.0
                _emit_button_event(event, state)
                _on_button(event)
            elif _in_menu:
                # In menu/overlay: fire instantly, no double-tap wait
                _desktop_press_time[0] = 0.0
                _emit_button_event("short_press", state)
                _on_button("short_press")
            else:
                # Normal: start double-tap timer
                _desktop_waiting_double[0] = True
                _desktop_first_release_time[0] = time.time()
                _desktop_press_time[0] = 0.0

    if hasattr(backend, "set_button_callbacks"):
        backend.set_button_callbacks(_on_space_press, _on_space_release)

    # Hardware button handler (Whisplay single button)
    #   short_press → cycle views (face/drawer/chat) or navigate in menu
    #   double_tap  → push-to-talk (recording — needs server.py integration)
    #   long_press  → menu open / select
    #   sleep       → enter sleep mode
    #   shutdown    → shutdown Pi (with confirmation countdown)
    def _on_button(btn: str) -> None:
        # Any button press during sleep wakes the device
        if state.state == "SLEEPING" and btn not in ("sleep", "shutdown"):
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Wake from sleep (button press)")
            return

        # Any button press during shutdown countdown cancels it
        if state.shutdown_confirm:
            state.shutdown_confirm = False
            state._shutdown_at = 0.0
            log.info("Shutdown cancelled (button press)")
            return

        # Pairing request: short press = approve (show PIN), long press = deny
        if state.pairing_request:
            if btn in ("short_press", "double_tap"):
                state.pairing_request = False
                state.pairing_approved = True
                state.pairing_mode = True  # show the PIN
                log.info(f"Pairing approved for {state.pairing_request_from}")
            elif btn == "long_press":
                state.pairing_request = False
                state.pairing_denied = True
                log.info(f"Pairing denied for {state.pairing_request_from}")
            return

        # Dismiss pairing overlay on any button press
        if state.pairing_mode:
            state.pairing_mode = False
            log.info("Pairing mode dismissed")
            return

        if menu.open:
            if btn == "short_press":
                menu.navigate(1)   # tap = next (down)
            elif btn == "medium_press":
                menu.navigate(-1)  # brief hold = previous (up)
            elif btn == "double_tap":
                menu.back()        # double-tap = back/close
            elif btn == "long_press":
                menu.select(state) # long hold = select
            elif btn in ("sleep", "shutdown"):
                menu.open = False
                log.info(f"Menu force-closed ({btn})")
            return

        # While actively listening, ANY short press or double_tap stops recording
        if state.state == "LISTENING" and btn in ("short_press", "double_tap"):
            ws_send({"type": "button", "button": "release"})
            log.info("Push-to-talk: stop recording (%s)", btn)
            return

        # While speaking, ANY short press or double_tap cancels playback
        if state.state == "SPEAKING" and btn in ("short_press", "double_tap"):
            ws_send({"type": "button", "button": "press"})
            # Also stop local playback if running
            try:
                from core.audio import stop_playback
                stop_playback()
            except Exception:
                pass
            state.speaking = False
            state.amplitude = 0.0
            state.state = "IDLE"
            state.mood = "neutral"
            log.info("Push-to-talk: cancel speaking (%s)", btn)
            return

        if btn == "short_press":
            # Cycle views: face -> chat_drawer -> chat_full -> face
            views = ["face", "chat_drawer", "chat_full"]
            idx = views.index(state.view) if state.view in views else 0
            state.view = views[(idx + 1) % len(views)]
            log.info(f"View: {state.view}")
        elif btn == "double_tap":
            # Push-to-talk: only from face view in IDLE state
            if state.view != "face":
                log.debug("Talk ignored — not on face view (view=%s)", state.view)
            elif state.state != "IDLE":
                log.debug("Talk ignored — not idle (state=%s)", state.state)
            else:
                # Start listening — send press to server
                ws_send({"type": "button", "button": "press"})
                state.state = "LISTENING"
                state.mood = "listening"
                state.view = "face"  # ensure face view during talk
                log.info("Push-to-talk: start recording (double tap → server)")
        elif btn == "long_press":
            menu.open = True
            log.info("Menu opened (long press)")
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
        led.off()
        backend.cleanup()
        log.info("Display service stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Voxel PIL Display Service")
    parser.add_argument("--url", type=str, default=None,
                        help="WebSocket server URL (e.g. ws://localhost:8080)")
    parser.add_argument("--scale", type=int, default=1,
                        help="Preview window scale factor (default: 1, true 1:1 with Pi LCD)")
    parser.add_argument("--backend", choices=["auto", "pygame", "whisplay"], default="auto",
                        help="Output backend (default: auto-detect)")
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
