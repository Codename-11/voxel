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

FONT_SIZE = 18       # compact for 240px width
FONT_SIZE_SM = 14    # labels/hints
LINE_HEIGHT = 24     # ~1.4x font size
PAD_X = 6            # outer horizontal padding
BUBBLE_PAD_X = 8     # inner bubble horizontal padding
BUBBLE_PAD_Y = 7     # inner bubble vertical padding
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
            draw.text((PAD_X, y), label, fill=TEXT_LABEL, font=get_font(12))
            y += 12

        lines = wrap_text(font, text, SCREEN_W - 20)
        for line in lines:
            if y > SCREEN_H - 4:
                break
            tx = SCREEN_W - PAD_X - text_width(font, line) if is_user else PAD_X
            draw.text((tx, y), line, fill=color, font=font)
            y += LINE_HEIGHT - 2
        y += 2


# ── Full chat view (replaces face entirely) ───────────────────────────────

CHAT_TOP = STATUS_H + 2


def draw_chat(draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
    """Draw full-screen chat history with bubble layout."""
    draw.rectangle([0, CHAT_TOP, SCREEN_W - 1, 279], fill=BG)
    _render_messages(draw, state, CHAT_TOP + 4, 272)


# ── Peek bubble overlay on face view ──────────────────────────────────────

PEEK_DURATION = 4.0    # seconds visible
PEEK_SLIDE_IN = 0.3    # seconds to slide up
PEEK_FADE_OUT = 0.5    # seconds to fade out before dismissing
PEEK_PAD_X = 12        # horizontal padding from screen edge
PEEK_PAD_Y = 8         # inner vertical padding
PEEK_RADIUS = 12       # bubble corner radius
PEEK_BOTTOM = SCREEN_H - 10  # bottom edge of peek area (above corner bevel)
PEEK_FONT_SIZE = 16    # readable but not dominant


def draw_peek_bubble(draw: ImageDraw.ImageDraw, img, state: DisplayState,
                     now: float) -> None:
    """Draw a semi-transparent peek bubble at the bottom of the face view.

    Shows 1-2 lines of the latest transcript entry, with a slide-up
    entrance and fade-out dismissal. Drawn on top of everything.
    """
    if now >= state._peek_until:
        return

    remaining = state._peek_until - now
    elapsed = PEEK_DURATION - remaining

    # Slide-up entrance (0 -> 1 over PEEK_SLIDE_IN)
    # Fade-out exit (1 -> 0 over PEEK_FADE_OUT at the end)
    if elapsed < PEEK_SLIDE_IN:
        progress = elapsed / PEEK_SLIDE_IN
        alpha = progress  # fades in as it slides up
    elif remaining < PEEK_FADE_OUT:
        progress = 1.0
        alpha = remaining / PEEK_FADE_OUT
    else:
        progress = 1.0
        alpha = 1.0

    if alpha <= 0.01:
        return

    if not state.transcripts:
        return

    entry = state.transcripts[-1]
    font = get_font(PEEK_FONT_SIZE)
    is_user = entry.role == "user"

    text = entry.text
    if entry.status == "partial":
        text += "\u258c"

    # Word-wrap to fit bubble (max 2 lines)
    inner_w = SCREEN_W - PEEK_PAD_X * 2 - 16
    lines = wrap_text(font, text, inner_w)
    if len(lines) > 2:
        # Truncate to 2 lines, add ellipsis to second line
        lines = lines[:2]
        second = lines[1]
        while text_width(font, second + "...") > inner_w and len(second) > 1:
            second = second[:-1]
        lines[1] = second + "..."

    if not lines:
        return

    # Measure bubble size
    line_h = PEEK_FONT_SIZE + 6
    bubble_h = len(lines) * line_h + PEEK_PAD_Y * 2
    bubble_w = SCREEN_W - PEEK_PAD_X * 2

    # Slide-up animation: bubble rises from below screen to its rest position
    rest_top = PEEK_BOTTOM - bubble_h
    start_top = SCREEN_H + 4  # start just off-screen
    # Ease-out for slide
    ease = 1.0 - (1.0 - progress) ** 2
    bubble_top = int(start_top + (rest_top - start_top) * ease)
    bubble_left = PEEK_PAD_X

    if bubble_top >= SCREEN_H:
        return

    # Draw using RGBA overlay for semi-transparency
    from PIL import Image as _PILImage
    overlay = _PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    from PIL import ImageDraw as _PILDraw
    ov_draw = _PILDraw.Draw(overlay)

    # Semi-transparent dark background
    bg_alpha = int(180 * alpha)
    ov_draw.rounded_rectangle(
        [bubble_left, bubble_top, bubble_left + bubble_w, bubble_top + bubble_h],
        radius=PEEK_RADIUS,
        fill=(10, 10, 15, bg_alpha),
    )

    # Text color: white at 90% for assistant, cyan at 70% for user
    if is_user:
        text_alpha = int(178 * alpha)  # 70% of 255
        text_color = (0, 212, 210, text_alpha)
    else:
        text_alpha = int(230 * alpha)  # 90% of 255
        text_color = (255, 255, 255, text_alpha)

    # Draw text lines
    ty = bubble_top + PEEK_PAD_Y
    for line in lines:
        tx = bubble_left + 8
        ov_draw.text((tx, ty), line, fill=text_color, font=font)
        ty += line_h

    # Composite overlay onto the main image
    img_rgba = img.convert("RGBA")
    img_rgba = _PILImage.alpha_composite(img_rgba, overlay)
    img.paste(img_rgba.convert("RGB"))


# ── View position indicator dots ──────────────────────────────────────────

VIEW_ORDER = ["face", "chat"]
DOT_Y = SCREEN_H - 8
DOT_SPACING = 12
DOT_R = 2


def draw_view_dots(draw: ImageDraw.ImageDraw, current_view: str) -> None:
    """Draw two dots indicating current view position."""
    n = len(VIEW_ORDER)
    total_w = (n - 1) * DOT_SPACING
    start_x = (SCREEN_W - total_w) // 2

    for i, view in enumerate(VIEW_ORDER):
        x = start_x + i * DOT_SPACING
        active = view == current_view
        color = (0, 150, 148) if active else (40, 40, 60)
        r = DOT_R + 1 if active else DOT_R
        draw.ellipse([x - r, DOT_Y - r, x + r, DOT_Y + r], fill=color)
