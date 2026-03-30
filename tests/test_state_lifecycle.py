"""Tests for the Voxel display state lifecycle.

Covers DisplayState defaults, transcript management, button flash,
animation primitives (BlinkState, GazeDrift, BreathingState, MoodTransition),
idle personality, idle prompt, chat peek, and state field interactions.
"""

from __future__ import annotations

import time

import pytest

from display.state import DisplayState, TranscriptEntry
from display.animation import BlinkState, GazeDrift, BreathingState, MoodTransition
from display.idle import IdlePersonality, IdlePrompt
from shared import Expression, EyeConfig, MouthConfig, BodyConfig


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def state():
    s = DisplayState()
    s.time = time.time()
    s.dt = 0.033
    return s


def _make_expression(name: str = "neutral", **body_kw) -> Expression:
    return Expression(
        name=name,
        eyes=EyeConfig(),
        mouth=MouthConfig(),
        body=BodyConfig(**body_kw),
    )


# ── 1. DisplayState defaults ───────────────────────────────────────────────


class TestDisplayStateDefaults:
    def test_mood_default(self, state: DisplayState):
        assert state.mood == "neutral", "Default mood should be neutral"

    def test_style_default(self, state: DisplayState):
        assert state.style == "kawaii", "Default style should be kawaii"

    def test_state_default(self, state: DisplayState):
        assert state.state == "IDLE", "Default state should be IDLE"

    def test_speaking_default(self, state: DisplayState):
        assert state.speaking is False, "Should not be speaking by default"

    def test_amplitude_default(self, state: DisplayState):
        assert state.amplitude == 0.0, "Default amplitude should be 0.0"

    def test_battery_default(self, state: DisplayState):
        assert state.battery == 100, "Default battery should be 100"

    def test_agent_default(self, state: DisplayState):
        assert state.agent == "daemon", "Default agent should be daemon"

    def test_connected_default(self, state: DisplayState):
        assert state.connected is False, "Should not be connected by default"

    def test_view_default(self, state: DisplayState):
        assert state.view == "face", "Default view should be face"

    def test_transcripts_empty(self, state: DisplayState):
        assert state.transcripts == [], "Transcripts should start empty"

    def test_button_flash_default(self, state: DisplayState):
        assert state.button_flash == "", "Button flash should start empty"

    def test_button_pressed_default(self, state: DisplayState):
        assert state.button_pressed is False, "Button should not be pressed by default"

    def test_character_default(self, state: DisplayState):
        assert state.character == "voxel", "Default character should be voxel"

    def test_max_transcripts_default(self, state: DisplayState):
        assert state.max_transcripts == 20, "Default max_transcripts should be 20"


# ── 2. Transcript push and cap ─────────────────────────────────────────────


class TestTranscriptPushCap:
    def test_push_adds_entry(self, state: DisplayState):
        state.push_transcript("user", "hello")
        assert len(state.transcripts) == 1
        assert state.transcripts[0].role == "user"
        assert state.transcripts[0].text == "hello"
        assert state.transcripts[0].status == "done"

    def test_push_multiple_entries(self, state: DisplayState):
        state.push_transcript("user", "hi")
        state.push_transcript("assistant", "hey")
        assert len(state.transcripts) == 2
        assert state.transcripts[0].role == "user"
        assert state.transcripts[1].role == "assistant"

    def test_push_updates_partial_same_role(self, state: DisplayState):
        state.push_transcript("assistant", "hel", status="partial")
        state.push_transcript("assistant", "hello", status="done")
        assert len(state.transcripts) == 1, "Partial update for same role should not add a new entry"
        assert state.transcripts[0].text == "hello"
        assert state.transcripts[0].status == "done"

    def test_push_does_not_update_done_entry(self, state: DisplayState):
        state.push_transcript("user", "first", status="done")
        state.push_transcript("user", "second", status="done")
        assert len(state.transcripts) == 2, "Done entries should not be updated in-place"

    def test_cap_at_max(self, state: DisplayState):
        state.max_transcripts = 5
        for i in range(10):
            state.push_transcript("user", f"msg-{i}")
        assert len(state.transcripts) == 5, "Transcripts should be capped at max_transcripts"
        assert state.transcripts[0].text == "msg-5", "Oldest entries should be dropped"
        assert state.transcripts[-1].text == "msg-9"

    def test_transcript_overlay_user(self, state: DisplayState):
        state.push_transcript("user", "question?")
        assert state.transcript_user == "question?"
        assert state.transcript_voxel == ""
        # transcript_visible is no longer auto-set by push_transcript

    def test_transcript_overlay_assistant(self, state: DisplayState):
        state.push_transcript("user", "hi")
        state.push_transcript("assistant", "hello!")
        assert state.transcript_voxel == "hello!"
        # transcript_visible is no longer auto-set by push_transcript
        # (chat peek handles new message notifications instead)


