"""Device status decorative overlays — connection and battery events.

Renders independently from mood decorations (display/decorations.py) so
both can show simultaneously.  Uses STATUS_ICON_Y (below ICON_Y) to
avoid visual collision with mood decorations.
"""

from __future__ import annotations

import math
from PIL import Image, ImageDraw
from display.layout import SCREEN_W, STATUS_ICON_Y
from display.overlay import color_with_alpha as _color_with_alpha, draw_on_overlay as _draw_on_overlay

# ── Constants ──────────────────────────────────────────────────────────────

# Duration (seconds) that transient connection events stay visible
_CONNECTED_DURATION = 2.0
_DISCONNECTED_DURATION = 3.0

# Colors
_COLOR_CONNECTED = (64, 255, 120)
_COLOR_DISCONNECTED = (255, 80, 60)
_COLOR_LOW_BATTERY = (212, 160, 32)
_COLOR_CRITICAL_BATTERY = (255, 60, 60)

# Battery icon geometry
_BAT_W = 24
_BAT_H = 14
_BAT_NUB_W = 3
_BAT_NUB_H = 6


# ── Connected: ascending WiFi arcs + checkmark ────────────────────────────

def _draw_connected(img: Image.Image, now: float, event_time: float) -> None:
    """Three expanding WiFi arcs in green with a brief checkmark, fading out."""
    elapsed = now - event_time
    if elapsed < 0 or elapsed > _CONNECTED_DURATION:
        return

    t = elapsed / _CONNECTED_DURATION

    # Fade out in the last 30% of the duration
    if t > 0.7:
        master_alpha = 1.0 - (t - 0.7) / 0.3
    else:
        master_alpha = 1.0

    cx = SCREEN_W // 2
    cy = STATUS_ICON_Y

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        # Three concentric arcs expanding outward
        for i in range(3):
            arc_delay = i * 0.12
            arc_t = max(0.0, min(1.0, (t - arc_delay) / 0.5))
            if arc_t <= 0:
                continue
            base_r = 8 + i * 7
            r = int(base_r * arc_t)
            if r < 2:
                continue
            arc_alpha = master_alpha * (0.5 + 0.5 * arc_t)
            color = _color_with_alpha(_COLOR_CONNECTED, arc_alpha * 0.85)
            bbox = [cx - r, cy - r, cx + r, cy + r]
            od.arc(bbox, start=-150, end=-30, fill=color, width=2)

        # Small dot at the base of the arcs
        dot_alpha = master_alpha * min(1.0, t / 0.15)
        dot_color = _color_with_alpha(_COLOR_CONNECTED, dot_alpha * 0.9)
        od.ellipse([cx - 2, cy + 2, cx + 2, cy + 6], fill=dot_color)

        # Checkmark appears after arcs have expanded (t > 0.35)
        if t > 0.35:
            check_t = min(1.0, (t - 0.35) / 0.2)
            check_alpha = master_alpha * check_t
            check_color = _color_with_alpha(_COLOR_CONNECTED, check_alpha * 0.95)
            check_y = cy + 14
            check_x = cx - 6
            od.line(
                [(check_x, check_y), (check_x + 4, check_y + 4),
                 (check_x + 12, check_y - 4)],
                fill=check_color, width=2,
            )

    _draw_on_overlay(img, _overlay)


# ── Disconnected: WiFi icon with red X slash ──────────────────────────────

def _draw_disconnected(img: Image.Image, now: float, event_time: float) -> None:
    """WiFi arcs in red with an X slash through them, fading out."""
    elapsed = now - event_time
    if elapsed < 0 or elapsed > _DISCONNECTED_DURATION:
        return

    t = elapsed / _DISCONNECTED_DURATION

    if t > 0.7:
        master_alpha = 1.0 - (t - 0.7) / 0.3
    else:
        master_alpha = 1.0

    cx = SCREEN_W // 2
    cy = STATUS_ICON_Y

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        # Static WiFi arcs in red (dimmed)
        for i in range(3):
            r = 8 + i * 7
            arc_alpha = master_alpha * 0.55
            color = _color_with_alpha(_COLOR_DISCONNECTED, arc_alpha)
            bbox = [cx - r, cy - r, cx + r, cy + r]
            od.arc(bbox, start=-150, end=-30, fill=color, width=2)

        # Base dot
        dot_color = _color_with_alpha(_COLOR_DISCONNECTED, master_alpha * 0.7)
        od.ellipse([cx - 2, cy + 2, cx + 2, cy + 6], fill=dot_color)

        # Red X slash over the icon
        x_alpha = master_alpha * 0.95
        x_color = _color_with_alpha(_COLOR_DISCONNECTED, x_alpha)
        s = 10
        od.line([(cx - s, cy - s), (cx + s, cy + s)], fill=x_color, width=2)
        od.line([(cx + s, cy - s), (cx - s, cy + s)], fill=x_color, width=2)

    _draw_on_overlay(img, _overlay)


