"""Abstract output backend for the display service."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class OutputBackend(ABC):
    """Push rendered PIL frames to a display target."""

    @abstractmethod
    def init(self) -> None:
        """Initialize the output (open window / init SPI)."""

    @abstractmethod
    def push_frame(self, image: Image.Image) -> None:
        """Send a rendered 240x280 RGB frame to the display."""

    @abstractmethod
    def should_quit(self) -> bool:
        """Return True if the user requested exit."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources."""
