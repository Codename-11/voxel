"""Transcript and chat components — PinchChat-inspired bubble layout.

Adapted for the 240x280 PIL display:
  - User messages: right-aligned, accent-tinted bubble
  - Assistant messages: left-aligned, dark elevated bubble
  - Tool calls: left-aligned, muted purple with gear icon
  - Proper word wrapping within bubble bounds
  - Rounded bubble corners (drawn as rounded_rectangle)
"""

from __future__ import annotations

from PIL import ImageDraw

from display.fonts import get_font, wrap_text, text_width
from display.state import DisplayState
from display.layout import SCREEN_W, SCREEN_H, STATUS_H

# ── Sizing ────────────────────────────────────────────────────────────────

FONT_SIZE = 13       # compact for 240px width
FONT_SIZE_SM = 11    # labels/hints
LINE_HEIGHT = 18     # ~1.4x font size
PAD_X = 6            # outer horizontal padding
BUBBLE_PAD_X = 8     # inner bubble horizontal padding
BUBBLE_PAD_Y = 5     # inner bubble vertical padding
BUBBLE_GAP = 4       # vertical gap between bubbles
BUBBLE_RADIUS = 10   # corner radius for bubbles
MAX_BUBBLE_W = SCREEN_W - PAD_X * 2 - 20  # max bubble width (~208px)
MIN_BUBBLE_W = 60    # minimum bubble width

# ── Colors ────────────────────────────────────────────────────────────────

TEXT_DIM = (100, 100, 120)
TEXT_USER = (220, 220, 240)
TEXT_ASSISTANT = (200, 210, 220)
TEXT_TOOL = (160, 140, 200)
TEXT_LABEL = (80, 80, 100)

# Bubble backgrounds
BG_USER = (0, 40, 38)           # dark cyan tint (user)
BG_ASSISTANT = (28, 28, 42)     # dark elevated (assistant)
BG_TOOL = (24, 20, 36)          # dark purple tint (tool)
BORDER_USER = (0, 80, 76)       # subtle cyan border
BORDER_ASSISTANT = (44, 44, 64) # subtle gray border
BORDER_TOOL = (44, 36, 60)      # subtle purple border

BG = (12, 12, 18)
DIVIDER = (40, 40, 60)


# ── Bubble rendering ─────────────────────────────────────────────────────

def _render_bubble(draw: ImageDraw.ImageDraw, entry, font, y: int,
                   max_y: int) -> int:
    """Render a single chat bubble. Returns the Y position after the bubble."""
    is_user = entry.role == "user"
    is_tool = entry.role == "tool"

    # Choose colors
    if is_user:
        bg, border, text_color = BG_USER, BORDER_USER, TEXT_USER
    elif is_tool:
        bg, border, text_color = BG_TOOL, BORDER_TOOL, TEXT_TOOL
    else:
        bg, border, text_color = BG_ASSISTANT, BORDER_ASSISTANT, TEXT_ASSISTANT

    # Prepare text
    display_text = entry.text
    if entry.status == "partial":
        display_text += "\u258c"  # blinking cursor
    if is_tool:
        display_text = "\u2699 " + display_text  # gear prefix

    # Word wrap within bubble bounds
    inner_w = MAX_BUBBLE_W - BUBBLE_PAD_X * 2
    lines = wrap_text(font, display_text, inner_w)

    # Calculate bubble dimensions
    longest_line = max(text_width(font, line) for line in lines) if lines else 0
    bubble_w = max(MIN_BUBBLE_W, longest_line + BUBBLE_PAD_X * 2 + 4)
    bubble_w = min(bubble_w, MAX_BUBBLE_W)
    bubble_h = len(lines) * LINE_HEIGHT + BUBBLE_PAD_Y * 2

    # Check if bubble fits
    if y + bubble_h > max_y:
        return -1  # signal: doesn't fit

    # Position: user = right-aligned, assistant/tool = left-aligned
    if is_user:
        bx = SCREEN_W - PAD_X - bubble_w
    else:
        bx = PAD_X

    # Draw bubble background + border
    draw.rounded_rectangle(
        [bx, y, bx + bubble_w, y + bubble_h],
        radius=BUBBLE_RADIUS, fill=bg, outline=border, width=1,
    )

    # Draw text lines inside bubble
    ty = y + BUBBLE_PAD_Y
    for line in lines:
        tx = bx + BUBBLE_PAD_X
        draw.text((tx, ty), line, fill=text_color, font=font)
        ty += LINE_HEIGHT

    return y + bubble_h + BUBBLE_GAP


