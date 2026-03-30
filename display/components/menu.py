"""Settings menu overlay for single-button device.

Menu items: Agent, Character, Setup, Brightness, Volume, Battery, Update, About, Close.
Sub-screens: agent selection, character selection, brightness/volume sliders,
battery status, update check, about info.

Navigation (single button, no touch screen):
  Tap (<0.4s)     = move cursor down (next item)
  Hold (0.4-1s)   = move cursor up (previous item)
  Long hold (>1s) = select / enter sub-screen
  Double-tap      = back / close menu
"""

from __future__ import annotations

import time

from PIL import ImageDraw

from display.fonts import get_font, text_width, wrap_text
from display.state import DisplayState
from display.characters import character_names

# ── Colors (all RGB — no alpha, pre-blended against dark bg) ────────────────

PANEL_BG = (16, 16, 24)
CYAN = (0, 212, 210)
CYAN_DIM = (0, 100, 96)
HIGHLIGHT_BG = (18, 30, 30)
FLASH_BG = (0, 60, 58)
ACTIVE_BAR = (0, 160, 158)
TEXT = (160, 160, 180)
TEXT_BRIGHT = (220, 220, 240)
TEXT_DIM = (100, 100, 128)
DIVIDER = (40, 40, 60)
GREEN = (52, 211, 81)
ORANGE = (255, 119, 0)
RED = (255, 60, 60)

# ── Font sizes ──────────────────────────────────────────────────────────────

FONT_TITLE = 16       # section titles
FONT_ITEM = 16        # menu item labels
FONT_ICON = 14        # item icons
FONT_HINT = 13        # bottom hint bar
FONT_VALUE = 22       # large value display (slider, battery)

# ── Layout ──────────────────────────────────────────────────────────────────

SCREEN_W = 240
SCREEN_H = 280
HINT_H = 28           # bottom hint bar height
HINT_Y = SCREEN_H - HINT_H
ITEM_H = 34           # menu row height
LIST_TOP = 36         # below title + divider
MAX_LABEL_W = 170     # max width before text scrolls

# Scroll speed for long labels (pixels per second)
SCROLL_SPEED = 30

# ── Menu structure ──────────────────────────────────────────────────────────

MENU_ITEMS = [
    ("agent", ">", "Agent"),
    ("character", "#", "Character"),
    ("accent", "~", "Accent Color"),
    ("setup", "@", "Setup"),
    ("brightness", "*", "Brightness"),
    ("volume", ")", "Volume"),
    ("battery", "%", "Battery"),
    ("update", "^", "Update"),
    ("about", "i", "About"),
    ("reboot", "!", "Reboot"),
    ("close", "x", "Close"),
]

ACCENT_PRESETS = [
    ("#00d4d2", "Cyan"),
    ("#00e080", "Green"),
    ("#6090ff", "Blue"),
    ("#c060ff", "Purple"),
    ("#ff6080", "Pink"),
    ("#ffa030", "Orange"),
    ("#ffdd40", "Yellow"),
    ("#f0f0f0", "White"),
]

AGENTS = [
    ("daemon", "Daemon", "Lead agent"),
    ("soren", "Soren", "Architect"),
    ("ash", "Ash", "Builder"),
    ("mira", "Mira", "Operator"),
    ("jace", "Jace", "Flex agent"),
    ("pip", "Pip", "Intern"),
]

# ── Button actions (single source of truth for hint text) ───────────────────
# Timings must match display/service.py thresholds:
#   Tap:    <0.4s (instant in menu)    Hold: 0.4-0.7s    Long: >0.7s
#   Double-tap: two taps within 0.4s   Sleep: >5s        Shutdown: >10s

BUTTON_ACTIONS = {
    "list": {
        "tap": "next",
        "hold": "prev",
        "long": "select",
        "2x": "back",
    },
    "slider": {
        "tap": "+5",
        "hold": "-5",
        "2x": "back",
    },
    "info": {
        "long": "back",
        "2x": "back",
    },
}


def _hint_from_actions(context: str) -> str:
    """Build hint string from button action mapping."""
    actions = BUTTON_ACTIONS.get(context, {})
    parts = []
    for btn, action in actions.items():
        parts.append(f"{btn}={action}")
    return "  ".join(parts)


