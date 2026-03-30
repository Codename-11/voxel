"""Button hold indicator — visual feedback for single-button interaction.

Shows a progress arc/ring while the button is held, with THREE zones:
  Zone 1 (0-1s):  Cyan ring filling    → "menu" label
  Zone 2 (1-5s):  Blue/indigo continues → "sleep" label
  Zone 3 (5-10s): Orange/red continues  → "shutdown" label

The ring does NOT appear until the button has been held past the short-press
threshold (400ms / 0.04 normalised).  It then fades in over ~200ms worth of
progress.  Quick taps only show the flash pill on release.

Brief flash pill on release with action-specific labels:
  short_press → "Tap"      (cyan)
  double_tap  → "Talk"     (bright green)
  long_press  → "Menu"     (bright cyan)
  sleep       → "Sleep"    (blue/indigo)
  shutdown    → "Shutdown"  (red)

Flash pills slide in from below and fade out smoothly (0.5s total).
"""

from __future__ import annotations

import math

from PIL import ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Colors ──────────────────────────────────────────────────────────────────

CYAN = (0, 212, 210)
CYAN_BRIGHT = (64, 255, 248)
CYAN_DIM = (0, 80, 78)
BLUE = (80, 80, 255)
BLUE_DIM = (30, 30, 120)
INDIGO = (100, 60, 220)
ORANGE = (255, 170, 40)
ORANGE_DIM = (120, 70, 10)
RED = (255, 60, 40)
RED_DIM = (140, 30, 15)
GREEN_BRIGHT = (40, 255, 120)
BG_PILL = (20, 20, 32)
WHITE = (220, 220, 240)
FLASH_BG = (24, 28, 32)

# ── Layout ──────────────────────────────────────────────────────────────────

# Progress arc drawn as a ring at bottom-center
ARC_CX = SCREEN_W // 2
ARC_CY = SCREEN_H - 40
ARC_R = 16
ARC_THICKNESS = 4

# Flash label final resting Y position
FLASH_Y = SCREEN_H - 64

# ── Thresholds (must match display/service.py) ────────────────────────────

SHORT_THRESHOLD = 0.4         # seconds — must match display/service.py
FULL_SCALE = 10.0             # seconds — ring represents 0-10s
RING_VISIBLE_FRAC = SHORT_THRESHOLD / FULL_SCALE  # 0.04 normalised
RING_FADEIN_RANGE = 0.02      # fade ring brightness over this much progress after threshold

LONG_PRESS_THRESHOLD = 1.0    # menu open from face
MENU_LONG_PRESS = 0.9         # menu select (wider window for reliable medium press)
SLEEP_THRESHOLD = 5.0
SHUTDOWN_THRESHOLD = 10.0

# Flash animation phases (total 0.5s)
FLASH_TOTAL = 0.5
FLASH_SLIDE_END = 0.12        # slide-up phase ends
FLASH_HOLD_END = 0.35         # hold phase ends, fade-out begins
# fade-out runs from FLASH_HOLD_END to FLASH_TOTAL

# Zone fractions matching actual release thresholds (ring = 0-10s):
#   Zone 1: 0-5s  → release = Menu (long_press at 1s+)     — cyan
#   Zone 2: 5-10s → release = Sleep (5s+) / Shutdown (10s)  — orange/red
# Tick mark at 1s shows when menu "arms"
ZONE_MENU_ARM = 1.0 / 10.0    # 0.1 — menu arms at 1s (tick mark)
ZONE_SLEEP = 5.0 / 10.0       # 0.5 — sleep threshold
# Shutdown at 1.0 (10s)


