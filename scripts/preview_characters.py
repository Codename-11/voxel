"""Generate preview images showing both characters side by side.

Usage: uv run scripts/preview_characters.py
Outputs: out/character_preview.png
"""

from __future__ import annotations

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from shared import load_expressions, load_styles, Expression
from display.characters import get_character, character_names
from display.components.face import BG

SCREEN_W = 240
SCREEN_H = 280


def render_character(char_name: str, mood: str, expressions: dict, style) -> Image.Image:
    """Render a single character frame."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    expr = expressions.get(mood, Expression(name=mood))
    character = get_character(char_name)

    character.draw(
        draw, img, expr, style,
        blink_factor=1.0,
        gaze_x=0.0,
        gaze_y=0.0,
        amplitude=0.0,
        now=time.time(),
    )

    return img


def main() -> None:
    expressions = load_expressions()
    styles = load_styles()
    style = styles.get("kawaii") or next(iter(styles.values()))

    moods = ["neutral", "happy", "thinking", "error"]
    names = character_names()

    # Grid: rows = moods, cols = characters
    cols = len(names)
    rows = len(moods)
    padding = 4
    label_h = 24

    total_w = cols * SCREEN_W + (cols + 1) * padding
    total_h = rows * (SCREEN_H + label_h) + (rows + 1) * padding + label_h

    canvas = Image.new("RGB", (total_w, total_h), (20, 20, 30))
    canvas_draw = ImageDraw.Draw(canvas)

    # Try to load a font for labels
    try:
        from display.fonts import get_font
        font = get_font(14)
    except Exception:
        font = ImageFont.load_default()

    # Column headers
    for ci, name in enumerate(names):
        x = padding + ci * (SCREEN_W + padding) + SCREEN_W // 2
        canvas_draw.text((x - 20, 4), name.upper(), fill=(0, 212, 210), font=font)

    for ri, mood in enumerate(moods):
        for ci, name in enumerate(names):
            frame = render_character(name, mood, expressions, style)

            x = padding + ci * (SCREEN_W + padding)
            y = label_h + padding + ri * (SCREEN_H + label_h + padding)

            canvas.paste(frame, (x, y))

            # Mood label below
            canvas_draw.text(
                (x + SCREEN_W // 2 - 20, y + SCREEN_H + 2),
                mood, fill=(160, 160, 180), font=font,
            )

    # Save
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "character_preview.png")
    canvas.save(out_path)
    print(f"Saved preview to {out_path}")


if __name__ == "__main__":
    main()