HINT_LIST = _hint_from_actions("list")
HINT_SLIDER = _hint_from_actions("slider")
HINT_INFO = _hint_from_actions("info")


# ── Menu state ──────────────────────────────────────────────────────────────

class MenuState:
    """Tracks menu navigation state."""

    def __init__(self) -> None:
        self.open: bool = False
        self.cursor: int = 0
        self.sub_screen: str = ""
        self.agent_cursor: int = 0
        self.character_cursor: int = 0
        self.accent_cursor: int = 0
        self._select_flash_idx: int = -1
        self._select_flash_time: float = 0.0
        self._reboot_confirmed: bool = False

    def navigate(self, direction: int) -> None:
        if self.sub_screen == "agent":
            self.agent_cursor = (self.agent_cursor + direction) % len(AGENTS)
        elif self.sub_screen == "character":
            names = character_names()
            self.character_cursor = (self.character_cursor + direction) % len(names)
        elif self.sub_screen == "accent":
            self.accent_cursor = (self.accent_cursor + direction) % len(ACCENT_PRESETS)
        elif self.sub_screen in ("brightness", "volume"):
            pass
        elif not self.sub_screen:
            self.cursor = (self.cursor + direction) % len(MENU_ITEMS)

    def is_select_flashing(self, idx: int) -> bool:
        if idx != self._select_flash_idx:
            return False
        return (time.time() - self._select_flash_time) < 0.15

    def select(self, state: DisplayState) -> None:
        if self.sub_screen == "agent":
            self._select_flash_idx = self.agent_cursor
            self._select_flash_time = time.time()
            state.agent = AGENTS[self.agent_cursor][0]
            self.sub_screen = ""
        elif self.sub_screen == "character":
            self._select_flash_idx = self.character_cursor
            self._select_flash_time = time.time()
            names = character_names()
            state.character = names[self.character_cursor]
            self.sub_screen = ""
        elif self.sub_screen == "accent":
            self._select_flash_idx = self.accent_cursor
            self._select_flash_time = time.time()
            state.accent_color = ACCENT_PRESETS[self.accent_cursor][0]
            self.sub_screen = ""
        elif self.sub_screen == "reboot":
            self._reboot_confirmed = True
            self.sub_screen = ""
            self.open = False
        elif self.sub_screen:
            self.sub_screen = ""
        else:
            self._select_flash_idx = self.cursor
            self._select_flash_time = time.time()
            item_id = MENU_ITEMS[self.cursor][0]
            if item_id == "close":
                self.open = False
            else:
                self.sub_screen = item_id
                self._sync_cursor_to_selection(state)

    def back(self) -> None:
        if self.sub_screen:
            self.sub_screen = ""
        else:
            self.open = False

    def _sync_cursor_to_selection(self, state: DisplayState) -> None:
        if self.sub_screen == "agent":
            for i, (agent_id, _, _) in enumerate(AGENTS):
                if agent_id == state.agent:
                    self.agent_cursor = i
                    break
        elif self.sub_screen == "character":
            names = character_names()
            for i, name in enumerate(names):
                if name == state.character:
                    self.character_cursor = i
                    break
        elif self.sub_screen == "accent":
            for i, (hex_val, _) in enumerate(ACCENT_PRESETS):
                if hex_val == state.accent_color:
                    self.accent_cursor = i
                    break

    def adjust(self, state: DisplayState, delta: int) -> None:
        if self.sub_screen == "brightness":
            state.brightness = max(0, min(100, state.brightness + delta))
        elif self.sub_screen == "volume":
            state.volume = max(0, min(100, state.volume + delta))


# ── Drawing ─────────────────────────────────────────────────────────────────