def draw_button_indicator(draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
    """Draw button hold progress and release flash."""
    now = state.time

    # ── Flash label (brief pill after release) ──
    if state.button_flash and now < state._button_flash_until:
        _draw_flash(draw, state.button_flash, now, state._button_flash_until)
    elif state.button_flash:
        state.button_flash = ""

    # ── Hold progress (while button is pressed) ──
    if not state.button_pressed:
        return

    progress = min(state.button_hold, 1.0)  # 0..1 over 10s

    # Before the ring appears (first 0.4s), show a pulsing dot so the user
    # gets immediate visual feedback that the press registered.
    if progress < RING_VISIBLE_FRAC:
        # Breathe pulse: radius oscillates 2-4px using a sine wave
        pulse = math.sin(now * 8.0) * 0.5 + 0.5  # 0..1, ~4 Hz
        dot_r = int(2 + 2 * pulse)
        draw.ellipse(
            [ARC_CX - dot_r, ARC_CY - dot_r, ARC_CX + dot_r, ARC_CY + dot_r],
            fill=CYAN_DIM,
        )
        return

    # Ring fade-in: ramp brightness from 0→1 over RING_FADEIN_RANGE of progress
    # after crossing the visibility threshold.
    fade_progress = progress - RING_VISIBLE_FRAC
    ring_alpha = min(fade_progress / RING_FADEIN_RANGE, 1.0) if RING_FADEIN_RANGE > 0 else 1.0

    # ── Background ring with threshold tick marks ──
    bg_color = _scale_color((30, 30, 50), ring_alpha)
    _draw_ring(draw, ARC_CX, ARC_CY, ARC_R, ARC_THICKNESS, bg_color)

    # Tick at 1s (menu arms) and 5s (sleep threshold)
    _draw_zone_tick(draw, ZONE_MENU_ARM, ring_alpha)
    _draw_zone_tick(draw, ZONE_SLEEP, ring_alpha)

    # ── Progress arc — two zones matching release behavior ──
    start_angle = -90  # 12 o'clock
    bbox = [ARC_CX - ARC_R, ARC_CY - ARC_R, ARC_CX + ARC_R, ARC_CY + ARC_R]

    if progress <= ZONE_SLEEP:
        # Zone 1: 0-5s — cyan (release = Menu once past 1s)
        end_angle = start_angle + int(360 * progress)
        t = min(progress / ZONE_SLEEP, 1.0)
        ring_color = _scale_color(_lerp_color(CYAN_DIM, CYAN, t), ring_alpha)
        draw.arc(bbox, start_angle, end_angle, fill=ring_color, width=ARC_THICKNESS)

        # Brighter pulse once menu is armed (past 1s)
        if progress >= ZONE_MENU_ARM:
            dot_color = _scale_color(CYAN, ring_alpha)
            draw.ellipse(
                [ARC_CX - 3, ARC_CY - 3, ARC_CX + 3, ARC_CY + 3],
                fill=dot_color,
            )
    else:
        # Zone 1 full (cyan) + Zone 2 partial (orange→red)
        sleep_end = start_angle + int(360 * ZONE_SLEEP)
        draw.arc(bbox, start_angle, sleep_end,
                 fill=_scale_color(CYAN, ring_alpha), width=ARC_THICKNESS)

        zone2_progress = (progress - ZONE_SLEEP) / (1.0 - ZONE_SLEEP)
        t2 = min(zone2_progress, 1.0)
        zone2_color = _scale_color(_lerp_color(ORANGE_DIM, RED, t2), ring_alpha)
        end_angle = sleep_end + int(360 * (1.0 - ZONE_SLEEP) * zone2_progress)
        draw.arc(bbox, sleep_end, end_angle, fill=zone2_color, width=ARC_THICKNESS)

        # Center dot — orange/red
        dot_color = _scale_color(_lerp_color(ORANGE, RED, t2), ring_alpha)
        draw.ellipse(
            [ARC_CX - 4, ARC_CY - 4, ARC_CX + 4, ARC_CY + 4],
            fill=dot_color,
        )

    # ── Label below the ring — shows what release does NOW ──
    font = get_font(13)
    if progress >= ZONE_SLEEP:
        # Past 5s: release = sleep (approaching shutdown at 10s)
        t2 = min((progress - ZONE_SLEEP) / (1.0 - ZONE_SLEEP), 1.0)
        if t2 > 0.8:
            label = "Shutdown"
            color = RED
        else:
            label = "Sleep"
            color = _lerp_color(ORANGE, RED, t2)
    elif progress >= ZONE_MENU_ARM:
        # Past 1s: release = menu (armed)
        label = "Menu"
        color = CYAN
    else:
        # 0.4-1s: approaching menu threshold
        label = "Menu"
        t1 = progress / ZONE_MENU_ARM
        color = _lerp_color(CYAN_DIM, CYAN, t1)

    color = _scale_color(color, ring_alpha)
    tw = text_width(font, label)
    draw.text((ARC_CX - tw // 2, ARC_CY + ARC_R + 5), label, fill=color, font=font)


def _draw_zone_tick(draw: ImageDraw.ImageDraw, frac: float, alpha: float = 1.0) -> None:
    """Draw a subtle tick mark at a zone boundary on the ring."""
    angle_rad = math.radians(-90 + 360 * frac)
    tick_x = ARC_CX + int((ARC_R + 3) * math.cos(angle_rad))
    tick_y = ARC_CY + int((ARC_R + 3) * math.sin(angle_rad))
    color = _scale_color((60, 60, 80), alpha)
    draw.ellipse([tick_x - 1, tick_y - 1, tick_x + 1, tick_y + 1], fill=color)


def _ease_out(t: float) -> float:
    """Ease-out (fast start, slow end)."""
    return 1.0 - (1.0 - t) ** 2


def _scale_color(color: tuple, alpha: float) -> tuple:
    """Scale an RGB color's brightness by an alpha factor (0..1)."""
    alpha = max(0.0, min(1.0, alpha))
    return (int(color[0] * alpha), int(color[1] * alpha), int(color[2] * alpha))


def _lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    """Linearly interpolate between two RGB colors."""
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _draw_ring(draw: ImageDraw.ImageDraw, cx: int, cy: int,
               r: int, width: int, color: tuple) -> None:
    """Draw a full circle ring (background track)."""
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.arc(bbox, 0, 360, fill=color, width=width)


def _draw_flash(draw: ImageDraw.ImageDraw, flash_type: str, now: float,
                until: float) -> None:
    """Draw a brief label pill after button release.

    Animation phases (0.5s total):
      0.00 - 0.12s  slide up from off-screen (ease-out)
      0.12 - 0.35s  hold at final position
      0.35 - 0.50s  fade out
    """
    font = get_font(13)
    elapsed = now - (until - FLASH_TOTAL)  # time since flash started

    # Compute visibility (fade) and vertical offset (slide)
    if elapsed < FLASH_SLIDE_END:
        # Phase 1: slide up
        t = elapsed / FLASH_SLIDE_END if FLASH_SLIDE_END > 0 else 1.0
        slide = 1.0 - _ease_out(min(t, 1.0))  # 1 = off-screen, 0 = final pos
        fade = 1.0
    elif elapsed < FLASH_HOLD_END:
        # Phase 2: hold visible
        slide = 0.0
        fade = 1.0
    else:
        # Phase 3: fade out
        slide = 0.0
        t = (elapsed - FLASH_HOLD_END) / (FLASH_TOTAL - FLASH_HOLD_END)
        fade = max(1.0 - min(t, 1.0), 0.0)

    if fade <= 0:
        return

    # Action-specific labels and colors
    if flash_type == "short_press":
        label = "Tap"
        color = CYAN
    elif flash_type == "double_tap":
        label = "Talk"
        color = GREEN_BRIGHT
    elif flash_type == "medium_press":
        label = "Prev"
        color = CYAN
    elif flash_type == "long_press":
        label = "Menu"
        color = CYAN_BRIGHT
    elif flash_type == "sleep":
        label = "Sleep"
        color = INDIGO
    elif flash_type == "shutdown":
        label = "Shutdown"
        color = RED
    else:
        # Legacy fallback
        label = flash_type.replace("_", " ").title()
        color = CYAN

    # Dim color by fade
    color = _scale_color(color, fade)

    tw = text_width(font, label)

    # Vertical position: slide from SCREEN_H (off-screen) up to FLASH_Y
    slide_distance = SCREEN_H - FLASH_Y  # pixels to travel
    py = int(FLASH_Y + slide_distance * slide)

    # Pill background
    pill_w = tw + 24
    pill_x = (SCREEN_W - pill_w) // 2
    bg_color = _scale_color(FLASH_BG, fade)
    draw.rounded_rectangle(
        [pill_x, py - 2, pill_x + pill_w, py + 20],
        radius=10, fill=bg_color,
    )
    draw.text(((SCREEN_W - tw) // 2, py), label, fill=color, font=font)
