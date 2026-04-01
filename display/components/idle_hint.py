"""Idle and chat view button hints — teach the single-button UX naturally.

IdleButtonHint: Shows "Hold to talk / Tap for more" on face view after
    prolonged idle. Fades in, holds, fades out. Limited show count
    persisted in .setup-state.

ChatEntryHint: Shows "Hold for settings" when switching to chat view.
    Fades in, holds, fades out. Limited show count persisted.

Both use background-blend color technique (no alpha compositing) for
performance on Pi Zero 2W.
"""

from __future__ import annotations

import time

from PIL import ImageDraw

from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Background color (must match face.py BG) ──────────────────────────────

BG = (10, 10, 15)

# ── Defaults ──────────────────────────────────────────────────────────────

DEFAULT_IDLE_DELAY = 45.0     # seconds of idle before hint shows
DEFAULT_IDLE_MAX = 5          # max times to show idle hint
DEFAULT_CHAT_MAX = 3          # max times to show chat hint


def _blend_color(fg: tuple, bg: tuple, alpha: float) -> tuple:
    """Blend foreground onto background using alpha (0=bg, 1=fg)."""
    alpha = max(0.0, min(1.0, alpha))
    return (
        int(fg[0] * alpha + bg[0] * (1 - alpha)),
        int(fg[1] * alpha + bg[1] * (1 - alpha)),
        int(fg[2] * alpha + bg[2] * (1 - alpha)),
    )


class IdleButtonHint:
    """Shows "Hold to talk / Tap for more" on face view after idle timeout.

    Lifecycle:
      - Waits for IDLE_DELAY seconds of idle on face view
      - Fades in (0.8s), holds (5s), fades out (0.8s)
      - Increments show count (persisted in .setup-state)
      - Resets on any button press, state change, or view change
      - Does not show when idle prompt "?" is visible or peek bubble active
    """

    FADE_IN = 0.8
    HOLD = 5.0
    FADE_OUT = 0.8

    def __init__(self, enabled: bool = True, max_shows: int = DEFAULT_IDLE_MAX,
                 idle_delay: float = DEFAULT_IDLE_DELAY) -> None:
        self._enabled = enabled
        self._max_shows = max_shows
        self._idle_delay = idle_delay

        self._idle_start: float = 0.0
        self._showing: bool = False
        self._show_start: float = 0.0
        self._show_count: int = 0
        self._count_loaded: bool = False

        # Track state changes for reset
        self._last_state: str = ""
        self._last_view: str = ""
        self._last_button: bool = False

    def _load_count(self) -> None:
        """Load persistent show count from .setup-state."""
        if self._count_loaded:
            return
        self._count_loaded = True
        try:
            from display.components.onboarding import get_setup_state
            state = get_setup_state()
            self._show_count = state.get("idle_hint_count", 0)
        except Exception:
            self._show_count = 0

    def _save_count(self) -> None:
        """Save show count to .setup-state."""
        try:
            from display.components.onboarding import save_setup_flag
            save_setup_flag("idle_hint_count", self._show_count)
        except Exception:
            pass

    def update(self, state: DisplayState, now: float) -> float:
        """Update hint state and return current alpha (0.0-1.0).

        Must be called every frame. Returns alpha for draw functions.
        """
        if not self._enabled:
            state._idle_hint_alpha = 0.0
            return 0.0

        self._load_count()

        # Check for reset conditions
        changed = False
        if state.state != self._last_state:
            changed = True
            self._last_state = state.state
        if state.view != self._last_view:
            changed = True
            self._last_view = state.view
        if state.button_pressed and not self._last_button:
            changed = True
        self._last_button = state.button_pressed

        if changed:
            self._showing = False
            self._idle_start = now
            state._idle_hint_alpha = 0.0
            return 0.0

        # Only show on face view during IDLE
        if state.view != "face" or state.state != "IDLE":
            self._idle_start = now
            state._idle_hint_alpha = 0.0
            return 0.0

        # Don't show when idle prompt "?" is visible or peek bubble active
        if state.idle_prompt_visible or now < state._peek_until:
            self._idle_start = now
            self._showing = False
            state._idle_hint_alpha = 0.0
            return 0.0

        # Don't show when menu/pairing/tutorial is active
        if state.tutorial_active or state.pairing_mode or state.pairing_request:
            self._idle_start = now
            self._showing = False
            state._idle_hint_alpha = 0.0
            return 0.0

        # Check show count limit
        if self._show_count >= self._max_shows:
            state._idle_hint_alpha = 0.0
            return 0.0

        # Wait for idle delay
        if not self._showing:
            if now - self._idle_start >= self._idle_delay:
                self._showing = True
                self._show_start = now
                self._show_count += 1
                self._save_count()
            else:
                state._idle_hint_alpha = 0.0
                return 0.0

        # Compute alpha based on show phase
        elapsed = now - self._show_start
        total = self.FADE_IN + self.HOLD + self.FADE_OUT

        if elapsed >= total:
            # Done showing — reset for next cycle
            self._showing = False
            self._idle_start = now
            state._idle_hint_alpha = 0.0
            return 0.0

        if elapsed < self.FADE_IN:
            alpha = elapsed / self.FADE_IN
        elif elapsed < self.FADE_IN + self.HOLD:
            alpha = 1.0
        else:
            alpha = 1.0 - (elapsed - self.FADE_IN - self.HOLD) / self.FADE_OUT

        alpha = max(0.0, min(1.0, alpha))
        state._idle_hint_alpha = alpha
        return alpha


