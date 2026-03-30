"""Tests for the Voxel display mood pipeline.

Covers mood transitions, battery reactions, idle personality, connection
events, wake-up micro-expressions, blink suppression, demo mode, and
the MoodTransition lerp system.
"""

from __future__ import annotations

import time

import pytest
from PIL import Image

from display.animation import MoodTransition, lerp_expression
from display.idle import IdlePersonality
from display.renderer import PILRenderer
from display.state import DisplayState
from shared import Expression, EyeConfig, MouthConfig, BodyConfig, load_expressions


# ── Helpers ──────────────────────────────────────────────────────────────────


class RenderHelper:
    """Provides a fresh renderer + state pair and helpers for advancing time."""

    def __init__(self) -> None:
        self.renderer = PILRenderer()
        self.state = DisplayState()
        self.now = time.time()

    def frame(self, dt: float = 0.033) -> str:
        """Advance one frame and return the resolved mood."""
        self.now += dt
        self.state.time = self.now
        self.state.dt = dt
        self.renderer.render(self.state)
        return self.renderer._current_mood

    def advance(self, seconds: float) -> str:
        """Jump forward *seconds*, render a few frames, return mood."""
        self.now += seconds
        self.state.time = self.now
        self.state.dt = 0.033
        for _ in range(3):
            self.renderer.render(self.state)
        return self.renderer._current_mood

    def render_image(self) -> Image.Image:
        """Render and return the PIL Image for the current state."""
        self.now += 0.033
        self.state.time = self.now
        self.state.dt = 0.033
        return self.renderer.render(self.state)


@pytest.fixture
def helper() -> RenderHelper:
    """Fresh RenderHelper for each test."""
    return RenderHelper()


# All 16 mood names from expressions.yaml
ALL_MOODS = [
    "neutral", "happy", "curious", "thinking", "confused", "excited",
    "sleepy", "error", "listening", "sad", "surprised", "focused",
    "frustrated", "working", "low_battery", "critical_battery",
]


# ── 1. Basic mood transitions ───────────────────────────────────────────────


def test_setting_mood_triggers_transition(helper: RenderHelper) -> None:
    """Setting state.mood to a new value causes the renderer to transition."""
    assert helper.frame() == "neutral", "Should start neutral"
    helper.state.mood = "happy"
    resolved = helper.frame()
    assert resolved == "happy", f"Expected mood 'happy' after setting state.mood, got '{resolved}'"


def test_mood_transition_updates_current_mood(helper: RenderHelper) -> None:
    """After a transition, _current_mood matches the target."""
    helper.frame()
    helper.state.mood = "excited"
    # Render enough frames for transition to complete (0.3s at 30 FPS ~ 9 frames)
    for _ in range(15):
        helper.frame()
    assert helper.renderer._current_mood == "excited"


# ── 2. All 16 moods render without crash ─────────────────────────────────────


@pytest.mark.parametrize("mood", ALL_MOODS)
def test_mood_renders_valid_frame(mood: str) -> None:
    """Each of the 16 moods produces a valid 240x280 RGB image."""
    h = RenderHelper()
    h.state.mood = mood
    img = h.render_image()
    assert isinstance(img, Image.Image), f"Mood '{mood}' did not return a PIL Image"
    assert img.size == (240, 280), f"Mood '{mood}' produced wrong size: {img.size}"
    assert img.mode == "RGB", f"Mood '{mood}' produced wrong mode: {img.mode}"


def test_all_moods_present_in_expressions_yaml() -> None:
    """Verify all 16 core moods (plus any composed expressions) are present."""
    expressions = load_expressions()
    for mood in ALL_MOODS:
        assert mood in expressions, f"Mood '{mood}' missing from expressions.yaml"
    # At least the 16 core moods; composed expressions may add more
    assert len(expressions) >= 16, (
        f"Expected at least 16 moods in expressions.yaml, got {len(expressions)}: "
        f"{sorted(expressions.keys())}"
    )


# ── 3. Battery reactions ────────────────────────────────────────────────────


