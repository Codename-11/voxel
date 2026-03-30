"""Mood-specific decorative sub-animations.

Sparkles for excited, sweat drops for frustrated, ZZZs for sleepy, etc.
Drawn on top of the character face as lightweight overlay effects.

Position reference (Voxel character):
  Face center: ~(120, 155) with bounce/tilt offsets
  Eye spacing: ±30px from face center
  Eyes: pill shapes at face_cy, EYE_BASE_H ~72px
  Margins: 22px above, 21px right, 38px below, 31px left

Eye positions are passed as (left_eye, right_eye) tuples so decorations
like tears and blush land on the correct spots regardless of character.
"""

from __future__ import annotations

import math
import random
from PIL import Image, ImageDraw
from display.layout import SCREEN_W, SCREEN_H, ICON_Y
from display.fonts import get_font
from display.overlay import color_with_alpha as _color_with_alpha, draw_on_overlay as _draw_on_overlay

# ── Animation state ────────────────────────────────────────────────────────

_state: dict[str, float] = {}
_last_mood: str = ""
_sparkle_positions: list[tuple[int, int]] = []


def _reset_state() -> None:
    """Clear all animation state for a fresh mood transition."""
    global _sparkle_positions
    _state.clear()
    _sparkle_positions = []


# ── Thinking dots ─────────────────────────────────────────────────────────

