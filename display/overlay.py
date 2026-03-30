"""Shared overlay helpers for decoration rendering.

Used by both mood decorations (decorations.py) and status decorations
(status_decorations.py) for alpha-blended drawing on RGBA images.
"""

from __future__ import annotations

from PIL import Image, ImageDraw


def color_with_alpha(base: tuple[int, int, int], alpha: float) -> tuple[int, int, int, int]:
    """Return an RGBA color tuple with clamped alpha."""
    a = max(0, min(255, int(alpha * 255)))
    return (base[0], base[1], base[2], a)


def draw_on_overlay(img: Image.Image, draw_fn) -> None:
    """Create a transparent overlay, call draw_fn on it, then composite onto img.

    Args:
        img: Target RGBA image to composite onto.
        draw_fn: Callable(overlay_draw, overlay_img) that draws on the overlay.
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    draw_fn(overlay_draw, overlay)
    img.alpha_composite(overlay)