def draw_idle_hint(draw: ImageDraw.ImageDraw, alpha: float,
                   accent: tuple = (0, 212, 210)) -> None:
    """Draw the idle button hint text at the bottom of the face view.

    Uses background-blend technique for performance (no RGBA compositing).
    """
    if alpha <= 0.01:
        return

    font = get_font(14)
    text = "Hold to talk  /  Tap for more"

    # Reduce max alpha to 60% for subtlety
    alpha *= 0.6

    y = SCREEN_H - 48

    # Blend text color with background
    color = _blend_color(accent, BG, alpha)
    tw = text_width(font, text)
    x = (SCREEN_W - tw) // 2
    draw.text((x, y), text, fill=color, font=font)


class ChatEntryHint:
    """Shows "Hold for settings" when switching to chat view.

    Lifecycle:
      - Triggers when view changes to "chat"
      - Fades in (0.4s), holds (3s), fades out (0.5s)
      - Increments show count (persisted in .setup-state)
      - Limited to max_shows total appearances
    """

    FADE_IN = 0.4
    HOLD = 3.0
    FADE_OUT = 0.5

    def __init__(self, enabled: bool = True, max_shows: int = DEFAULT_CHAT_MAX) -> None:
        self._enabled = enabled
        self._max_shows = max_shows

        self._showing: bool = False
        self._show_start: float = 0.0
        self._show_count: int = 0
        self._count_loaded: bool = False
        self._last_view: str = "face"

    def _load_count(self) -> None:
        """Load persistent show count from .setup-state."""
        if self._count_loaded:
            return
        self._count_loaded = True
        try:
            from display.components.onboarding import get_setup_state
            state = get_setup_state()
            self._show_count = state.get("chat_hint_count", 0)
        except Exception:
            self._show_count = 0

    def _save_count(self) -> None:
        """Save show count to .setup-state."""
        try:
            from display.components.onboarding import save_setup_flag
            save_setup_flag("chat_hint_count", self._show_count)
        except Exception:
            pass

    def update(self, state: DisplayState, now: float) -> float:
        """Update hint state and return current alpha (0.0-1.0).

        Must be called every frame. Returns alpha for draw functions.
        """
        if not self._enabled:
            state._chat_hint_alpha = 0.0
            return 0.0

        self._load_count()

        # Detect view change to chat
        if state.view == "chat" and self._last_view != "chat":
            # Just switched to chat view — trigger hint if count allows
            if self._show_count < self._max_shows and not self._showing:
                self._showing = True
                self._show_start = now
                state._chat_hint_start = now
                self._show_count += 1
                self._save_count()
        self._last_view = state.view

        # Only show in chat view
        if state.view != "chat" or not self._showing:
            if state.view != "chat":
                self._showing = False
            state._chat_hint_alpha = 0.0
            return 0.0

        # Don't show during tutorial
        if state.tutorial_active:
            state._chat_hint_alpha = 0.0
            return 0.0

        # Compute alpha based on show phase
        elapsed = now - self._show_start
        total = self.FADE_IN + self.HOLD + self.FADE_OUT

        if elapsed >= total:
            self._showing = False
            state._chat_hint_alpha = 0.0
            return 0.0

        if elapsed < self.FADE_IN:
            alpha = elapsed / self.FADE_IN
        elif elapsed < self.FADE_IN + self.HOLD:
            alpha = 1.0
        else:
            alpha = 1.0 - (elapsed - self.FADE_IN - self.HOLD) / self.FADE_OUT

        alpha = max(0.0, min(1.0, alpha))
        state._chat_hint_alpha = alpha
        return alpha


def draw_chat_hint(draw: ImageDraw.ImageDraw, alpha: float,
                   accent: tuple = (0, 212, 210)) -> None:
    """Draw the chat entry hint text at the bottom of the chat view.

    Uses background-blend technique for performance (no RGBA compositing).
    """
    if alpha <= 0.01:
        return

    font = get_font(13)
    text = "Hold for settings"

    # Reduce max alpha to 50% for subtlety
    alpha *= 0.5

    y = SCREEN_H - 40

    # Blend text color with background
    color = _blend_color(accent, BG, alpha)
    tw = text_width(font, text)
    x = (SCREEN_W - tw) // 2
    draw.text((x, y), text, fill=color, font=font)
