"""Face renderer — orchestrates VoxelCharacter, maps states to moods, manages styles."""

import logging

import pygame

from face.character import VoxelCharacter
from face.expressions import Mood
from face.styles import STYLES, STYLE_LIST, DEFAULT_STYLE
from states.machine import State

log = logging.getLogger("voxel.face.renderer")

# State -> Mood mapping (expanded to cover all moods reachable from states)
_STATE_MOOD_MAP: dict[State, Mood] = {
    State.IDLE:      Mood.NEUTRAL,
    State.LISTENING: Mood.LISTENING,
    State.THINKING:  Mood.THINKING,
    State.SPEAKING:  Mood.NEUTRAL,
    State.ERROR:     Mood.ERROR,
    State.SLEEPING:  Mood.SLEEPY,
    State.MENU:      Mood.NEUTRAL,
}


class FaceRenderer:
    """Manages the Voxel character face and its lifecycle.

    Supports runtime style switching and the full set of moods from the
    design system (neutral, happy, curious, thinking, confused, excited,
    sleepy, error, listening, sad, surprised, focused, frustrated, working,
    lowBattery, criticalBattery).
    """

    def __init__(self, style_name: str = DEFAULT_STYLE):
        self._character = VoxelCharacter(style_name=style_name)
        self._style_name = style_name
        log.info(f"Face renderer initialized (style: {style_name})")

    @property
    def character(self) -> VoxelCharacter:
        return self._character

    # ── Style management ─────────────────────────────────────────────────────

    def set_style(self, style_name: str) -> None:
        """Change face style at runtime (kawaii, retro, minimal)."""
        self._character.set_style(style_name)
        self._style_name = style_name

    def get_style_name(self) -> str:
        return self._style_name

    def cycle_style(self) -> str:
        """Cycle to the next style. Returns the new style name."""
        idx = STYLE_LIST.index(self._style_name) if self._style_name in STYLE_LIST else 0
        next_idx = (idx + 1) % len(STYLE_LIST)
        new_style = STYLE_LIST[next_idx]
        self.set_style(new_style)
        return new_style

    # ── Mood management ──────────────────────────────────────────────────────

    def set_mood(self, mood: Mood) -> None:
        """Directly set a mood (for testing/override)."""
        self._character.set_mood(mood)

    def on_state_change(self, old_state: State, new_state: State) -> None:
        """Callback for state machine transitions. Maps state to mood."""
        mood = _STATE_MOOD_MAP.get(new_state, Mood.NEUTRAL)
        self._character.set_mood(mood)

    # ── Audio ────────────────────────────────────────────────────────────────

    def set_audio_amplitude(self, amplitude: float) -> None:
        """Feed audio amplitude for mouth sync."""
        self._character.audio_amplitude = amplitude

    # ── Frame lifecycle ──────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Update animation. Call once per frame."""
        self._character.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the character face."""
        self._character.draw(surface)
