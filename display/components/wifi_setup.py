"""WiFi setup screen — shown on the LCD when in AP onboarding mode."""

from __future__ import annotations

from PIL import Image, ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H

CYAN = (0, 212, 210)
CYAN_BRIGHT = (64, 255, 248)
TEXT = (200, 200, 220)
TEXT_DIM = (120, 120, 140)
BG = (16, 16, 24)


def draw_wifi_setup(draw: ImageDraw.ImageDraw, img: Image.Image,
                    ap_ssid: str, ap_password: str, portal_url: str) -> None:
    """Draw the WiFi AP onboarding screen on the LCD."""
    font_title = get_font(18)
    font_main = get_font(16)
    font_sm = get_font(13)
    font_pin = get_font(20)

    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=BG)

    # Title
    title = "WiFi Setup"
    tw = text_width(font_title, title)
    draw.text(((SCREEN_W - tw) // 2, 12), title, fill=CYAN, font=font_title)

    y = 44
    draw.text((20, y), "1. Join WiFi:", fill=TEXT_DIM, font=font_sm)
    y += 18
    tw = text_width(font_main, ap_ssid)
    draw.text(((SCREEN_W - tw) // 2, y), ap_ssid, fill=CYAN_BRIGHT, font=font_main)
    y += 22
    draw.text((24, y), f"Pass: {ap_password}", fill=TEXT, font=font_sm)

    y += 28
    draw.text((20, y), "2. Open:", fill=TEXT_DIM, font=font_sm)
    y += 18
    url_short = portal_url.replace("http://", "")
    tw = text_width(font_main, url_short)
    draw.text((max(10, (SCREEN_W - tw) // 2), y), url_short, fill=CYAN_BRIGHT, font=font_main)

    # PIN + QR
    y += 28
    try:
        from display.config_server import get_access_pin, get_direct_url
        pin = get_access_pin()
        if pin:
            draw.text((20, y), "3. Enter PIN:", fill=TEXT_DIM, font=font_sm)
            y += 18
            tw = text_width(font_pin, pin)
            draw.text(((SCREEN_W - tw) // 2, y), pin, fill=CYAN_BRIGHT, font=font_pin)

        # QR code with pre-authenticated URL
        y += 28
        try:
            qr_url = get_direct_url(portal_url)
            from display.components.qr_overlay import _generate_qr
            qr_img = _generate_qr(qr_url)
            qr_size = min(80, SCREEN_H - y - 20)
            if qr_size > 40:
                qr_w, qr_h = qr_img.size
                if qr_w != qr_size:
                    from PIL import Image as _Img
                    qr_img = qr_img.resize((qr_size, qr_size), _Img.NEAREST)
                qr_x = (SCREEN_W - qr_size) // 2
                img.paste(qr_img, (qr_x, y))
        except Exception:
            pass
    except Exception:
        draw.text((20, y), "3. Configure WiFi", fill=TEXT_DIM, font=font_sm)