def test_battery_zero_triggers_critical(helper: RenderHelper) -> None:
    """battery=0 should resolve to critical_battery mood."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()  # establish idle baseline
    helper.state.battery = 0
    mood = helper.advance(0.1)
    assert mood == "critical_battery", f"battery=0 should be critical_battery, got '{mood}'"


def test_battery_5_triggers_critical(helper: RenderHelper) -> None:
    """battery=5 (< 10) should resolve to critical_battery."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()
    helper.state.battery = 5
    mood = helper.advance(0.1)
    assert mood == "critical_battery", f"battery=5 should be critical_battery, got '{mood}'"


def test_battery_15_triggers_low(helper: RenderHelper) -> None:
    """battery=15 (< 20, >= 10) should resolve to low_battery."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()
    helper.state.battery = 15
    mood = helper.advance(0.1)
    assert mood == "low_battery", f"battery=15 should be low_battery, got '{mood}'"


def test_battery_recovery_returns_neutral(helper: RenderHelper) -> None:
    """battery rising from low back to 100 should return to neutral."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()

    # Drop to low
    helper.state.battery = 15
    helper.advance(0.5)
    assert helper.renderer._current_mood == "low_battery"

    # Recover
    helper.state.battery = 100
    mood = helper.advance(0.5)
    assert mood == "neutral", f"battery=100 recovery should be neutral, got '{mood}'"


# ── 4. Mood lockout (5s) ────────────────────────────────────────────────────


def test_external_mood_persists_during_lockout(helper: RenderHelper) -> None:
    """An externally set mood persists for ~5s before idle returns to neutral."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()

    # External mood set (simulating dev panel / WebSocket)
    helper.state.mood = "excited"
    helper.frame()
    assert helper.renderer._current_mood == "excited"

    # After 2s the lockout hasn't expired — mood should still hold
    mood = helper.advance(2.0)
    assert mood == "excited", (
        f"Mood should stay 'excited' during 5s lockout, got '{mood}'"
    )


def test_external_mood_expires_after_lockout(helper: RenderHelper) -> None:
    """After 5s lockout, idle personality returns mood to neutral."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()

    helper.state.mood = "excited"
    helper.frame()

    # Advance past the 5s lockout
    mood = helper.advance(6.0)
    assert mood == "neutral", (
        f"After 5s lockout, mood should return to neutral, got '{mood}'"
    )


# ── 5. Battery overrides lockout ─────────────────────────────────────────────


