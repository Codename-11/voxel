"""Onboarding screens — shown on LCD when setup is incomplete."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H

CYAN = (0, 212, 210)
CYAN_BRIGHT = (64, 255, 248)
TEXT = (200, 200, 220)
TEXT_DIM = (120, 120, 140)
BG = (16, 16, 24)
GREEN = (80, 220, 120)

_SETUP_STATE_PATH = Path(__file__).resolve().parent.parent.parent / "config" / ".setup-state"
_cached_state: dict | None = None
_cache_time: float = 0.0


def get_setup_state() -> dict:
    """Load setup state with 5-second cache to avoid disk reads every frame."""
    global _cached_state, _cache_time
    import time
    now = time.time()
    if _cached_state is not None and (now - _cache_time) < 5.0:
        return _cached_state

    if not _SETUP_STATE_PATH.exists():
        _cached_state = {}
        _cache_time = now
        return _cached_state

    try:
        import yaml
        _cached_state = yaml.safe_load(_SETUP_STATE_PATH.read_text()) or {}
    except Exception:
        _cached_state = {}
    _cache_time = now
    return _cached_state


def save_setup_flag(key: str, value: bool = True) -> None:
    """Set a flag in the setup state file."""
    global _cached_state, _cache_time
    import yaml
    state = get_setup_state().copy()
    state[key] = value
    try:
        _SETUP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETUP_STATE_PATH.write_text(yaml.dump(state, default_flow_style=False))
        _cached_state = state
        _cache_time = 0.0  # force re-read next time
    except Exception:
        pass


def needs_onboarding() -> bool:
    """Check if the device needs onboarding (config not yet done).

    Returns True only if the gateway token is genuinely missing.
    Checks the actual config (local.yaml + env vars), not a separate state file.
    Once the user sets the token via web UI or CLI, this returns False.
    """
    # Check the real config — if gateway token exists, onboarding is done
    try:
        from config.settings import load_settings
        settings = load_settings()
        token = settings.get("gateway", {}).get("token", "")
        if token:
            # Token is set — mark setup state so we don't re-check every frame
            state = get_setup_state()
            if not state.get("gateway_configured"):
                save_setup_flag("gateway_configured", True)
            return False
    except Exception:
        pass

    # Also check the setup state file (for manual override)
    state = get_setup_state()
    return not state.get("gateway_configured", False)


def draw_configure_screen(draw: ImageDraw.ImageDraw, img: Image.Image,
                          config_url: str, access_pin: str = "") -> None:
    """Draw the 'scan to configure' screen — shown after WiFi is connected
    but before API keys are set."""
    font_title = get_font(20)
    font_main = get_font(18)
    font_pin = get_font(26)
    font_hint = get_font(14)

    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=BG)

    # Title
    title = "Configure"
    tw = text_width(font_title, title)
    draw.text(((SCREEN_W - tw) // 2, 10), title, fill=CYAN, font=font_title)

    # Subtitle
    sub = "Scan to set up"
    sw = text_width(font_hint, sub)
    draw.text(((SCREEN_W - sw) // 2, 32), sub, fill=TEXT_DIM, font=font_hint)

    # QR code
    y = 48
    try:
        from display.config_server import get_direct_url
        from display.components.qr_overlay import _generate_qr
        qr_url = get_direct_url(config_url)
        qr_img = _generate_qr(qr_url)
        qr_size = 120
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        img.paste(qr_img, ((SCREEN_W - qr_size) // 2, y))
        y += qr_size + 6
    except Exception:
        y += 10

    # URL
    url_short = config_url.replace("http://", "")
    tw = text_width(font_main, url_short)
    draw.text((max(4, (SCREEN_W - tw) // 2), y), url_short, fill=CYAN, font=font_main)

    # PIN
    if access_pin:
        y += 24
        pin_text = f"PIN: {access_pin}"
        tw = text_width(font_pin, pin_text)
        draw.text(((SCREEN_W - tw) // 2, y), pin_text, fill=CYAN_BRIGHT, font=font_pin)

    # Hint
    hint = "Set gateway token + API keys"
    hw = text_width(font_hint, hint)
    draw.text(((SCREEN_W - hw) // 2, SCREEN_H - 22), hint, fill=TEXT_DIM, font=font_hint)


def draw_ready_screen(draw: ImageDraw.ImageDraw) -> None:
    """Draw the 'ready' screen — shown briefly after onboarding completes."""
    font_lg = get_font(24)
    font_sm = get_font(14)
    font_hint = get_font(14)

    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=BG)

    # Checkmark
    check = "Ready!"
    tw = text_width(font_lg, check)
    draw.text(((SCREEN_W - tw) // 2, SCREEN_H // 2 - 30), check, fill=GREEN, font=font_lg)

    # Hint
    hint = "Hold button to talk"
    hw = text_width(font_sm, hint)
    draw.text(((SCREEN_W - hw) // 2, SCREEN_H // 2 + 10), hint, fill=TEXT, font=font_sm)

    sub = "Double-tap = push-to-talk"
    sw = text_width(font_hint, sub)
    draw.text(((SCREEN_W - sw) // 2, SCREEN_H // 2 + 34), sub, fill=TEXT_DIM, font=font_hint)
