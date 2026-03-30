"""Face style themes — each defines how eyes, mouth, and body render.

Mirrors design/src/styles.js. Three styles: kawaii (default), retro, minimal.
Each style defines eye type, colors, sizes, and mouth rendering type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Color helpers ─────────────────────────────────────────────────────────────

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' hex string to (r, g, b) tuple."""
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgba_tuple(r: int, g: int, b: int, a: int = 255) -> tuple[int, int, int, int]:
    return (r, g, b, a)


# ── Theme color palette (matches CSS custom properties) ──────────────────────

COLORS = {
    "background":   hex_to_rgb("#0a0a0f"),
    "body":         hex_to_rgb("#1a1a2e"),
    "body_light":   hex_to_rgb("#222244"),
    "body_dark":    hex_to_rgb("#121220"),
    "cyan":         hex_to_rgb("#00d4d2"),
    "cyan_bright":  hex_to_rgb("#40fff8"),
    "cyan_dim":     hex_to_rgb("#006460"),
    "eye_white":    hex_to_rgb("#f0f0f0"),
    "mouth_white":  hex_to_rgb("#f0f0f0"),
    "error":        hex_to_rgb("#ff3c3c"),
    "highlight":    hex_to_rgb("#ffffff"),
}


# ── Style dataclasses ────────────────────────────────────────────────────────

@dataclass
class EyeStyle:
    """Defines how eyes are rendered for a given style."""
    type: str = "roundrect"         # "roundrect", "iris", "dot"
    base_width: int = 30
    base_height: int = 38
    highlight_size: int = 0
    highlight_color: tuple = (255, 255, 255, 230)
    fill_color: tuple = (240, 240, 240)     # #f0f0f0 white
    glow_color: tuple = (240, 240, 240, 38) # rgba(240,240,240,0.15)
    border_radius: float = 0.28     # fraction of size for rounded rect
    closed_radius: float = 0.35     # flatter when nearly closed
    # iris-style extras
    iris_color: tuple = (10, 10, 18)
    iris_size: float = 0.55         # relative to eye min dimension


@dataclass
class MouthStyle:
    """Defines how the mouth is rendered for a given style."""
    type: str = "offset"            # "offset", "teeth", "arc"
    base_width: int = 30
    stroke_width: int = 3
    color: tuple = (240, 240, 240)  # #f0f0f0 white
    teeth_color: tuple = (255, 255, 255)
    lip_color: tuple = (18, 18, 32)


@dataclass
class XEyeStyle:
    """Defines X_X error eye appearance."""
    color: tuple = (255, 60, 60)
    thickness: int = 3
    size: int = 22


@dataclass
class FaceStyle:
    """Complete face style theme."""
    name: str = "Kawaii"
    description: str = ""
    eye: EyeStyle = field(default_factory=EyeStyle)
    mouth: MouthStyle = field(default_factory=MouthStyle)
    x_eye: XEyeStyle = field(default_factory=XEyeStyle)


# ── Style definitions (mirrors design/src/styles.js) ─────────────────────────

STYLES: dict[str, FaceStyle] = {
    "kawaii": FaceStyle(
        name="Kawaii",
        description="White rounded-rect eyes, small offset smile - modern companion style",
        eye=EyeStyle(
            type="roundrect",
            base_width=30,
            base_height=38,
            highlight_size=0,
            highlight_color=(0, 0, 0, 0),
            fill_color=(240, 240, 240),             # #f0f0f0
            glow_color=(240, 240, 240, 38),         # rgba(240,240,240,0.15)
            border_radius=0.28,
            closed_radius=0.35,
        ),
        mouth=MouthStyle(
            type="offset",
            base_width=30,
            stroke_width=3,
            color=(240, 240, 240),                  # #f0f0f0
        ),
        x_eye=XEyeStyle(
            color=(255, 60, 60),
            thickness=3,
            size=22,
        ),
    ),

    "retro": FaceStyle(
        name="Retro",
        description="Big expressive eyes with irises, toothy grin - Fallout/Cuphead style",
        eye=EyeStyle(
            type="iris",
            base_width=36,
            base_height=42,
            highlight_size=7,
            highlight_color=(255, 255, 255, 230),
            fill_color=(240, 240, 240),             # white sclera
            glow_color=(255, 255, 255, 26),         # rgba(255,255,255,0.1)
            border_radius=0.50,
            closed_radius=0.45,
            iris_color=(10, 10, 18),
            iris_size=0.55,
        ),
        mouth=MouthStyle(
            type="teeth",
            base_width=36,
            stroke_width=2,
            color=(240, 240, 240),
            teeth_color=(255, 255, 255),
            lip_color=(18, 18, 32),
        ),
        x_eye=XEyeStyle(
            color=(255, 60, 60),
            thickness=4,
            size=26,
        ),
    ),

    "minimal": FaceStyle(
        name="Minimal",
        description="Tiny dot eyes, dash mouth - lo-fi pixel style",
        eye=EyeStyle(
            type="dot",
            base_width=10,
            base_height=10,
            highlight_size=0,
            highlight_color=(0, 0, 0, 0),
            fill_color=(0, 212, 210),               # cyan
            glow_color=(0, 212, 210, 102),          # rgba(0,212,210,0.4)
            border_radius=0.50,
            closed_radius=0.50,
        ),
        mouth=MouthStyle(
            type="arc",
            base_width=18,
            stroke_width=2,
            color=(0, 100, 96),                     # cyan-dim
        ),
        x_eye=XEyeStyle(
            color=(255, 60, 60),
            thickness=2,
            size=12,
        ),
    ),
}

STYLE_LIST: list[str] = list(STYLES.keys())
DEFAULT_STYLE: str = "kawaii"