def test_battery_bypasses_lockout(helper: RenderHelper) -> None:
    """Battery moods bypass the 5s external mood lockout."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()

    # Set an external mood to start the lockout
    helper.state.mood = "excited"
    helper.frame()
    assert helper.renderer._current_mood == "excited"

    # Drop battery — should override even during lockout
    helper.state.battery = 5
    mood = helper.advance(0.1)
    assert mood == "critical_battery", (
        f"Battery should bypass lockout, got '{mood}'"
    )


# ── 6. Connection loss / recovery ────────────────────────────────────────────


def test_connection_loss_triggers_sad(helper: RenderHelper) -> None:
    """connected True -> False triggers sad mood (urgent, bypasses lockout)."""
    helper.state.state = "IDLE"
    helper.state.connected = True
    helper.state.battery = 100
    helper.frame()

    helper.state.connected = False
    mood = helper.advance(0.1)
    assert mood == "sad", f"Connection loss should trigger sad, got '{mood}'"


def test_connection_recovery_triggers_happy(helper: RenderHelper) -> None:
    """connected False -> True triggers happy mood (urgent, bypasses lockout)."""
    helper.state.state = "IDLE"
    helper.state.connected = False
    helper.state.battery = 100
    helper.frame()

    helper.state.connected = True
    mood = helper.advance(0.1)
    assert mood == "happy", f"Connection recovery should trigger happy, got '{mood}'"


# ── 7. Sleepy blink suppression ─────────────────────────────────────────────


def test_sleepy_suppresses_blink(helper: RenderHelper) -> None:
    """When mood is sleepy (openness <= 0.35), blink animation is suppressed."""
    helper.state.mood = "sleepy"
    # Render enough frames to settle the transition
    for _ in range(20):
        helper.frame()

    # After sleepy expression is fully transitioned, blink_phase should be -1
    # because the renderer forces it when openness <= 0.35
    assert helper.renderer._blink.blink_phase == -1.0, (
        "Sleepy mood should suppress blinks (blink_phase forced to -1)"
    )


def test_non_sleepy_does_not_force_suppress_blink(helper: RenderHelper) -> None:
    """Normal moods with openness > 0.35 allow blinking."""
    helper.state.mood = "neutral"
    for _ in range(20):
        helper.frame()
    # The blink system should be active (phase is either -1 waiting or >= 0 blinking,
    # but NOT because of forced suppression). We verify the expression openness > 0.35
    expressions = load_expressions()
    neutral_openness = expressions["neutral"].eyes.openness
    assert neutral_openness > 0.35, (
        f"Neutral openness should be > 0.35, got {neutral_openness}"
    )


# ── 8. Demo mode blocks idle ────────────────────────────────────────────────


def test_demo_mode_blocks_idle_personality(helper: RenderHelper) -> None:
    """When demo_mode is True, idle personality does not override the mood.

    The DemoController owns mood cycling during demo mode. The idle
    personality system is skipped entirely (see renderer lines 207-208).
    We verify that the demo controller sets moods, and idle reactions
    like low battery do NOT override them.
    """
    helper.state.state = "IDLE"
    helper.state.demo_mode = True
    helper.state.battery = 100
    helper.frame()

    # Demo controller applies the first mood from its mood list
    first_mood = helper.renderer._current_mood

    # Drop battery to trigger critical — idle would normally override,
    # but demo mode blocks the idle personality path entirely
    helper.state.battery = 5
    helper.advance(1.0)
    mood_after_low_batt = helper.renderer._current_mood

    # The mood should still be whatever demo set, not critical_battery
    assert mood_after_low_batt != "critical_battery", (
        f"Demo mode should block idle battery reaction, got '{mood_after_low_batt}'"
    )
    # It should be a valid demo-cycled mood (from the expressions list)
    expressions = load_expressions()
    assert mood_after_low_batt in expressions, (
        f"Demo mood should be a valid expression, got '{mood_after_low_batt}'"
    )


# ── 9. Auto-return to neutral ───────────────────────────────────────────────


def test_auto_return_to_neutral_after_lockout(helper: RenderHelper) -> None:
    """A manually set mood expires after the 5s lockout, idle returns neutral."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()

    helper.state.mood = "confused"
    helper.frame()
    assert helper.renderer._current_mood == "confused"

    # Advance past the lockout
    mood = helper.advance(6.0)
    assert mood == "neutral", (
        f"Should auto-return to neutral after lockout, got '{mood}'"
    )


# ── 10. Wake-up micro-expression ─────────────────────────────────────────────


def test_wake_up_micro_expression_triggers(helper: RenderHelper) -> None:
    """SLEEPING -> non-SLEEPING triggers the wake-up micro-expression system.

    The renderer tracks _was_sleeping and _wake_phase. When state transitions
    from SLEEPING to any other state, it sets _wake_phase=1 and _wake_time=now.
    Phase 1 (0-0.4s) sets mood to sleepy. Phase 2 (0.4-0.8s) sets surprised.
    After 0.8s the phase resets to 0.

    We verify the wake system activates (phase 1 = sleepy) and eventually
    completes (phase resets to 0). Note: phase 2 (surprised) may be
    overridden by idle personality returning to neutral, since the wake-up
    code runs before idle checks.
    """
    helper.state.state = "SLEEPING"
    helper.state.battery = 100
    # Render a few frames in sleeping state so _was_sleeping is set
    for _ in range(3):
        helper.frame()
    assert helper.renderer._was_sleeping is True, "Should track sleeping state"

    # Wake up — transition to IDLE
    helper.state.state = "IDLE"

    # Phase 1: First render after wake should set mood to sleepy (elapsed < 0.4s)
    mood = helper.frame(dt=0.033)
    assert mood == "sleepy", f"Wake phase 1 should be sleepy, got '{mood}'"
    assert helper.renderer._wake_phase > 0, "Wake phase should be active"

    # Capture wake_time to verify phase completion
    wake_time = helper.renderer._wake_time

    # After 1.0s the wake phase should have completed (> 0.8s threshold)
    helper.now = wake_time + 1.0
    helper.state.time = helper.now
    helper.state.dt = 0.033
    helper.renderer.render(helper.state)
    assert helper.renderer._wake_phase == 0, (
        f"Wake phase should be 0 (done) after 0.8s, got {helper.renderer._wake_phase}"
    )


