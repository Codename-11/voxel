#!/usr/bin/env python3
"""Boot splash — runs before the main display service to kill the blue screen.

Called as ExecStartPre in the systemd service. Sequence:
  1. LED → solid cyan immediately (first sign of life)
  2. LCD → fill black (kills the blue screen)
  3. LCD → draw splash with "Voxel" title + "Starting..."
  4. LED → slow pulse cyan (indicates loading)
  5. Exit — display/service.py takes over LCD and LED
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("boot_splash")

ROOT = Path(__file__).resolve().parent.parent


def _load_board():
    """Load WhisPlay driver, patch GPIO, create board."""
    home = Path.home()
    candidates = [
        Path(os.getenv("VOXEL_WHISPLAY_DRIVER", "")),
        home / "Whisplay" / "Driver",
        home / "voxel" / ".cache" / "whisplay" / "Driver",
    ]
    for p in candidates:
        if p.is_dir() and (p / "WhisPlay.py").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            break

    module = importlib.import_module("WhisPlay")

    # Patch GPIO edge detect
    gpio = getattr(module, "GPIO", None)
    if gpio and hasattr(gpio, "add_event_detect"):
        orig = gpio.add_event_detect
        def _safe(*a, **k):
            try:
                return orig(*a, **k)
            except RuntimeError:
                pass
        gpio.add_event_detect = _safe

    return module.WhisPlayBoard()


def _get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        toml_path = ROOT / "pyproject.toml"
        for line in toml_path.read_text().splitlines():
            if line.strip().startswith("version"):
                return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "0.1.0"


def _draw_splash(board):
    """Draw the boot splash on the LCD."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
    except ImportError:
        return

    W, H = board.LCD_WIDTH, board.LCD_HEIGHT
    img = Image.new("RGB", (W, H), (10, 10, 15))
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_path = ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
    try:
        font_title = ImageFont.truetype(str(font_path), 42)
        font_sub = ImageFont.truetype(str(font_path), 16)
        font_ver = ImageFont.truetype(str(font_path), 12)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_ver = font_title

    cyan = (0, 212, 210)
    dim = (50, 50, 70)
    dark_cyan = (0, 100, 96)

    # Centered "Voxel" title — large
    title = "Voxel"
    try:
        tw = font_title.getlength(title)
    except AttributeError:
        tw = len(title) * 24
    title_y = H // 2 - 45
    draw.text(((W - int(tw)) // 2, title_y), title, fill=cyan, font=font_title)

    # Subtitle
    sub = "Starting..."
    try:
        sw = font_sub.getlength(sub)
    except AttributeError:
        sw = len(sub) * 9
    draw.text(((W - int(sw)) // 2, title_y + 52), sub, fill=dim, font=font_sub)

    # Version at bottom
    version = f"v{_get_version()}"
    try:
        vw = font_ver.getlength(version)
    except AttributeError:
        vw = len(version) * 7
    draw.text(((W - int(vw)) // 2, H - 30), version, fill=dark_cyan, font=font_ver)

    # Subtle top/bottom accent lines
    draw.line([(40, title_y - 16), (W - 40, title_y - 16)], fill=dark_cyan, width=1)
    draw.line([(40, title_y + 80), (W - 40, title_y + 80)], fill=dark_cyan, width=1)

    # Convert to RGB565 and push
    arr = np.array(img, dtype=np.uint16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    data = rgb565.astype(">u2").tobytes()

    board.set_window(0, 0, W - 1, H - 1)
    board._send_data(data)


def _led_on(board, r: int, g: int, b: int) -> None:
    """Set LED color, silently ignoring errors."""
    if board is None:
        return
    try:
        board.set_rgb(r, g, b)
    except Exception:
        pass


def main():
    try:
        board = _load_board()

        # ── Step 1: LED on immediately — first sign of life ──
        _led_on(board, 0, 255, 255)  # solid cyan
        log.info("LED: boot indicator ON")

        # ── Step 2: Kill the blue screen ASAP ──
        board.fill_screen(0x0000)
        board.set_backlight(100)
        log.info("LCD initialized (blue screen cleared)")

        # ── Step 3: Draw splash ──
        _draw_splash(board)
        log.info("Boot splash displayed")

        # ── Step 4: LED pulse — indicates loading in progress ──
        # Two quick cyan flashes then hold dim, so the user knows
        # the device is still booting (not frozen)
        import time
        for _ in range(2):
            _led_on(board, 0, 255, 255)
            time.sleep(0.15)
            _led_on(board, 0, 0, 0)
            time.sleep(0.15)
        # Leave LED on dim-ish cyan (full on, since no PWM dimming)
        _led_on(board, 0, 255, 255)
        # Display service will take over LED control when it starts

    except Exception as e:
        log.warning(f"Boot splash failed: {e}")


if __name__ == "__main__":
    main()
