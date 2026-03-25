"""Voxel display sanity test for desktop and Whisplay hardware."""

from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

from cli.display import fail, header, info, ok, warn
from hardware.platform import probe_hardware


def _driver_candidates() -> list[Path]:
    home = Path.home()
    candidates = [
        Path(os.getenv("VOXEL_WHISPLAY_DRIVER", "")),
        home / "Whisplay" / "Driver",
        home / "voxel" / ".cache" / "whisplay" / "Driver",
        Path.cwd() / "Whisplay" / "Driver",
        Path(__file__).resolve().parent.parent / ".cache" / "whisplay" / "Driver",
    ]
    return [path for path in candidates if str(path)]


def _load_whisplay_board():
    try:
        module = importlib.import_module("WhisPlay")
        return module
    except Exception:
        pass

    for candidate in _driver_candidates():
        module_path = candidate / "WhisPlay.py"
        if not module_path.exists():
            continue
        path_str = str(candidate)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        module = importlib.import_module("WhisPlay")
        return module

    raise ModuleNotFoundError(
        "WhisPlay.py not found. Set VOXEL_WHISPLAY_DRIVER or clone PiSugar/Whisplay to ~/Whisplay."
    )


def _to_rgb565_bytes(image) -> list[int]:
    pixel_data: list[int] = []
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b = image.getpixel((x, y))
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            pixel_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])
    return pixel_data


def _make_test_pattern(width: int, height: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (7, 10, 16))
    draw = ImageDraw.Draw(img)

    bands = [
        ((18, 28, 48), (0, 0, width, height // 3)),
        ((8, 36, 38), (0, height // 3, width, 2 * height // 3)),
        ((20, 10, 30), (0, 2 * height // 3, width, height)),
    ]
    for color, box in bands:
        draw.rectangle(box, fill=color)

    swatches = [
        ((255, 64, 64), (12, 12, 68, 68)),
        ((64, 255, 128), (86, 12, 142, 68)),
        ((64, 160, 255), (160, 12, 216, 68)),
        ((255, 220, 96), (12, 86, 68, 142)),
    ]
    for color, box in swatches:
        draw.rounded_rectangle(box, radius=10, fill=color)

    draw.rounded_rectangle((10, 176, width - 10, height - 14), radius=18, outline=(70, 240, 255), width=3)
    draw.text((18, 154), "VOXEL", fill=(220, 250, 255))
    draw.text((18, 178), "Display Test", fill=(220, 250, 255))
    draw.text((18, 202), "RGB + panel sanity", fill=(150, 215, 225))
    draw.text((18, 226), f"{width}x{height}", fill=(150, 215, 225))
    return img


def _run_whisplay_test(args) -> int:
    probe = probe_hardware()
    if not probe.whisplay_detected:
        warn("Whisplay not auto-detected; continuing anyway because this is a direct sanity test.")

    try:
        whisplay_module = _load_whisplay_board()
    except ModuleNotFoundError as exc:
        fail(str(exc))
        info("Expected locations checked include ~/Whisplay/Driver and VOXEL_WHISPLAY_DRIVER.")
        return 1

    WhisPlayBoard = whisplay_module.WhisPlayBoard

    # PiSugar's board init installs GPIO edge detection for the button. On some
    # Pi setups that fails even though SPI/LCD access still works, so degrade the
    # display sanity test to a button-less mode instead of aborting.
    gpio_module = getattr(whisplay_module, "GPIO", None)
    original_add_event_detect = None
    if probe.is_pi and gpio_module is not None and hasattr(gpio_module, "add_event_detect"):
        original_add_event_detect = gpio_module.add_event_detect

        def _safe_add_event_detect(*event_args, **event_kwargs):
            try:
                return original_add_event_detect(*event_args, **event_kwargs)
            except Exception as exc:
                warn(f"Button edge detect unavailable; continuing without button events ({exc})")
                return False

        gpio_module.add_event_detect = _safe_add_event_detect

    try:
        from PIL import Image  # noqa: F401
    except Exception:
        fail("Pillow is not installed. Run: sudo apt install python3-pil")
        return 1

    board = None
    try:
        board = WhisPlayBoard()
        board.set_backlight(args.backlight)
        ok(f"Whisplay board initialized at backlight {args.backlight}%")

        image = _make_test_pattern(board.LCD_WIDTH, board.LCD_HEIGHT)
        board.draw_image(0, 0, board.LCD_WIDTH, board.LCD_HEIGHT, _to_rgb565_bytes(image))
        ok("Rendered Voxel test pattern")
        time.sleep(args.hold)

        for label, color565, led in [
            ("Red", 0xF800, (255, 0, 0)),
            ("Green", 0x07E0, (0, 255, 0)),
            ("Blue", 0x001F, (0, 0, 255)),
            ("White", 0xFFFF, (255, 255, 255)),
        ]:
            info(f"Showing {label} fill")
            board.fill_screen(color565)
            board.set_rgb(*led)
            time.sleep(args.color_hold)

        board.draw_image(0, 0, board.LCD_WIDTH, board.LCD_HEIGHT, _to_rgb565_bytes(image))
        board.set_rgb(0, 180, 255)
        ok("Display sanity test complete")
        return 0
    except Exception as exc:
        fail(f"Display test failed: {exc}")
        return 1
    finally:
        if gpio_module is not None and original_add_event_detect is not None:
            gpio_module.add_event_detect = original_add_event_detect
        if board is not None:
            try:
                board.cleanup()
            except Exception:
                pass


def run(args) -> int:
    header("Voxel Display Test")
    info("This test bypasses Cog and talks to the Whisplay driver directly.")

    probe = probe_hardware()
    if probe.is_pi:
        return _run_whisplay_test(args)

    warn("Desktop fallback: opening a local pygame window instead of Whisplay hardware.")
    try:
        import pygame

        pygame.init()
        screen = pygame.display.set_mode((240, 280))
        pygame.display.set_caption("Voxel Display Test")
        image = _make_test_pattern(240, 280)
        mode = image.mode
        data = image.tobytes()
        surface = pygame.image.fromstring(data, image.size, mode)
        screen.blit(surface, (0, 0))
        pygame.display.flip()
        time.sleep(args.hold)
        pygame.quit()
        ok("Desktop display test complete")
        return 0
    except Exception as exc:
        fail(f"Desktop display test failed: {exc}")
        return 1
