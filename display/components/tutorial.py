"""Gesture tutorial overlay — three-phase animated guide for single-button UX.

Phase 1 (0-4s):  "Hold to talk"      — animated button circle with growing ring arc
Phase 2 (4-8s):  "Tap to switch"     — button with tap bounce animation
Phase 3 (8-12s): "Hold for settings" — ring growing to menu threshold
Auto-dismiss at 13s, any button press dismisses immediately.

Dark semi-transparent background, accent color highlights.
"""

from __future__ import annotations

import math

from PIL import ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Colors ──────────────────────────────────────────────────────────────────

BG_OVERLAY = (10, 10, 15)
ACCENT = (0, 212, 210)
ACCENT_DIM = (0, 80, 78)
ACCENT_BRIGHT = (64, 255, 248)
TEXT_DIM = (70, 70, 90)
WHITE = (200, 200, 220)

# ── Timing ──────────────────────────────────────────────────────────────────

PHASE_1_START = 0.0
PHASE_1_END = 4.0
PHASE_2_START = 4.0
PHASE_2_END = 8.0
PHASE_3_START = 8.0
PHASE_3_END = 12.0
TOTAL_DURATION = 13.0

# ── Layout ──────────────────────────────────────────────────────────────────

CX = SCREEN_W // 2
CY = 140             # center of the animated circle
CIRCLE_R = 24        # button circle radius
RING_R = 32          # ring radius (around button circle)
RING_THICKNESS = 4
LABEL_Y = CY + 50    # text label below the circle
SKIP_Y = SCREEN_H - 30


def _progress(now: float, start: float, end: float) -> float:
    """Return 0..1 progress through a time range (clamped)."""
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    return (now - start) / (end - start)


def _ease_out(t: float) -> float:
    """Ease-out — fast start, slow end."""
    return 1.0 - (1.0 - t) ** 2


def _ease_in_out(t: float) -> float:
    """Smooth-step easing."""
    return t * t * (3.0 - 2.0 * t)


def _scale_color(color: tuple, alpha: float) -> tuple:
    """Scale an RGB color's brightness by an alpha factor."""
    alpha = max(0.0, min(1.0, alpha))
    return (int(color[0] * alpha), int(color[1] * alpha), int(color[2] * alpha))


def _blend_color(fg: tuple, bg: tuple, alpha: float) -> tuple:
    """Blend foreground onto background using alpha (0=bg, 1=fg)."""
    alpha = max(0.0, min(1.0, alpha))
    return (
        int(fg[0] * alpha + bg[0] * (1 - alpha)),
        int(fg[1] * alpha + bg[1] * (1 - alpha)),
        int(fg[2] * alpha + bg[2] * (1 - alpha)),
    )


def update_tutorial(state: DisplayState, now: float) -> None:
    """Advance tutorial phase based on elapsed time."""
    if not state.tutorial_active:
        return

    elapsed = now - state._tutorial_start

    if elapsed >= TOTAL_DURATION:
        # Auto-dismiss
        state.tutorial_active = False
        state.tutorial_phase = 0
        return

    # Determine current phase
    if elapsed < PHASE_1_END:
        state.tutorial_phase = 1
    elif elapsed < PHASE_2_END:
        state.tutorial_phase = 2
    elif elapsed < PHASE_3_END:
        state.tutorial_phase = 3
    else:
        state.tutorial_phase = 3  # hold last phase until dismiss


