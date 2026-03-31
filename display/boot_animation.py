"""Boot animation — "wake up" sequence for Voxel.

Plays a ~3-second cinematic boot animation after the splash screen,
BEFORE the main render loop starts. The character's eyes power on,
slide apart, blink open, look around, and settle into neutral.

Works on both Pi (SPI backend) and desktop (tkinter/pygame backend).
Uses the same PIL rendering approach as voxel.py for visual consistency.
"""

from __future__ import annotations

import logging
import math
import time

from PIL import Image, ImageDraw

from display.layout import SCREEN_W, SCREEN_H, STATUS_H
from display.characters.voxel import (
    CX, CY, EYE_SPACING as _MAIN_EYE_SPACING, EYE_BASE_W, EYE_BASE_H, GLOW_PAD, BG,
)

# Boot animation uses tighter spacing than the main renderer.
# Eyes start together and slide to this distance — slightly closer
# than the final rendering spacing for a cozy "waking up" feel.
# The main render loop uses the full EYE_SPACING from voxel.py.
BOOT_EYE_SPACING = 32

log = logging.getLogger("voxel.display.boot_animation")

# ── Animation timing (seconds) ──────────────────────────────────────────────

PHASE_GLOW_START    = 0.0
PHASE_GLOW_END      = 0.5

PHASE_BARS_START    = 0.5
PHASE_BARS_END      = 1.0

PHASE_SLIDE_START   = 1.0
PHASE_SLIDE_END     = 1.5

PHASE_BLINK_L_START = 1.5      # left eye opens first
PHASE_BLINK_L_END   = 1.7      # fast: 200ms
PHASE_BLINK_R_START = 1.65     # right eye starts 150ms after left
PHASE_BLINK_R_END   = 1.85

PHASE_LOOK_START    = 2.3
PHASE_LOOK_END      = 2.8

PHASE_SETTLE_START  = 2.8
PHASE_SETTLE_END    = 3.0

TOTAL_DURATION      = 3.0

# ── Easing functions ─────────────────────────────────────────────────────────


def _ease_out(t: float) -> float:
    """Deceleration — fast start, smooth stop."""
    return 1.0 - (1.0 - t) * (1.0 - t)


def _ease_in_out(t: float) -> float:
    """Smooth acceleration and deceleration."""
    return t * t * (3.0 - 2.0 * t)


