"""Shutdown confirmation overlay — full-screen warning with countdown.

Drawn on top of everything when state.shutdown_confirm is True.
Shows a pulsing "SHUTTING DOWN" title, large countdown numbers (3..2..1),
and a "Press to cancel" hint. After countdown reaches 0, the display
service executes the actual shutdown.
"""

from __future__ import annotations

import math

from PIL import ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Colors ──────────────────────────────────────────────────────────────────

BG_OVERLAY = (10, 5, 5, 200)  # dark red-tinted overlay (used if RGBA)
BG_SOLID = (15, 5, 5)         # fallback for RGB mode
RED = (255, 50, 40)
RED_DIM = (140, 25, 20)
RED_BRIGHT = (255, 80, 60)
WHITE_DIM = (140, 140, 150)
CANCEL_COLOR = (80, 80, 100)

# ── Constants ───────────────────────────────────────────────────────────────

COUNTDOWN_DURATION = 3.0  # seconds — matches display_service._on_button


def draw_shutdown_overlay(draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
    """Draw the shutdown confirmation overlay with countdown."""
    if not state.shutdown_confirm or state._shutdown_at <= 0:
        return

    now = state.time
    remaining = max(state._shutdown_at - now, 0.0)
    countdown_int = int(math.ceil(remaining))  # 3, 2, 1, 0

    # ── Dark overlay background ──
    draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=BG_SOLID)

    # ── Pulsing "SHUTTING DOWN" title ──
    pulse = 0.5 + 0.5 * math.sin(now * 6.0)  # ~1Hz pulse
    title_font = get_font(16)
    title = "SHUTTING DOWN"
    title_color = (
        int(RED_DIM[0] + (RED_BRIGHT[0] - RED_DIM[0]) * pulse),
        int(RED_DIM[1] + (RED_BRIGHT[1] - RED_DIM[1]) * pulse),
        int(RED_DIM[2] + (RED_BRIGHT[2] - RED_DIM[2]) * pulse),
    )
    tw = text_width(title_font, title)
    draw.text(((SCREEN_W - tw) // 2, 80), title, fill=title_color, font=title_font)

    # ── Large countdown number ──
    if countdown_int > 0:
        count_font = get_font(48)
        count_text = str(countdown_int)
        cw = text_width(count_font, count_text)
        # Fade intensity based on fractional part (bright at start of each second)
        frac = remaining - int(remaining) if remaining > 0 else 0
        intensity = 0.4 + 0.6 * frac
        count_color = (
            int(RED[0] * intensity),
            int(RED[1] * intensity),
            int(RED[2] * intensity),
        )
        draw.text(((SCREEN_W - cw) // 2, 120), count_text, fill=count_color, font=count_font)
    else:
        # Countdown finished — show solid block
        done_font = get_font(20)
        done_text = "..."
        dw = text_width(done_font, done_text)
        draw.text(((SCREEN_W - dw) // 2, 135), done_text, fill=RED, font=done_font)

    # ── Countdown dots: "3... 2... 1..." ──
    dots_font = get_font(13)
    if countdown_int > 0:
        dots = "  ".join(
            str(i) + ("..." if i == countdown_int else "")
            for i in range(3, 0, -1)
        )
    else:
        dots = "0"
    dw = text_width(dots_font, dots)
    draw.text(((SCREEN_W - dw) // 2, 185), dots, fill=WHITE_DIM, font=dots_font)

    # ── "Press to cancel" hint ──
    hint_font = get_font(11)
    hint = "press to cancel"
    hw = text_width(hint_font, hint)
    # Gentle blink
    blink = 0.4 + 0.3 * math.sin(now * 3.0)
    hint_color = (
        int(CANCEL_COLOR[0] * blink),
        int(CANCEL_COLOR[1] * blink),
        int(CANCEL_COLOR[2] * blink),
    )
    draw.text(((SCREEN_W - hw) // 2, 220), hint, fill=hint_color, font=hint_font)
