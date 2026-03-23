"""Voxel procedural face — draws the cube mascot from Expression dataclasses."""

import math
import time
import random
import logging
from dataclasses import dataclass, field

import pygame

from face.expressions import (
    Expression, EyeConfig, MouthConfig, BodyConfig,
    Mood, EXPRESSIONS,
)

log = logging.getLogger("voxel.face.character")

# ── Layout constants (240x280 screen, 24px status bar) ──────────────────────

SCREEN_W = 240
SCREEN_H = 280
STATUS_H = 24
FACE_AREA_H = SCREEN_H - STATUS_H  # 256px

# Face center
CX = SCREEN_W // 2          # 120
CY = FACE_AREA_H // 2 - 4   # ~124 (slightly above center for visual balance)

# Cube body
BODY_W = 180
BODY_H = 160
BODY_RADIUS = 24

# Eyes
EYE_SPACING = 56             # distance from center to each eye center
EYE_Y_OFFSET = -12           # above face center
EYE_BASE_W = 42
EYE_BASE_H = 34
PUPIL_COLOR = (10, 12, 18)

# Mouth
MOUTH_Y_OFFSET = 44          # below face center

# ── Colors ───────────────────────────────────────────────────────────────────

BG           = (10, 10, 15)
BODY_FILL    = (26, 26, 46)
BODY_DARK    = (18, 18, 32)
EDGE_GLOW    = (0, 212, 210)
EDGE_DIM     = (0, 100, 98)
EYE_COLOR    = (0, 210, 200)
EYE_BRIGHT   = (140, 255, 250)
HIGHLIGHT     = (200, 255, 252)
MOUTH_COLOR  = (0, 200, 190)
MOUTH_DIM    = (0, 120, 110)
ERROR_RED    = (255, 60, 60)


# ── Lerp helpers ─────────────────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(_lerp(ac, bc, t)) for ac, bc in zip(a, b))


