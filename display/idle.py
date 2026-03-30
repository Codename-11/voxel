"""Idle personality system — state-reactive moods and idle prompt.

Instead of randomly cycling through micro-expressions, the idle system
reacts to actual device state: battery level, connection status, time
since last interaction, and time of day. Physical animations (breathing,
blinking, gaze drift) provide life — mood only changes when there's a
real reason.

Also manages the idle prompt indicator ("?" hint) that appears after
prolonged inactivity to hint that the user can interact.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime

from display.state import DisplayState

log = logging.getLogger("voxel.display.idle")


# ── Reactive Idle Personality ────────────────────────────────────────────


# How long a reactive mood lingers before returning to neutral (seconds)
_MOOD_LINGER: dict[str, float] = {
    "happy": 8.0,
    "curious": 6.0,
    "sleepy": 0.0,     # stays until condition clears
    "low_battery": 0.0,
    "critical_battery": 0.0,
    "sad": 10.0,
    "confused": 6.0,
}

# Idle duration thresholds (seconds)
_IDLE_SLEEPY = 5 * 60       # 5 min → sleepy
_IDLE_SLEEPING = 10 * 60    # 10 min → sleeping state


class IdlePersonality:
    """Reactive mood system — mood changes come from real device events."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._idle_since: float = 0.0
        self._was_idle: bool = False

        # Track state transitions to trigger brief reactive moods
        self._prev_connected: bool = False
        self._prev_battery: int = 100
        self._prev_state: str = ""

        # Current reactive mood (overrides "neutral" while active)
        self._reactive_mood: str | None = None
        self._reactive_until: float = 0.0  # 0 = indefinite (condition-based)

        # Cooldown so we don't spam transitions
        self._last_reaction_time: float = 0.0

    def update_ex(self, state: DisplayState, now: float) -> tuple[str | None, bool]:
        """Return (mood, urgent) — mood override and whether it's a device reaction.

        Urgent reactions (battery, connection) should bypass manual lockout.
        Non-urgent returns (neutral, sleepy) should respect it.
        """
        mood = self._update_inner(state, now)
        urgent = self._reactive_mood in (
            "critical_battery", "low_battery", "sad", "happy",
        ) and mood == self._reactive_mood
        return mood, urgent

    def update(self, state: DisplayState, now: float) -> str | None:
        """Legacy API — returns mood only."""
        mood, _ = self.update_ex(state, now)
        return mood

    def _update_inner(self, state: DisplayState, now: float) -> str | None:
        """Core logic — return a mood override based on device state.

        Priority (highest first):
          1. Critical battery (<10%)
          2. Low battery (<20%)
          3. Connection lost → sad (brief)
          4. Connection regained → happy (brief)
          5. Long idle → sleepy
          6. Just entered idle after conversation → curious (brief)
          7. Time of day (night → sleepy bias)
          8. None → stay neutral, let physical animations carry it
        """
        if not self._enabled:
            return None

        if state.state != "IDLE":
            was_not_idle = not self._was_idle
            self._was_idle = False
            self._reactive_mood = None
            self._reactive_until = 0.0
            self._prev_state = state.state
            self._prev_connected = state.connected
            self._prev_battery = state.battery
            return None

        # Just entered idle
        if not self._was_idle:
            self._was_idle = True
            self._idle_since = now
            self._prev_connected = state.connected
            self._prev_battery = state.battery

            # Coming from a conversation? Brief curiosity
            if self._prev_state in ("SPEAKING", "THINKING"):
                self._set_reactive("curious", now, 6.0)
                log.info("Idle: curious after conversation")

            self._prev_state = state.state
            return self._reactive_mood

        # ── Priority 1-2: Battery ──────────────────────────────────────
        if state.battery < 10:
            if self._reactive_mood != "critical_battery":
                self._set_reactive("critical_battery", now, 0.0)
                state.battery_warning = "critical_battery"
                log.warning("Idle: critical battery (%d%%)", state.battery)
            return "critical_battery"

        if state.battery < 20:
            if self._reactive_mood != "low_battery":
                self._set_reactive("low_battery", now, 0.0)
                state.battery_warning = "low_battery"
                log.warning("Idle: low battery (%d%%)", state.battery)
            return "low_battery"

        # Clear battery moods when charging back up
        if self._reactive_mood in ("critical_battery", "low_battery") and state.battery >= 20:
            log.info("Idle: battery recovered (%d%%), back to neutral", state.battery)
            self._reactive_mood = None
            state.battery_warning = None
            return "neutral"  # actively clear the battery mood

        # ── Priority 3-4: Connection changes ───────────────────────────
        conn_changed = state.connected != self._prev_connected
        self._prev_connected = state.connected
        self._prev_battery = state.battery

        if conn_changed:
            if not state.connected:
                self._set_reactive("sad", now, 10.0)
                state.connection_event = "disconnected"
                state.connection_event_time = now
                # Emoji reinforcement
                state.reaction_emoji = "\u274c"  # ❌
                state.reaction_time = now
                state.reaction_duration = 2.0
                log.info("Idle: sad — lost connection")
            else:
                self._set_reactive("happy", now, 8.0)
                state.connection_event = "connected"
                state.connection_event_time = now
                # Emoji reinforcement
                state.reaction_emoji = "\u2705"  # ✅
                state.reaction_time = now
                state.reaction_duration = 2.0
                log.info("Idle: happy — reconnected")

        # ── Priority 5: Long idle → sleepy ─────────────────────────────
        idle_duration = now - self._idle_since

        if idle_duration > _IDLE_SLEEPY:
            if self._reactive_mood != "sleepy":
                self._set_reactive("sleepy", now, 0.0)
                log.info("Idle: sleepy after %.0fs", idle_duration)
            return "sleepy"

        # ── Priority 6: Time of day ────────────────────────────────────
        hour = datetime.now().hour
        if hour >= 23 or hour < 5:
            # Late night — lean sleepy (but not forced, just a suggestion)
            if self._reactive_mood is None and idle_duration > 60:
                self._set_reactive("sleepy", now, 0.0)
                return "sleepy"

        # ── Check if current reactive mood has expired ─────────────────
        if self._reactive_mood is not None:
            if self._reactive_until > 0 and now >= self._reactive_until:
                old = self._reactive_mood
                # Clear connection event when the connection mood expires
                if old in ("sad", "happy") and state.connection_event is not None:
                    state.connection_event = None
                self._reactive_mood = None
                self._reactive_until = 0.0
                log.info("Idle: %s expired, back to neutral", old)
                return "neutral"  # actively transition back
            return self._reactive_mood

        # ── Default: neutral (ensures mood returns from any override) ──
        return "neutral"

    def _set_reactive(self, mood: str, now: float, duration: float) -> None:
        """Set a reactive mood with optional duration (0 = indefinite)."""
        self._reactive_mood = mood
        self._reactive_until = now + duration if duration > 0 else 0.0


