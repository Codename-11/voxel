"""Abstract base class for character renderers.

All characters use the same Expression dataclass (eyes.openness, mouth.smile,
body.bounce_amount, etc.) — they just interpret the parameters differently
visually. This lets us swap characters without changing the expression system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image, ImageDraw

from shared import Expression, FaceStyle


class Character(ABC):
    """Base class for all renderable characters."""

    name: str  # e.g. "cube", "bmo"

    # Last drawn face center — set by draw(), read by renderer for decorations.
    # Defaults to rough screen center; characters override with exact position.
    _last_face_cx: int = 120
    _last_face_cy: int = 154

    # Last drawn eye centers — set by draw(), read by decorations for
    # positioning tears, blush, etc. relative to actual eye locations.
    _last_left_eye: tuple[int, int] = (90, 154)
    _last_right_eye: tuple[int, int] = (150, 154)

    # Accent color — set by renderer from config before draw().
    # Characters can use this for their primary glow/eye/edge color.
    _accent: tuple[int, int, int] = (0, 212, 210)

    @abstractmethod
    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float) -> None:
        """Draw the character onto the image.

        Args:
            draw: PIL ImageDraw context
            img: PIL Image (for compositing if needed)
            expr: Current (possibly interpolated) expression
            style: Face style theme
            blink_factor: 0.0 (closed) to 1.0 (open) from BlinkState
            gaze_x, gaze_y: Combined gaze position (-1..1)
            amplitude: Audio amplitude 0..1 for mouth sync
            now: Current time for bounce animation
        """

    def idle_quirk(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float) -> None:
        """Optional character-specific idle decoration.

        Called during IDLE state after the main face is drawn.
        Override in subclasses to add decorative effects.
        Default implementation does nothing.
        """