def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out curve."""
    return t * t * (3.0 - 2.0 * t)


def _lerp_eye(a: EyeConfig, b: EyeConfig, t: float) -> EyeConfig:
    return EyeConfig(
        width=_lerp(a.width, b.width, t),
        height=_lerp(a.height, b.height, t),
        openness=_lerp(a.openness, b.openness, t),
        pupil_size=_lerp(a.pupil_size, b.pupil_size, t),
        gaze_x=_lerp(a.gaze_x, b.gaze_x, t),
        gaze_y=_lerp(a.gaze_y, b.gaze_y, t),
        blink_rate=_lerp(a.blink_rate, b.blink_rate, t),
        squint=_lerp(a.squint, b.squint, t),
    )


def _lerp_mouth(a: MouthConfig, b: MouthConfig, t: float) -> MouthConfig:
    return MouthConfig(
        openness=_lerp(a.openness, b.openness, t),
        smile=_lerp(a.smile, b.smile, t),
        width=_lerp(a.width, b.width, t),
    )


def _lerp_body(a: BodyConfig, b: BodyConfig, t: float) -> BodyConfig:
    return BodyConfig(
        bounce_speed=_lerp(a.bounce_speed, b.bounce_speed, t),
        bounce_amount=_lerp(a.bounce_amount, b.bounce_amount, t),
        tilt=_lerp(a.tilt, b.tilt, t),
        scale=_lerp(a.scale, b.scale, t),
    )


def _lerp_expression(a: Expression, b: Expression, t: float) -> Expression:
    t = _ease_in_out(t)
    return Expression(
        mood=b.mood,
        eyes=_lerp_eye(a.eyes, b.eyes, t),
        mouth=_lerp_mouth(a.mouth, b.mouth, t),
        body=_lerp_body(a.body, b.body, t),
    )


# ── Blink state ──────────────────────────────────────────────────────────────

@dataclass
class _BlinkState:
    next_blink: float = 0.0
    blink_phase: float = -1.0  # -1 = not blinking, 0..1 = blink progress
    BLINK_DURATION: float = 0.15  # seconds for full close-open cycle


# ── Gaze drift state ────────────────────────────────────────────────────────

@dataclass
class _GazeDrift:
    target_x: float = 0.0
    target_y: float = 0.0
    current_x: float = 0.0
    current_y: float = 0.0
    next_change: float = 0.0


# ── VoxelCharacter ───────────────────────────────────────────────────────────

class VoxelCharacter:
    """Draws and animates the Voxel cube mascot procedurally."""

    TRANSITION_TIME = 0.3  # seconds to lerp between moods

    def __init__(self):
        self._current = EXPRESSIONS[Mood.NEUTRAL]
        self._target = self._current
        self._previous = self._current
        self._transition_start: float = 0.0
        self._transitioning = False

        self._blink = _BlinkState(next_blink=time.time() + random.uniform(1.0, 4.0))
        self._gaze = _GazeDrift(next_change=time.time() + random.uniform(2.0, 5.0))
        self._time = time.time()

        # Audio amplitude for mouth sync (set externally)
        self.audio_amplitude: float = 0.0

        # Pre-create surfaces for glow effects
        self._glow_surface = pygame.Surface((SCREEN_W, FACE_AREA_H), pygame.SRCALPHA)

    def set_mood(self, mood: Mood) -> None:
        """Transition to a new mood."""
        if mood == self._target.mood:
            return
        self._previous = self._get_current_expression()
        self._target = EXPRESSIONS[mood]
        self._transition_start = time.time()
        self._transitioning = True
        log.debug(f"Mood: {self._previous.mood.name} → {mood.name}")

    def get_mood(self) -> Mood:
        return self._target.mood

    def _get_current_expression(self) -> Expression:
        """Get the current interpolated expression."""
        if not self._transitioning:
            return self._current
        elapsed = time.time() - self._transition_start
        t = min(elapsed / self.TRANSITION_TIME, 1.0)
        if t >= 1.0:
            self._transitioning = False
            self._current = self._target
            return self._current
        return _lerp_expression(self._previous, self._target, t)

    def update(self, dt: float) -> None:
        """Update animation state. Call once per frame."""
        now = time.time()
        self._time = now
        self._current = self._get_current_expression()
        self._update_blink(now)
        self._update_gaze_drift(now, dt)

    def _update_blink(self, now: float) -> None:
        blink = self._blink
        if blink.blink_phase >= 0:
            blink.blink_phase += 1.0 / (blink.BLINK_DURATION * 30)  # ~30fps
            if blink.blink_phase >= 1.0:
                blink.blink_phase = -1.0
                interval = 10.0 / max(self._current.eyes.blink_rate, 0.1)
                blink.next_blink = now + interval + random.uniform(-0.5, 0.5)
        elif now >= blink.next_blink:
            blink.blink_phase = 0.0

    def _update_gaze_drift(self, now: float, dt: float) -> None:
        gaze = self._gaze
        if now >= gaze.next_change:
            gaze.target_x = random.uniform(-0.3, 0.3)
            gaze.target_y = random.uniform(-0.2, 0.2)
            gaze.next_change = now + random.uniform(2.0, 6.0)
        # Smooth follow
        speed = 2.0 * dt
        gaze.current_x += (gaze.target_x - gaze.current_x) * speed
        gaze.current_y += (gaze.target_y - gaze.current_y) * speed

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the character onto the surface."""
        expr = self._current
        now = self._time

        # Body animation
        bounce_y = math.sin(now * expr.body.bounce_speed * 2 * math.pi) * expr.body.bounce_amount
        body_cy = int(CY + bounce_y)

        self._draw_body(surface, CX, body_cy, expr)
        self._draw_eyes(surface, CX, body_cy, expr, now)
        self._draw_mouth(surface, CX, body_cy, expr)

    def _draw_body(self, surface: pygame.Surface, cx: int, cy: int, expr: Expression) -> None:
        """Draw the dark cube body with glowing edge accents."""
        scale = expr.body.scale
        w = int(BODY_W * scale)
        h = int(BODY_H * scale)
        r = int(BODY_RADIUS * scale)

        body_rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)

        # Body fill (dark charcoal)
        pygame.draw.rect(surface, BODY_FILL, body_rect, border_radius=r)

        # Inner shadow / depth (darker rect slightly offset)
        inner = body_rect.inflate(-6, -6)
        pygame.draw.rect(surface, BODY_DARK, inner, border_radius=r - 2)

        # Edge glow (outline)
        pygame.draw.rect(surface, EDGE_GLOW, body_rect, width=2, border_radius=r)

        # Corner accent dots (subtle glow at corners)
        accent_r = 3
        corners = [
            (body_rect.left + r, body_rect.top + r),
            (body_rect.right - r, body_rect.top + r),
            (body_rect.left + r, body_rect.bottom - r),
            (body_rect.right - r, body_rect.bottom - r),
        ]
        for px, py in corners:
            pygame.draw.circle(surface, EDGE_GLOW, (px, py), accent_r)
            pygame.draw.circle(surface, EYE_BRIGHT, (px, py), accent_r - 1)

    def _draw_eyes(self, surface: pygame.Surface, cx: int, cy: int, expr: Expression, now: float) -> None:
        """Draw both eyes with pupils, highlights, and blink."""
        eyes = expr.eyes

        # Blink: temporarily override openness
        openness = eyes.openness
        if self._blink.blink_phase >= 0:
            # Blink curve: quick close then open (triangle wave)
            phase = self._blink.blink_phase
            if phase < 0.5:
                blink_close = phase * 2.0  # 0→1
            else:
                blink_close = (1.0 - phase) * 2.0  # 1→0
            openness = openness * (1.0 - blink_close * 0.95)

        # Squint reduces openness from top
        openness = openness * (1.0 - eyes.squint * 0.4)

        ew = int(EYE_BASE_W * eyes.width)
        eh = int(EYE_BASE_H * eyes.height * max(openness, 0.05))

        # Gaze: combine expression gaze + idle drift
        gaze_x = eyes.gaze_x + self._gaze.current_x
        gaze_y = eyes.gaze_y + self._gaze.current_y
        gaze_x = max(-1.0, min(1.0, gaze_x))
        gaze_y = max(-1.0, min(1.0, gaze_y))

        eye_y = cy + EYE_Y_OFFSET

        for side in (-1, 1):  # -1=left, 1=right
            ex = cx + side * EYE_SPACING

            if expr.mood == Mood.ERROR:
                self._draw_x_eye(surface, ex, eye_y, ew, eh)
                continue

            eye_rect = pygame.Rect(ex - ew // 2, eye_y - eh // 2, ew, eh)

            # Eye background (bright teal)
            pygame.draw.ellipse(surface, EYE_COLOR, eye_rect)

            # Brighter inner
            inner_rect = eye_rect.inflate(-4, -4)
            if inner_rect.height > 2:
                pygame.draw.ellipse(surface, EYE_BRIGHT, inner_rect)

            # Pupil
            if openness > 0.15:
                pupil_r = int(min(ew, eh) * eyes.pupil_size * 0.5)
                pupil_x = int(ex + gaze_x * ew * 0.2)
                pupil_y = int(eye_y + gaze_y * eh * 0.15)
                if pupil_r > 1:
                    pygame.draw.circle(surface, PUPIL_COLOR, (pupil_x, pupil_y), pupil_r)

                # Highlight dot (glossy)
                hl_x = pupil_x - int(pupil_r * 0.5)
                hl_y = pupil_y - int(pupil_r * 0.6)
                hl_r = max(2, pupil_r // 3)
                pygame.draw.circle(surface, HIGHLIGHT, (hl_x, hl_y), hl_r)

            # Eyelid effect for squint (dark rect from top)
            if eyes.squint > 0.1:
                lid_h = int(eh * eyes.squint * 0.35)
                lid_rect = pygame.Rect(eye_rect.x - 1, eye_rect.y - 1, eye_rect.width + 2, lid_h)
                pygame.draw.rect(surface, BG, lid_rect)

    def _draw_x_eye(self, surface: pygame.Surface, cx: int, cy: int, w: int, h: int) -> None:
        """Draw X_X error eyes."""
        size = min(w, h) // 2
        thickness = 3
        pygame.draw.line(surface, ERROR_RED,
                         (cx - size, cy - size), (cx + size, cy + size), thickness)
        pygame.draw.line(surface, ERROR_RED,
                         (cx + size, cy - size), (cx - size, cy + size), thickness)

    def _draw_mouth(self, surface: pygame.Surface, cx: int, cy: int, expr: Expression) -> None:
        """Draw the mouth — arc for smile/frown, ellipse for open."""
        mouth = expr.mouth
        mouth_y = cy + MOUTH_Y_OFFSET

        # Audio-reactive: override openness during speech
        openness = mouth.openness
        if self.audio_amplitude > 0.05:
            openness = max(openness, self.audio_amplitude * 0.8)

        base_w = int(36 * mouth.width)

        if expr.mood == Mood.ERROR:
            # Flat line mouth
            pygame.draw.line(surface, ERROR_RED,
                             (cx - base_w // 2, mouth_y),
                             (cx + base_w // 2, mouth_y), 2)
            return

        if openness > 0.15:
            # Open mouth (ellipse)
            mouth_h = int(20 * openness)
            mouth_w = int(base_w * (0.6 + openness * 0.4))
            # Shift up slightly when open
            my = mouth_y - mouth_h // 4
            mouth_rect = pygame.Rect(cx - mouth_w // 2, my - mouth_h // 2, mouth_w, mouth_h)
            pygame.draw.ellipse(surface, MOUTH_COLOR, mouth_rect)
            # Dark interior
            inner = mouth_rect.inflate(-4, -4)
            if inner.width > 2 and inner.height > 2:
                pygame.draw.ellipse(surface, BODY_DARK, inner)
        else:
            # Closed mouth — arc/curve based on smile amount
            smile = mouth.smile
            arc_h = int(16 * abs(smile)) if abs(smile) > 0.05 else 0

            if arc_h < 2:
                # Neutral: small line
                pygame.draw.line(surface, MOUTH_COLOR,
                                 (cx - base_w // 3, mouth_y),
                                 (cx + base_w // 3, mouth_y), 2)
            else:
                # Smile or frown arc
                arc_rect = pygame.Rect(cx - base_w // 2, mouth_y - arc_h, base_w, arc_h * 2)
                if smile > 0:
                    # Smile: bottom half of ellipse
                    pygame.draw.arc(surface, MOUTH_COLOR, arc_rect,
                                    math.pi + 0.3, 2 * math.pi - 0.3, 2)
                else:
                    # Frown: top half of ellipse
                    pygame.draw.arc(surface, MOUTH_COLOR, arc_rect,
                                    0.3, math.pi - 0.3, 2)
