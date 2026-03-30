"""Animation helpers — pure math, no pygame dependency.

Ported from face/character.py lerp helpers, blink state, and gaze drift.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Optional

from shared import (
    EyeConfig, MouthConfig, BodyConfig, PerEyeOverride, Expression,
)


# ── Lerp helpers ────────────────────────────────────────────────────────────

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(lerp(ac, bc, t)) for ac, bc in zip(a, b))


def ease_in_out(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def lerp_eye(a: EyeConfig, b: EyeConfig, t: float) -> EyeConfig:
    return EyeConfig(
        width=lerp(a.width, b.width, t),
        height=lerp(a.height, b.height, t),
        openness=lerp(a.openness, b.openness, t),
        pupil_size=lerp(a.pupil_size, b.pupil_size, t),
        gaze_x=lerp(a.gaze_x, b.gaze_x, t),
        gaze_y=lerp(a.gaze_y, b.gaze_y, t),
        blink_rate=lerp(a.blink_rate, b.blink_rate, t),
        squint=lerp(a.squint, b.squint, t),
    )


def lerp_mouth(a: MouthConfig, b: MouthConfig, t: float) -> MouthConfig:
    return MouthConfig(
        openness=lerp(a.openness, b.openness, t),
        smile=lerp(a.smile, b.smile, t),
        width=lerp(a.width, b.width, t),
    )


def lerp_body(a: BodyConfig, b: BodyConfig, t: float) -> BodyConfig:
    return BodyConfig(
        bounce_speed=lerp(a.bounce_speed, b.bounce_speed, t),
        bounce_amount=lerp(a.bounce_amount, b.bounce_amount, t),
        tilt=lerp(a.tilt, b.tilt, t),
        scale=lerp(a.scale, b.scale, t),
    )


def lerp_per_eye(a: Optional[PerEyeOverride], b: Optional[PerEyeOverride],
                  t: float) -> Optional[PerEyeOverride]:
    if a is None and b is None:
        return None
    a = a or PerEyeOverride()
    b = b or PerEyeOverride()

    def _lo(av: Optional[float], bv: Optional[float]) -> Optional[float]:
        if av is None and bv is None:
            return None
        fa = av if av is not None else 0.0
        fb = bv if bv is not None else 0.0
        if av is None:
            return fb * t if t > 0 else None
        if bv is None:
            return fa * (1.0 - t) if t < 1.0 else None
        return lerp(fa, fb, t)

    return PerEyeOverride(
        openness=_lo(a.openness, b.openness),
        height=_lo(a.height, b.height),
        width=_lo(a.width, b.width),
        squint=_lo(a.squint, b.squint),
        tilt=_lo(a.tilt, b.tilt),
    )


def lerp_expression(a: Expression, b: Expression, t: float) -> Expression:
    t = ease_in_out(t)
    return Expression(
        name=b.name,
        eyes=lerp_eye(a.eyes, b.eyes, t),
        mouth=lerp_mouth(a.mouth, b.mouth, t),
        body=lerp_body(a.body, b.body, t),
        left_eye=lerp_per_eye(a.left_eye, b.left_eye, t),
        right_eye=lerp_per_eye(a.right_eye, b.right_eye, t),
        eye_color_override=b.eye_color_override if t >= 0.5 else a.eye_color_override,
    )


# ── Breathing state ────────────────────────────────────────────────────────

@dataclass
class BreathingState:
    """Subtle breathing oscillation — organic scale pulse.

    Config: character.breathing_speed (0.1 = very slow, 1.0 = fast)
    """
    speed: float = 0.3       # config: character.breathing_speed
    phase: float = 0.0
    speed_variation: float = 0.0
    _next_variation: float = 0.0

    def update(self, now: float, dt: float) -> float:
        """Return a scale multiplier (0.98..1.02) for breathing effect."""
        if now >= self._next_variation:
            self.speed_variation = random.uniform(-0.15, 0.15)
            self._next_variation = now + 4.0 + random.uniform(-0.5, 0.5)

        # speed=0.3 → ~4s cycle, speed=1.0 → ~1.2s cycle
        base_speed = 1.57 * (self.speed / 0.3)
        speed = base_speed * (1.0 + self.speed_variation)
        self.phase += speed * dt

        if self.phase > 6.2832:
            self.phase -= 6.2832

        return 1.0 + 0.02 * math.sin(self.phase)


# ── Blink state ─────────────────────────────────────────────────────────────

@dataclass
class BlinkState:
    """Periodic blinks with clustering.

    Config: character.idle_blink_interval (seconds between blinks, scales expression blink_rate)
    """
    interval_scale: float = 1.0  # config: multiplier from idle_blink_interval
    next_blink: float = 0.0
    blink_phase: float = -1.0    # -1 = not blinking
    BLINK_DURATION: float = 0.15
    _cluster_remaining: int = 0

    def update(self, now: float, blink_rate: float) -> None:
        if self.blink_phase >= 0:
            self.blink_phase += 1.0 / (self.BLINK_DURATION * 20)  # 20 FPS
            if self.blink_phase >= 1.0:
                self.blink_phase = -1.0
                if self._cluster_remaining > 0:
                    self._cluster_remaining -= 1
                    self.next_blink = now + random.uniform(0.2, 0.4)
                elif random.random() < 0.3:
                    self._cluster_remaining = random.randint(0, 1)
                    self.next_blink = now + random.uniform(0.2, 0.4)
                else:
                    self._cluster_remaining = 0
                    # interval_scale lets config tune blink frequency
                    interval = 10.0 / max(blink_rate, 0.1) * self.interval_scale
                    self.next_blink = now + interval + random.uniform(-0.5, 0.5)
        elif now >= self.next_blink:
            self.blink_phase = 0.0

    def get_openness_factor(self) -> float:
        """Returns 0.0 (fully closed) to 1.0 (fully open)."""
        if self.blink_phase < 0:
            return 1.0
        if self.blink_phase < 0.5:
            blink_close = self.blink_phase * 2.0
        else:
            blink_close = (1.0 - self.blink_phase) * 2.0
        return 1.0 - blink_close * 0.95


# ── Gaze drift ──────────────────────────────────────────────────────────────

@dataclass
class GazeDrift:
    """Saccadic eye movement — fast snaps between fixation points.

    Config: character.gaze_drift_speed (0.1 = very slow/rare, 1.0 = fast/frequent)
    """
    speed: float = 0.5       # config: character.gaze_drift_speed
    target_x: float = 0.0
    target_y: float = 0.0
    current_x: float = 0.0
    current_y: float = 0.0
    next_change: float = 0.0
    _saccade_active: bool = False
    _fixation_time: float = 0.0

    def update(self, now: float, dt: float) -> None:
        if now >= self.next_change:
            # Gaze range scales with speed (faster = wider range)
            r = 0.2 + self.speed * 0.2
            self.target_x = random.uniform(-r, r)
            self.target_y = random.uniform(-r * 0.67, r * 0.67)
            # Fixation interval: speed=0.5 → 2-6s, speed=1.0 → 1-3s
            interval_scale = 1.0 / max(self.speed, 0.1)
            self.next_change = now + random.uniform(2.0, 6.0) * interval_scale
            self._saccade_active = True

        if self._saccade_active:
            snap_speed = 12.0 * dt
            self.current_x += (self.target_x - self.current_x) * snap_speed
            self.current_y += (self.target_y - self.current_y) * snap_speed
            # Saccade complete when close enough to target
            dx = self.target_x - self.current_x
            dy = self.target_y - self.current_y
            if dx * dx + dy * dy < 0.0004:  # ~0.02 threshold
                self.current_x = self.target_x
                self.current_y = self.target_y
                self._saccade_active = False
                self._fixation_time = now
        else:
            # Holding fixation — smooth micro-drift (not random per-frame)
            elapsed = now - self._fixation_time
            drift = 0.012
            self.current_x = self.target_x + math.sin(elapsed * 2.3) * drift
            self.current_y = self.target_y + math.sin(elapsed * 3.1) * drift * 0.7


# ── Mood transition ─────────────────────────────────────────────────────────

class MoodTransition:
    """Manages smooth transitions between expression states."""

    TRANSITION_TIME = 0.3  # seconds

    def __init__(self, initial: Expression):
        self._current = initial
        self._target = initial
        self._previous = initial
        self._transition_start: float = 0.0
        self._transitioning = False

    def set_target(self, target: Expression) -> None:
        if target.name == self._target.name:
            return
        self._previous = self.get_current()
        self._target = target
        self._transition_start = time.time()
        self._transitioning = True

    def get_current(self) -> Expression:
        if not self._transitioning:
            return self._current
        elapsed = time.time() - self._transition_start
        t = min(elapsed / self.TRANSITION_TIME, 1.0)
        if t >= 1.0:
            self._transitioning = False
            self._current = self._target
            return self._current
        return lerp_expression(self._previous, self._target, t)

    def update(self) -> Expression:
        self._current = self.get_current()
        return self._current
