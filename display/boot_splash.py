"""Boot splash screen — retro terminal-style init sequence.

Shows a glowing "V O X E L" title with progressive status lines as each
subsystem initialises.  Works on both Pi (SPI backend) and desktop
(tkinter/pygame backend) — just pushes PIL frames via the backend.

Replaces the old ``scripts/boot_splash.py`` ExecStartPre approach by
running *inside* the display service so status lines reflect real init.
"""

from __future__ import annotations

import logging
import time

from PIL import Image, ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H

log = logging.getLogger("voxel.display.boot")

# ── Colour palette ────────────────────────────────────────────────────────

BG = (12, 12, 18)
CYAN = (0, 212, 210)
DIM = (100, 100, 120)
DIVIDER = (40, 40, 60)
VERSION_GRAY = (60, 60, 80)

STATUS_COLORS: dict[str, tuple[int, int, int]] = {
    "OK": (52, 211, 81),
    "SKIP": (255, 180, 0),
    "FAIL": (255, 60, 60),
    "...": CYAN,
}

# ── Fonts ─────────────────────────────────────────────────────────────────

TITLE_SIZE = 20
LINE_SIZE = 11
VERSION_SIZE = 11


class BootSplash:
    """Renders a retro terminal-style boot splash on the display backend.

    Usage::

        splash = BootSplash(backend)
        splash.show_title(version="0.1.0")   # push title frame
        splash.add_line("Display", "OK")      # push with first status line
        splash.add_line("Expressions", "OK")
        splash.add_line("Audio", "SKIP")
        splash.add_line("Gateway", "OK")
        splash.show_ready()                   # "Ready!" + 0.5s hold
    """

    def __init__(self, backend) -> None:
        self.backend = backend
        self.lines: list[tuple[str, str]] = []  # (label, status)
        self._version = ""

    # ── Public API ────────────────────────────────────────────────────────

    def show_title(self, version: str = "") -> None:
        """Render and push the title frame (no status lines yet)."""
        self._version = version
        self._push()
        log.info("Boot splash: title displayed")

    def add_line(self, label: str, status: str = "OK") -> None:
        """Append a status line and re-render.

        Args:
            label:  Subsystem name (e.g. "Display").
            status: One of "OK", "SKIP", "FAIL", "..." (in progress).
        """
        self.lines.append((label, status))
        self._push()
        log.info("Boot splash: %s  %s", label, status)

    def show_ready(self, hold: float = 0.5) -> None:
        """Show the final 'Ready!' line, hold, then return."""
        self.lines.append(("Ready!", ""))
        self._push()
        log.info("Boot splash: Ready!")
        time.sleep(hold)

    # ── Rendering ─────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        """Render current splash state to a 240x280 RGB PIL Image."""
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
        draw = ImageDraw.Draw(img)

        font_title = get_font(TITLE_SIZE)
        font_line = get_font(LINE_SIZE)
        font_ver = get_font(VERSION_SIZE)

        # ── Title: "V O X E L" ────────────────────────────────────────
        title = "V O X E L"
        tw = text_width(font_title, title)
        title_x = (SCREEN_W - tw) // 2
        title_y = 60

        # Glow effect — draw the title twice: a dim spread behind, then
        # the bright text on top.  PIL doesn't have blur, so we fake it
        # with slightly offset copies in a darker shade.
        glow = (0, 80, 78)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw.text((title_x + dx, title_y + dy), title,
                      fill=glow, font=font_title)
        draw.text((title_x, title_y), title, fill=CYAN, font=font_title)

        # ── Version ───────────────────────────────────────────────────
        if self._version:
            ver_text = f"v{self._version}"
            vw = text_width(font_ver, ver_text)
            draw.text(((SCREEN_W - vw) // 2, title_y + 28),
                      ver_text, fill=VERSION_GRAY, font=font_ver)

        # ── Divider line ──────────────────────────────────────────────
        divider_y = title_y + 48
        draw.line([(40, divider_y), (SCREEN_W - 40, divider_y)],
                  fill=DIVIDER, width=1)

        # ── Status lines ──────────────────────────────────────────────
        line_y = divider_y + 16
        line_height = 18
        left_x = 30

        for label, status in self.lines:
            if label == "Ready!":
                # Special: "Ready!" in cyan, centered
                ready_text = "> Ready!"
                rw = text_width(font_line, ready_text)
                draw.text(((SCREEN_W - rw) // 2, line_y),
                          ready_text, fill=CYAN, font=font_line)
            else:
                # Format: "> Label......  STATUS"
                prefix = f"> {label}"
                # Pad with dots to align status text
                max_label_w = 140  # pixels for label + dots
                dots = ""
                while text_width(font_line, prefix + dots) < max_label_w:
                    dots += "."
                # Trim one dot if we overshot
                while dots and text_width(font_line, prefix + dots) > max_label_w:
                    dots = dots[:-1]

                label_text = prefix + dots
                draw.text((left_x, line_y), label_text,
                          fill=DIM, font=font_line)

                # Status text — right-aligned after the dots
                if status:
                    status_color = STATUS_COLORS.get(status, DIM)
                    status_x = left_x + text_width(font_line, label_text) + 6
                    draw.text((status_x, line_y), status,
                              fill=status_color, font=font_line)

            line_y += line_height

        return img

    # ── Internal ──────────────────────────────────────────────────────────

    def _push(self) -> None:
        """Render and push the current frame to the backend."""
        img = self.render()
        self.backend.push_frame(img)
