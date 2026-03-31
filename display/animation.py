"""Animation helpers — pure math, no pygame dependency.

Ported from face/character.py lerp helpers, blink state, and gaze drift.
Enhanced with Disney-research asymmetric blinks, blink clustering,
and pink-noise microsaccadic jitter for lifelike eye movement.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
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
        modifiers=b.modifiers if t >= 0.5 else a.modifiers,
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
    """Periodic blinks with asymmetric timing and clustering.

    Disney/Pixar research finding: eyelids close faster than they open.
    Close phase ~42ms, open phase ~108ms (150ms total at default duration).
    This makes blinks feel natural and "alive" rather than mechanical.

    Blink phase advances using delta-time (dt) so animation speed is
    frame-rate independent — blinks take the same wall-clock time whether
    running at 20 FPS on the Pi or 60 FPS on desktop.

    Blink clustering: real humans blink in bursts of 2-3 with short gaps
    (0.15-0.35s), then pause for 3-8s. This pattern is more realistic
    than evenly-spaced blinks.

    Config: character.idle_blink_interval (seconds between blinks, scales expression blink_rate)
    """
    interval_scale: float = 1.0  # config: multiplier from idle_blink_interval
    next_blink: float = 0.0
    blink_phase: float = -1.0    # -1 = not blinking
    BLINK_DURATION: float = 0.15
    _cluster_remaining: int = 0

    # Asymmetric timing: close is fast, open is slow (Disney research).
    # close_fraction is the proportion of the blink spent closing.
    # 0.28 means closing takes 28% of the duration (~42ms at 150ms total),
    # opening takes the remaining 72% (~108ms). This creates the snappy
    # close + gentle open that makes animated characters feel alive.
    CLOSE_FRACTION: float = 0.28

    def update(self, now: float, blink_rate: float, dt: float = 0.05) -> None:
        if self.blink_phase >= 0:
            self.blink_phase += dt / self.BLINK_DURATION
            if self.blink_phase >= 1.0:
                self.blink_phase = -1.0
                if self._cluster_remaining > 0:
                    self._cluster_remaining -= 1
                    # Short gap within a cluster
                    self.next_blink = now + random.uniform(0.15, 0.35)
                elif random.random() < 0.35:
                    # Start a new cluster of 1-2 additional blinks
                    self._cluster_remaining = random.randint(1, 2)
                    self.next_blink = now + random.uniform(0.15, 0.35)
                else:
                    self._cluster_remaining = 0
                    # Long pause between clusters (3-8s scaled by blink rate)
                    interval = 10.0 / max(blink_rate, 0.1) * self.interval_scale
                    self.next_blink = now + interval + random.uniform(-0.5, 0.5)
        elif now >= self.next_blink:
            self.blink_phase = 0.0

    def get_openness_factor(self) -> float:
        """Returns 0.0 (fully closed) to 1.0 (fully open).

        Uses asymmetric timing: fast close, slow open. The closing phase
        uses the first CLOSE_FRACTION of the blink_phase, and the opening
        phase uses the remainder. Each sub-phase is normalized to 0-1 and
        uses ease-in-out for smooth motion.
        """
        if self.blink_phase < 0:
            return 1.0

        cf = self.CLOSE_FRACTION

        if self.blink_phase < cf:
            # Closing phase (fast): normalize to 0..1
            t = self.blink_phase / cf
            # Ease-in for snappy start
            blink_close = t * t
        else:
            # Opening phase (slow): normalize to 0..1
            t = (self.blink_phase - cf) / (1.0 - cf)
            # Ease-out for gentle finish
            blink_close = 1.0 - (t * t)

        return 1.0 - blink_close * 0.95


# ── Gaze drift ──────────────────────────────────────────────────────────────

@dataclass
class PinkNoiseJitter:
    """Approximate 1/f (pink) noise for microsaccadic eye jitter.

    Real eyes exhibit tiny involuntary movements even during fixation.
    These microsaccades follow a 1/f power spectrum — neither pure random
    (white noise, too jittery) nor pure sinusoidal (too mechanical).

    Implementation: simple recursive filter that accumulates white noise
    through a leaky integrator, producing correlated noise with more
    low-frequency content. The amplitude is very small (±0.02 range)
    to stay subtle and lifelike.
    """
    _accum_x: float = 0.0
    _accum_y: float = 0.0
    _decay: float = 0.92        # how much previous value persists (higher = more low-freq)
    _amplitude: float = 0.018   # maximum jitter magnitude
    _drive: float = 0.08        # white noise injection strength

    def sample(self, dt: float) -> tuple[float, float]:
        """Return a (jitter_x, jitter_y) offset pair."""
        # Leaky integrator: accumulate white noise, decay toward zero.
        # This produces correlated noise with a 1/f-like spectrum.
        # Use dt-adjusted decay so behavior is frame-rate independent
        # (same jitter character at 20 FPS on Pi and 60 FPS on desktop).
        decay = self._decay ** (dt * 30.0) if dt > 0 else self._decay
        self._accum_x = self._accum_x * decay + random.gauss(0, self._drive)
        self._accum_y = self._accum_y * decay + random.gauss(0, self._drive)

        # Soft-clamp to amplitude range
        jx = max(-self._amplitude, min(self._amplitude, self._accum_x))
        jy = max(-self._amplitude, min(self._amplitude, self._accum_y))
        return (jx, jy)


@dataclass
class GazeDrift:
    """Saccadic eye movement — fast snaps between fixation points.

    Enhanced with pink-noise microsaccadic jitter during fixation for
    subtle, lifelike eye tremor that prevents the "dead stare" look.

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
    _jitter: PinkNoiseJitter = field(default_factory=PinkNoiseJitter)

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
            snap_speed = min(12.0 * dt, 1.0)  # clamp to prevent overshoot on lag spikes
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
            # Holding fixation — sinusoidal micro-drift + pink noise jitter.
            # The sinusoidal component provides slow organic movement,
            # while the pink noise adds subtle involuntary tremor.
            elapsed = now - self._fixation_time
            drift = 0.012
            jx, jy = self._jitter.sample(dt)
            self.current_x = self.target_x + math.sin(elapsed * 2.3) * drift + jx
            self.current_y = self.target_y + math.sin(elapsed * 3.1) * drift * 0.7 + jy


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
