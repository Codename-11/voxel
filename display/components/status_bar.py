"""Status bar — compact single-line bar for 240x280 LCD.

Layout: Agent  State·icon  Battery% ●wifi
Single line at 24px keeps the face area large. Content padded to
stay inside the 40px corner bevel at the top of the screen.
"""

from __future__ import annotations

import math

from PIL import ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W
from display.state import DisplayState

HEIGHT = 60
PAD = 26          # horizontal inset (inside corner bevel)
BG = (16, 16, 24)
TEXT_COLOR = (160, 160, 180)
TEXT_DIM = (80, 80, 100)
CYAN = (0, 212, 210)
GREEN = (52, 211, 81)
RED = (255, 60, 60)
ORANGE = (255, 119, 0)
DIVIDER = (40, 40, 60)

AGENT_NAMES = {
    "daemon": "Daemon",
    "soren": "Soren",
    "ash": "Ash",
    "mira": "Mira",
    "jace": "Jace",
    "pip": "Pip",
}

# State: (short label, color, has_icon)
STATE_INFO = {
    "IDLE": ("Idle", TEXT_DIM, False),
    "LISTENING": ("Listening", CYAN, True),
    "THINKING": ("Thinking", CYAN, True),
    "SPEAKING": ("Speaking", CYAN, True),
    "ERROR": ("Error", RED, False),
    "SLEEPING": ("Sleep", TEXT_DIM, False),
    "MENU": ("Menu", TEXT_DIM, False),
}


def _draw_wifi_icon(draw: ImageDraw.ImageDraw, x: int, y: int,
                    connected: bool) -> None:
    """Draw a wifi icon. (x, y) is top-left of a ~16x16 box."""
    color = GREEN if connected else TEXT_DIM
    cx = x + 8
    base_y = y + 14
    # Base dot
    draw.ellipse([cx - 1, base_y - 1, cx + 1, base_y + 1], fill=color)
    # Three arcs
    for r in (4, 7, 10):
        bbox = [cx - r, base_y - r, cx + r, base_y + r]
        draw.arc(bbox, start=225, end=315, fill=color, width=1)
    if not connected:
        draw.line([(cx - 6, y + 2), (cx + 6, base_y)], fill=RED, width=2)


def _draw_state_icon(draw: ImageDraw.ImageDraw, x: int, y: int,
                     state_name: str, time: float) -> int:
    """Draw a state indicator icon. Returns width consumed."""
    if state_name == "LISTENING":
        # Mic: vertical stem + arcs
        mx = x + 7
        my = y + 8
        draw.line([(mx, my - 6), (mx, my + 4)], fill=CYAN, width=3)
        draw.line([(mx - 4, my - 2), (mx - 4, my + 2)], fill=CYAN, width=2)
        draw.line([(mx + 4, my - 2), (mx + 4, my + 2)], fill=CYAN, width=2)
        draw.line([(mx - 3, my + 6), (mx + 3, my + 6)], fill=CYAN, width=2)
        return 18

    elif state_name == "SPEAKING":
        # Three animated bars
        bar_base = y + 18
        for i in range(3):
            phase = time * 4.0 + i * 1.2
            h = 4 + int(abs(math.sin(phase)) * 8)
            bx = x + i * 6
            draw.line([(bx, bar_base - h), (bx, bar_base)], fill=CYAN, width=3)
        return 20

    elif state_name == "THINKING":
        # Animated dots
        n = int(time * 2) % 4
        dots = "." * max(1, n)
        f = get_font(13)
        draw.text((x, y), dots, fill=CYAN, font=f)
        return text_width(f, "...") + 2

    return 0


def draw_status_bar(draw: ImageDraw.ImageDraw, state: DisplayState,
                    font=None, config: dict | None = None) -> None:
    """Draw a single-line status bar in the top 48px."""
    f = get_font(18)
    f_sm = get_font(14)

    # Background
    draw.rectangle([0, 0, SCREEN_W - 1, HEIGHT - 1], fill=BG)

    y = 12  # vertically center text in 48px bar

    # ── Left: Agent name ──
    agent_name = AGENT_NAMES.get(state.agent, state.agent.capitalize())
    draw.text((PAD, y), agent_name, fill=CYAN, font=f)

    # Dev mode indicator (after agent name)
    if state.dev_mode:
        dx = PAD + text_width(f, agent_name) + 4
        draw.text((dx, y + 1), "D", fill=ORANGE, font=f_sm)

    # ── Center: State icon only for active states (no text — face shows state) ──
    _, label_color, has_icon = STATE_INFO.get(
        state.state, (state.state, TEXT_COLOR, False),
    )
    if has_icon:
        # Center the small icon between agent name and battery
        agent_w = text_width(f, agent_name) + PAD
        if state.dev_mode:
            agent_w += text_width(f_sm, "D") + 4
        left_edge = agent_w + 6
        right_edge = SCREEN_W - PAD - 60
        icon_w = 20
        cx = max(left_edge, (left_edge + right_edge - icon_w) // 2)
        _draw_state_icon(draw, cx, y, state.state, state.time)

    # ── Right: battery + wifi icon (flush together) ──
    bat = state.battery
    if bat <= 10:
        bat_color = RED
    elif bat <= 30:
        bat_color = ORANGE
    else:
        bat_color = GREEN

    bat_text = f"{bat}%"
    btw = text_width(f, bat_text)

    # Position: battery text then wifi icon directly after, anchored to right edge
    wifi_w = 18  # wifi icon width
    total_w = btw + 4 + wifi_w  # battery + gap + wifi
    rx = SCREEN_W - PAD - total_w

    # Update indicator (before battery if present)
    if state.update_available:
        draw.text((rx - 10, y + 1), "^", fill=CYAN, font=f_sm)

    draw.text((rx, y), bat_text, fill=bat_color, font=f)
    _draw_wifi_icon(draw, rx + btw + 3, y, state.wifi_connected)

    # Bottom divider
    draw.line([(0, HEIGHT - 1), (SCREEN_W - 1, HEIGHT - 1)], fill=DIVIDER, width=1)
