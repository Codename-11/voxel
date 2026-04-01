"""Error toast pill — brief human-readable error message at the bottom of the face.

Shown when the voice/text pipeline errors (e.g. STT failure, gateway
unreachable, recording too short).  Auto-dismisses after a configurable
duration (default 4 seconds).  Only visible on the face view.
"""

from __future__ import annotations

import time

from PIL import ImageDraw

from display.fonts import get_font, text_width, wrap_text
from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Layout ──────────────────────────────────────────────────────────────────

TOAST_Y = SCREEN_H - 55       # above peek bubble zone
TOAST_PAD_X = 10               # inner horizontal padding
TOAST_PAD_Y = 5                # inner vertical padding
TOAST_RADIUS = 10              # pill corner radius
TOAST_FONT_SIZE = 14
TOAST_MAX_W = SCREEN_W - 24   # max pill width (12px margin each side)
TOAST_LINE_H = 18              # line height for wrapped text

# ── Colors ──────────────────────────────────────────────────────────────────

TOAST_BG = (40, 15, 15)               # dark pill with red tint
TOAST_BORDER = (120, 50, 30)          # subtle red/orange border
TOAST_TEXT = (240, 230, 230)           # near-white text

# ── Duration ────────────────────────────────────────────────────────────────

TOAST_DURATION = 4.0  # seconds


def trigger_error_toast(state: DisplayState, message: str,
                        duration: float = TOAST_DURATION) -> None:
    """Set an error toast message on the display state."""
    state.error_toast = message
    state._error_toast_until = time.time() + duration


def clear_error_toast(state: DisplayState) -> None:
    """Immediately dismiss the error toast."""
    state.error_toast = ""
    state._error_toast_until = 0.0


def draw_error_toast(draw: ImageDraw.ImageDraw, state: DisplayState,
                     now: float) -> None:
    """Draw the error toast pill at the bottom of the face view.

    Only draws when state.error_toast is non-empty and the toast has
    not yet expired.  Auto-clears the toast after expiry.
    """
    if not state.error_toast:
        return

    if now >= state._error_toast_until:
        # Expired — clear and stop drawing
        state.error_toast = ""
        state._error_toast_until = 0.0
        return

    font = get_font(TOAST_FONT_SIZE)

    # Word-wrap to fit pill
    inner_w = TOAST_MAX_W - TOAST_PAD_X * 2
    lines = wrap_text(font, state.error_toast, inner_w)
    if not lines:
        return

    # Limit to 2 lines
    if len(lines) > 2:
        lines = lines[:2]
        second = lines[1]
        while text_width(font, second + "...") > inner_w and len(second) > 1:
            second = second[:-1]
        lines[1] = second + "..."

    # Measure pill dimensions
    longest_line = max(text_width(font, line) for line in lines)
    pill_w = min(TOAST_MAX_W, longest_line + TOAST_PAD_X * 2 + 4)
    pill_h = len(lines) * TOAST_LINE_H + TOAST_PAD_Y * 2

    # Center horizontally
    pill_x = (SCREEN_W - pill_w) // 2
    pill_y = TOAST_Y - pill_h // 2  # vertically centered on TOAST_Y

    # Draw pill background + border
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=TOAST_RADIUS,
        fill=TOAST_BG,
        outline=TOAST_BORDER,
        width=1,
    )

    # Draw text lines centered in the pill
    ty = pill_y + TOAST_PAD_Y
    for line in lines:
        tw = text_width(font, line)
        tx = (SCREEN_W - tw) // 2
        draw.text((tx, ty), line, fill=TOAST_TEXT, font=font)
        ty += TOAST_LINE_H