# ── Idle Prompt Indicator ─────────────────────────────────────────────────


class IdlePrompt:
    """Manages the "?" hint that appears after prolonged idle.

    The indicator fades in, holds for a few seconds, then fades out.
    It repeats on a configurable interval.
    """

    def __init__(self, enabled: bool = True, interval: float = 90.0) -> None:
        self._enabled = enabled
        self._interval = interval

        # Timing
        self._idle_start: float = 0.0
        self._was_idle: bool = False
        self._next_show: float = 0.0
        self._last_interaction: float = 0.0

        # Animation state
        self._phase: str = "hidden"  # hidden, fade_in, hold, fade_out
        self._phase_start: float = 0.0

        # Durations
        self._fade_in_dur: float = 0.8
        self._hold_dur: float = 3.0
        self._fade_out_dur: float = 0.8

    def update(self, state: DisplayState, now: float) -> None:
        """Update the idle prompt state. Writes to state.idle_prompt_visible
        and state._idle_prompt_alpha.

        Must be called every frame.
        """
        if not self._enabled:
            state.idle_prompt_visible = False
            state._idle_prompt_alpha = 0.0
            return

        if state.state != "IDLE":
            self._was_idle = False
            self._phase = "hidden"
            state.idle_prompt_visible = False
            state._idle_prompt_alpha = 0.0
            return

        # Just entered idle
        if not self._was_idle:
            self._was_idle = True
            self._idle_start = now
            # First appearance after 60s of idle
            self._next_show = now + 60.0
            self._phase = "hidden"
            state.idle_prompt_visible = False
            state._idle_prompt_alpha = 0.0
            return

        # State machine for the "?" indicator
        if self._phase == "hidden":
            if now >= self._next_show:
                self._phase = "fade_in"
                self._phase_start = now
                state.idle_prompt_visible = True

        elif self._phase == "fade_in":
            elapsed = now - self._phase_start
            t = min(elapsed / self._fade_in_dur, 1.0)
            state._idle_prompt_alpha = t
            state.idle_prompt_visible = True
            if t >= 1.0:
                self._phase = "hold"
                self._phase_start = now

        elif self._phase == "hold":
            state._idle_prompt_alpha = 1.0
            state.idle_prompt_visible = True
            elapsed = now - self._phase_start
            if elapsed >= self._hold_dur:
                self._phase = "fade_out"
                self._phase_start = now

        elif self._phase == "fade_out":
            elapsed = now - self._phase_start
            t = min(elapsed / self._fade_out_dur, 1.0)
            state._idle_prompt_alpha = 1.0 - t
            state.idle_prompt_visible = t < 1.0
            if t >= 1.0:
                self._phase = "hidden"
                state.idle_prompt_visible = False
                state._idle_prompt_alpha = 0.0
                # Schedule next appearance
                jitter = random.uniform(-15.0, 15.0)
                self._next_show = now + self._interval + jitter

    def reset(self) -> None:
        """Reset on user interaction (button press, transcript, etc.)."""
        self._phase = "hidden"
        self._was_idle = False