def _render_messages(draw: ImageDraw.ImageDraw, state: DisplayState,
                     top: int, bottom: int, show_label: bool = True) -> None:
    """Render chat messages as bubbles, bottom-aligned (newest at bottom)."""
    font = get_font(FONT_SIZE)
    font_sm = get_font(FONT_SIZE_SM)

    if not state.transcripts:
        draw.text((PAD_X + 4, top + 20), "No messages yet",
                  fill=TEXT_DIM, font=font)
        return

    # Measure all bubbles to find which ones fit (bottom-aligned)
    usable_h = bottom - top
    entries_with_heights: list[tuple] = []

    for entry in state.transcripts:
        display_text = entry.text
        if entry.status == "partial":
            display_text += "\u258c"
        if entry.role == "tool":
            display_text = "\u2699 " + display_text

        inner_w = MAX_BUBBLE_W - BUBBLE_PAD_X * 2
        lines = wrap_text(font, display_text, inner_w)
        h = len(lines) * LINE_HEIGHT + BUBBLE_PAD_Y * 2 + BUBBLE_GAP
        entries_with_heights.append((entry, h))

    # Take as many entries from the end as fit
    total_h = 0
    visible_start = len(entries_with_heights)
    for i in range(len(entries_with_heights) - 1, -1, -1):
        h = entries_with_heights[i][1]
        if total_h + h > usable_h:
            break
        total_h += h
        visible_start = i

    # Render visible entries top-to-bottom
    y = bottom - total_h
    for i in range(visible_start, len(entries_with_heights)):
        entry = entries_with_heights[i][0]
        result = _render_bubble(draw, entry, font, y, bottom)
        if result < 0:
            break
        y = result


# ── Transcript overlay (temporary, during conversation) ───────────────────

def draw_transcript_overlay(draw: ImageDraw.ImageDraw,
                            state: DisplayState) -> None:
    """Draw a small transcript peek at the bottom — only when visible."""
    if not state.transcript_visible:
        return

    font = get_font(FONT_SIZE_SM)

    # Show last 2 entries at most
    entries = state.transcripts[-2:] if state.transcripts else []
    if not entries:
        return

    # Measure height needed
    total_lines = 0
    for entry in entries:
        text = entry.text
        if entry.role == "tool":
            text = "\u2699 " + text
        lines = wrap_text(font, text, SCREEN_W - 20)
        total_lines += len(lines)

    padding = 6
    area_h = total_lines * (LINE_HEIGHT - 2) + padding * 2 + (len(entries) - 1) * 4
    area_h = min(area_h, 100)  # cap height
    area_top = SCREEN_H - area_h

    draw.rectangle([0, area_top, SCREEN_W - 1, SCREEN_H - 1], fill=BG)
    draw.line([(0, area_top), (SCREEN_W - 1, area_top)], fill=DIVIDER, width=1)

    y = area_top + padding
    for entry in entries:
        is_user = entry.role == "user"
        text = entry.text
        if entry.role == "tool":
            text = "\u2699 " + text

        color = TEXT_USER if is_user else TEXT_ASSISTANT
        if entry.role == "tool":
            color = TEXT_TOOL

        # Role label
        label = "You" if is_user else ("" if entry.role == "tool" else state.agent.capitalize())
        if label:
            draw.text((PAD_X, y), label, fill=TEXT_LABEL, font=get_font(9))
            y += 12

        lines = wrap_text(font, text, SCREEN_W - 20)
        for line in lines:
            if y > SCREEN_H - 4:
                break
            tx = SCREEN_W - PAD_X - text_width(font, line) if is_user else PAD_X
            draw.text((tx, y), line, fill=color, font=font)
            y += LINE_HEIGHT - 2
        y += 2


# ── Chat drawer (peek from bottom, ~45% of screen) ───────────────────────

DRAWER_REST = 140
DRAWER_HIDDEN = 280


