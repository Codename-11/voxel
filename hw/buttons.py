"""Button abstraction — keyboard (desktop) or GPIO (Pi)."""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable

from hw.detect import IS_PI

log = logging.getLogger(f"voxel.{__name__}")


class ButtonEvent(Enum):
    BUTTON_LEFT = auto()    # Navigate left / previous
    BUTTON_RIGHT = auto()   # Navigate right / next
    BUTTON_PRESS = auto()   # Push-to-talk / confirm
    BUTTON_RELEASE = auto() # Button released
    BUTTON_MENU = auto()    # Open menu / escape


# Pi GPIO pin assignments (Whisplay HAT)
_GPIO_LEFT = 17
_GPIO_RIGHT = 22
_GPIO_PRESS = 27

_gpio_available = False
_last_gpio: dict[int, int] = {}
_callbacks: list[Callable[[ButtonEvent], None]] = []

# Desktop key bindings (pygame) — loaded lazily
_KEY_MAP: dict | None = None


def _get_key_map() -> dict:
    """Lazy-load pygame key map (avoids crash on Pi where pygame isn't installed)."""
    global _KEY_MAP
    if _KEY_MAP is None:
        try:
            import pygame
            _KEY_MAP = {
                pygame.K_z: ButtonEvent.BUTTON_LEFT,
                pygame.K_x: ButtonEvent.BUTTON_RIGHT,
                pygame.K_SPACE: ButtonEvent.BUTTON_PRESS,
                pygame.K_ESCAPE: ButtonEvent.BUTTON_MENU,
            }
        except ImportError:
            _KEY_MAP = {}
    return _KEY_MAP


def init() -> None:
    """Initialize button input."""
    global _gpio_available, _last_gpio

    if IS_PI:
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            for pin in (_GPIO_LEFT, _GPIO_RIGHT, _GPIO_PRESS):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                _last_gpio[pin] = GPIO.input(pin)
            _gpio_available = True
            log.info("Buttons: GPIO mode initialized")
        except ImportError:
            log.warning("RPi.GPIO not available — falling back to keyboard input")
    else:
        log.info("Buttons: Desktop keyboard mode (Z=left, X=right, Space=PTT, Esc=menu)")


def poll() -> list[ButtonEvent]:
    """Return list of button events since last call."""
    events: list[ButtonEvent] = []

    if IS_PI and _gpio_available:
        events.extend(_poll_gpio())
    else:
        events.extend(_poll_keyboard())

    return events


def _poll_keyboard() -> list[ButtonEvent]:
    """Read keyboard events from pygame event queue."""
    try:
        import pygame
    except ImportError:
        return []
    events: list[ButtonEvent] = []
    key_map = _get_key_map()
    for event in pygame.event.get(pygame.KEYDOWN):
        btn = key_map.get(event.key)
        if btn is not None:
            events.append(btn)
    return events


def _poll_gpio() -> list[ButtonEvent]:
    """Read GPIO button state changes (active-low)."""
    global _last_gpio
    events: list[ButtonEvent] = []
    try:
        import RPi.GPIO as GPIO  # type: ignore
        pin_map = {
            _GPIO_LEFT: ButtonEvent.BUTTON_LEFT,
            _GPIO_RIGHT: ButtonEvent.BUTTON_RIGHT,
            _GPIO_PRESS: ButtonEvent.BUTTON_PRESS,
        }
        for pin, btn in pin_map.items():
            current = GPIO.input(pin)
            if _last_gpio.get(pin, 1) == 1 and current == 0:
                # Falling edge = button pressed (active-low)
                events.append(btn)
            _last_gpio[pin] = current
    except ImportError:
        pass
    return events


def cleanup() -> None:
    """Release button resources."""
    if IS_PI and _gpio_available:
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.cleanup()
        except ImportError:
            pass
    log.info("Buttons cleaned up.")
