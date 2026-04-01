"""Tests for the unified button state machine (_poll_button_unified).

Covers all button interaction paths: taps, hold-to-record, recording
release/cancel, menu navigation, sleep, shutdown, and state blocking.
"""

from __future__ import annotations

import time

import pytest

from display.state import DisplayState
from display.service import (
    _poll_button_unified,
    _btn_reset,
    _btn_enter_menu,
    _btn_exit_menu,
    TAP_THRESHOLD,
    RECORD_START_THRESHOLD,
    RECORD_MIN_DURATION,
    MENU_OPEN_THRESHOLD,
    SLEEP_THRESHOLD,
    SHUTDOWN_THRESHOLD,
    MENU_TAP_THRESHOLD,
    MENU_SELECT_THRESHOLD,
    MENU_IDLE_TIMEOUT,
)

# We need to manipulate the module-level _btn_press_start and _btn_state
# directly for precise timing tests.
import display.service as svc


# ── Helpers ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_button():
    """Reset the button state machine before every test."""
    _btn_reset()
    yield
    _btn_reset()


def _make_state(**overrides) -> DisplayState:
    """Create a DisplayState with sensible defaults for button tests."""
    s = DisplayState()
    s.time = time.time()
    s.dt = 0.033
    s.view = "face"
    s.state = "IDLE"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ── 1. Tap (short press < 400ms, release) ──────────────────────────────────


def test_tap_from_face_produces_short_tap():
    """Press and release within TAP_THRESHOLD produces 'short_tap'."""
    state = _make_state(view="face", state="IDLE")

    # Press
    events = _poll_button_unified(True, state, in_menu=False)
    assert events == [], "Press alone should not emit events"
    assert state.button_pressed is True

    # Release quickly (simulate short hold by not advancing time significantly)
    # _btn_press_start was just set, so hold_time ~ 0
    events = _poll_button_unified(False, state, in_menu=False)
    assert "short_tap" in events, f"Expected 'short_tap', got {events}"
    assert state.button_pressed is False
    assert state.button_hold == 0.0


def test_tap_from_chat_produces_short_tap():
    """Tap from chat view also produces 'short_tap'."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)
    events = _poll_button_unified(False, state, in_menu=False)
    assert "short_tap" in events


def test_tap_sets_button_flash():
    """Short tap should set button_flash to 'short_press'."""
    state = _make_state(view="face", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)
    _poll_button_unified(False, state, in_menu=False)
    assert state.button_flash == "short_press"
    assert state._button_flash_until > time.time()


# ── 2. Hold from face view > 400ms → recording ─────────────────────────────


def test_hold_from_face_starts_recording():
    """Hold from face view past RECORD_START_THRESHOLD starts recording."""
    state = _make_state(view="face", state="IDLE")

    # Press
    _poll_button_unified(True, state, in_menu=False)

    # Simulate time passing beyond record threshold
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "start_recording" in events, f"Expected 'start_recording', got {events}"
    assert svc._btn_state == "RECORDING"


def test_recording_only_starts_from_face_idle():
    """Recording should NOT start from chat view or non-IDLE state."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "start_recording" not in events, "Should not start recording from chat view"


def test_recording_not_from_face_thinking():
    """Recording should NOT start when state is THINKING (not IDLE)."""
    state = _make_state(view="face", state="THINKING")

    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "start_recording" not in events, "Should not start recording during THINKING"


# ── 3. Release during RECORDING ────────────────────────────────────────────


def test_release_recording_after_min_duration_stops():
    """Release after min recording duration produces 'stop_recording'."""
    state = _make_state(view="face", state="IDLE")

    # Press and enter recording
    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)
    _poll_button_unified(True, state, in_menu=False)  # triggers start_recording
    assert svc._btn_state == "RECORDING"

    # Simulate recording for longer than RECORD_MIN_DURATION
    svc._btn_recording_start = time.time() - (RECORD_MIN_DURATION + 0.1)

    events = _poll_button_unified(False, state, in_menu=False)
    assert "stop_recording" in events, f"Expected 'stop_recording', got {events}"
    assert state.button_pressed is False


def test_release_recording_before_min_duration_cancels():
    """Release before min recording duration produces 'cancel_recording'."""
    state = _make_state(view="face", state="IDLE")

    # Press and enter recording
    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)
    _poll_button_unified(True, state, in_menu=False)  # triggers start_recording
    assert svc._btn_state == "RECORDING"

    # Recording just started — release immediately (< RECORD_MIN_DURATION)
    # _btn_recording_start was just set to now, so duration ~ 0
    events = _poll_button_unified(False, state, in_menu=False)
    assert "cancel_recording" in events, f"Expected 'cancel_recording', got {events}"


