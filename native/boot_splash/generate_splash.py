#!/usr/bin/env python3
"""Generate the Voxel boot splash frame as an RGB565 file.

Renders two cyan closed-eye bars on a dark background — the starting
position for the wake-up animation. Matches the Voxel character's closed
eye appearance from display/characters/voxel.py.

Output:
    splash.rgb565  — 134,400 bytes raw RGB565 big-endian (240x280)
    splash.png     — PNG preview for desktop viewing

Usage:
    python generate_splash.py
    python generate_splash.py --output-dir /boot
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)

# ── Display constants (from display/layout.py) ──────────────────────────────

SCREEN_W = 240
SCREEN_H = 280

# ── Character geometry (from display/characters/voxel.py) ────────────────────

STATUS_H = 60
FACE_AREA_H = SCREEN_H - STATUS_H       # 220
CX = SCREEN_W // 2                      # 120
CY = STATUS_H + int(FACE_AREA_H * 0.46) # ~161

EYE_SPACING = 39    # center-to-center half-distance
EYE_BASE_W  = 46    # base eye width
GLOW_PAD    = 6     # glow halo padding

# ── Colors ───────────────────────────────────────────────────────────────────

BG     = (10, 10, 15)
ACCENT = (0, 212, 210)  # cyan


def _scale_color(c: tuple[int, ...], f: float) -> tuple[int, ...]:
    return tuple(min(255, int(v * f)) for v in c)


def _pil_to_rgb565(image: Image.Image) -> bytes:
    """Convert a PIL RGB image to RGB565 big-endian bytes."""
    pixels = image.convert("RGB").load()
    w, h = image.size
    data = bytearray(w * h * 2)

    idx = 0
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            data[idx]     = (rgb565 >> 8) & 0xFF  # big-endian high byte
            data[idx + 1] = rgb565 & 0xFF          # big-endian low byte
            idx += 2

    return bytes(data)


def draw_closed_bar(
    draw: ImageDraw.ImageDraw,
    cx: int, cy: int, width: int,
    accent: tuple[int, ...], glow_alpha: float = 0.9,
) -> None:
    """Draw a closed-eye bar with filleted ends and glow halo.

    Matches the closed-eye rendering in voxel.py _draw_eye (openness < 0.15).
    """
    bar_h = 7       # matches max(5, int(7 * scale)) at scale=1.0
    fillet = 3      # matches max(2, int(3 * scale)) at scale=1.0

    fill = _scale_color(accent, glow_alpha)

    # Glow halo (subtle pill-shaped glow behind the bar)
    glow_c = _scale_color(accent, 0.12 * glow_alpha)
    gp = GLOW_PAD
    glow_r = min(width // 2 + gp, (bar_h + 2 * gp) // 2)
    draw.rounded_rectangle(
        [cx - width // 2 - gp, cy - bar_h // 2 - gp,
         cx + width // 2 + gp, cy + bar_h // 2 + gp],
        radius=glow_r, fill=glow_c,
    )

    # Main bar
    draw.rounded_rectangle(
        [cx - width // 2, cy - bar_h // 2,
         cx + width // 2, cy + bar_h // 2],
        radius=fillet, fill=fill,
    )


def generate_splash(output_dir: Path) -> None:
    """Generate the boot splash frame files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create image
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    # Draw two closed-eye bars (the "asleep" starting position)
    for side in (-1, 1):
        ex = CX + side * EYE_SPACING
        draw_closed_bar(draw, ex, CY, EYE_BASE_W, ACCENT)

    # Save PNG preview
    png_path = output_dir / "splash.png"
    img.save(png_path)
    print(f"  PNG preview: {png_path}")

    # Save RGB565 raw frame
    rgb565_path = output_dir / "splash.rgb565"
    rgb565_data = _pil_to_rgb565(img)
    rgb565_path.write_bytes(rgb565_data)
    print(f"  RGB565 frame: {rgb565_path} ({len(rgb565_data)} bytes)")

    # Verify size
    expected = SCREEN_W * SCREEN_H * 2
    if len(rgb565_data) != expected:
        print(f"  WARNING: expected {expected} bytes, got {len(rgb565_data)}", file=sys.stderr)
    else:
        print(f"  Frame size OK ({expected} bytes = {SCREEN_W}x{SCREEN_H} RGB565)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Voxel boot splash frame (RGB565 + PNG preview)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory (default: same directory as this script)",
    )
    args = parser.parse_args()

    print("Generating Voxel boot splash...")
    generate_splash(args.output_dir)
    print("Done.")


if __name__ == "__main__":
    main()
