"""Font management — loads and caches fonts at multiple sizes.

Includes support for Noto Color Emoji (Google) which renders full-color
emoji via CBDT bitmap glyphs.  The font only supports size=109 natively;
``render_emoji()`` renders at native size and scales to the requested
pixel dimensions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("voxel.display.fonts")

_FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"
_EMOJI_FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "NotoColorEmoji.ttf"
_FALLBACK_PATHS = [
    Path(__file__).parent.parent / ".cache" / "lvgl-src" / "scripts" / "built_in_font" / "DejaVuSans.ttf",
]

_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_emoji_font: ImageFont.FreeTypeFont | None = None
_emoji_cache: dict[tuple[str, int], Image.Image] = {}  # (char, size) → RGBA image


def _find_ttf() -> Path | None:
    if _FONT_PATH.exists():
        return _FONT_PATH
    for p in _FALLBACK_PATHS:
        if p.exists():
            return p
    return None


def get_font(size: int = 12) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Get a font at the given size, cached after first load."""
    if size in _font_cache:
        return _font_cache[size]

    ttf = _find_ttf()
    if ttf:
        try:
            f = ImageFont.truetype(str(ttf), size)
            _font_cache[size] = f
            return f
        except Exception:
            pass

    f = ImageFont.load_default()
    _font_cache[size] = f
    return f


def text_width(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> int:
    """Get the pixel width of text with the given font."""
    try:
        return int(font.getlength(text))
    except AttributeError:
        return len(text) * 6


def wrap_text(font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
              text: str, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word
        if text_width(font, test) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


# ── Noto Color Emoji ──────────────────────────────────────────────────────

def _load_emoji_font() -> ImageFont.FreeTypeFont | None:
    """Load the Noto Color Emoji font (CBDT, fixed size 109)."""
    global _emoji_font
    if _emoji_font is not None:
        return _emoji_font
    if _EMOJI_FONT_PATH.exists():
        try:
            _emoji_font = ImageFont.truetype(str(_EMOJI_FONT_PATH), size=109)
            log.debug("Loaded Noto Color Emoji font")
            return _emoji_font
        except Exception as e:
            log.warning("Could not load emoji font: %s", e)
    return None


def render_emoji(char: str, size: int = 28) -> Image.Image | None:
    """Render a single emoji character as an RGBA PIL Image.

    Uses Noto Color Emoji (renders at native 109px, scales to *size*).
    Returns None if the emoji font isn't available.  Results are cached.
    """
    key = (char, size)
    if key in _emoji_cache:
        return _emoji_cache[key]

    font = _load_emoji_font()
    if font is None:
        return None

    try:
        # Render at native CBDT size on transparent background
        canvas = Image.new("RGBA", (136, 136), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((4, 4), char, font=font, embedded_color=True)

        # Crop to content
        bbox = canvas.getbbox()
        if not bbox:
            return None
        cropped = canvas.crop(bbox)

        # Scale to requested size (maintain aspect ratio)
        w, h = cropped.size
        aspect = w / h
        if aspect >= 1.0:
            nw, nh = size, max(1, int(size / aspect))
        else:
            nw, nh = max(1, int(size * aspect)), size

        scaled = cropped.resize((nw, nh), Image.LANCZOS)
        _emoji_cache[key] = scaled
        return scaled

    except Exception as e:
        log.debug("Emoji render failed for %r: %s", char, e)
        return None


def emoji_available() -> bool:
    """Return True if the Noto Color Emoji font is installed."""
    return _EMOJI_FONT_PATH.exists()