# ── 4. Recording blocks menu/sleep/shutdown ─────────────────────────────────


def test_recording_blocks_sleep_and_shutdown():
    """While in RECORDING state, holding longer should NOT trigger sleep or shutdown."""
    state = _make_state(view="face", state="IDLE")

    # Enter recording
    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (RECORD_START_THRESHOLD + 0.1)
    _poll_button_unified(True, state, in_menu=False)  # triggers start_recording
    assert svc._btn_state == "RECORDING"

    # Hold for much longer than shutdown threshold — still in RECORDING
    svc._btn_press_start = time.time() - (SHUTDOWN_THRESHOLD + 1.0)
    svc._btn_recording_start = time.time() - (SHUTDOWN_THRESHOLD + 0.5)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "shutdown" not in events, "Recording should block shutdown"
    assert "sleep" not in events, "Recording should block sleep"
    assert "menu_open" not in events, "Recording should block menu"
    assert svc._btn_state == "RECORDING", "Should remain in RECORDING state"


# ── 5. Hold from chat view thresholds ───────────────────────────────────────


def test_hold_from_chat_opens_menu():
    """Hold > 1s from chat view (non-face, non-recording) → menu_open."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)

    # Advance past record threshold (0.4s) without recording (chat view),
    # then past menu threshold (1.0s)
    svc._btn_press_start = time.time() - (MENU_OPEN_THRESHOLD + 0.1)
    # Need to set _btn_fired_record so that the code path falls through
    # to the menu check. The code checks hold_time >= RECORD_START_THRESHOLD
    # first, finds non-face view, then checks >= MENU_OPEN_THRESHOLD.
    svc._btn_fired_record = False

    events = _poll_button_unified(True, state, in_menu=False)
    assert "menu_open" in events, f"Expected 'menu_open', got {events}"


def test_hold_triggers_sleep():
    """Hold > 5s from non-face view → sleep."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)

    # Jump past sleep threshold
    svc._btn_press_start = time.time() - (SLEEP_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "sleep" in events, f"Expected 'sleep', got {events}"


def test_hold_triggers_shutdown():
    """Hold > 10s → shutdown."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)

    # Jump past shutdown threshold
    svc._btn_press_start = time.time() - (SHUTDOWN_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "shutdown" in events, f"Expected 'shutdown', got {events}"


def test_threshold_events_fire_only_once():
    """Sleep and shutdown should fire only once even if button stays held."""
    state = _make_state(view="chat", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (SHUTDOWN_THRESHOLD + 0.1)

    events1 = _poll_button_unified(True, state, in_menu=False)
    assert "shutdown" in events1

    # Reset state since shutdown calls _btn_reset
    # After shutdown fires, the state machine resets to IDLE.
    # A new press should not immediately re-fire shutdown.
    _poll_button_unified(True, state, in_menu=False)
    events2 = _poll_button_unified(True, state, in_menu=False)
    assert "shutdown" not in events2, "Shutdown should not fire again immediately"


# ── 6. Menu navigation ─────────────────────────────────────────────────────


def test_menu_tap_produces_menu_next():
    """Short tap inside menu produces 'menu_next'."""
    state = _make_state(view="face", state="IDLE")

    # Enter menu mode
    _btn_enter_menu(state)
    assert svc._btn_state == "IN_MENU_IDLE"

    # Press
    events = _poll_button_unified(True, state, in_menu=True)
    assert events == []

    # Release quickly (within MENU_TAP_THRESHOLD)
    events = _poll_button_unified(False, state, in_menu=True)
    assert "menu_next" in events, f"Expected 'menu_next', got {events}"


def test_menu_hold_produces_menu_select():
    """Hold > 500ms inside menu produces 'menu_select'."""
    state = _make_state(view="face", state="IDLE")

    _btn_enter_menu(state)

    # Press
    _poll_button_unified(True, state, in_menu=True)

    # Hold past select threshold
    svc._btn_press_start = time.time() - (MENU_SELECT_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=True)
    assert "menu_select" in events, f"Expected 'menu_select', got {events}"


def test_menu_idle_timeout():
    """Menu auto-closes after MENU_IDLE_TIMEOUT seconds of no input."""
    state = _make_state(view="face", state="IDLE")

    _btn_enter_menu(state)

    # Simulate time passing beyond idle timeout
    svc._btn_menu_last_input = time.time() - (MENU_IDLE_TIMEOUT + 0.1)

    events = _poll_button_unified(False, state, in_menu=True)
    assert "menu_timeout" in events, f"Expected 'menu_timeout', got {events}"
    # Should exit menu mode
    assert svc._btn_state == "IDLE"


def test_menu_select_fires_only_once():
    """Menu select should not re-fire if button stays held."""
    state = _make_state(view="face", state="IDLE")

    _btn_enter_menu(state)
    _poll_button_unified(True, state, in_menu=True)
    svc._btn_press_start = time.time() - (MENU_SELECT_THRESHOLD + 0.1)

    events1 = _poll_button_unified(True, state, in_menu=True)
    assert "menu_select" in events1

    # Continue holding — should not re-fire
    events2 = _poll_button_unified(True, state, in_menu=True)
    assert "menu_select" not in events2


def test_menu_entered_externally():
    """If in_menu=True but button was not in menu state, it syncs."""
    state = _make_state(view="face", state="IDLE")

    # Button is in IDLE state but menu is opened externally (e.g. keyboard)
    assert svc._btn_state == "IDLE"
    events = _poll_button_unified(False, state, in_menu=True)
    # Should have transitioned to IN_MENU_IDLE
    assert svc._btn_state == "IN_MENU_IDLE"


def test_menu_closed_externally():
    """If in_menu=False but button was in menu state, it syncs."""
    state = _make_state(view="face", state="IDLE")

    _btn_enter_menu(state)
    assert svc._btn_state == "IN_MENU_IDLE"

    # Menu closed externally
    _poll_button_unified(False, state, in_menu=False)
    assert svc._btn_state == "IDLE"


# ── 7. Button hold progress ────────────────────────────────────────────────


def test_button_hold_progress_normalized():
    """button_hold should be normalized to SHUTDOWN_THRESHOLD (10s)."""
    state = _make_state(view="face", state="IDLE")

    _poll_button_unified(True, state, in_menu=False)

    # Simulate a hold of 0.3s — below any threshold that resets state,
    # but enough to see the normalized progress value.
    svc._btn_press_start = time.time() - 0.3

    _poll_button_unified(True, state, in_menu=False)
    # 0.3 / 10.0 = 0.03
    expected = 0.3 / SHUTDOWN_THRESHOLD
    assert abs(state.button_hold - expected) < 0.05, (
        f"Expected ~{expected:.3f}, got {state.button_hold}"
    )


# ── 8. _btn_reset clears all state ─────────────────────────────────────────


def test_btn_reset_clears_all():
    """_btn_reset() should clear all button state machine globals."""
    svc._btn_state = "RECORDING"
    svc._btn_press_start = 12345.0
    svc._btn_recording_start = 12345.0
    svc._btn_fired_record = True
    svc._btn_fired_menu = True
    svc._btn_fired_sleep = True
    svc._btn_fired_shutdown = True

    _btn_reset()

    assert svc._btn_state == "IDLE"
    assert svc._btn_press_start == 0.0
    assert svc._btn_recording_start == 0.0
    assert svc._btn_fired_record is False
    assert svc._btn_fired_menu is False
    assert svc._btn_fired_sleep is False
    assert svc._btn_fired_shutdown is False


# ── 9. No events when idle and not pressed ──────────────────────────────────


def test_idle_no_press_no_events():
    """No events should be emitted when button is IDLE and not pressed."""
    state = _make_state(view="face", state="IDLE")
    events = _poll_button_unified(False, state, in_menu=False)
    assert events == []


def test_press_alone_no_events():
    """Initial press alone should not emit any events (just transitions to PRESSED)."""
    state = _make_state(view="face", state="IDLE")
    events = _poll_button_unified(True, state, in_menu=False)
    assert events == []
    assert svc._btn_state == "PRESSED"
    assert state.button_pressed is True


# ── 10. Hold past record threshold from face in non-IDLE state → menu ──────


def test_face_non_idle_hold_opens_menu_at_1s():
    """From face view but NOT IDLE (e.g. SPEAKING), hold >1s opens menu."""
    state = _make_state(view="face", state="SPEAKING")

    _poll_button_unified(True, state, in_menu=False)
    svc._btn_press_start = time.time() - (MENU_OPEN_THRESHOLD + 0.1)

    events = _poll_button_unified(True, state, in_menu=False)
    assert "menu_open" in events, f"Expected 'menu_open' from non-IDLE face view, got {events}"
    assert "start_recording" not in events


# ── 11. _btn_enter_menu / _btn_exit_menu ────────────────────────────────────


def test_btn_enter_exit_menu():
    """_btn_enter_menu sets state to IN_MENU_IDLE, _btn_exit_menu back to IDLE."""
    state = _make_state()

    _btn_enter_menu(state)
    assert svc._btn_state == "IN_MENU_IDLE"
    assert state.button_pressed is False
    assert state.button_hold == 0.0

    _btn_exit_menu()
    assert svc._btn_state == "IDLE"
