"""Face rendering — thin wrapper that delegates to the character system.

Originally contained all cube drawing logic. Now delegates to
display.characters for pluggable character rendering. Kept for
backwards compatibility so existing imports still work.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from shared import Expression, FaceStyle
from display.characters import get_character

# ── Background color (used by renderer.py for Image.new) ───────────────────

BG = (10, 10, 15)


def draw_face(draw: ImageDraw.ImageDraw, expr: Expression, style: FaceStyle,
              blink_factor: float, gaze_x: float, gaze_y: float,
              amplitude: float, now: float,
              *, character_name: str = "cube",
              img: Image.Image | None = None) -> None:
    """Draw the complete face onto the draw context.

    Delegates to the active character renderer. The ``character_name``
    parameter selects which character to draw (default "cube" for
    backwards compatibility).

    Args:
        draw: PIL ImageDraw context
        expr: Current (possibly interpolated) expression
        style: Face style theme
        blink_factor: 0.0 (closed) to 1.0 (open) from BlinkState
        gaze_x, gaze_y: Combined gaze position (-1..1)
        amplitude: Audio amplitude 0..1 for mouth sync
        now: Current time for bounce animation
        character_name: Which character to render ("cube", "bmo", etc.)
        img: PIL Image for compositing (passed through to character)
    """
    character = get_character(character_name)

    # Create a dummy image if none provided (backwards compat)
    if img is None:
        img = Image.new("RGB", (240, 280), BG)

    character.draw(draw, img, expr, style, blink_factor, gaze_x, gaze_y,
                   amplitude, now)