def _ease_in(t: float) -> float:
    """Acceleration — slow start, fast end."""
    return t * t


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation, clamped to [0, 1]."""
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def _progress(now: float, start: float, end: float) -> float:
    """Return 0..1 progress through a time range (clamped)."""
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start) / (end - start)


def _scale_color(c: tuple, f: float) -> tuple:
    """Scale an RGB color by a brightness factor."""
    return tuple(min(255, int(v * f)) for v in c)


# ── Core rendering helpers ───────────────────────────────────────────────────


def _draw_glow_pulse(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                     intensity: float, accent: tuple) -> None:
    """Draw a soft radial glow at center — the 'soul' powering on."""
    if intensity <= 0.001:
        return
    # Layered concentric rounded rectangles for a soft glow effect
    layers = [
        (80, 0.04),   # large, very dim
        (50, 0.08),   # medium
        (30, 0.14),   # smaller, brighter
        (16, 0.22),   # core glow
    ]
    for radius, base_alpha in layers:
        alpha = base_alpha * intensity
        color = _scale_color(accent, alpha)
        r = int(radius * (0.6 + 0.4 * intensity))
        draw.rounded_rectangle(
            [cx - r, cy - r, cx + r, cy + r],
            radius=r // 2,
            fill=color,
        )


def _draw_closed_bar(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                     width: int, alpha: float, accent: tuple,
                     glow_alpha: float = 1.0) -> None:
    """Draw a closed-eye bar with filleted ends (matches voxel.py closed eyes)."""
    if alpha <= 0.001:
        return
    bar_h = max(5, 7)
    fillet = max(2, 3)
    fill = _scale_color(accent, alpha)

    # Subtle glow halo
    if glow_alpha > 0.01:
        glow_c = _scale_color(accent, 0.12 * alpha * glow_alpha)
        gp = GLOW_PAD
        glow_r = min(width // 2 + gp, (bar_h + 2 * gp) // 2)
        draw.rounded_rectangle(
            [cx - width // 2 - gp, cy - bar_h // 2 - gp,
             cx + width // 2 + gp, cy + bar_h // 2 + gp],
            radius=glow_r, fill=glow_c,
        )

    draw.rounded_rectangle(
        [cx - width // 2, cy - bar_h // 2,
         cx + width // 2, cy + bar_h // 2],
        radius=fillet, fill=fill,
    )


def _draw_open_eye(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   width: int, height: int, openness: float,
                   accent: tuple, glow: float = 1.0) -> None:
    """Draw an open pill-shaped eye at the given openness (0=closed, 1=full open)."""
    # When openness is very low, draw a bar instead
    if openness < 0.12:
        _draw_closed_bar(draw, cx, cy, width, glow, accent, glow_alpha=glow)
        return

    # Compute eye height from openness
    eh = max(int(height * openness), 6)
    ew = width

    # Enforce pill aspect ratio (same as voxel.py)
    if openness > 0.4:
        eh = max(eh, int(ew * 1.35))

    radius = ew // 2  # full capsule ends

    x0 = cx - ew // 2
    y0 = cy - eh // 2
    x1 = cx + ew // 2
    y1 = cy + eh // 2

    fill = _scale_color(accent, glow)

    # Glow halo
    gp = GLOW_PAD
    glow_c = _scale_color(accent, 0.12 * glow)
    glow_r = min(ew // 2 + gp, (eh + 2 * gp) // 2)
    draw.rounded_rectangle(
        [x0 - gp, y0 - gp, x1 + gp, y1 + gp],
        radius=glow_r, fill=glow_c,
    )

    # Main pill
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


# ── Blink open animation ────────────────────────────────────────────────────
# Asymmetric timing: fast close (28%), slow open (72%) — from animation.py.
# For the boot "blink open", we reverse it: we start closed and open up.
# Phase 0..1: 0=fully closed, 1=fully open.
# Close fraction 28% → means the first 28% is the "snap" (close→open fast),
# remaining 72% is the gentle ease open.
# Since we're opening FROM closed, we go 0→1 where:
#   0.0-0.28: rapid initial opening (ease-in quadratic for snap)
#   0.28-1.0: gentle complete opening (ease-out for smooth finish)

CLOSE_FRACTION = 0.28


def _blink_open_curve(t: float) -> float:
    """Map blink-open progress (0=closed, 1=open) with asymmetric timing."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    if t < CLOSE_FRACTION:
        # Fast initial opening (0→~30% openness)
        sub_t = t / CLOSE_FRACTION
        return sub_t * sub_t * 0.3  # ease-in, caps at 30%
    else:
        # Slow gentle complete opening (30%→100%)
        sub_t = (t - CLOSE_FRACTION) / (1.0 - CLOSE_FRACTION)
        eased = 1.0 - (1.0 - sub_t) * (1.0 - sub_t)  # ease-out
        return 0.3 + eased * 0.7


# ── Main animation function ─────────────────────────────────────────────────


