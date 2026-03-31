"""QR code overlay — shows a scannable link to the web config page."""

from __future__ import annotations

from PIL import Image, ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H

CYAN = (0, 212, 210)
TEXT_DIM = (120, 120, 140)
BG = (16, 16, 24)

_qr_cache: dict[str, Image.Image] = {}


def _generate_qr(url: str) -> Image.Image:
    """Generate a QR code PIL image, cached after first call."""
    if url in _qr_cache:
        return _qr_cache[url]

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="black")
        img = img.convert("RGB")
        _qr_cache[url] = img
        return img
    except Exception:
        # Fallback placeholder
        img = Image.new("RGB", (120, 120), (0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([10, 10, 110, 110], outline=CYAN, width=2)
        d.text((30, 50), "QR", fill=CYAN, font=get_font(22))
        return img


def draw_setup_screen(draw: ImageDraw.ImageDraw, img: Image.Image,
                      config_url: str, access_pin: str = "") -> None:
    """Draw the setup/config screen with QR code, URL, and PIN.

    The QR code embeds a pre-authenticated URL (token in query param) so
    scanning gives instant access. The displayed text URL is plain (requires
    PIN entry when typed manually).
    """
    font_title = get_font(20)
    font_url = get_font(16)
    font_pin = get_font(26)
    font_hint = get_font(14)

    # Background
    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=BG)

    # Title
    draw.text((20, 8), "SETUP", fill=CYAN, font=font_title)
    draw.line([(20, 26), (220, 26)], fill=(40, 40, 60), width=1)

    # QR code — embed authenticated URL for instant access
    try:
        from display.config_server import get_direct_url
        qr_url = get_direct_url(config_url)
    except Exception:
        qr_url = config_url
    qr_img = _generate_qr(qr_url)
    target_size = 130
    qr_w, qr_h = qr_img.size
    if qr_w != target_size:
        qr_img = qr_img.resize((target_size, target_size), Image.NEAREST)

    qr_x = (SCREEN_W - target_size) // 2
    qr_y = 32
    img.paste(qr_img, (qr_x, qr_y))

    # URL
    url_y = qr_y + target_size + 4
    url_short = config_url.replace("http://", "")
    tw = text_width(font_url, url_short)
    draw.text((max(4, (SCREEN_W - tw) // 2), url_y), url_short, fill=CYAN, font=font_url)

    # PIN — large, prominent
    if access_pin:
        pin_y = url_y + 24
        pin_label = "PIN:"
        pin_display = f"  {access_pin}"
        lw = text_width(font_hint, pin_label)
        pw = text_width(font_pin, pin_display)
        total = lw + pw
        start_x = (SCREEN_W - total) // 2
        draw.text((start_x, pin_y + 4), pin_label, fill=TEXT_DIM, font=font_hint)
        draw.text((start_x + lw, pin_y), pin_display, fill=(64, 255, 248), font=font_pin)

    # Hint
    hint = "Scan or open in browser"
    hw = text_width(font_hint, hint)
    hint_y = SCREEN_H - 24
    draw.text(((SCREEN_W - hw) // 2, hint_y), hint, fill=TEXT_DIM, font=font_hint)