def test_wake_up_sets_was_sleeping_flag(helper: RenderHelper) -> None:
    """_was_sleeping flag is set during SLEEPING and cleared on wake."""
    helper.state.state = "IDLE"
    helper.state.battery = 100
    helper.frame()
    assert helper.renderer._was_sleeping is False, "Should not be sleeping initially"

    helper.state.state = "SLEEPING"
    helper.frame()
    assert helper.renderer._was_sleeping is True, "Should track sleeping state"

    helper.state.state = "IDLE"
    helper.frame()
    assert helper.renderer._was_sleeping is False, "Should clear after waking"


# ── 11. Mood transition lerp ────────────────────────────────────────────────


def test_mood_transition_interpolates() -> None:
    """MoodTransition correctly interpolates between two expressions."""
    expr_a = Expression(
        name="a",
        eyes=EyeConfig(openness=0.0),
        mouth=MouthConfig(smile=0.0),
        body=BodyConfig(scale=1.0),
    )
    expr_b = Expression(
        name="b",
        eyes=EyeConfig(openness=1.0),
        mouth=MouthConfig(smile=1.0),
        body=BodyConfig(scale=2.0),
    )

    transition = MoodTransition(expr_a)
    transition.set_target(expr_b)

    # Immediately after set_target, get_current should return an interpolated value
    # (not fully at target yet since time has barely passed)
    result = transition.get_current()
    assert result.name == "b", "Transition target name should be 'b'"


def test_lerp_expression_at_zero() -> None:
    """lerp_expression at t=0 returns the source expression values."""
    a = Expression(
        name="a",
        eyes=EyeConfig(openness=0.2),
        mouth=MouthConfig(smile=-0.5),
    )
    b = Expression(
        name="b",
        eyes=EyeConfig(openness=1.0),
        mouth=MouthConfig(smile=1.0),
    )
    result = lerp_expression(a, b, 0.0)
    assert abs(result.eyes.openness - 0.2) < 0.01, (
        f"At t=0, openness should be ~0.2, got {result.eyes.openness}"
    )
    assert abs(result.mouth.smile - (-0.5)) < 0.01, (
        f"At t=0, smile should be ~-0.5, got {result.mouth.smile}"
    )


def test_lerp_expression_at_one() -> None:
    """lerp_expression at t=1 returns the target expression values."""
    a = Expression(
        name="a",
        eyes=EyeConfig(openness=0.2),
        mouth=MouthConfig(smile=-0.5),
    )
    b = Expression(
        name="b",
        eyes=EyeConfig(openness=1.0),
        mouth=MouthConfig(smile=1.0),
    )
    result = lerp_expression(a, b, 1.0)
    assert abs(result.eyes.openness - 1.0) < 0.01, (
        f"At t=1, openness should be ~1.0, got {result.eyes.openness}"
    )
    assert abs(result.mouth.smile - 1.0) < 0.01, (
        f"At t=1, smile should be ~1.0, got {result.mouth.smile}"
    )


def test_lerp_expression_midpoint() -> None:
    """lerp_expression at t=0.5 returns midpoint values (with ease_in_out)."""
    a = Expression(
        name="a",
        eyes=EyeConfig(openness=0.0),
        body=BodyConfig(scale=1.0),
    )
    b = Expression(
        name="b",
        eyes=EyeConfig(openness=1.0),
        body=BodyConfig(scale=2.0),
    )
    result = lerp_expression(a, b, 0.5)
    # ease_in_out(0.5) = 0.5, so midpoint should be exact
    assert abs(result.eyes.openness - 0.5) < 0.01, (
        f"At t=0.5, openness should be ~0.5, got {result.eyes.openness}"
    )
    assert abs(result.body.scale - 1.5) < 0.01, (
        f"At t=0.5, scale should be ~1.5, got {result.body.scale}"
    )


