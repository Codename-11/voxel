"""WhisPlay SPI backend — pushes PIL frames to the ST7789 LCD on Pi."""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from display.backends.base import OutputBackend

log = logging.getLogger("voxel.display.whisplay")


def _patch_gpio_edge_detect(module: Any) -> None:
    """Patch GPIO.add_event_detect to swallow RuntimeError.

    The WhisPlay driver calls GPIO.add_event_detect during init for button
    events, but this fails on some Pi configurations (busy pin, permission
    issues). We don't need button events in the display service — the backend
    just pushes frames to SPI — so we make the call a safe no-op on failure.
    """
    gpio = getattr(module, "GPIO", None)
    if gpio is None or not hasattr(gpio, "add_event_detect"):
        return

    original = gpio.add_event_detect

    def _safe_add_event_detect(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except RuntimeError as e:
            log.warning(f"GPIO edge detect unavailable (ok for display): {e}")
            return False

    gpio.add_event_detect = _safe_add_event_detect


def _load_whisplay_module() -> Any:
    """Import the WhisPlay module, searching known locations.

    Priority order:
      1. Vendored copy at hw/WhisPlay.py (always available)
      2. Already importable (e.g. installed globally)
      3. VOXEL_WHISPLAY_DRIVER env override
      4. Legacy cache/clone locations (fallback)
    """
    import sys

    # 1. Vendored copy in hw/ (preferred — ships with the repo)
    vendored_dir = Path(__file__).resolve().parent.parent.parent / "hw"
    if (vendored_dir / "WhisPlay.py").exists():
        if str(vendored_dir) not in sys.path:
            sys.path.insert(0, str(vendored_dir))
        return importlib.import_module("WhisPlay")

    # 2. Already importable
    try:
        return importlib.import_module("WhisPlay")
    except ImportError:
        pass

    # 3. Env override and legacy locations
    home = Path.home()
    candidates = [
        Path(os.getenv("VOXEL_WHISPLAY_DRIVER", "")),
        home / "Whisplay" / "Driver",
        home / "voxel" / ".cache" / "whisplay" / "Driver",
        Path.cwd() / "Whisplay" / "Driver",
        Path(__file__).resolve().parent.parent.parent / ".cache" / "whisplay" / "Driver",
    ]
    for p in candidates:
        if p.is_dir() and (p / "WhisPlay.py").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            return importlib.import_module("WhisPlay")

    raise RuntimeError("WhisPlay driver not found — run 'voxel hw' to install")


def _load_whisplay_board() -> Any:
    """Load WhisPlay module, patch GPIO, and create the board."""
    module = _load_whisplay_module()
    _patch_gpio_edge_detect(module)
    return module.WhisPlayBoard()


def _pil_to_rgb565(image: Image.Image) -> bytes:
    """Convert a PIL RGB image to RGB565 big-endian bytes using numpy."""
    arr = np.array(image.convert("RGB"), dtype=np.uint16)
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype(">u2").tobytes()


class WhisplayBackend(OutputBackend):
    """Pushes PIL frames to the Whisplay HAT LCD via SPI."""

    def __init__(self) -> None:
        self._board: Any = None
        self._use_fast_path: bool = True

    def init(self) -> None:
        self._board = _load_whisplay_board()
        log.info("WhisPlay board initialized (SPI LCD)")

        # Backlight at 100% — SoftPWM flickers at any other value
        try:
            self._board.set_backlight(100)
            log.info("Backlight set to 100%")
        except Exception as e:
            log.warning(f"Could not set backlight: {e}")

        # Re-draw the splash immediately after board init to cover the
        # brief black flash from WhisPlayBoard()'s constructor fill_screen(0).
        # This keeps "Voxel Starting..." visible until the first render frame.
        try:
            self._redraw_splash()
        except Exception:
            pass  # non-fatal, first render frame will arrive shortly

    def _redraw_splash(self) -> None:
        """Redraw the boot splash to cover the constructor's fill_screen(0)."""
        from PIL import ImageDraw, ImageFont
        from pathlib import Path

        W = self._board.LCD_WIDTH
        H = self._board.LCD_HEIGHT
        img = Image.new("RGB", (W, H), (10, 10, 15))
        draw = ImageDraw.Draw(img)

        font_path = Path(__file__).parent.parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"
        try:
            font_lg = ImageFont.truetype(str(font_path), 36)
            font_sm = ImageFont.truetype(str(font_path), 14)
        except Exception:
            font_lg = ImageFont.load_default()
            font_sm = font_lg

        cyan = (0, 212, 210)
        dim = (60, 60, 80)

        text = "Voxel"
        try:
            tw = font_lg.getlength(text)
        except AttributeError:
            tw = len(text) * 20
        draw.text(((W - int(tw)) // 2, H // 2 - 36), text, fill=cyan, font=font_lg)

        sub = "Loading..."
        try:
            sw = font_sm.getlength(sub)
        except AttributeError:
            sw = len(sub) * 8
        draw.text(((W - int(sw)) // 2, H // 2 + 14), sub, fill=dim, font=font_sm)

        data = _pil_to_rgb565(img)
        self._board.set_window(0, 0, W - 1, H - 1)
        self._board._send_data(data)

    def push_frame(self, image: Image.Image) -> None:
        if self._board is None:
            return
        data = _pil_to_rgb565(image)
        board = self._board

        if self._use_fast_path:
            try:
                # Fast path: push bytes directly via SPI (writebytes2 accepts bytes)
                board.set_window(0, 0, board.LCD_WIDTH - 1, board.LCD_HEIGHT - 1)
                board._send_data(data)
                return
            except Exception as e:
                log.warning(f"Fast SPI path failed, falling back to draw_image: {e}")
                self._use_fast_path = False

        # Fallback: use the driver's draw_image (converts to list internally)
        board.draw_image(0, 0, board.LCD_WIDTH, board.LCD_HEIGHT, list(data))

    def should_quit(self) -> bool:
        return False

    def cleanup(self) -> None:
        if self._board is not None:
            try:
                self._board.cleanup()
            except Exception:
                pass
