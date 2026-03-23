"""Voxel procedural face — draws the cube mascot matching the React/CSS design system.

Renders white rounded-rectangle eyes (kawaii default), offset mouth curves,
mood icons, and the dark cube body with cyan edge glow lines. Supports three
face styles (kawaii, retro, minimal) and smooth lerp transitions between moods.
"""

import math
import time
import random
import logging
from dataclasses import dataclass
from typing import Optional

import pygame

from face.expressions import (
    Expression, EyeConfig, MouthConfig, BodyConfig, PerEyeOverride,
    Mood, EXPRESSIONS,
)
from face.styles import (
    FaceStyle, EyeStyle, MouthStyle, XEyeStyle,
    STYLES, DEFAULT_STYLE, COLORS,
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

# Cube body (matches CSS .cube 130px + some display scaling)
BODY_W = 160
BODY_H = 150
BODY_RADIUS = 20

# Eyes layout
EYE_SPACING = 28             # distance from center to each eye center
EYE_Y_OFFSET = -10           # above face center
EYE_GAP = 16                 # gap between eyes (matches CSS .eyes-row gap: 16px)

# Mouth
MOUTH_Y_OFFSET = 18          # below eyes (CSS gap:14px + mouth area)

# Edge glow inset (matches CSS .edge-glow left/right 12px inset)
EDGE_INSET = 12

# ── Colors from design system ───────────────────────────────────────────────

BG           = COLORS["background"]     # (10, 10, 15)
BODY_FILL    = COLORS["body"]           # (26, 26, 46)
BODY_LIGHT   = COLORS["body_light"]     # (34, 34, 68)
BODY_DARK    = COLORS["body_dark"]      # (18, 18, 32)
EDGE_GLOW    = COLORS["cyan"]           # (0, 212, 210)
CYAN_BRIGHT  = COLORS["cyan_bright"]    # (64, 255, 248)
CYAN_DIM     = COLORS["cyan_dim"]       # (0, 100, 96)
ERROR_RED    = COLORS["error"]          # (255, 60, 60)


# ── Mood icon definitions ────────────────────────────────────────────────────

# Maps mood name to (text, color, font_size, animation_type)
# animation_type: "pulse", "float", "spin", "bounce", "blink", "shake", "none"
_MOOD_ICONS: dict[str, tuple[str, tuple, int, str]] = {
    "HAPPY":            ("\u2665",     (255, 107, 138),  18, "pulse"),    # heart
    "THINKING":         ("?",          EDGE_GLOW,        18, "bounce"),   # brain+cog simplified
    "CONFUSED":         ("???",        EDGE_GLOW,        13, "blink"),
    "EXCITED":          ("!!",         CYAN_BRIGHT,      18, "pulse"),
    "SLEEPY":           ("Zzz",        EDGE_GLOW,        14, "float"),
    "LISTENING":        (")))",        EDGE_GLOW,        12, "blink"),
    "SAD":              ("~",          (136, 136, 170),  16, "bounce"),
    "SURPRISED":        ("!",          CYAN_BRIGHT,      22, "pulse"),
    "CURIOUS":          ("?",          EDGE_GLOW,        22, "bounce"),
    "FOCUSED":          ("...",        EDGE_GLOW,        16, "blink"),
    "WORKING":          ("*",          EDGE_GLOW,        20, "spin"),     # gear simplified
    "FRUSTRATED":       ("#",          (255, 107, 74),   18, "shake"),
    "ERROR":            ("?!",         ERROR_RED,        18, "blink"),
    "LOW_BATTERY":      ("!",          (212, 160, 32),   16, "blink"),
    "CRITICAL_BATTERY": ("!!",         (160, 120, 24),   16, "blink"),
}


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


def _lerp_per_eye(a: Optional[PerEyeOverride], b: Optional[PerEyeOverride],
                   t: float) -> Optional[PerEyeOverride]:
    """Lerp between per-eye overrides, handling None gracefully."""
    if a is None and b is None:
        return None
    # Default "no override" values
    a = a or PerEyeOverride()
    b = b or PerEyeOverride()

    def _lo(av: Optional[float], bv: Optional[float]) -> Optional[float]:
        if av is None and bv is None:
            return None
        fa = av if av is not None else 0.0
        fb = bv if bv is not None else 0.0
        result = _lerp(fa, fb, t)
        # If transitioning from None to a value, fade in; from value to None, fade out
        if av is None:
            return fb * t if t > 0 else None
        if bv is None:
            return fa * (1.0 - t) if t < 1.0 else None
        return result

    return PerEyeOverride(
        openness=_lo(a.openness, b.openness),
        height=_lo(a.height, b.height),
        width=_lo(a.width, b.width),
        squint=_lo(a.squint, b.squint),
        tilt=_lo(a.tilt, b.tilt),
    )


def _lerp_expression(a: Expression, b: Expression, t: float) -> Expression:
    t = _ease_in_out(t)
    return Expression(
        mood=b.mood,
        eyes=_lerp_eye(a.eyes, b.eyes, t),
        mouth=_lerp_mouth(a.mouth, b.mouth, t),
        body=_lerp_body(a.body, b.body, t),
        left_eye=_lerp_per_eye(a.left_eye, b.left_eye, t),
        right_eye=_lerp_per_eye(a.right_eye, b.right_eye, t),
        eye_color_override=b.eye_color_override if t >= 0.5 else a.eye_color_override,
    )


# ── Eye color override helper ────────────────────────────────────────────────

def _parse_eye_color_override(hex_str: Optional[str]) -> Optional[tuple[int, int, int]]:
    """Convert a hex color string like '#d4a020' to an RGB tuple, or None."""
    if not hex_str:
        return None
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return None


# ── Blink state ──────────────────────────────────────────────────────────────

@dataclass
class _BlinkState:
    next_blink: float = 0.0
    blink_phase: float = -1.0  # -1 = not blinking, 0..1 = blink progress
    BLINK_DURATION: float = 0.15  # seconds for full close-open cycle


# ── Gaze drift state ─────────────────────────────────────────────────────────

@dataclass
class _GazeDrift:
    target_x: float = 0.0
    target_y: float = 0.0
    current_x: float = 0.0
    current_y: float = 0.0
    next_change: float = 0.0


# ── Mood icon animation state ────────────────────────────────────────────────

@dataclass
class _MoodIconState:
    phase: float = 0.0          # animation phase 0..2pi
    visible_alpha: float = 0.0  # for fade in/out


# ── Drawing helpers ──────────────────────────────────────────────────────────

def _draw_rounded_rect(surface: pygame.Surface, color: tuple, rect: pygame.Rect,
                        radius: int, tilt: float = 0.0) -> None:
    """Draw a filled rounded rectangle, optionally rotated by tilt degrees."""
    if tilt == 0.0:
        pygame.draw.rect(surface, color, rect, border_radius=radius)
        return

    # For tilted eyes, render to a temp surface and rotate
    temp = pygame.Surface((rect.width + 4, rect.height + 4), pygame.SRCALPHA)
    temp_rect = pygame.Rect(2, 2, rect.width, rect.height)
    pygame.draw.rect(temp, color, temp_rect, border_radius=radius)
    rotated = pygame.transform.rotate(temp, -tilt)
    rot_rect = rotated.get_rect(center=rect.center)
    surface.blit(rotated, rot_rect)


def _draw_glow_rect(surface: pygame.Surface, color: tuple, rect: pygame.Rect,
                     radius: int, glow_alpha: int = 40) -> None:
    """Draw a soft glow behind a rounded rect (for eye glow effect)."""
    glow_surf = pygame.Surface((rect.width + 12, rect.height + 12), pygame.SRCALPHA)
    glow_rect = pygame.Rect(6, 6, rect.width, rect.height)
    glow_color = (*color[:3], glow_alpha) if len(color) == 3 else (*color[:3], glow_alpha)
    pygame.draw.rect(glow_surf, glow_color, glow_rect, border_radius=radius)
    # Slight blur by scaling down and back up
    small = pygame.transform.smoothscale(glow_surf, (glow_surf.get_width() // 2, glow_surf.get_height() // 2))
    blurred = pygame.transform.smoothscale(small, glow_surf.get_size())
    surface.blit(blurred, (rect.x - 6, rect.y - 6), special_flags=pygame.BLEND_RGBA_ADD)


def _quadratic_bezier_points(p0: tuple, p1: tuple, p2: tuple, steps: int = 16) -> list[tuple]:
    """Generate points along a quadratic bezier curve."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        inv = 1.0 - t
        x = inv * inv * p0[0] + 2 * inv * t * p1[0] + t * t * p2[0]
        y = inv * inv * p0[1] + 2 * inv * t * p1[1] + t * t * p2[1]
        points.append((int(x), int(y)))
    return points


# ── VoxelCharacter ───────────────────────────────────────────────────────────

class VoxelCharacter:
    """Draws and animates the Voxel cube mascot procedurally.

    Matches the design system from design/src/components/VoxelCube.jsx.
    Supports kawaii (default), retro, and minimal face styles.
    """

    TRANSITION_TIME = 0.3  # seconds to lerp between moods

    def __init__(self, style_name: str = DEFAULT_STYLE):
        self._current = EXPRESSIONS[Mood.NEUTRAL]
        self._target = self._current
        self._previous = self._current
        self._transition_start: float = 0.0
        self._transitioning = False

        self._blink = _BlinkState(next_blink=time.time() + random.uniform(1.0, 4.0))
        self._gaze = _GazeDrift(next_change=time.time() + random.uniform(2.0, 5.0))
        self._mood_icon = _MoodIconState()
        self._time = time.time()

        # Style
        self._style_name = style_name
        self._style: FaceStyle = STYLES.get(style_name, STYLES[DEFAULT_STYLE])

        # Audio amplitude for mouth sync (set externally)
        self.audio_amplitude: float = 0.0

        # Font for mood icons (lazy init)
        self._icon_font: Optional[pygame.font.Font] = None
        self._icon_fonts: dict[int, pygame.font.Font] = {}

        # Pre-create surfaces for glow effects
        self._glow_surface = pygame.Surface((SCREEN_W, FACE_AREA_H), pygame.SRCALPHA)

    # ── Style management ─────────────────────────────────────────────────────

    def set_style(self, style_name: str) -> None:
        """Change the face rendering style at runtime."""
        if style_name not in STYLES:
            log.warning(f"Unknown style '{style_name}', keeping '{self._style_name}'")
            return
        self._style_name = style_name
        self._style = STYLES[style_name]
        log.info(f"Face style: {style_name}")

    def get_style_name(self) -> str:
        return self._style_name

    # ── Mood management ──────────────────────────────────────────────────────

    def set_mood(self, mood: Mood) -> None:
        """Transition to a new mood."""
        if mood == self._target.mood:
            return
        self._previous = self._get_current_expression()
        self._target = EXPRESSIONS[mood]
        self._transition_start = time.time()
        self._transitioning = True
        log.debug(f"Mood: {self._previous.mood.name} -> {mood.name}")

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

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Update animation state. Call once per frame."""
        now = time.time()
        self._time = now
        self._current = self._get_current_expression()
        self._update_blink(now)
        self._update_gaze_drift(now, dt)
        self._update_mood_icon(dt)

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

    def _update_mood_icon(self, dt: float) -> None:
        """Update mood icon animation phase and fade."""
        icon = self._mood_icon
        icon.phase += dt * 2.5  # animation speed
        if icon.phase > math.pi * 2:
            icon.phase -= math.pi * 2

        # Fade in/out based on whether current mood has an icon
        mood_name = self._current.mood.name
        has_icon = mood_name in _MOOD_ICONS and mood_name != "NEUTRAL"
        target_alpha = 1.0 if has_icon else 0.0
        fade_speed = 4.0 * dt
        icon.visible_alpha += (target_alpha - icon.visible_alpha) * fade_speed

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the character onto the surface."""
        expr = self._current
        now = self._time
        style = self._style

        # Body animation
        bounce_y = math.sin(now * expr.body.bounce_speed * 2 * math.pi) * expr.body.bounce_amount
        body_cy = int(CY + bounce_y)

        # Apply body tilt by slight horizontal offset (simulates rotation)
        tilt_rad = math.radians(expr.body.tilt)
        tilt_offset_x = int(math.sin(tilt_rad) * 4)

        self._draw_ambient_glow(surface, CX + tilt_offset_x, body_cy)
        self._draw_body(surface, CX + tilt_offset_x, body_cy, expr)
        self._draw_eyes(surface, CX + tilt_offset_x, body_cy, expr, now, style)
        self._draw_mouth(surface, CX + tilt_offset_x, body_cy, expr, style)
        self._draw_mood_icon(surface, CX + tilt_offset_x, body_cy)

    # ── Ambient glow ─────────────────────────────────────────────────────────

    def _draw_ambient_glow(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        """Draw a subtle radial glow behind the cube (matches CSS .ambient-glow)."""
        glow_r = 80  # 160px diameter / 2
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        # Draw concentric circles with decreasing alpha for radial gradient
        for i in range(glow_r, 0, -2):
            frac = i / glow_r
            alpha = int(12 * (1.0 - frac) * (1.0 - frac * frac))
            if alpha > 0:
                pygame.draw.circle(glow_surf, (0, 212, 210, alpha), (glow_r, glow_r), i)
        surface.blit(glow_surf, (cx - glow_r, cy - glow_r), special_flags=pygame.BLEND_RGBA_ADD)

    # ── Body ─────────────────────────────────────────────────────────────────

    def _draw_body(self, surface: pygame.Surface, cx: int, cy: int, expr: Expression) -> None:
        """Draw the dark cube body with glowing edge accents.

        Matches CSS: .cube-face.front background #1a1a2e, .edge-glow #00d4d2.
        """
        scale = expr.body.scale
        w = int(BODY_W * scale)
        h = int(BODY_H * scale)
        r = int(BODY_RADIUS * scale)

        body_rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)

        # Body fill (dark charcoal gradient approximation)
        # Main body color
        pygame.draw.rect(surface, BODY_FILL, body_rect, border_radius=r)

        # Subtle lighter top-left for pseudo-gradient (matches CSS linear-gradient 145deg)
        grad_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for row in range(h):
            frac = row / max(h - 1, 1)
            # Top is lighter, bottom is darker
            alpha = int(8 * (1.0 - frac))
            if alpha > 0:
                pygame.draw.line(grad_surf, (255, 255, 255, alpha), (0, row), (w, row))
        surface.blit(grad_surf, body_rect.topleft)

        # Edge glow lines (matches CSS .edge-glow with 12px inset)
        inset = int(EDGE_INSET * scale)
        glow_w = 2  # matches CSS height: 2px / width: 2px

        # Top edge
        pygame.draw.line(surface, EDGE_GLOW,
                         (body_rect.left + inset, body_rect.top),
                         (body_rect.right - inset, body_rect.top), glow_w)
        # Bottom edge
        pygame.draw.line(surface, EDGE_GLOW,
                         (body_rect.left + inset, body_rect.bottom - 1),
                         (body_rect.right - inset, body_rect.bottom - 1), glow_w)
        # Left edge
        pygame.draw.line(surface, EDGE_GLOW,
                         (body_rect.left, body_rect.top + inset),
                         (body_rect.left, body_rect.bottom - inset), glow_w)
        # Right edge
        pygame.draw.line(surface, EDGE_GLOW,
                         (body_rect.right - 1, body_rect.top + inset),
                         (body_rect.right - 1, body_rect.bottom - inset), glow_w)

        # Edge glow soft bloom (wider dim line behind bright line)
        bloom_surf = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
        bx, by = 4, 4
        bloom_color = (0, 212, 210, 30)
        # Top
        pygame.draw.line(bloom_surf, bloom_color,
                         (bx + inset, by - 1), (bx + w - inset, by - 1), 4)
        # Bottom
        pygame.draw.line(bloom_surf, bloom_color,
                         (bx + inset, by + h), (bx + w - inset, by + h), 4)
        # Left
        pygame.draw.line(bloom_surf, bloom_color,
                         (bx - 1, by + inset), (bx - 1, by + h - inset), 4)
        # Right
        pygame.draw.line(bloom_surf, bloom_color,
                         (bx + w, by + inset), (bx + w, by + h - inset), 4)
        surface.blit(bloom_surf, (body_rect.left - 4, body_rect.top - 4),
                     special_flags=pygame.BLEND_RGBA_ADD)

    # ── Eyes ─────────────────────────────────────────────────────────────────

    def _draw_eyes(self, surface: pygame.Surface, cx: int, cy: int,
                   expr: Expression, now: float, style: FaceStyle) -> None:
        """Draw both eyes based on the active style."""
        eyes = expr.eyes
        s = style.eye

        # Blink: temporarily override openness
        base_openness = eyes.openness
        if self._blink.blink_phase >= 0:
            phase = self._blink.blink_phase
            if phase < 0.5:
                blink_close = phase * 2.0
            else:
                blink_close = (1.0 - phase) * 2.0
            base_openness = base_openness * (1.0 - blink_close * 0.95)

        # Squint reduces openness from top
        base_openness = base_openness * (1.0 - eyes.squint * 0.4)

        # Gaze: combine expression gaze + idle drift
        gaze_x = eyes.gaze_x + self._gaze.current_x
        gaze_y = eyes.gaze_y + self._gaze.current_y
        gaze_x = max(-1.0, min(1.0, gaze_x))
        gaze_y = max(-1.0, min(1.0, gaze_y))

        eye_y = cy + EYE_Y_OFFSET

        # Check for eye color override from expression (battery states)
        eye_color_override = _parse_eye_color_override(expr.eye_color_override)

        # Error mood: draw X_X eyes
        if expr.mood == Mood.ERROR:
            xs = style.x_eye
            for side in (-1, 1):
                ex = cx + side * EYE_SPACING
                self._draw_x_eye(surface, ex, eye_y, xs)
            return

        # Get per-eye overrides from the Expression dataclass
        per_eye_overrides: list[Optional[PerEyeOverride]] = [expr.left_eye, expr.right_eye]

        for side_idx, (side, override) in enumerate(zip((-1, 1), per_eye_overrides)):
            ex = cx + side * EYE_SPACING

            # Apply per-eye overrides from PerEyeOverride dataclass
            eye_width = eyes.width
            eye_height = eyes.height
            eye_openness = base_openness
            eye_tilt = 0.0

            if override is not None:
                if override.width is not None:
                    eye_width = override.width
                if override.height is not None:
                    eye_height = override.height
                if override.openness is not None:
                    # Use the per-eye openness but still apply blink
                    eye_openness = override.openness
                    if self._blink.blink_phase >= 0:
                        phase = self._blink.blink_phase
                        if phase < 0.5:
                            blink_close = phase * 2.0
                        else:
                            blink_close = (1.0 - phase) * 2.0
                        eye_openness = eye_openness * (1.0 - blink_close * 0.95)
                    # Also apply squint
                    sq = override.squint if override.squint is not None else eyes.squint
                    eye_openness = eye_openness * (1.0 - sq * 0.4)
                if override.tilt is not None:
                    eye_tilt = override.tilt

            # Compute eye dimensions
            ew = int(s.base_width * eye_width)
            eh = int(s.base_height * eye_height * max(eye_openness, 0.08))

            fill_color = eye_color_override if eye_color_override else s.fill_color
            glow_color = (*eye_color_override, 85) if eye_color_override else s.glow_color

            # Choose radius based on openness
            if eye_openness < 0.3:
                radius_frac = s.closed_radius
            else:
                radius_frac = s.border_radius
            radius = int(min(ew, eh) * radius_frac)

            eye_rect = pygame.Rect(ex - ew // 2, eye_y - eh // 2, ew, eh)

            if s.type == "roundrect":
                self._draw_eye_roundrect(surface, eye_rect, fill_color, glow_color,
                                          radius, eye_tilt, eye_openness, eyes.squint)
            elif s.type == "iris":
                self._draw_eye_iris(surface, eye_rect, fill_color, glow_color, s,
                                     radius, eye_tilt, eye_openness, eyes.squint,
                                     gaze_x, gaze_y, eye_color_override)
            elif s.type == "dot":
                self._draw_eye_dot(surface, eye_rect, fill_color, glow_color, radius)

    def _draw_eye_roundrect(self, surface: pygame.Surface, rect: pygame.Rect,
                             fill_color: tuple, glow_color: tuple, radius: int,
                             tilt: float, openness: float, squint: float) -> None:
        """Draw kawaii-style rounded rectangle eye (white, solid fill).

        Matches CSS .eye--roundrect with boxShadow glow.
        """
        # Glow behind the eye
        _draw_glow_rect(surface, fill_color, rect, radius,
                        glow_alpha=glow_color[3] if len(glow_color) > 3 else 38)

        # Main eye fill
        _draw_rounded_rect(surface, fill_color, rect, radius, tilt)

        # Eyelid (squint) — draws from top down
        if squint > 0.1 and rect.height > 4:
            lid_h = int(rect.height * squint * 0.45)
            if lid_h > 0:
                lid_surf = pygame.Surface((rect.width + 2, lid_h + 2), pygame.SRCALPHA)
                lid_rect = pygame.Rect(0, 0, rect.width + 2, lid_h + 2)
                pygame.draw.rect(lid_surf, (*BODY_FILL, 240), lid_rect,
                                 border_radius=max(2, radius // 3))
                if tilt != 0.0:
                    lid_surf = pygame.transform.rotate(lid_surf, -tilt)
                    lr = lid_surf.get_rect(midtop=(rect.centerx, rect.top - 1))
                    surface.blit(lid_surf, lr)
                else:
                    surface.blit(lid_surf, (rect.x - 1, rect.y - 1))

    def _draw_eye_iris(self, surface: pygame.Surface, rect: pygame.Rect,
                        fill_color: tuple, glow_color: tuple, s: EyeStyle,
                        radius: int, tilt: float, openness: float, squint: float,
                        gaze_x: float, gaze_y: float,
                        color_override: Optional[tuple] = None) -> None:
        """Draw retro-style eye with sclera + dark iris + highlight.

        Matches CSS .eye--iris with nested .eye-fill, .eye-iris, .eye-highlight.
        """
        # Sclera (white background)
        _draw_rounded_rect(surface, fill_color, rect, radius, tilt)

        # Iris (dark circle centered in eye, offset by gaze)
        min_dim = min(rect.width, rect.height)
        iris_r = int(min_dim * s.iris_size * 0.5)
        iris_x = int(rect.centerx + gaze_x * 5)
        iris_y = int(rect.centery + gaze_y * 4)

        iris_color = s.iris_color
        pygame.draw.circle(surface, iris_color, (iris_x, iris_y), iris_r)

        # Highlight dot (glossy)
        if s.highlight_size > 0 and openness > 0.3:
            hl_r = s.highlight_size // 2
            hl_x = rect.right - 6 - hl_r
            hl_y = rect.top + 4 + hl_r
            hl_color = s.highlight_color[:3] if len(s.highlight_color) > 3 else s.highlight_color
            pygame.draw.circle(surface, hl_color, (hl_x, hl_y), hl_r)

        # Eyelid
        if squint > 0.1 and rect.height > 4:
            lid_h = int(rect.height * squint * 0.45)
            if lid_h > 0:
                lid_surf = pygame.Surface((rect.width + 2, lid_h + 2), pygame.SRCALPHA)
                lid_rect_local = pygame.Rect(0, 0, rect.width + 2, lid_h + 2)
                pygame.draw.rect(lid_surf, (*BODY_FILL, 240), lid_rect_local,
                                 border_radius=max(1, 4))
                surface.blit(lid_surf, (rect.x - 1, rect.y - 1))

    def _draw_eye_dot(self, surface: pygame.Surface, rect: pygame.Rect,
                       fill_color: tuple, glow_color: tuple, radius: int) -> None:
        """Draw minimal-style dot eye (small circle).

        Matches CSS .eye--dot.
        """
        # Glow
        glow_a = glow_color[3] if len(glow_color) > 3 else 102
        glow_surf = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*fill_color[:3], glow_a),
                          (rect.width // 2 + 8, rect.height // 2 + 8),
                          max(rect.width, rect.height) // 2 + 4)
        surface.blit(glow_surf, (rect.x - 8, rect.y - 8), special_flags=pygame.BLEND_RGBA_ADD)

        # Dot
        pygame.draw.circle(surface, fill_color, rect.center,
                          max(rect.width, rect.height) // 2)

    def _draw_x_eye(self, surface: pygame.Surface, cx: int, cy: int,
                     xs: XEyeStyle) -> None:
        """Draw X_X error eyes.

        Matches CSS .x-eye .x-line with rotate(45deg)/-45deg.
        """
        size = xs.size // 2
        thickness = xs.thickness
        color = xs.color

        # X lines with glow
        glow_surf = pygame.Surface((xs.size + 12, xs.size + 12), pygame.SRCALPHA)
        gcx, gcy = glow_surf.get_width() // 2, glow_surf.get_height() // 2
        glow_color = (*color[:3], 80)

        # Glow lines
        pygame.draw.line(glow_surf, glow_color,
                         (gcx - size, gcy - size), (gcx + size, gcy + size), thickness + 4)
        pygame.draw.line(glow_surf, glow_color,
                         (gcx + size, gcy - size), (gcx - size, gcy + size), thickness + 4)
        surface.blit(glow_surf, (cx - glow_surf.get_width() // 2, cy - glow_surf.get_height() // 2),
                     special_flags=pygame.BLEND_RGBA_ADD)

        # Sharp lines
        pygame.draw.line(surface, color,
                         (cx - size, cy - size), (cx + size, cy + size), thickness)
        pygame.draw.line(surface, color,
                         (cx + size, cy - size), (cx - size, cy + size), thickness)

    # ── Mouth ────────────────────────────────────────────────────────────────

    def _draw_mouth(self, surface: pygame.Surface, cx: int, cy: int,
                     expr: Expression, style: FaceStyle) -> None:
        """Draw the mouth based on the active style.

        Matches VoxelCube.jsx Mouth component with style-based rendering.
        """
        mouth = expr.mouth
        s = style.mouth
        mood_name = self._current.mood.name

        # Position mouth below eyes (gap: 14px from CSS .face-inner)
        mouth_y = cy + MOUTH_Y_OFFSET

        # Error: flat line mouth
        if expr.mood == Mood.ERROR:
            line_w = 28  # CSS .mouth-flat width: 28px
            # Glow
            glow_surf = pygame.Surface((line_w + 12, 12), pygame.SRCALPHA)
            pygame.draw.line(glow_surf, (*ERROR_RED[:3], 80),
                            (6, 6), (line_w + 6, 6), 5)
            surface.blit(glow_surf, (cx - line_w // 2 - 6, mouth_y - 6),
                         special_flags=pygame.BLEND_RGBA_ADD)
            pygame.draw.line(surface, ERROR_RED,
                             (cx - line_w // 2, mouth_y),
                             (cx + line_w // 2, mouth_y), 3)
            return

        # Audio-reactive: override openness during speech
        openness = mouth.openness
        if self.audio_amplitude > 0.05:
            openness = max(openness, self.audio_amplitude * 0.8)

        if s.type == "offset":
            self._draw_mouth_offset(surface, cx, mouth_y, mouth, s, openness)
        elif s.type == "teeth":
            self._draw_mouth_teeth(surface, cx, mouth_y, mouth, s, openness)
        elif s.type == "arc":
            self._draw_mouth_arc(surface, cx, mouth_y, mouth, s, openness)

    def _draw_mouth_offset(self, surface: pygame.Surface, cx: int, mouth_y: int,
                            mouth: MouthConfig, s: MouthStyle, openness: float) -> None:
        """Draw offset-style mouth (kawaii): small centered curve or open ellipse.

        Matches CSS .mouth-offset with SVG bezier curves.
        """
        smile = mouth.smile
        w = int(s.base_width * mouth.width)

        # Open mouth (speaking or expressive)
        if openness > 0.15:
            mouth_w = int(w * (0.6 + openness * 0.4))
            mouth_h = int(14 * openness)
            if mouth_h < 3:
                mouth_h = 3

            rect = pygame.Rect(cx - mouth_w // 2, mouth_y - mouth_h // 2, mouth_w, mouth_h)

            # Determine border radius based on smile
            if smile > 0.5:
                # Happy open mouth: flat top, round bottom (CSS borderRadius: 2px 2px 50% 50%)
                # Approximate with a moderate radius
                br = max(2, mouth_h // 2)
            else:
                # Round open mouth
                br = max(2, min(mouth_w, mouth_h) // 2)

            # Draw filled mouth
            mouth_color = (*s.color[:3], int(255 * 0.9))
            mouth_surf = pygame.Surface((mouth_w + 2, mouth_h + 2), pygame.SRCALPHA)
            mr = pygame.Rect(1, 1, mouth_w, mouth_h)
            pygame.draw.rect(mouth_surf, mouth_color, mr, border_radius=br)
            surface.blit(mouth_surf, (rect.x - 1, rect.y - 1))
            return

        # Closed mouth: SVG-style bezier curve
        # Matches: M 2 5 Q 15 {5 + curveDepth} 28 5 (smile) or M 2 9 Q 15 {9 + curveDepth} 28 9 (frown)
        half_w = w // 2
        curve_depth = smile * 8  # matches JS curveDepth = smile * 8

        if smile >= 0:
            # Smile curve: start at baseline, curve downward
            baseline_y = mouth_y
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_depth))
            p2 = (cx + half_w, baseline_y)
        else:
            # Frown: curve upward
            baseline_y = mouth_y + 4
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_depth))
            p2 = (cx + half_w, baseline_y)

        points = _quadratic_bezier_points(p0, p1, p2, steps=20)
        if len(points) > 1:
            pygame.draw.lines(surface, s.color, False, points, s.stroke_width)

    def _draw_mouth_teeth(self, surface: pygame.Surface, cx: int, mouth_y: int,
                           mouth: MouthConfig, s: MouthStyle, openness: float) -> None:
        """Draw retro-style mouth with teeth.

        Matches CSS .mouth-teeth with .tooth elements.
        """
        smile = mouth.smile
        w = int(s.base_width * mouth.width)

        # Open mouth with teeth
        if openness > 0.15 or smile > 0.4:
            mouth_w = w
            mouth_h = max(int(14 * max(openness, smile * 0.5)), 8)

            rect = pygame.Rect(cx - mouth_w // 2, mouth_y - mouth_h // 2, mouth_w, mouth_h)

            # Dark mouth background
            pygame.draw.rect(surface, (26, 10, 10), rect, border_radius=4)
            # Border
            pygame.draw.rect(surface, (0, 0, 0, 50), rect, width=2, border_radius=4)

            # Teeth row
            tooth_w = 5
            tooth_h = min(6, mouth_h - 2)
            num_teeth = max(int(mouth_w / 6), 3)
            total_teeth_w = num_teeth * tooth_w + (num_teeth - 1)
            start_x = rect.centerx - total_teeth_w // 2

            for i in range(num_teeth):
                tx = start_x + i * (tooth_w + 1)
                ty = rect.top + 1
                tooth_rect = pygame.Rect(tx, ty, tooth_w, tooth_h)
                pygame.draw.rect(surface, s.teeth_color, tooth_rect,
                                 border_radius=1)
            return

        # Closed retro mouth: bezier curve
        half_w = w // 2
        curve_y = smile * 6

        if smile >= 0:
            baseline_y = mouth_y
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_y))
            p2 = (cx + half_w, baseline_y)
        else:
            baseline_y = mouth_y + 4
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_y))
            p2 = (cx + half_w, baseline_y)

        points = _quadratic_bezier_points(p0, p1, p2, steps=20)
        if len(points) > 1:
            pygame.draw.lines(surface, s.color, False, points, s.stroke_width)

    def _draw_mouth_arc(self, surface: pygame.Surface, cx: int, mouth_y: int,
                         mouth: MouthConfig, s: MouthStyle, openness: float) -> None:
        """Draw minimal arc-style mouth.

        Matches CSS .mouth-open (ellipse) and .mouth-closed (SVG arc).
        """
        smile = mouth.smile

        # Open mouth: ellipse
        if openness > 0.15:
            mouth_w = int(s.base_width * mouth.width * (0.6 + openness * 0.4))
            mouth_h = int(18 * openness)
            if mouth_h < 2:
                mouth_h = 2
            rect = pygame.Rect(cx - mouth_w // 2, mouth_y - mouth_h // 2, mouth_w, mouth_h)
            pygame.draw.ellipse(surface, s.color, rect)
            # Dark interior
            inner = rect.inflate(-4, -4)
            if inner.width > 2 and inner.height > 2:
                pygame.draw.ellipse(surface, BODY_DARK, inner)
            return

        # Closed: arc curve
        base_w = int(s.base_width * mouth.width)
        half_w = base_w // 2
        curve_y = smile * 6

        if smile >= 0:
            baseline_y = mouth_y
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_y))
            p2 = (cx + half_w, baseline_y)
        else:
            baseline_y = mouth_y + 4
            p0 = (cx - half_w, baseline_y)
            p1 = (cx, baseline_y + int(curve_y))
            p2 = (cx + half_w, baseline_y)

        points = _quadratic_bezier_points(p0, p1, p2, steps=16)
        if len(points) > 1:
            pygame.draw.lines(surface, s.color, False, points, s.stroke_width)

    # ── Mood icons ───────────────────────────────────────────────────────────

    def _get_icon_font(self, size: int) -> pygame.font.Font:
        """Lazy-init and cache fonts by size."""
        if size not in self._icon_fonts:
            try:
                self._icon_fonts[size] = pygame.font.SysFont("monospace", size, bold=True)
            except Exception:
                self._icon_fonts[size] = pygame.font.Font(None, size)
        return self._icon_fonts[size]

    def _draw_mood_icon(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        """Draw floating mood effect icons in the upper-right area.

        Matches VoxelCube.jsx MoodEffects component with per-mood icons.
        """
        mood_name = self._current.mood.name
        icon_data = _MOOD_ICONS.get(mood_name)
        if icon_data is None:
            return

        alpha = self._mood_icon.visible_alpha
        if alpha < 0.05:
            return

        text, color, font_size, anim_type = icon_data
        phase = self._mood_icon.phase
        now = self._time

        # Base position: upper-right area (matches CSS top/right positioning)
        # Body rect upper-right corner area
        body_right = cx + BODY_W // 2
        body_top = cy - BODY_H // 2
        icon_x = body_right - 10
        icon_y = body_top - 4

        # Animation offsets
        anim_offset_x = 0.0
        anim_offset_y = 0.0
        anim_scale = 1.0
        anim_alpha = alpha

        if anim_type == "pulse":
            # Scale pulse (matches animate scale: [1, 1.15, 1])
            anim_scale = 1.0 + 0.15 * math.sin(phase)
            anim_alpha *= 0.6 + 0.4 * (0.5 + 0.5 * math.sin(phase))

        elif anim_type == "float":
            # Float upward (zzz effect)
            anim_offset_y = -10 * (0.5 + 0.5 * math.sin(phase))
            anim_alpha *= 0.5 + 0.5 * math.sin(phase * 0.5 + 0.3)

        elif anim_type == "bounce":
            # Gentle vertical bounce (matches animate y: [0, -3, 0])
            anim_offset_y = -3 * math.sin(phase)

        elif anim_type == "blink":
            # Fade in and out (matches animate opacity: [0.3, 0.8, 0.3])
            anim_alpha *= 0.3 + 0.5 * (0.5 + 0.5 * math.sin(phase))

        elif anim_type == "spin":
            # For text we just pulse since we can't rotate text easily
            anim_alpha *= 0.6 + 0.4 * (0.5 + 0.5 * math.sin(phase))

        elif anim_type == "shake":
            # Horizontal shake (matches animate x: [-1, 1, -1])
            anim_offset_x = 2 * math.sin(phase * 4)
            anim_alpha *= 0.5 + 0.4 * (0.5 + 0.5 * math.sin(phase))

        # Render text
        font = self._get_icon_font(font_size)
        text_surf = font.render(text, True, color)

        # Apply alpha
        final_alpha = int(max(0, min(255, anim_alpha * 255)))
        if final_alpha < 10:
            return

        text_surf.set_alpha(final_alpha)

        # Position with animation offsets
        draw_x = int(icon_x + anim_offset_x - text_surf.get_width())
        draw_y = int(icon_y + anim_offset_y)

        surface.blit(text_surf, (draw_x, draw_y))