def _draw_thinking(draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float, cx: int, cy: int,
                   left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Three dots appearing one by one above the cube, then fading."""
    cycle = 2.4
    phase = (now % cycle) / cycle

    dot_appear_time = 0.125
    dots_y = ICON_Y
    dot_spacing = 12
    dot_r = 4

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        start_x = SCREEN_W // 2 - dot_spacing
        for i in range(3):
            dot_start = i * dot_appear_time
            dot_x = start_x + i * dot_spacing
            dot_y = dots_y

            if phase < dot_start:
                continue

            time_since_appear = phase - dot_start
            fade_start = 3 * dot_appear_time + 0.3
            if phase > fade_start:
                fade_t = (phase - fade_start) / (1.0 - fade_start)
                alpha = 1.0 - min(1.0, fade_t)
            else:
                pop_t = min(1.0, time_since_appear / 0.08)
                alpha = pop_t

            color = _color_with_alpha((180, 200, 210), alpha * 0.85)
            od.ellipse([
                dot_x - dot_r, dot_y - dot_r,
                dot_x + dot_r, dot_y + dot_r,
            ], fill=color)

    _draw_on_overlay(img, _overlay)


# ── Floating ZZZ (sleepy) ─────────────────────────────────────────────────

def _draw_sleepy(draw: ImageDraw.ImageDraw, img: Image.Image,
                 now: float, cx: int, cy: int,
                 left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Floating 'Z z z' rising from upper-right of cube toward top margin."""
    cycle = 3.5
    phase = (now % cycle) / cycle

    z_configs = [
        {"size": 16, "offset_x": 40, "delay": 0.0},
        {"size": 12, "offset_x": 48, "delay": 0.15},
        {"size": 9,  "offset_x": 54, "delay": 0.30},
    ]

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        for cfg in z_configs:
            z_phase = phase - cfg["delay"]
            if z_phase < 0:
                z_phase += 1.0

            start_y = cy - 50
            rise = int(z_phase * 55)
            zy = start_y - rise
            zx = cx + cfg["offset_x"] + int(math.sin(z_phase * math.pi * 2) * 3)

            if z_phase < 0.2:
                alpha = z_phase / 0.2
            elif z_phase > 0.8:
                alpha = (1.0 - z_phase) / 0.2
            else:
                alpha = 1.0

            font = get_font(cfg["size"])
            color = _color_with_alpha((160, 200, 220), alpha * 0.8)
            od.text((zx, zy), "Z", fill=color, font=font)

    _draw_on_overlay(img, _overlay)


# ── Exclamation mark (surprised) ──────────────────────────────────────────

def _draw_surprised(draw: ImageDraw.ImageDraw, img: Image.Image,
                    now: float, cx: int, cy: int,
                    left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """'!' that pops above the cube, then fades."""
    cycle = 2.5
    phase = (now % cycle) / cycle

    if phase > 0.4:
        return

    t = phase / 0.4

    if t < 0.2:
        scale = t / 0.2
        alpha = scale
    elif t < 0.6:
        scale = 1.0
        alpha = 1.0
    else:
        scale = 1.0
        alpha = 1.0 - (t - 0.6) / 0.4

    font_size = int(24 * max(0.3, scale))
    bang_x = SCREEN_W // 2
    bang_y = ICON_Y

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        font = get_font(font_size)
        color = _color_with_alpha((255, 240, 100), alpha * 0.95)
        od.text((bang_x, bang_y), "!", fill=color, font=font, anchor="mm")

    _draw_on_overlay(img, _overlay)


# ── Sweat drop (frustrated) ───────────────────────────────────────────────

def _draw_frustrated(draw: ImageDraw.ImageDraw, img: Image.Image,
                     now: float, cx: int, cy: int,
                     left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Sweat drop sliding down the right side of the cube."""
    cycle = 2.5
    phase = (now % cycle) / cycle

    drop_x = cx + 50
    start_y = cy - 55
    end_y = cy - 5
    drop_y = int(start_y + (end_y - start_y) * phase)

    alpha = 1.0 if phase < 0.7 else 1.0 - (phase - 0.7) / 0.3

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        color = _color_with_alpha((120, 180, 220), alpha * 0.9)
        r = 4
        od.ellipse([drop_x - r, drop_y - r, drop_x + r, drop_y + r], fill=color)
        od.polygon([
            (drop_x, drop_y - r - 7),
            (drop_x - r, drop_y - r + 1),
            (drop_x + r, drop_y - r + 1),
        ], fill=color)

    _draw_on_overlay(img, _overlay)


# ── Tear drops (sad) ──────────────────────────────────────────────────────

def _draw_sad(draw: ImageDraw.ImageDraw, img: Image.Image,
              now: float, cx: int, cy: int,
              left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Small tears under each eye that grow, fall, and reset.

    Uses actual eye positions so tears fall from the correct spots.
    """
    cycle = 2.0
    phase = (now % cycle) / cycle

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        for eye_x, eye_y in (left_eye, right_eye):
            ey = eye_y + 14

            if phase < 0.4:
                t = phase / 0.4
                tear_h = int(3 + t * 4)
                tear_y = ey
                alpha = 0.5 + t * 0.5
            elif phase < 0.9:
                t = (phase - 0.4) / 0.5
                tear_h = 7
                tear_y = ey + int(t * 15)
                alpha = 1.0
            else:
                t = (phase - 0.9) / 0.1
                tear_h = 7
                tear_y = ey + 15
                alpha = 1.0 - t

            tear_w = 3
            color = _color_with_alpha((100, 160, 220), alpha * 0.75)
            od.ellipse([
                eye_x - tear_w, tear_y,
                eye_x + tear_w, tear_y + tear_h,
            ], fill=color)

    _draw_on_overlay(img, _overlay)


# ── Hearts (happy) ───────────────────────────────────────────────────────

def _draw_happy(draw: ImageDraw.ImageDraw, img: Image.Image,
                now: float, cx: int, cy: int,
                left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Small floating heart that pops and fades above the face."""
    cycle = 3.0
    phase = (now % cycle) / cycle

    if phase > 0.6:
        return

    t = phase / 0.6
    if t < 0.15:
        scale_f = t / 0.15
        alpha = scale_f
    elif t < 0.5:
        scale_f = 1.0
        alpha = 1.0
    else:
        scale_f = 1.0
        alpha = 1.0 - (t - 0.5) / 0.5

    rise = int(t * 20)
    heart_x = right_eye[0] + 16
    heart_y = right_eye[1] - 30 - rise

    font_size = max(10, int(16 * scale_f))

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        font = get_font(font_size)
        color = _color_with_alpha((255, 107, 138), alpha * 0.9)
        od.text((heart_x, heart_y), "\u2665", fill=color, font=font, anchor="mm")

    _draw_on_overlay(img, _overlay)


# ── Bouncing !! (excited) ────────────────────────────────────────────────

def _draw_excited(draw: ImageDraw.ImageDraw, img: Image.Image,
                  now: float, cx: int, cy: int,
                  left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Bouncing '!!' marks above the face with warm sparkle accents."""
    cycle = 1.8
    phase = (now % cycle) / cycle

    bounce = abs(math.sin(phase * math.pi * 2)) * 8
    text_y = ICON_Y - int(bounce)

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        font = get_font(18)
        alpha = 0.7 + 0.3 * math.sin(phase * math.pi * 4)
        color = _color_with_alpha((64, 255, 248), alpha)
        od.text((SCREEN_W // 2, text_y), "!!", fill=color, font=font, anchor="mm")

        # Small warm sparkle accents in margins
        sparkle_phase = (now * 1.5) % 1.0
        for i, (sx, sy) in enumerate([
            (cx - 45, cy - 20),
            (cx + 48, cy + 10),
        ]):
            sp = (sparkle_phase + i * 0.4) % 1.0
            sa = math.sin(sp * math.pi) * 0.6
            if sa > 0.05:
                sc = _color_with_alpha((255, 220, 100), sa)
                s = 4
                od.line([(sx, sy - s), (sx, sy + s)], fill=sc, width=1)
                od.line([(sx - s, sy), (sx + s, sy)], fill=sc, width=1)

    _draw_on_overlay(img, _overlay)


# ── Question marks (confused) ────────────────────────────────────────────

def _draw_confused(draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float, cx: int, cy: int,
                   left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Three '???' with staggered pulse animation above the face."""
    cycle = 2.5
    phase = (now % cycle) / cycle

    font = get_font(15)

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        for i, offset_x in enumerate([-12, 0, 12]):
            t = (phase + i * 0.12) % 1.0
            alpha = 0.35 + 0.55 * max(0.0, math.sin(t * math.pi * 2))
            color = _color_with_alpha((0, 212, 210), alpha * 0.85)
            od.text(
                (SCREEN_W // 2 + offset_x, ICON_Y), "?",
                fill=color, font=font, anchor="mm",
            )

    _draw_on_overlay(img, _overlay)


# ── Spinning dots (working) ──────────────────────────────────────────────

def _draw_working(draw: ImageDraw.ImageDraw, img: Image.Image,
                  now: float, cx: int, cy: int,
                  left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Spinning loading dots above the face — like a gear/cog rotation."""
    num_dots = 8
    radius = 10
    center_x = SCREEN_W // 2
    center_y = ICON_Y
    rotation = now * 2.5

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        for i in range(num_dots):
            angle = rotation + i * (2 * math.pi / num_dots)
            dx = int(math.cos(angle) * radius)
            dy = int(math.sin(angle) * radius)
            t = i / num_dots
            alpha = 0.15 + 0.75 * t
            r = 3 if i >= num_dots // 2 else 2
            color = _color_with_alpha((0, 212, 210), alpha * 0.9)
            od.ellipse([
                center_x + dx - r, center_y + dy - r,
                center_x + dx + r, center_y + dy + r,
            ], fill=color)

    _draw_on_overlay(img, _overlay)


# ── Listening arcs ───────────────────────────────────────────────────────

def _draw_listening(draw: ImageDraw.ImageDraw, img: Image.Image,
                    now: float, cx: int, cy: int,
                    left_eye: tuple[int, int], right_eye: tuple[int, int]) -> None:
    """Pulsing expanding arcs ))) above the face — indicates active mic."""
    cycle = 2.0
    phase = (now % cycle) / cycle

    arc_cx = SCREEN_W // 2
    arc_cy = ICON_Y

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        for i in range(3):
            # Staggered expanding arcs
            t = (phase + i * 0.12) % 1.0
            arc_r = 4 + i * 5
            alpha = 0.3 + 0.6 * max(0.0, math.sin(t * math.pi * 2))
            color = _color_with_alpha((0, 212, 210), alpha * 0.8)
            # Draw right-facing arc (like a ))) symbol)
            bbox = [arc_cx + i * 4 - arc_r, arc_cy - arc_r,
                    arc_cx + i * 4 + arc_r, arc_cy + arc_r]
            od.arc(bbox, start=-60, end=60, fill=color, width=2)

    _draw_on_overlay(img, _overlay)


# ── Mood dispatch table ──────────────────────────────────────────────────

_MOOD_RENDERERS = {
    "excited": _draw_excited,
    "frustrated": _draw_frustrated,
    "sleepy": _draw_sleepy,
    "sad": _draw_sad,
    "surprised": _draw_surprised,
    "thinking": _draw_thinking,
    "happy": _draw_happy,
    "confused": _draw_confused,
    "working": _draw_working,
    "listening": _draw_listening,
}


# ── Public API ────────────────────────────────────────────────────────────

def draw_mood_decorations(draw: ImageDraw.ImageDraw, img: Image.Image,
                          mood: str, now: float,
                          face_cx: int, face_cy: int,
                          left_eye: tuple[int, int] | None = None,
                          right_eye: tuple[int, int] | None = None) -> None:
    global _last_mood

    if mood != _last_mood:
        _reset_state()
        _last_mood = mood

    renderer = _MOOD_RENDERERS.get(mood)
    if renderer is not None:
        if left_eye is None:
            left_eye = (face_cx - 30, face_cy)
        if right_eye is None:
            right_eye = (face_cx + 30, face_cy)
        renderer(draw, img, now, face_cx, face_cy, left_eye, right_eye)