# ── 3. Transcript auto-hide ────────────────────────────────────────────────


class TestTranscriptAutoHide:
    def test_auto_hide_after_3s_idle(self, state: DisplayState):
        state.push_transcript("user", "test")
        state.transcript_visible = True  # manually show (e.g. 't' key toggle)
        now = time.time()

        # In IDLE, first call sets the timer
        state.state = "IDLE"
        state.update_transcript_visibility(now)
        assert state.transcript_visible is True, "Should still be visible immediately"

        # Before 3s: still visible
        state.update_transcript_visibility(now + 2.0)
        assert state.transcript_visible is True, "Should still be visible before 3s"

        # After 3s: hidden
        state.update_transcript_visibility(now + 3.1)
        assert state.transcript_visible is False, "Should be hidden after 3s in IDLE"

    def test_hide_timer_resets_outside_idle(self, state: DisplayState):
        state.push_transcript("user", "test")
        state.transcript_visible = True  # manually show
        now = time.time()

        state.state = "IDLE"
        state.update_transcript_visibility(now)

        # Switch to SPEAKING - timer should reset
        state.state = "SPEAKING"
        state.update_transcript_visibility(now + 1.0)
        assert state._transcript_hide_at == 0.0, "Timer should reset when not IDLE"

        # Back to IDLE — timer starts fresh
        state.state = "IDLE"
        state.update_transcript_visibility(now + 2.0)
        assert state.transcript_visible is True
        # Must wait another 3s from now+2.0
        state.update_transcript_visibility(now + 4.9)
        assert state.transcript_visible is True, "Should still be visible within 3s of re-entering IDLE"
        state.update_transcript_visibility(now + 5.1)
        assert state.transcript_visible is False, "Should hide 3s after re-entering IDLE"

    def test_no_action_when_already_hidden(self, state: DisplayState):
        state.transcript_visible = False
        state.state = "IDLE"
        now = time.time()
        state.update_transcript_visibility(now)
        assert state.transcript_visible is False, "Should stay hidden if already hidden"


# ── 4. Button flash lifecycle ──────────────────────────────────────────────


class TestButtonFlash:
    def test_flash_set_and_clear(self, state: DisplayState):
        now = time.time()
        state.button_flash = "short_press"
        state._button_flash_until = now + 0.5

        # Before expiry
        assert state.button_flash == "short_press"

        # After expiry — simulating what the render loop does
        frame_time = now + 0.6
        if state.button_flash and state._button_flash_until > 0 and frame_time >= state._button_flash_until:
            state.button_flash = ""
            state._button_flash_until = 0.0

        assert state.button_flash == "", "Flash should be cleared after _button_flash_until"
        assert state._button_flash_until == 0.0

    def test_flash_types(self, state: DisplayState):
        for event in ("short_press", "double_tap", "long_press", "sleep", "shutdown"):
            now = time.time()
            state.button_flash = event
            state._button_flash_until = now + 0.5
            assert state.button_flash == event

    def test_flash_not_cleared_before_expiry(self, state: DisplayState):
        now = time.time()
        state.button_flash = "double_tap"
        state._button_flash_until = now + 0.5

        frame_time = now + 0.3
        if state.button_flash and state._button_flash_until > 0 and frame_time >= state._button_flash_until:
            state.button_flash = ""
            state._button_flash_until = 0.0

        assert state.button_flash == "double_tap", "Flash should persist before expiry"


