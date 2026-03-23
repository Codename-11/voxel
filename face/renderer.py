"""Face renderer — orchestrates VoxelCharacter and maps states to moods."""

import logging

import pygame

from face.character import VoxelCharacter
from face.expressions import Mood
from states.machine import State

log = logging.getLogger("voxel.face.renderer")

# State → Mood mapping
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
    """Manages the Voxel character face and its lifecycle."""

    def __init__(self):
        self._character = VoxelCharacter()
        log.info("Face renderer initialized")

    @property
    def character(self) -> VoxelCharacter:
        return self._character

    def set_mood(self, mood: Mood) -> None:
        """Directly set a mood (for testing/override)."""
        self._character.set_mood(mood)

    def on_state_change(self, old_state: State, new_state: State) -> None:
        """Callback for state machine transitions. Maps state to mood."""
        mood = _STATE_MOOD_MAP.get(new_state, Mood.NEUTRAL)
        self._character.set_mood(mood)

    def set_audio_amplitude(self, amplitude: float) -> None:
        """Feed audio amplitude for mouth sync."""
        self._character.audio_amplitude = amplitude

    def update(self, dt: float) -> None:
        """Update animation. Call once per frame."""
        self._character.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the character face."""
        self._character.draw(surface)
