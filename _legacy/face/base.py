"""Abstract base renderer interface for the Voxel face engine.

Defines the contract that all renderer backends (pygame, web, etc.) must
implement.  The interface uses plain strings for mood and style names so
that non-pygame backends never need to import pygame-specific types.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseRenderer(ABC):
    """Backend-agnostic face renderer interface."""

    # ── Mood management ──────────────────────────────────────────────────────

    @abstractmethod
    def set_mood(self, mood_name: str) -> None:
        """Set the current mood by name (e.g. "neutral", "happy", "error")."""
        ...

    @abstractmethod
    def get_mood(self) -> str:
        """Return the current mood name as a lowercase string."""
        ...

    # ── Style management ─────────────────────────────────────────────────────

    @abstractmethod
    def set_style(self, style_name: str) -> None:
        """Change the visual style (e.g. "kawaii", "retro", "minimal")."""
        ...

    @abstractmethod
    def get_style(self) -> str:
        """Return the current style name."""
        ...

    @abstractmethod
    def cycle_style(self) -> str:
        """Cycle to the next style. Returns the new style name."""
        ...

    # ── Audio ────────────────────────────────────────────────────────────────

    @abstractmethod
    def set_audio_amplitude(self, amplitude: float) -> None:
        """Feed audio amplitude (0.0 – 1.0) for mouth-sync animation."""
        ...

    # ── Frame lifecycle ──────────────────────────────────────────────────────

    @abstractmethod
    def update(self, dt: float) -> None:
        """Advance animations by *dt* seconds. Call once per frame."""
        ...

    @abstractmethod
    def draw(self, surface: Any) -> None:
        """Render the current frame to *surface*.

        The type of *surface* depends on the backend (e.g. ``pygame.Surface``
        for the pygame backend, an HTML canvas reference for the web backend).
        """
        ...

    # ── Cleanup ──────────────────────────────────────────────────────────────

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources held by the renderer."""
        ...
