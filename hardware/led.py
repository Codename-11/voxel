"""LED abstraction — visual indicator (desktop) or RGB LED via GPIO/PWM (Pi)."""

from __future__ import annotations

import logging
import math
import time
import threading
from typing import Tuple

import pygame
from hardware.platform import IS_PI

log = logging.getLogger(__name__)

Color = Tuple[int, int, int]

# Desktop LED indicator: small circle in top-right corner
_LED_X = 220
_LED_Y = 12
_LED_RADIUS = 8

# Current state
_current_color: Color = (0, 0, 0)
_pulse_thread: threading.Thread | None = None
_pulse_stop = threading.Event()

# Pi GPIO PWM pins (BCM, adjust for actual Whisplay HAT wiring)
_PIN_R = 16
_PIN_G = 20
_PIN_B = 21
_pwm_r = None
_pwm_g = None
_pwm_b = None


def init() -> None:
    """Initialize LED."""
    global _pwm_r, _pwm_g, _pwm_b

    if IS_PI:
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            for pin in (_PIN_R, _PIN_G, _PIN_B):
                GPIO.setup(pin, GPIO.OUT)
            _pwm_r = GPIO.PWM(_PIN_R, 1000)
            _pwm_g = GPIO.PWM(_PIN_G, 1000)
            _pwm_b = GPIO.PWM(_PIN_B, 1000)
            _pwm_r.start(0)
            _pwm_g.start(0)
            _pwm_b.start(0)
            log.info("LED: GPIO/PWM initialized")
        except ImportError:
            log.warning("RPi.GPIO not available — LED disabled on Pi")
    else:
        log.info("LED: Desktop indicator mode (top-right corner)")


def set_color(r: int, g: int, b: int) -> None:
    """Set LED to an RGB color (0–255 each)."""
    global _current_color
    _stop_pulse()
    _current_color = (r, g, b)
    _apply_color(r, g, b)


def _apply_color(r: int, g: int, b: int) -> None:
    if IS_PI and _pwm_r:
        try:
            _pwm_r.ChangeDutyCycle(r / 255 * 100)
            _pwm_g.ChangeDutyCycle(g / 255 * 100)
            _pwm_b.ChangeDutyCycle(b / 255 * 100)
        except Exception:
            pass


def pulse(color: Color, speed: float = 1.0) -> None:
    """Pulse LED at given speed (Hz). Runs in background thread."""
    global _pulse_thread, _pulse_stop, _current_color
    _stop_pulse()
    _current_color = color
    _pulse_stop.clear()

    def _run():
        while not _pulse_stop.is_set():
            t = time.time()
            # Sine wave brightness 0..1
            brightness = (math.sin(2 * math.pi * speed * t) + 1) / 2
            r = int(color[0] * brightness)
            g = int(color[1] * brightness)
            b = int(color[2] * brightness)
            _apply_color(r, g, b)
            # Store pulsed color for desktop rendering
            global _current_color
            _current_color = (r, g, b)
            time.sleep(0.05)

    _pulse_thread = threading.Thread(target=_run, daemon=True)
    _pulse_thread.start()


def off() -> None:
    """Turn LED off."""
    set_color(0, 0, 0)


def _stop_pulse() -> None:
    global _pulse_thread
    _pulse_stop.set()
    if _pulse_thread and _pulse_thread.is_alive():
        _pulse_thread.join(timeout=0.2)
    _pulse_thread = None


def draw_indicator(surface: pygame.Surface) -> None:
    """Draw the desktop LED indicator circle onto the given surface."""
    if not IS_PI:
        pygame.draw.circle(surface, _current_color, (_LED_X, _LED_Y), _LED_RADIUS)
        # White outline
        pygame.draw.circle(surface, (60, 60, 60), (_LED_X, _LED_Y), _LED_RADIUS, 1)


def get_color() -> Color:
    """Return current LED color."""
    return _current_color


def cleanup() -> None:
    """Release LED resources."""
    _stop_pulse()
    off()
    if IS_PI:
        try:
            import RPi.GPIO as GPIO  # type: ignore
            if _pwm_r:
                _pwm_r.stop()
            if _pwm_g:
                _pwm_g.stop()
            if _pwm_b:
                _pwm_b.stop()
        except ImportError:
            pass
    log.info("LED cleaned up.")