def draw_menu(draw: ImageDraw.ImageDraw, state: DisplayState,
              menu: MenuState) -> None:
    if not menu.open:
        return

    font = get_font(FONT_ITEM)
    font_sm = get_font(FONT_ICON)
    font_lg = get_font(FONT_VALUE)

    # Full background
    draw.rectangle([0, 0, SCREEN_W - 1, SCREEN_H - 1], fill=PANEL_BG)

    if menu.sub_screen == "agent":
        _draw_agent_screen(draw, state, menu, font, font_sm)
    elif menu.sub_screen == "character":
        _draw_character_screen(draw, state, menu, font, font_sm)
    elif menu.sub_screen == "accent":
        _draw_accent_screen(draw, state, menu, font, font_sm)
    elif menu.sub_screen == "setup":
        pass  # Drawn by renderer using QR overlay
    elif menu.sub_screen == "brightness":
        warn = "Below 100% may flicker (SW PWM)" if state.brightness < 100 else ""
        _draw_slider_screen(draw, "BRIGHTNESS", state.brightness, font, font_sm, font_lg, warning=warn)
    elif menu.sub_screen == "volume":
        _draw_slider_screen(draw, "VOLUME", state.volume, font, font_sm, font_lg)
    elif menu.sub_screen == "battery":
        _draw_battery_screen(draw, state, font, font_sm, font_lg)
    elif menu.sub_screen == "update":
        _draw_update_screen(draw, state, font, font_sm, font_lg)
    elif menu.sub_screen == "about":
        _draw_about_screen(draw, font, font_sm)
    elif menu.sub_screen == "reboot":
        _draw_reboot_screen(draw, state, font, font_sm, font_lg)
    else:
        _draw_main_menu(draw, menu, font, font_sm)


