"""Linux framebuffer backend — writes PIL frames to /dev/fb1 (fbtft/mipi-dbi-spi).

This backend is used when the ST7789 LCD is driven by the kernel's fbtft
framebuffer driver instead of the WhisPlay userspace SPI driver.  The kernel
creates /dev/fb1 via the mipi-dbi-spi device-tree overlay.

Enable the overlay in /boot/firmware/config.txt (see native/boot_splash/fbtft-config.txt),
then start the display service with:

    uv run display/service.py --backend framebuffer

EXPERIMENTAL: This backend has not been validated on all Pi OS versions.
"""

from __future__ import annotations

import logging
import os
import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image

from display.backends.base import OutputBackend

log = logging.getLogger("voxel.display.framebuffer")

# Default framebuffer device — fbtft typically creates fb1 (fb0 = HDMI).
DEFAULT_FB_DEVICE = "/dev/fb1"

# Expected display dimensions
EXPECTED_WIDTH = 240
EXPECTED_HEIGHT = 280

# RGB565 frame size: 240 * 280 * 2 bytes per pixel
FRAME_BYTES = EXPECTED_WIDTH * EXPECTED_HEIGHT * 2


def _read_sysfs_int(path: str) -> int | None:
    """Read an integer from a sysfs file, or None on failure."""
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def _pil_to_rgb565(image: Image.Image) -> bytes:
    """Convert a PIL RGB image to RGB565 big-endian bytes using numpy.

    Same conversion as the WhisPlay SPI backend — the ST7789 controller
    expects big-endian RGB565 regardless of transport (SPI or framebuffer).
    """
    arr = np.array(image.convert("RGB"), dtype=np.uint16)
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.astype(">u2").tobytes()


class FramebufferBackend(OutputBackend):
    """Write PIL frames to a Linux framebuffer device (e.g., /dev/fb1 via fbtft).

    The fbtft driver (mipi-dbi-spi overlay) exposes the ST7789 LCD as a
    standard Linux framebuffer.  This backend converts each PIL frame to
    RGB565 and writes it directly to the fb device file.
    """

    def __init__(self, device: str | None = None) -> None:
        self._device_path = device or os.environ.get("VOXEL_FB_DEVICE", DEFAULT_FB_DEVICE)
        self._fb: BinaryIO | None = None
        self._width: int = EXPECTED_WIDTH
        self._height: int = EXPECTED_HEIGHT

    def init(self) -> None:
        device = Path(self._device_path)

        if not device.exists():
            raise RuntimeError(
                f"Framebuffer device {self._device_path} not found. "
                f"Is the mipi-dbi-spi overlay enabled in config.txt? "
                f"See native/boot_splash/fbtft-config.txt for setup instructions."
            )

        # Read actual dimensions from sysfs if available
        fb_name = device.name  # e.g. "fb1"
        sysfs_base = f"/sys/class/graphics/{fb_name}"

        sysfs_w = _read_sysfs_int(f"{sysfs_base}/virtual_size")
        if sysfs_w is not None:
            # virtual_size is "width,height" in some kernels, or just the
            # stride.  Try reading the resolution from the bits_per_pixel
            # and stride files instead.
            pass

        # Try FBIOGET_VSCREENINFO ioctl for reliable dimensions
        try:
            self._width, self._height = self._get_fb_dimensions(str(device))
        except Exception:
            log.warning(
                "Could not read framebuffer dimensions via ioctl, "
                "assuming %dx%d", self._width, self._height
            )

        self._fb = open(str(device), "wb")
        log.info(
            "Framebuffer backend initialized: %s (%dx%d, RGB565)",
            self._device_path, self._width, self._height,
        )

    @staticmethod
    def _get_fb_dimensions(device_path: str) -> tuple[int, int]:
        """Read framebuffer dimensions via FBIOGET_VSCREENINFO ioctl.

        The ioctl returns a fb_var_screeninfo struct.  We only need the
        first two uint32 fields: xres and yres.
        """
        import fcntl

        FBIOGET_VSCREENINFO = 0x4600
        # fb_var_screeninfo is 160 bytes; xres and yres are the first two uint32s
        buf = bytearray(160)

        with open(device_path, "rb") as fb:
            fcntl.ioctl(fb.fileno(), FBIOGET_VSCREENINFO, buf)

        xres, yres = struct.unpack("II", buf[:8])
        return xres, yres

    def push_frame(self, image: Image.Image) -> None:
        if self._fb is None:
            return

        # Resize if the image doesn't match the framebuffer dimensions
        if image.size != (self._width, self._height):
            image = image.resize((self._width, self._height), Image.LANCZOS)

        rgb565 = _pil_to_rgb565(image)

        try:
            self._fb.seek(0)
            self._fb.write(rgb565)
            self._fb.flush()
        except OSError as e:
            log.error("Failed to write to framebuffer: %s", e)

    def should_quit(self) -> bool:
        return False

    def cleanup(self) -> None:
        if self._fb is not None:
            try:
                self._fb.close()
            except OSError:
                pass
            self._fb = None
            log.info("Framebuffer device closed")