def draw_tutorial(draw: ImageDraw.ImageDraw, state: DisplayState, now: float) -> None:
    """Render the current tutorial phase."""
    if not state.tutorial_active or state.tutorial_phase == 0:
        return

    elapsed = now - state._tutorial_start

    # Dark full-screen background
    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=BG_OVERLAY)

    # Phase title at top
    font_title = get_font(14)
    title = "Button Guide"
    tw = text_width(font_title, title)
    draw.text(((SCREEN_W - tw) // 2, 30), title, fill=ACCENT_DIM, font=font_title)

    # Draw current phase
    phase = state.tutorial_phase
    if phase == 1:
        _draw_phase_hold_to_talk(draw, elapsed, now)
    elif phase == 2:
        _draw_phase_tap_to_switch(draw, elapsed, now)
    elif phase == 3:
        _draw_phase_hold_for_menu(draw, elapsed, now)

    # Phase dots (bottom area, above skip text)
    dot_y = SKIP_Y - 20
    dot_spacing = 12
    dot_start_x = CX - dot_spacing
    for i in range(3):
        dx = dot_start_x + i * dot_spacing
        r = 3
        if i + 1 == phase:
            draw.ellipse([dx - r, dot_y - r, dx + r, dot_y + r], fill=ACCENT)
        else:
            draw.ellipse([dx - r, dot_y - r, dx + r, dot_y + r], fill=ACCENT_DIM)

    # "press to skip" hint
    font_skip = get_font(13)
    skip = "press to skip"
    sw = text_width(font_skip, skip)
    # Gentle blink
    blink = 0.3 + 0.2 * math.sin(now * 2.5)
    skip_color = _scale_color(TEXT_DIM, blink + 0.5)
    draw.text(((SCREEN_W - sw) // 2, SKIP_Y), skip, fill=skip_color, font=font_skip)


def _draw_phase_hold_to_talk(draw: ImageDraw.ImageDraw, elapsed: float,
                             now: float) -> None:
    """Phase 1: Hold to talk — button circle with growing ring arc."""
    p = _progress(elapsed, PHASE_1_START, PHASE_1_END)

    # Button circle (filled, pulsing)
    pulse = 0.6 + 0.4 * math.sin(now * 4.0)
    circle_color = _scale_color(ACCENT_DIM, pulse)
    draw.ellipse(
        [CX - CIRCLE_R, CY - CIRCLE_R, CX + CIRCLE_R, CY + CIRCLE_R],
        fill=circle_color,
    )

    # Growing arc around the circle (simulates holding the button)
    arc_progress = _ease_in_out(p)
    if arc_progress > 0.01:
        ring_bbox = [CX - RING_R, CY - RING_R, CX + RING_R, CY + RING_R]
        start_angle = -90
        end_angle = start_angle + int(360 * arc_progress * 0.3)  # ~30% of ring for talk zone
        ring_color = _scale_color(ACCENT, min(arc_progress * 2, 1.0))
        draw.arc(ring_bbox, start_angle, end_angle, fill=ring_color, width=RING_THICKNESS)

    # Pulsing center dot (recording indicator)
    if p > 0.3:
        dot_pulse = math.sin(now * 6.0) * 0.3 + 0.7
        dot_color = _scale_color(ACCENT_BRIGHT, dot_pulse * min((p - 0.3) / 0.2, 1.0))
        draw.ellipse([CX - 4, CY - 4, CX + 4, CY + 4], fill=dot_color)

    # Label
    font = get_font(20)
    label = "Hold to talk"
    lw = text_width(font, label)
    # Fade in over first 0.5s
    label_alpha = min(p / 0.2, 1.0)
    label_color = _blend_color(WHITE, BG_OVERLAY, label_alpha)
    draw.text(((SCREEN_W - lw) // 2, LABEL_Y), label, fill=label_color, font=font)

    # Sub-label
    font_sm = get_font(14)
    sub = "from face view"
    sw = text_width(font_sm, sub)
    sub_color = _blend_color(ACCENT_DIM, BG_OVERLAY, label_alpha * 0.7)
    draw.text(((SCREEN_W - sw) // 2, LABEL_Y + 24), sub, fill=sub_color, font=font_sm)


def _draw_phase_tap_to_switch(draw: ImageDraw.ImageDraw, elapsed: float,
                              now: float) -> None:
    """Phase 2: Tap to switch views — button with tap bounce."""
    p = _progress(elapsed, PHASE_2_START, PHASE_2_END)

    # Repeating tap bounce animation (every 1.2s)
    tap_cycle = (elapsed - PHASE_2_START) % 1.2
    if tap_cycle < 0.15:
        # Press down
        bounce = _ease_out(tap_cycle / 0.15) * 3
    elif tap_cycle < 0.3:
        # Release bounce up
        t = (tap_cycle - 0.15) / 0.15
        bounce = 3 * (1.0 - _ease_out(t))
    else:
        bounce = 0.0

    # Button circle (with bounce offset)
    cy_offset = CY + int(bounce)
    circle_color = ACCENT_DIM if tap_cycle >= 0.15 else ACCENT
    draw.ellipse(
        [CX - CIRCLE_R, cy_offset - CIRCLE_R, CX + CIRCLE_R, cy_offset + CIRCLE_R],
        fill=circle_color,
    )

    # Expanding ring on "tap" (ripple effect)
    if tap_cycle < 0.4:
        ripple_t = tap_cycle / 0.4
        ripple_r = CIRCLE_R + int(16 * _ease_out(ripple_t))
        ripple_alpha = 1.0 - ripple_t
        ripple_color = _scale_color(ACCENT, ripple_alpha * 0.5)
        draw.ellipse(
            [CX - ripple_r, CY - ripple_r, CX + ripple_r, CY + ripple_r],
            outline=ripple_color, width=2,
        )

    # Label
    font = get_font(20)
    label = "Tap to switch"
    lw = text_width(font, label)
    label_alpha = min(p / 0.2, 1.0)
    label_color = _blend_color(WHITE, BG_OVERLAY, label_alpha)
    draw.text(((SCREEN_W - lw) // 2, LABEL_Y), label, fill=label_color, font=font)

    # Sub-label
    font_sm = get_font(14)
    sub = "face / chat views"
    sw = text_width(font_sm, sub)
    sub_color = _blend_color(ACCENT_DIM, BG_OVERLAY, label_alpha * 0.7)
    draw.text(((SCREEN_W - sw) // 2, LABEL_Y + 24), sub, fill=sub_color, font=font_sm)


def _draw_phase_hold_for_menu(draw: ImageDraw.ImageDraw, elapsed: float,
                              now: float) -> None:
    """Phase 3: Hold for settings — ring growing to menu threshold."""
    p = _progress(elapsed, PHASE_3_START, PHASE_3_END)

    # Button circle (pressed state)
    pulse = 0.5 + 0.3 * math.sin(now * 3.0)
    circle_color = _scale_color(ACCENT_DIM, pulse)
    draw.ellipse(
        [CX - CIRCLE_R, CY - CIRCLE_R, CX + CIRCLE_R, CY + CIRCLE_R],
        fill=circle_color,
    )

    # Ring filling to "menu" threshold — slower arc growth
    arc_progress = _ease_in_out(p)
    ring_bbox = [CX - RING_R, CY - RING_R, CX + RING_R, CY + RING_R]

    # Background ring track
    draw.arc(ring_bbox, 0, 360, fill=(30, 30, 50), width=RING_THICKNESS)

    # Progress arc (fills from top)
    start_angle = -90
    # Fill up to the "menu" position (~36 degrees for 1s/10s)
    end_angle = start_angle + int(360 * arc_progress * 0.1)
    ring_color = _scale_color(ACCENT_BRIGHT, min(arc_progress * 1.5, 1.0))
    draw.arc(ring_bbox, start_angle, end_angle, fill=ring_color, width=RING_THICKNESS)

    # Tick mark at menu threshold
    if arc_progress > 0.5:
        tick_angle = math.radians(-90 + 360 * 0.1)
        tick_x = CX + int((RING_R + 5) * math.cos(tick_angle))
        tick_y = CY + int((RING_R + 5) * math.sin(tick_angle))
        draw.ellipse([tick_x - 2, tick_y - 2, tick_x + 2, tick_y + 2], fill=ACCENT_BRIGHT)

    # Label
    font = get_font(20)
    label = "Hold for settings"
    lw = text_width(font, label)
    label_alpha = min(p / 0.2, 1.0)
    label_color = _blend_color(WHITE, BG_OVERLAY, label_alpha)
    draw.text(((SCREEN_W - lw) // 2, LABEL_Y), label, fill=label_color, font=font)

    # Sub-label
    font_sm = get_font(14)
    sub = "from chat view"
    sw = text_width(font_sm, sub)
    sub_color = _blend_color(ACCENT_DIM, BG_OVERLAY, label_alpha * 0.7)
    draw.text(((SCREEN_W - sw) // 2, LABEL_Y + 24), sub, fill=sub_color, font=font_sm)