def draw_chat_drawer(draw: ImageDraw.ImageDraw, state: DisplayState,
                     slide_y: int = DRAWER_REST) -> None:
    """Draw a chat drawer that peeks up from the bottom with bubble layout."""
    top = slide_y
    if top >= 280:
        return

    draw.rectangle([0, top, SCREEN_W - 1, 279], fill=BG)
    draw.line([(0, top), (SCREEN_W - 1, top)], fill=DIVIDER, width=1)

    # Handle grip
    draw.rounded_rectangle([105, top + 4, 135, top + 7], radius=2, fill=DIVIDER)

    _render_messages(draw, state, top + 12, 275)


# ── Full chat view (replaces face entirely) ───────────────────────────────

CHAT_TOP = STATUS_H + 2


def draw_chat_full(draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
    """Draw full-screen chat history with bubble layout."""
    draw.rectangle([0, CHAT_TOP, SCREEN_W - 1, 279], fill=BG)
    _render_messages(draw, state, CHAT_TOP + 4, 272)


# ── Chat notification peek (slides up briefly on new message) ─────────────

PEEK_H = 40
PEEK_DURATION = 3.5  # seconds visible
PEEK_BOTTOM = SCREEN_H - 28  # stay above bottom corner bevel (40px radius)


def draw_chat_peek(draw: ImageDraw.ImageDraw, state: DisplayState,
                   now: float) -> None:
    """Draw a notification bar of the latest message at the bottom."""
    if now >= state._peek_until:
        return

    remaining = state._peek_until - now
    elapsed = PEEK_DURATION - remaining

    # Fade in/out
    if remaining < 0.4:
        alpha = remaining / 0.4
    else:
        alpha = min(elapsed / 0.12, 1.0)

    if alpha <= 0:
        return

    if not state.transcripts:
        return

    entry = state.transcripts[-1]
    font = get_font(FONT_SIZE)
    label_font = get_font(9)
    is_user = entry.role == "user"

    if entry.role == "tool":
        label = "Tool"
        text_color = TEXT_TOOL
        accent = (80, 60, 140)
    elif is_user:
        label = "You"
        text_color = TEXT_USER
        accent = (0, 160, 155)
    else:
        label = state.agent.capitalize()
        text_color = TEXT_ASSISTANT
        accent = (0, 212, 210)

    text = entry.text
    if entry.status == "partial":
        text += "\u258c"

    # Truncate to fit one line (leave room for accent stripe + padding)
    max_w = SCREEN_W - 24
    if text_width(font, text) > max_w:
        while text_width(font, text + "..") > max_w and len(text) > 1:
            text = text[:-1]
        text += ".."

    slide_y = int(PEEK_BOTTOM - PEEK_H * alpha)
    if slide_y >= PEEK_BOTTOM - 2:
        return  # not enough room to draw

    def _a(c: tuple) -> tuple:
        return tuple(int(v * alpha) for v in c)

    bg = BG_USER if is_user else BG_ASSISTANT
    # Background extends to screen bottom (fills below text safe area)
    draw.rectangle([0, slide_y, SCREEN_W - 1, SCREEN_H - 1], fill=_a(bg))
    draw.line([(0, slide_y), (SCREEN_W - 1, slide_y)], fill=_a(DIVIDER))
    # Accent stripe on left edge
    draw.rectangle([0, slide_y + 1, 2, SCREEN_H - 1], fill=_a(accent))
    # Label
    draw.text((8, slide_y + 5), label, fill=_a(TEXT_LABEL), font=label_font)
    # Message text
    draw.text((8, slide_y + 18), text, fill=_a(text_color), font=font)


# ── View position indicator dots ──────────────────────────────────────────

VIEW_ORDER = ["face", "chat_drawer", "chat_full"]
DOT_Y = SCREEN_H - 8
DOT_SPACING = 12
DOT_R = 2


def draw_view_dots(draw: ImageDraw.ImageDraw, current_view: str) -> None:
    """Draw three dots indicating current view position."""
    n = len(VIEW_ORDER)
    total_w = (n - 1) * DOT_SPACING
    start_x = (SCREEN_W - total_w) // 2

    for i, view in enumerate(VIEW_ORDER):
        x = start_x + i * DOT_SPACING
        active = view == current_view
        color = (0, 150, 148) if active else (40, 40, 60)
        r = DOT_R + 1 if active else DOT_R
        draw.ellipse([x - r, DOT_Y - r, x + r, DOT_Y + r], fill=color)