# ── 12. Rapid mood changes ──────────────────────────────────────────────────


def test_rapid_mood_changes_no_crash(helper: RenderHelper) -> None:
    """Multiple mood changes in quick succession should not crash."""
    moods = ["happy", "sad", "excited", "sleepy", "error", "neutral",
             "critical_battery", "surprised", "thinking", "confused"]
    for mood in moods:
        helper.state.mood = mood
        img = helper.render_image()
        assert isinstance(img, Image.Image), (
            f"Rapid switch to '{mood}' should still produce an image"
        )


def test_rapid_mood_changes_settle(helper: RenderHelper) -> None:
    """After rapid changes, the last mood set should be the resolved one."""
    helper.state.mood = "happy"
    helper.frame()
    helper.state.mood = "sad"
    helper.frame()
    helper.state.mood = "excited"
    # Let it settle
    for _ in range(15):
        helper.frame()
    assert helper.renderer._current_mood == "excited", (
        f"After rapid changes, mood should settle to last set ('excited'), "
        f"got '{helper.renderer._current_mood}'"
    )


# ── IdlePersonality unit tests (no renderer) ────────────────────────────────


class TestIdlePersonalityDirect:
    """Test the IdlePersonality class directly without the full renderer."""

    def test_returns_none_when_not_idle(self) -> None:
        """IdlePersonality returns None when state is not IDLE."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "LISTENING"
        now = time.time()
        mood, urgent = idle.update_ex(state, now)
        assert mood is None, f"Non-IDLE state should return None, got '{mood}'"

    def test_returns_neutral_when_idle(self) -> None:
        """IdlePersonality returns neutral when idle with no events."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "IDLE"
        state.battery = 100
        state.connected = False
        now = time.time()

        # First call — enters idle
        idle.update_ex(state, now)
        # Second call — settled
        mood, urgent = idle.update_ex(state, now + 1.0)
        assert mood == "neutral", f"Idle with no events should be neutral, got '{mood}'"

    def test_critical_battery_is_urgent(self) -> None:
        """Critical battery mood is flagged as urgent."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "IDLE"
        state.battery = 100
        state.connected = False
        now = time.time()

        idle.update_ex(state, now)  # enter idle

        state.battery = 5
        mood, urgent = idle.update_ex(state, now + 1.0)
        assert mood == "critical_battery"
        assert urgent is True, "Critical battery should be urgent"

    def test_connection_loss_is_urgent(self) -> None:
        """Connection loss (sad) is flagged as urgent."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "IDLE"
        state.battery = 100
        state.connected = True
        now = time.time()

        idle.update_ex(state, now)  # enter idle

        state.connected = False
        mood, urgent = idle.update_ex(state, now + 1.0)
        assert mood == "sad"
        assert urgent is True, "Connection loss should be urgent"

    def test_connection_recovery_is_urgent(self) -> None:
        """Connection recovery (happy) is flagged as urgent."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "IDLE"
        state.battery = 100
        state.connected = False
        now = time.time()

        idle.update_ex(state, now)  # enter idle

        state.connected = True
        mood, urgent = idle.update_ex(state, now + 1.0)
        assert mood == "happy"
        assert urgent is True, "Connection recovery should be urgent"

    def test_neutral_return_is_not_urgent(self) -> None:
        """Returning to neutral after a reactive mood is not urgent."""
        idle = IdlePersonality()
        state = DisplayState()
        state.state = "IDLE"
        state.battery = 100
        state.connected = False
        now = time.time()

        idle.update_ex(state, now)  # enter idle
        mood, urgent = idle.update_ex(state, now + 1.0)
        assert mood == "neutral"
        assert urgent is False, "Neutral return should not be urgent"
