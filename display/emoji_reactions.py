"""Emoji reaction system — agent-driven emoji decorations.

Agents can send emoji in their responses which trigger:
  1. A mood change (if the emoji maps to a known mood)
  2. A floating emoji decoration above the face

The emoji is parsed from the agent response text, mapped to a mood
if possible, and displayed as a decoration that auto-dismisses.

Usage:
  # Parse agent response and apply reaction
  from display.emoji_reactions import parse_reaction, apply_reaction

  emoji, clean_text = parse_reaction(agent_response_text)
  if emoji:
      apply_reaction(state, emoji, now)

  # Render the decoration (called by renderer)
  from display.emoji_reactions import draw_emoji_reaction
  draw_emoji_reaction(draw, state, now)
"""

from __future__ import annotations

import math
import re
from PIL import ImageDraw
from display.layout import SCREEN_W, ICON_Y
from display.fonts import get_font

# ── Emoji → mood mapping ─────────────────────────────────────────────────
# Known emoji are mapped to mood names.  The mood change is applied
# alongside the visual decoration.  Unmapped emoji still show visually.

EMOJI_MOOD_MAP: dict[str, str] = {
    # Happy / positive
    "\U0001f60a": "happy",       # 😊
    "\U0001f604": "happy",       # 😄
    "\U0001f60d": "happy",       # 😍
    "\u2764": "happy",           # ❤
    "\U0001f496": "happy",       # 💖
    "\U0001f44d": "happy",       # 👍
    "\U0001f389": "excited",     # 🎉
    "\U0001f31f": "excited",     # 🌟
    "\u2728": "excited",         # ✨
    # Thinking / curious
    "\U0001f914": "thinking",    # 🤔
    "\U0001f9d0": "curious",     # 🧐
    "\U0001f4a1": "curious",     # 💡
    # Sad / negative
    "\U0001f622": "sad",         # 😢
    "\U0001f625": "sad",         # 😥
    "\U0001f614": "sad",         # 😔
    # Surprised
    "\U0001f62e": "surprised",   # 😮
    "\U0001f632": "surprised",   # 😲
    "\u2757": "surprised",       # ❗
    # Sleepy
    "\U0001f634": "sleepy",      # 😴
    "\U0001f4a4": "sleepy",      # 💤
    # Confused
    "\U0001f615": "confused",    # 😕
    "\u2753": "confused",        # ❓
    # Frustrated / angry
    "\U0001f620": "frustrated",  # 😠
    "\U0001f621": "frustrated",  # 😡
    "\U0001f624": "frustrated",  # 😤
    # Focused / working
    "\U0001f4bb": "working",     # 💻
    "\u2699": "working",         # ⚙
    "\U0001f528": "working",     # 🔨
    # Listening
    "\U0001f3b5": "listening",   # 🎵
    "\U0001f3b6": "listening",   # 🎶
    "\U0001f442": "listening",   # 👂
}

# Regex: match one or more emoji at the start of a string (with optional space)
# Covers most common emoji ranges including modifiers and ZWJ sequences.
_EMOJI_RE = re.compile(
    r"^([\U0001f300-\U0001f9ff\u2600-\u27bf\u2700-\u27bf"
    r"\ufe00-\ufe0f\u200d\u20e3\U0001fa00-\U0001faff"
    r"\u2702-\u27b0\u24c2\u2934\u2935\u25aa-\u25fe"
    r"\u2764\u2757\u2753\u2728\u2699]+)\s*",
    re.UNICODE,
)


def parse_reaction(text: str) -> tuple[str, str]:
    """Extract a leading emoji from agent response text.

    Returns (emoji, clean_text).  If no leading emoji is found,
    returns ("", original_text).
    """
    if not text:
        return "", text

    m = _EMOJI_RE.match(text.strip())
    if m:
        emoji = m.group(1)
        clean = text.strip()[m.end():].strip()
        return emoji, clean

    return "", text


