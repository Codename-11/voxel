"""Battery abstraction — mock 100% (desktop) or PiSugar API (Pi)."""

from __future__ import annotations

import logging
from hardware.platform import IS_PI

log = logging.getLogger(f"voxel.{__name__}")

_PISUGAR_API = "http://localhost:8421"


def init() -> None:
    """Initialize battery monitor."""
    if IS_PI:
        log.info("Battery: PiSugar API mode")
    else:
        log.info("Battery: Desktop mock mode (always 100%)")


def get_level() -> int:
    """Return battery level as 0–100 integer."""
    if not IS_PI:
        return 100

    try:
        import urllib.request
        import json
        url = f"{_PISUGAR_API}/api/battery"
        with urllib.request.urlopen(url, timeout=1) as resp:
            data = json.loads(resp.read())
            return int(data.get("data", 100))
    except Exception as e:
        log.debug(f"Battery read failed: {e}")
        return -1  # Unknown


def is_charging() -> bool:
    """Return True if currently charging."""
    if not IS_PI:
        return False

    try:
        import urllib.request
        import json
        url = f"{_PISUGAR_API}/api/charging"
        with urllib.request.urlopen(url, timeout=1) as resp:
            data = json.loads(resp.read())
            return bool(data.get("data", False))
    except Exception as e:
        log.debug(f"Charging state read failed: {e}")
        return False


def cleanup() -> None:
    """Release battery resources."""
    log.info("Battery cleaned up.")