# ── Low battery: amber battery with draining fill ─────────────────────────

def _draw_low_battery(img: Image.Image, now: float) -> None:
    """Battery outline in amber/gold with an animated draining fill bar."""
    cx = SCREEN_W // 2
    cy = STATUS_ICON_Y

    bx = cx - _BAT_W // 2
    by = cy - _BAT_H // 2

    # Drain animation: fill oscillates between ~15% and ~45%
    cycle = 3.0
    phase = (now % cycle) / cycle
    fill_frac = 0.15 + 0.30 * (0.5 + 0.5 * math.sin(phase * math.pi * 2))

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        outline_color = _color_with_alpha(_COLOR_LOW_BATTERY, 0.85)
        od.rectangle([bx, by, bx + _BAT_W, by + _BAT_H], outline=outline_color, width=1)

        # Nub on right side
        nub_y = cy - _BAT_NUB_H // 2
        od.rectangle(
            [bx + _BAT_W, nub_y, bx + _BAT_W + _BAT_NUB_W, nub_y + _BAT_NUB_H],
            fill=outline_color,
        )

        # Fill bar inside (2px inset)
        inset = 2
        fill_max_w = _BAT_W - inset * 2
        fill_w = max(1, int(fill_max_w * fill_frac))
        fill_color = _color_with_alpha(_COLOR_LOW_BATTERY, 0.75)
        od.rectangle(
            [bx + inset, by + inset, bx + inset + fill_w, by + _BAT_H - inset],
            fill=fill_color,
        )

    _draw_on_overlay(img, _overlay)


# ── Critical battery: pulsing red battery, nearly empty ───────────────────

def _draw_critical_battery(img: Image.Image, now: float) -> None:
    """Battery outline pulsing red with a tiny fill bar."""
    cx = SCREEN_W // 2
    cy = STATUS_ICON_Y

    bx = cx - _BAT_W // 2
    by = cy - _BAT_H // 2

    # Pulse alpha between 0.4 and 1.0
    pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(now * math.pi * 2))

    def _overlay(od: ImageDraw.ImageDraw, _oi: Image.Image) -> None:
        outline_color = _color_with_alpha(_COLOR_CRITICAL_BATTERY, pulse * 0.9)
        od.rectangle([bx, by, bx + _BAT_W, by + _BAT_H], outline=outline_color, width=1)

        nub_y = cy - _BAT_NUB_H // 2
        od.rectangle(
            [bx + _BAT_W, nub_y, bx + _BAT_W + _BAT_NUB_W, nub_y + _BAT_NUB_H],
            fill=outline_color,
        )

        # Tiny fill (~10%) — also pulses
        inset = 2
        fill_max_w = _BAT_W - inset * 2
        fill_w = max(1, int(fill_max_w * 0.10))
        fill_color = _color_with_alpha(_COLOR_CRITICAL_BATTERY, pulse * 0.8)
        od.rectangle(
            [bx + inset, by + inset, bx + inset + fill_w, by + _BAT_H - inset],
            fill=fill_color,
        )

    _draw_on_overlay(img, _overlay)


# ── Public API ─────────────────────────────────────────────────────────────

def draw_status_decorations(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    now: float,
    connection_event: str | None,
    connection_event_time: float,
    battery_warning: str | None,
) -> None:
    """Render device-status overlays on *img*.

    Connection events auto-expire after their display duration.
    Battery warnings render persistently while the flag is set.

    Args:
        draw: Main draw context (unused — drawing goes through overlays).
        img: RGBA frame to composite onto.
        now: Current time (same clock as connection_event_time).
        connection_event: "connected", "disconnected", or None.
        connection_event_time: Timestamp when the event was raised.
        battery_warning: "low_battery", "critical_battery", or None.
    """
    if connection_event == "connected":
        _draw_connected(img, now, connection_event_time)
    elif connection_event == "disconnected":
        _draw_disconnected(img, now, connection_event_time)

    if battery_warning == "low_battery":
        _draw_low_battery(img, now)
    elif battery_warning == "critical_battery":
        _draw_critical_battery(img, now)