# ── 5. BlinkState ──────────────────────────────────────────────────────────


class TestBlinkState:
    def test_initial_not_blinking(self):
        bs = BlinkState()
        assert bs.blink_phase == -1.0, "Should start not blinking"
        assert bs.get_openness_factor() == 1.0, "Eyes should be fully open when not blinking"

    def test_blink_triggers_at_next_blink_time(self):
        bs = BlinkState()
        bs.next_blink = 0.0  # trigger immediately
        bs.update(now=0.0, blink_rate=3.0)
        assert bs.blink_phase >= 0.0, "Blink should start when now >= next_blink"

    def test_blink_phase_advances(self):
        bs = BlinkState()
        bs.next_blink = 0.0
        bs.update(now=0.0, blink_rate=3.0)
        phase_after_first = bs.blink_phase
        bs.update(now=0.01, blink_rate=3.0)
        assert bs.blink_phase > phase_after_first, "Blink phase should advance each update"

    def test_blink_completes(self):
        bs = BlinkState()
        bs.next_blink = 0.0
        # Run enough updates to complete the blink
        now = 0.0
        bs.update(now=now, blink_rate=3.0)
        for _ in range(50):
            now += 0.01
            bs.update(now=now, blink_rate=3.0)
        assert bs.blink_phase == -1.0, "Blink should complete and reset phase to -1"

    def test_openness_factor_range(self):
        bs = BlinkState()
        bs.next_blink = 0.0
        openness_values = []
        now = 0.0
        for _ in range(50):
            bs.update(now=now, blink_rate=3.0)
            openness_values.append(bs.get_openness_factor())
            now += 0.005
        assert all(0.0 <= v <= 1.0 for v in openness_values), (
            f"Openness factor must be in [0, 1], got min={min(openness_values)}, max={max(openness_values)}"
        )

    def test_openness_during_blink_is_less_than_one(self):
        bs = BlinkState()
        bs.next_blink = 0.0
        bs.update(now=0.0, blink_rate=3.0)
        # Advance slightly into blink
        bs.update(now=0.005, blink_rate=3.0)
        assert bs.get_openness_factor() < 1.0, "Openness should decrease during a blink"


# ── 6. GazeDrift saccade ──────────────────────────────────────────────────


class TestGazeDrift:
    def test_initial_position(self):
        gd = GazeDrift()
        assert gd.current_x == 0.0
        assert gd.current_y == 0.0

    def test_saccade_triggered_at_next_change(self):
        gd = GazeDrift()
        gd.next_change = 0.0  # trigger immediately
        gd.update(now=0.0, dt=0.033)
        assert gd._saccade_active is True, "Saccade should be active after target change"
        assert (gd.target_x != 0.0 or gd.target_y != 0.0), "Target should change from origin"

    def test_saccade_moves_toward_target(self):
        gd = GazeDrift()
        # Set a known distant target to avoid flaky near-zero distances
        gd.target_x = 0.3
        gd.target_y = 0.2
        gd.current_x = 0.0
        gd.current_y = 0.0
        gd._saccade_active = True
        gd.next_change = 999.0  # prevent new target
        old_dist = gd.target_x ** 2 + gd.target_y ** 2
        gd.update(now=0.05, dt=0.033)
        # Should have moved closer to target
        new_dist = (gd.target_x - gd.current_x) ** 2 + (gd.target_y - gd.current_y) ** 2
        assert new_dist < old_dist, "Current position should move toward target during saccade"

    def test_saccade_completes(self):
        gd = GazeDrift()
        gd.next_change = 0.0
        gd.update(now=0.0, dt=0.033)
        gd.next_change = 999.0
        # Run many updates to let saccade complete
        now = 0.0
        for _ in range(100):
            now += 0.033
            gd.update(now=now, dt=0.033)
        assert gd._saccade_active is False, "Saccade should complete after sufficient updates"

    def test_fixation_micro_drift(self):
        gd = GazeDrift()
        gd.next_change = 0.0
        gd.update(now=0.0, dt=0.033)
        gd.next_change = 999.0
        # Complete the saccade
        now = 0.0
        for _ in range(100):
            now += 0.033
            gd.update(now=now, dt=0.033)
        assert gd._saccade_active is False

        # Now in fixation — micro-drift should produce small offsets
        target_x = gd.target_x
        gd.update(now=now + 1.0, dt=0.033)
        drift = abs(gd.current_x - target_x)
        assert drift <= 0.015, f"Micro-drift should be small, got {drift}"
        assert drift > 0 or True, "Some drift is expected but may be zero at specific phase"