def _draw_hint_bar(draw: ImageDraw.ImageDraw, hint: str) -> None:
    """Draw the bottom hint bar with separator."""
    font = get_font(FONT_HINT)
    draw.line([(10, HINT_Y), (SCREEN_W - 10, HINT_Y)], fill=DIVIDER, width=1)
    tw = text_width(font, hint)
    # Center the hint text
    x = max(10, (SCREEN_W - tw) // 2)
    draw.text((x, HINT_Y + 6), hint, fill=TEXT_DIM, font=font)


def _draw_title(draw: ImageDraw.ImageDraw, title: str) -> None:
    """Draw a screen title with underline."""
    font = get_font(FONT_TITLE)
    draw.text((20, 10), title, fill=CYAN, font=font)
    draw.line([(20, 30), (220, 30)], fill=DIVIDER, width=1)


def _scrolled_text(draw: ImageDraw.ImageDraw, x: int, y: int,
                   label: str, max_w: int, color: tuple, font) -> None:
    """Draw text, scrolling horizontally if it exceeds max_w."""
    tw = text_width(font, label)
    if tw <= max_w:
        draw.text((x, y), label, fill=color, font=font)
        return

    # Scroll: ping-pong based on time
    overflow = tw - max_w
    t = time.time()
    # Scroll cycle: 1px per (1/SCROLL_SPEED)s, pause 1s at each end
    cycle_time = overflow / SCROLL_SPEED + 2.0  # scroll time + 2x 1s pause
    phase = t % (cycle_time * 2)  # full ping-pong cycle

    if phase < 1.0:
        offset = 0  # pause at start
    elif phase < 1.0 + overflow / SCROLL_SPEED:
        offset = int((phase - 1.0) * SCROLL_SPEED)  # scroll right
    elif phase < cycle_time:
        offset = overflow  # pause at end
    elif phase < cycle_time + 1.0:
        offset = overflow  # pause at end (reverse)
    elif phase < cycle_time + 1.0 + overflow / SCROLL_SPEED:
        offset = overflow - int((phase - cycle_time - 1.0) * SCROLL_SPEED)
    else:
        offset = 0

    offset = max(0, min(offset, overflow))
    draw.text((x - offset, y), label, fill=color, font=font)


def _draw_scrollable_list(draw: ImageDraw.ImageDraw, title: str,
                          items: list[tuple[str, str, str]],
                          cursor: int, selected_fn,
                          font, font_sm,
                          hint: str = HINT_LIST,
                          menu: MenuState | None = None) -> None:
    """Generic scrollable list with title, auto-scroll to keep cursor visible."""
    _draw_title(draw, title)

    visible_h = HINT_Y - LIST_TOP
    max_visible = visible_h // ITEM_H

    # Calculate scroll offset to keep cursor visible
    scroll = 0
    if len(items) > max_visible:
        scroll = max(0, min(cursor - max_visible // 2, len(items) - max_visible))

    for idx in range(scroll, min(scroll + max_visible, len(items))):
        item_id, icon, label = items[idx]
        active = idx == cursor
        selected = selected_fn(item_id)
        iy = LIST_TOP + (idx - scroll) * ITEM_H

        flashing = menu is not None and menu.is_select_flashing(idx)

        if active or flashing:
            bg = FLASH_BG if flashing else HIGHLIGHT_BG
            draw.rectangle([10, iy, 230, iy + ITEM_H - 2], fill=bg)
            draw.rectangle([6, iy + 6, 9, iy + ITEM_H - 8], fill=CYAN)

        color = CYAN if active else TEXT
        icon_color = CYAN if active else CYAN_DIM

        draw.text((18, iy + 9), icon, fill=icon_color, font=font_sm)

        # Scroll long labels only for the active item
        if active:
            _scrolled_text(draw, 38, iy + 7, label, MAX_LABEL_W, color, font)
        else:
            # Truncate for non-active items
            tw = text_width(font, label)
            if tw > MAX_LABEL_W:
                # Truncate with ellipsis
                truncated = label
                while text_width(font, truncated + "..") > MAX_LABEL_W and len(truncated) > 1:
                    truncated = truncated[:-1]
                draw.text((38, iy + 7), truncated + "..", fill=color, font=font)
            else:
                draw.text((38, iy + 7), label, fill=color, font=font)

        if selected:
            draw.ellipse([218, iy + ITEM_H // 2 - 4, 226, iy + ITEM_H // 2 + 4], fill=CYAN)

    # Scroll indicators
    if scroll > 0:
        draw.text((116, LIST_TOP - 4), "^", fill=CYAN_DIM, font=font_sm)
    if scroll + max_visible < len(items):
        draw.text((116, HINT_Y - 14), "v", fill=CYAN_DIM, font=font_sm)

    _draw_hint_bar(draw, hint)


def _draw_main_menu(draw: ImageDraw.ImageDraw, menu: MenuState,
                    font, font_sm) -> None:
    items = [(id, icon, label) for id, icon, label in MENU_ITEMS]
    _draw_scrollable_list(
        draw, "SETTINGS", items, menu.cursor,
        selected_fn=lambda _: False,
        font=font, font_sm=font_sm,
        menu=menu,
    )


def _draw_agent_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                       menu: MenuState, font, font_sm) -> None:
    items = [(a[0], ">", f"{a[1]} - {a[2]}") for a in AGENTS]
    _draw_scrollable_list(
        draw, "AGENT", items, menu.agent_cursor,
        selected_fn=lambda id: id == state.agent,
        font=font, font_sm=font_sm,
        menu=menu,
    )


CHARACTER_DESCRIPTIONS = {
    "voxel": "Voxel — expressive eyes",
    "cube": "Cube — isometric mascot",
    "bmo": "BMO — face (full screen)",
    "bmo-full": "BMO — body + controls",
}


def _draw_character_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                           menu: MenuState, font, font_sm) -> None:
    names = character_names()
    items = [(n, "#", CHARACTER_DESCRIPTIONS.get(n, n)) for n in names]
    _draw_scrollable_list(
        draw, "CHARACTER", items, menu.character_cursor,
        selected_fn=lambda id: id == state.character,
        font=font, font_sm=font_sm,
        menu=menu,
    )


def _draw_accent_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                        menu: MenuState, font, font_sm) -> None:
    """Draw accent color preset picker with color swatches."""
    _draw_title(draw, "ACCENT COLOR")

    y = 44
    for i, (hex_val, name) in enumerate(ACCENT_PRESETS):
        is_cursor = i == menu.accent_cursor
        is_selected = hex_val == state.accent_color
        item_y = y + i * 26

        # Parse hex to RGB for swatch
        h = hex_val.lstrip("#")
        rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

        # Highlight cursor row
        if is_cursor:
            draw.rectangle([4, item_y - 2, SCREEN_W - 5, item_y + 22], fill=(24, 24, 40))

        # Color swatch (circle)
        sw_x = 20
        sw_y = item_y + 10
        sw_r = 8
        draw.ellipse([sw_x - sw_r, sw_y - sw_r, sw_x + sw_r, sw_y + sw_r], fill=rgb)

        # Name
        name_color = rgb if is_cursor else (120, 120, 140)
        draw.text((38, item_y + 2), name, fill=name_color, font=font)

        # Checkmark if selected
        if is_selected:
            draw.text((SCREEN_W - 30, item_y + 2), "+", fill=rgb, font=font)

    _draw_hint_bar(draw, HINT_LIST)


def _draw_slider_screen(draw: ImageDraw.ImageDraw, title: str, value: int,
                        font, font_sm, font_lg,
                        warning: str = "") -> None:
    _draw_title(draw, title)

    # Value display
    val_text = f"{value}%"
    tw = text_width(font_lg, val_text)
    draw.text(((SCREEN_W - tw) // 2, 50), val_text, fill=CYAN, font=font_lg)

    # Slider track
    track_x, track_w, track_y, track_h = 20, 200, 100, 12
    draw.rounded_rectangle(
        [track_x, track_y, track_x + track_w, track_y + track_h],
        radius=5, fill=(30, 30, 50), outline=CYAN_DIM,
    )

    # Slider fill
    fill_w = int(track_w * value / 100)
    if fill_w > 2:
        draw.rounded_rectangle(
            [track_x, track_y, track_x + fill_w, track_y + track_h],
            radius=5, fill=CYAN,
        )

    # Warning text
    if warning:
        warn_font = get_font(13)
        lines = wrap_text(warn_font, warning, 200)
        wy = 124
        for line in lines:
            draw.text((20, wy), line, fill=ORANGE, font=warn_font)
            wy += 18

    _draw_hint_bar(draw, HINT_SLIDER)


def _draw_battery_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                         font, font_sm, font_lg) -> None:
    _draw_title(draw, "BATTERY")

    bat = state.battery
    if bat <= 10:
        color = RED
        msg = "Critical - charge soon!"
    elif bat <= 30:
        color = ORANGE
        msg = "Low battery"
    elif bat <= 60:
        color = CYAN
        msg = "Good"
    else:
        color = GREEN
        msg = "Fully charged" if bat >= 95 else "Healthy"

    val_text = f"{bat}%"
    tw = text_width(font_lg, val_text)
    draw.text(((SCREEN_W - tw) // 2, 70), val_text, fill=color, font=font_lg)

    mw = text_width(font, msg)
    draw.text(((SCREEN_W - mw) // 2, 110), msg, fill=TEXT, font=font)

    # Battery bar
    bar_x, bar_w, bar_y, bar_h = 40, 160, 150, 14
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
        radius=5, fill=(30, 30, 50), outline=DIVIDER,
    )
    fill_w = int(bar_w * bat / 100)
    if fill_w > 2:
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
            radius=5, fill=color,
        )

    _draw_hint_bar(draw, HINT_INFO)


def _draw_update_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                        font, font_sm, font_lg) -> None:
    _draw_title(draw, "UPDATE")

    if not state.update_checking and not state.update_available:
        state.update_checking = True

    y = 48

    try:
        from display.updater import get_current_version
        version = get_current_version()
    except Exception:
        version = "unknown"

    draw.text((20, y), f"Version: {version}", fill=TEXT, font=font)
    y += 28

    if state.update_checking:
        draw.text((20, y), "Checking for updates...", fill=CYAN, font=font)
    elif state.update_available:
        draw.text((20, y), "Update available!", fill=GREEN, font=font)
        y += 24
        draw.text((20, y), f"{state.update_behind} commit{'s' if state.update_behind != 1 else ''} behind",
                  fill=TEXT, font=font_sm)
        y += 20
        draw.text((20, y), "Use web UI to install", fill=TEXT_DIM, font=font_sm)
    else:
        draw.text((20, y), "Up to date", fill=GREEN, font=font)

    _draw_hint_bar(draw, HINT_INFO)


def _draw_about_screen(draw: ImageDraw.ImageDraw, font, font_sm) -> None:
    _draw_title(draw, "ABOUT")

    font_lg = get_font(20)
    font_info = get_font(FONT_HINT)

    # Title block
    y = 40
    title = "Voxel Relay"
    tw = text_width(font_lg, title)
    draw.text(((SCREEN_W - tw) // 2, y), title, fill=CYAN, font=font_lg)
    y += 24

    try:
        from display.updater import get_current_version
        version = get_current_version()
    except Exception:
        version = "0.1.0"
    vtxt = f"v{version}"
    vw = text_width(font_info, vtxt)
    draw.text(((SCREEN_W - vw) // 2, y), vtxt, fill=TEXT_DIM, font=font_info)
    y += 26

    # Info rows with icons
    rows = [
        (_icon_cpu, "Pi Zero 2W", TEXT),
        (_icon_board, "Whisplay HAT", TEXT),
        (_icon_display, "240 x 280 IPS", TEXT_DIM),
        (_icon_github, "Codename-11/voxel", CYAN_DIM),
        (_icon_web, "axiom-labs.ai", CYAN_DIM),
    ]

    for icon_fn, label, color in rows:
        icon_fn(draw, 24, y + 4, CYAN_DIM)
        draw.text((42, y), label, fill=color, font=font_info)
        y += 24

    _draw_hint_bar(draw, HINT_INFO)


def _icon_cpu(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    """CPU/chip icon (10x10)."""
    draw.rectangle([x + 2, y + 2, x + 8, y + 8], outline=color)
    draw.line([(x + 4, y), (x + 4, y + 2)], fill=color)
    draw.line([(x + 6, y), (x + 6, y + 2)], fill=color)
    draw.line([(x + 4, y + 8), (x + 4, y + 10)], fill=color)
    draw.line([(x + 6, y + 8), (x + 6, y + 10)], fill=color)
    draw.line([(x, y + 4), (x + 2, y + 4)], fill=color)
    draw.line([(x, y + 6), (x + 2, y + 6)], fill=color)
    draw.line([(x + 8, y + 4), (x + 10, y + 4)], fill=color)
    draw.line([(x + 8, y + 6), (x + 10, y + 6)], fill=color)


def _icon_board(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    """Circuit board icon (10x10)."""
    draw.rounded_rectangle([x, y, x + 10, y + 10], radius=2, outline=color)
    draw.ellipse([x + 3, y + 3, x + 5, y + 5], fill=color)
    draw.ellipse([x + 6, y + 6, x + 8, y + 8], fill=color)


def _icon_display(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    """Monitor/display icon (10x10)."""
    draw.rounded_rectangle([x, y, x + 10, y + 7], radius=1, outline=color)
    draw.line([(x + 5, y + 7), (x + 5, y + 9)], fill=color)
    draw.line([(x + 3, y + 9), (x + 7, y + 9)], fill=color)


def _icon_github(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    """Git branch icon (10x10)."""
    draw.line([(x + 3, y), (x + 3, y + 10)], fill=color)
    draw.line([(x + 7, y + 2), (x + 7, y + 5)], fill=color)
    draw.line([(x + 7, y + 5), (x + 3, y + 7)], fill=color)
    draw.ellipse([x + 2, y, x + 4, y + 2], fill=color)
    draw.ellipse([x + 6, y + 1, x + 8, y + 3], fill=color)
    draw.ellipse([x + 2, y + 8, x + 4, y + 10], fill=color)


def _draw_reboot_screen(draw: ImageDraw.ImageDraw, state: DisplayState,
                        font, font_sm, font_lg) -> None:
    """Draw reboot confirmation screen."""
    _draw_title(draw, "REBOOT")

    y = 60
    icon_text = "!"
    iw = text_width(font_lg, icon_text)
    draw.text(((SCREEN_W - iw) // 2, y), icon_text, fill=ORANGE, font=font_lg)
    y += 36

    msg = "Reboot device?"
    mw = text_width(font, msg)
    draw.text(((SCREEN_W - mw) // 2, y), msg, fill=TEXT_BRIGHT, font=font)
    y += 28

    hint_msg = "Display will go dark"
    hw = text_width(font_sm, hint_msg)
    draw.text(((SCREEN_W - hw) // 2, y), hint_msg, fill=TEXT_DIM, font=font_sm)
    y += 16

    hint_msg2 = "for ~30 seconds"
    hw2 = text_width(font_sm, hint_msg2)
    draw.text(((SCREEN_W - hw2) // 2, y), hint_msg2, fill=TEXT_DIM, font=font_sm)
    y += 36

    confirm_text = "Hold to confirm"
    cw = text_width(font_sm, confirm_text)
    draw.text(((SCREEN_W - cw) // 2, y), confirm_text, fill=ORANGE, font=font_sm)

    _draw_hint_bar(draw, "long=confirm  2x=back")


def _icon_web(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    """Globe icon (10x10)."""
    draw.ellipse([x, y, x + 10, y + 10], outline=color)
    draw.line([(x, y + 5), (x + 10, y + 5)], fill=color)
    draw.arc([x + 2, y, x + 8, y + 10], start=0, end=360, fill=color)
