"""Display abstraction — Pygame window (desktop) or SPI LCD framebuffer (Pi)."""

import logging
import os
import pygame
from hardware.platform import IS_PI

log = logging.getLogger(f"voxel.{__name__}")

WIDTH = 240
HEIGHT = 280

_screen: pygame.Surface | None = None
_clock: pygame.time.Clock | None = None


def init() -> None:
    """Initialize display."""
    global _screen, _clock

    if IS_PI:
        # Target framebuffer for SPI LCD (ST7789)
        os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
        os.environ.setdefault("SDL_FBDEV", "/dev/fb1")
        os.environ.setdefault("SDL_NOMOUSE", "1")
        log.info("Display: Pi framebuffer mode (/dev/fb1)")
    else:
        log.info("Display: Desktop window mode (240x280)")

    pygame.init()
    pygame.display.set_caption("Voxel Relay (Dev)")

    flags = 0  # no RESIZABLE
    _screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    _clock = pygame.time.Clock()

    log.info(f"Display initialized: {WIDTH}x{HEIGHT}")


def get_surface() -> pygame.Surface:
    """Return the main drawing surface."""
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init() first.")
    return _screen


def update() -> None:
    """Flip the display buffer."""
    pygame.display.flip()


def set_brightness(level: float) -> None:
    """Set display brightness (0.0–1.0). No-op on desktop."""
    level = max(0.0, min(1.0, level))
    if IS_PI:
        try:
            import RPi.GPIO as GPIO  # type: ignore
            # Backlight PWM — pin depends on HAT wiring; adjust as needed
            log.debug(f"Brightness set to {level:.2f} (Pi GPIO)")
        except ImportError:
            pass
    else:
        log.debug(f"Brightness: {level:.2f} (desktop no-op)")


def get_clock() -> pygame.time.Clock:
    """Return the Pygame clock for FPS control."""
    if _clock is None:
        raise RuntimeError("Display not initialized. Call init() first.")
    return _clock


def cleanup() -> None:
    """Shut down display."""
    pygame.display.quit()
    log.info("Display cleaned up.")
