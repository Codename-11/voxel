"""Demo mode controller — auto-cycles moods, characters, and styles.

Used for showcasing the device at events, in stores, or for development.
Cycles through all expressions, optionally switching characters and styles.
"""

from __future__ import annotations

import logging
from display.state import DisplayState
from shared import load_expressions, load_styles
from display.characters import character_names

log = logging.getLogger("voxel.display.demo")


class DemoController:
    """Manages demo mode cycling."""

    def __init__(self, cycle_speed: float = 5.0,
                 include_characters: bool = True,
                 include_styles: bool = True) -> None:
        self._cycle_speed = cycle_speed
        self._include_characters = include_characters
        self._include_styles = include_styles

        # Build ordered lists to cycle through
        self._moods = list(load_expressions().keys())
        self._characters = character_names() if include_characters else []
        self._styles = list(load_styles().keys()) if include_styles else []

        self._active = False
        log.info(f"Demo controller ready: {len(self._moods)} moods, "
                 f"{len(self._characters)} characters, {len(self._styles)} styles")

    def update(self, state: DisplayState, now: float) -> None:
        """Update demo state each frame. Modifies state in-place.

        Called from the renderer before mood/character resolution.
        Only acts when state.demo_mode is True.
        """
        if not state.demo_mode:
            if self._active:
                self._active = False
                log.info("Demo mode deactivated")
            return

        if not self._active:
            self._active = True
            state._demo_next_cycle = now + self._cycle_speed
            state.demo_mood_index = 0
            state.demo_char_index = 0
            state.demo_style_index = 0
            log.info("Demo mode activated")

        # Time to cycle?
        if now < state._demo_next_cycle:
            # Apply current demo state
            self._apply(state)
            return

        # Advance to next mood
        state.demo_mood_index = (state.demo_mood_index + 1) % max(len(self._moods), 1)

        # When moods wrap around, advance character
        if state.demo_mood_index == 0 and self._include_characters and self._characters:
            state.demo_char_index = (state.demo_char_index + 1) % len(self._characters)

            # When characters wrap, advance style
            if state.demo_char_index == 0 and self._include_styles and self._styles:
                state.demo_style_index = (state.demo_style_index + 1) % len(self._styles)

        state._demo_next_cycle = now + self._cycle_speed
        self._apply(state)

        mood = self._moods[state.demo_mood_index] if self._moods else "neutral"
        char = self._characters[state.demo_char_index] if self._characters else ""
        style = self._styles[state.demo_style_index] if self._styles else ""
        log.debug(f"Demo cycle: mood={mood}, char={char}, style={style}")

    def _apply(self, state: DisplayState) -> None:
        """Apply current demo settings to state."""
        if self._moods:
            state.mood = self._moods[state.demo_mood_index % len(self._moods)]
        if self._characters:
            state.character = self._characters[state.demo_char_index % len(self._characters)]
        if self._styles:
            state.style = self._styles[state.demo_style_index % len(self._styles)]
        # Force face view during demo
        state.state = "IDLE"
        state.view = "face"