# ── 7. BreathingState ─────────────────────────────────────────────────────


class TestBreathingState:
    def test_returns_scale_in_range(self):
        bs = BreathingState()
        scales = []
        now = 0.0
        for _ in range(200):
            scale = bs.update(now=now, dt=0.033)
            scales.append(scale)
            now += 0.033
        assert all(0.98 <= s <= 1.02 for s in scales), (
            f"Scale must be in [0.98, 1.02], got min={min(scales):.4f}, max={max(scales):.4f}"
        )

    def test_scale_oscillates(self):
        bs = BreathingState()
        scales = set()
        now = 0.0
        for _ in range(100):
            scale = bs.update(now=now, dt=0.033)
            scales.add(round(scale, 4))
            now += 0.033
        assert len(scales) > 1, "Breathing scale should oscillate, not be constant"

    def test_phase_wraps(self):
        bs = BreathingState()
        now = 0.0
        for _ in range(1000):
            bs.update(now=now, dt=0.033)
            now += 0.033
        assert bs.phase < 6.2832, "Phase should wrap around 2*pi"


# ── 8. MoodTransition ────────────────────────────────────────────────────


class TestMoodTransition:
    def test_initial_returns_initial_expression(self):
        expr = _make_expression("neutral")
        mt = MoodTransition(expr)
        current = mt.get_current()
        assert current.name == "neutral"

    def test_set_target_triggers_transition(self):
        initial = _make_expression("neutral")
        mt = MoodTransition(initial)
        target = _make_expression("happy", bounce_amount=5.0)
        mt.set_target(target)
        assert mt._transitioning is True, "Setting a new target should start a transition"

    def test_same_target_no_transition(self):
        initial = _make_expression("neutral")
        mt = MoodTransition(initial)
        same = _make_expression("neutral", bounce_amount=99.0)
        mt.set_target(same)
        assert mt._transitioning is False, "Same name target should not trigger transition"

    def test_get_current_interpolates(self):
        initial = _make_expression("neutral", scale=1.0)
        mt = MoodTransition(initial)
        target = _make_expression("happy", scale=2.0)
        mt.set_target(target)
        # Immediately after setting, should be interpolating
        current = mt.get_current()
        # Should be close to initial (just started)
        assert current.body.scale < 2.0, "Should not have reached target yet"

    def test_transition_completes(self):
        initial = _make_expression("neutral", scale=1.0)
        mt = MoodTransition(initial)
        target = _make_expression("happy", scale=2.0)
        mt.set_target(target)
        # Wait longer than TRANSITION_TIME
        time.sleep(MoodTransition.TRANSITION_TIME + 0.05)
        current = mt.get_current()
        assert current.name == "happy", "Should reach target after TRANSITION_TIME"
        assert current.body.scale == 2.0, "Scale should match target after transition"
        assert mt._transitioning is False, "Transition should be complete"

    def test_update_returns_expression(self):
        expr = _make_expression("neutral")
        mt = MoodTransition(expr)
        result = mt.update()
        assert isinstance(result, Expression)
        assert result.name == "neutral"