def get_mood_for_emoji(emoji: str) -> str | None:
    """Return the mood name for a known emoji, or None."""
    # Check single characters first, then try first char of multi-char emoji
    if emoji in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[emoji]
    if len(emoji) > 1 and emoji[0] in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[emoji[0]]
    return None


def apply_reaction(state, emoji: str, now: float,
                   duration: float = 3.0, set_mood: bool = True) -> None:
    """Apply an emoji reaction to the display state.

    Sets the reaction fields and optionally changes the mood if
    the emoji maps to a known mood.
    """
    state.reaction_emoji = emoji
    state.reaction_time = now
    state.reaction_duration = duration

    if set_mood:
        mood = get_mood_for_emoji(emoji)
        if mood:
            state.mood = mood


# ── Rendering ──────────────────────────────────────────────────────────────

# Target emoji size in pixels (rendered at native 109px and scaled down)
_EMOJI_SIZE = 36


def draw_emoji_reaction(draw: ImageDraw.ImageDraw,
                        img, state, now: float) -> None:
    """Draw the current emoji reaction above the face.

    Uses Noto Color Emoji for full-color rendering.  Falls back to
    monochrome text if the emoji font isn't available.

    Args:
        draw: PIL ImageDraw for fallback text rendering.
        img: PIL Image (RGB) for color emoji compositing.
        state: DisplayState with reaction_emoji fields.
        now: Current time for animation.
    """
    if not state.reaction_emoji:
        return

    elapsed = now - state.reaction_time
    duration = state.reaction_duration

    if elapsed < 0 or elapsed > duration:
        state.reaction_emoji = ""
        return

    t = elapsed / duration

    # Animation phases: pop-in (0-10%), hold (10-70%), fade-out (70-100%)
    if t < 0.1:
        phase_t = t / 0.1
        alpha = phase_t
        scale = 0.5 + phase_t * 0.6  # 0.5 → 1.1 overshoot
    elif t < 0.15:
        phase_t = (t - 0.1) / 0.05
        alpha = 1.0
        scale = 1.1 - phase_t * 0.1  # 1.1 → 1.0 settle
    elif t < 0.7:
        alpha = 1.0
        scale = 1.0
    else:
        phase_t = (t - 0.7) / 0.3
        alpha = 1.0 - phase_t
        scale = 1.0

    if alpha <= 0.01:
        return

    rise = int(t * 8)
    x = SCREEN_W // 2
    # Clamp so the emoji never overlaps the status bar
    from display.layout import STATUS_H
    y = max(STATUS_H + _EMOJI_SIZE // 2 + 2, ICON_Y - rise)

    # Try color emoji first
    from display.fonts import render_emoji
    emoji_size = max(8, int(_EMOJI_SIZE * scale))
    emoji_img = render_emoji(state.reaction_emoji, size=emoji_size)

    if emoji_img is not None:
        # Apply alpha fade by modulating the emoji alpha channel
        if alpha < 0.99:
            emoji_img = emoji_img.copy()
            a_channel = emoji_img.split()[3]
            a_channel = a_channel.point(lambda p: int(p * alpha))
            emoji_img.putalpha(a_channel)

        # Composite onto the frame (RGB → RGBA region → composite → paste back)
        px = x - emoji_img.width // 2
        py = y - emoji_img.height // 2
        # Clamp to image bounds
        px = max(0, min(px, img.width - emoji_img.width))
        py = max(0, min(py, img.height - emoji_img.height))

        region = img.crop((px, py, px + emoji_img.width, py + emoji_img.height))
        region = region.convert("RGBA")
        region.alpha_composite(emoji_img)
        img.paste(region.convert("RGB"), (px, py))
        return

    # Fallback: monochrome text emoji
    font = get_font(max(8, int(20 * scale)))
    bg = (10, 10, 15)
    r = int(255 * alpha + bg[0] * (1 - alpha))
    g = int(255 * alpha + bg[1] * (1 - alpha))
    b = int(255 * alpha + bg[2] * (1 - alpha))
    draw.text((x, y), state.reaction_emoji, fill=(r, g, b), font=font, anchor="mm")