def play_boot_animation(backend, config: dict | None = None) -> None:
    """Play the full wake-up boot animation.

    Renders frames directly to the backend (PIL -> push_frame).
    Blocking — plays the full ~3s animation, then returns.

    Args:
        backend: An initialized OutputBackend (SPI or tkinter/pygame).
        config: Optional config dict for accent color override.
    """
    config = config or {}
    char_cfg = config.get("character", {})
    accent_hex = char_cfg.get("accent_color", "#00d4d2")

    # Parse accent color
    h = accent_hex.lstrip("#")
    if len(h) == 6:
        accent = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    else:
        accent = (0, 212, 210)

    target_fps = config.get("display", {}).get("fps", 30)
    frame_interval = 1.0 / target_fps

    log.info("Boot animation: starting (%s, %.1fs, %d FPS)",
             accent_hex, TOTAL_DURATION, target_fps)

    start = time.time()
    frame_count = 0

    while True:
        frame_start = time.time()
        elapsed = frame_start - start

        if elapsed >= TOTAL_DURATION:
            break

        # ── Create frame ──────────────────────────────────────────
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
        draw = ImageDraw.Draw(img)

        # ── Phase 1: Glow pulse (0-0.5s) ─────────────────────────
        glow_p = _progress(elapsed, PHASE_GLOW_START, PHASE_GLOW_END)
        if glow_p > 0:
            # Pulsing intensity — sine wave that fades in
            pulse = math.sin(glow_p * math.pi * 2) * 0.3 + 0.7
            glow_intensity = _ease_in(glow_p) * pulse
            _draw_glow_pulse(draw, CX, CY, glow_intensity, accent)

        # Keep a subtle ambient glow through all subsequent phases
        if elapsed > PHASE_GLOW_END:
            ambient_glow = 0.15 + math.sin(elapsed * 0.5) * 0.05
            _draw_glow_pulse(draw, CX, CY, ambient_glow, accent)

        # ── Phase 2: Bars appear (0.5-1.0s) ──────────────────────
        bars_p = _progress(elapsed, PHASE_BARS_START, PHASE_BARS_END)
        if bars_p > 0 and elapsed < PHASE_SLIDE_END:
            bar_alpha = _ease_in_out(bars_p)
            bar_width = int(EYE_BASE_W * bar_alpha)

            # Bars start close together at center (spacing = 0)
            # During slide phase, they move apart
            slide_p = _progress(elapsed, PHASE_SLIDE_START, PHASE_SLIDE_END)
            current_spacing = int(BOOT_EYE_SPACING * _ease_out(slide_p))

            # Left bar
            _draw_closed_bar(draw, CX - current_spacing, CY,
                             bar_width, bar_alpha, accent)
            # Right bar
            _draw_closed_bar(draw, CX + current_spacing, CY,
                             bar_width, bar_alpha, accent)

        # ── Phase 3: Bars slide apart (1.0-1.5s) ─────────────────
        # Handled above in bars_p section (spacing increases via slide_p)

        # ── Phase 4: Eyes blink open (1.5-2.3s) ──────────────────
        if elapsed >= PHASE_BLINK_L_START:
            # Left eye
            left_p = _progress(elapsed, PHASE_BLINK_L_START, PHASE_BLINK_L_END)
            left_openness = _blink_open_curve(left_p)

            # Right eye (starts slightly later)
            right_p = _progress(elapsed, PHASE_BLINK_R_START, PHASE_BLINK_R_END)
            right_openness = _blink_open_curve(right_p)

            # Glow breathing
            glow_t = (math.sin(elapsed * 0.5) + 1.0) / 2.0
            glow = 0.85 + glow_t * 0.15

            # Gaze during look-around phase
            gaze_x = 0.0
            if elapsed >= PHASE_LOOK_START:
                look_p = _progress(elapsed, PHASE_LOOK_START, PHASE_LOOK_END)
                # Look left, then right, then center
                # 0-0.33: drift left, 0.33-0.66: drift right, 0.66-1.0: center
                if look_p < 0.33:
                    sub_t = look_p / 0.33
                    gaze_x = -_ease_in_out(sub_t) * 0.35
                elif look_p < 0.66:
                    sub_t = (look_p - 0.33) / 0.33
                    gaze_x = _lerp(-0.35, 0.35, _ease_in_out(sub_t))
                else:
                    sub_t = (look_p - 0.66) / 0.34
                    gaze_x = _lerp(0.35, 0.0, _ease_in_out(sub_t))

            gaze_shift_x = int(gaze_x * 35)

            # ── Settle phase: lerp eye spacing to match main renderer ──
            # During 2.8-3.0s, smoothly transition from BOOT_EYE_SPACING
            # to the real EYE_SPACING so the last frame has zero
            # discontinuity with the main render loop.
            settle_p = _progress(elapsed, PHASE_SETTLE_START, PHASE_SETTLE_END)
            current_eye_spacing = _lerp(
                BOOT_EYE_SPACING, _MAIN_EYE_SPACING, _ease_in_out(settle_p)
            )

            # Gaze-proportional perspective sizing
            for side in (-1, 1):
                ex = CX + side * int(current_eye_spacing) + gaze_shift_x
                openness = left_openness if side == -1 else right_openness

                # Perspective effect from gaze
                gaze_perspective = gaze_x * side
                perspective_w = 1.0 - gaze_perspective * 0.12
                perspective_h = 1.0 - gaze_perspective * 0.06

                ew = int(EYE_BASE_W * perspective_w)
                eh = int(EYE_BASE_H * perspective_h)

                _draw_open_eye(draw, ex, CY, ew, eh, openness,
                               accent, glow=glow)

        # ── Phase 5: Settle (2.8-3.0s) ────────────────────────────
        # Eye spacing lerps from BOOT_EYE_SPACING to _MAIN_EYE_SPACING
        # during the settle phase (handled above). Gaze returns to center
        # and both eyes reach full openness.

        # ── Push frame ────────────────────────────────────────────
        backend.push_frame(img)
        frame_count += 1

        # Frame timing
        frame_elapsed = time.time() - frame_start
        sleep_time = max(0, frame_interval - frame_elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Push one final frame with eyes fully open, centered gaze.
    # Use the real EYE_SPACING from the main renderer so there's
    # zero visual discontinuity when the render loop takes over.
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)
    glow = 0.92
    for side in (-1, 1):
        ex = CX + side * _MAIN_EYE_SPACING
        _draw_open_eye(draw, ex, CY, EYE_BASE_W, EYE_BASE_H, 1.0,
                       accent, glow=glow)
    backend.push_frame(img)

    log.info("Boot animation: complete (%d frames in %.2fs)",
             frame_count, time.time() - start)