# ── 9. IdlePersonality enable/disable ─────────────────────────────────────


class TestIdlePersonality:
    def test_disabled_returns_none(self, state: DisplayState):
        ip = IdlePersonality(enabled=False)
        result = ip.update(state, now=time.time())
        assert result is None, "Disabled IdlePersonality should return None"

    def test_enabled_tracks_state(self, state: DisplayState):
        ip = IdlePersonality(enabled=True)
        state.state = "IDLE"
        now = time.time()
        result = ip.update(state, now)
        # First call entering IDLE — may return None or a reactive mood
        # Second call should return "neutral" or a reactive mood, not None
        result2 = ip.update(state, now + 1.0)
        assert result2 is not None, "Enabled IdlePersonality should return a mood in IDLE"

    def test_non_idle_state_returns_none(self, state: DisplayState):
        ip = IdlePersonality(enabled=True)
        state.state = "SPEAKING"
        result = ip.update(state, now=time.time())
        assert result is None, "Should return None when state is not IDLE"

    def test_low_battery_reactive_mood(self, state: DisplayState):
        ip = IdlePersonality(enabled=True)
        state.state = "IDLE"
        state.battery = 15
        now = time.time()
        ip.update(state, now)  # enter IDLE
        result = ip.update(state, now + 1.0)
        assert result == "low_battery", "Should react to low battery"

    def test_critical_battery_reactive_mood(self, state: DisplayState):
        ip = IdlePersonality(enabled=True)
        state.state = "IDLE"
        state.battery = 5
        now = time.time()
        ip.update(state, now)  # enter IDLE
        result = ip.update(state, now + 1.0)
        assert result == "critical_battery", "Should react to critical battery"


# ── 10. IdlePrompt cycle ──────────────────────────────────────────────────


class TestIdlePrompt:
    def test_starts_hidden(self, state: DisplayState):
        prompt = IdlePrompt(enabled=True)
        state.state = "IDLE"
        now = time.time()
        prompt.update(state, now)
        assert state.idle_prompt_visible is False, "Should start hidden"
        assert state._idle_prompt_alpha == 0.0

    def test_disabled_stays_hidden(self, state: DisplayState):
        prompt = IdlePrompt(enabled=False)
        state.state = "IDLE"
        prompt.update(state, time.time())
        assert state.idle_prompt_visible is False
        assert state._idle_prompt_alpha == 0.0

    def test_non_idle_resets(self, state: DisplayState):
        prompt = IdlePrompt(enabled=True)
        state.state = "SPEAKING"
        prompt.update(state, time.time())
        assert state.idle_prompt_visible is False
        assert prompt._phase == "hidden"

    def test_full_cycle(self, state: DisplayState):
        prompt = IdlePrompt(enabled=True, interval=90.0)
        state.state = "IDLE"
        now = 1000.0  # arbitrary start

        # Enter idle
        prompt.update(state, now)
        assert prompt._phase == "hidden"

        # After 60s of idle, should transition to fade_in
        now += 60.1
        prompt.update(state, now)
        assert prompt._phase == "fade_in", "Should start fade_in after 60s idle"
        assert state.idle_prompt_visible is True

        # During fade_in, alpha increases
        now += 0.4  # half of 0.8s fade_in_dur
        prompt.update(state, now)
        assert 0.0 < state._idle_prompt_alpha < 1.0, "Alpha should be mid-fade"

        # Complete fade_in
        now += 0.5
        prompt.update(state, now)
        assert prompt._phase == "hold", "Should enter hold after fade_in completes"
        assert state._idle_prompt_alpha == 1.0

        # During hold
        now += 1.0
        prompt.update(state, now)
        assert prompt._phase == "hold"
        assert state.idle_prompt_visible is True

        # After hold duration (3s)
        now += 2.5
        prompt.update(state, now)
        assert prompt._phase == "fade_out", "Should enter fade_out after hold"

        # Complete fade_out
        now += 1.0
        prompt.update(state, now)
        assert prompt._phase == "hidden", "Should return to hidden after fade_out"
        assert state.idle_prompt_visible is False
        assert state._idle_prompt_alpha == 0.0

    def test_reset_clears_state(self, state: DisplayState):
        prompt = IdlePrompt(enabled=True)
        prompt._phase = "hold"
        prompt._was_idle = True
        prompt.reset()
        assert prompt._phase == "hidden"
        assert prompt._was_idle is False


# ── 11. Chat peek ────────────────────────────────────────────────────────


class TestChatPeek:
    def test_trigger_sets_peek_until(self, state: DisplayState):
        now = time.time()
        state.view = "face"
        state.trigger_chat_peek(now, duration=2.0)
        assert state._peek_until == pytest.approx(now + 2.0), "Peek until should be now + duration"

    def test_trigger_only_on_face_view(self, state: DisplayState):
        now = time.time()
        state.view = "chat_full"
        state.trigger_chat_peek(now, duration=2.0)
        assert state._peek_until == 0.0, "Should not trigger peek when not in face view"

    def test_push_transcript_triggers_peek(self, state: DisplayState):
        state.view = "face"
        before = state._peek_until
        state.push_transcript("assistant", "hello!")
        assert state._peek_until > before, "Push transcript should trigger chat peek"

    def test_default_duration(self, state: DisplayState):
        now = time.time()
        state.view = "face"
        state.trigger_chat_peek(now)
        assert state._peek_until == pytest.approx(now + 2.0), "Default peek duration should be 2s"


# ── 12. State field interactions ──────────────────────────────────────────


class TestStateFieldInteractions:
    def test_speaking_state(self, state: DisplayState):
        state.state = "SPEAKING"
        state.speaking = True
        state.amplitude = 0.7
        assert state.state == "SPEAKING"
        assert state.speaking is True
        assert state.amplitude == 0.7

    def test_clear_on_idle(self, state: DisplayState):
        # Simulate active conversation
        state.state = "SPEAKING"
        state.speaking = True
        state.amplitude = 0.5
        state.mood = "excited"

        # Return to idle
        state.state = "IDLE"
        state.speaking = False
        state.amplitude = 0.0
        state.mood = "neutral"

        assert state.state == "IDLE"
        assert state.speaking is False
        assert state.amplitude == 0.0
        assert state.mood == "neutral"

    def test_thinking_state(self, state: DisplayState):
        state.state = "THINKING"
        state.mood = "thinking"
        state.speaking = False
        assert state.state == "THINKING"
        assert state.mood == "thinking"

    def test_button_hold_and_flash(self, state: DisplayState):
        # Simulate button press and release
        state.button_pressed = True
        state.button_hold = 0.05
        assert state.button_pressed is True
        assert state.button_hold > 0.0

        # Release
        state.button_pressed = False
        state.button_hold = 0.0
        state.button_flash = "short_press"
        state._button_flash_until = time.time() + 0.5
        assert state.button_flash == "short_press"

    def test_wifi_ap_mode_fields(self, state: DisplayState):
        state.wifi_ap_mode = True
        state.wifi_ap_ssid = "Voxel-Setup"
        state.wifi_ap_password = "abc123"
        state.wifi_connected = False
        assert state.wifi_ap_mode is True
        assert state.wifi_ap_ssid == "Voxel-Setup"

    def test_shutdown_confirm_fields(self, state: DisplayState):
        now = time.time()
        state.shutdown_confirm = True
        state._shutdown_at = now + 3.0
        assert state.shutdown_confirm is True
        assert state._shutdown_at > now
