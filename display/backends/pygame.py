"""Pygame window backend — desktop preview of the 240x280 display."""

from __future__ import annotations

import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from display.backends.base import OutputBackend  # noqa: E402

WIDTH = 240
HEIGHT = 280


class PygameBackend(OutputBackend):
    """Renders PIL frames into a pygame window for local development."""

    def __init__(self, scale: int = 2):
        self._scale = scale
        self._screen: pygame.Surface | None = None
        self._quit = False

    def init(self) -> None:
        pygame.init()
        w = WIDTH * self._scale
        h = HEIGHT * self._scale
        self._screen = pygame.display.set_mode((w, h))
        pygame.display.set_caption("Voxel Display (PIL)")

    def push_frame(self, image: Image.Image) -> None:
        if self._screen is None:
            return
        # Pump events to keep window responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._quit = True
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._quit = True
                return

        # PIL RGB -> pygame Surface
        raw = image.tobytes()
        surface = pygame.image.fromstring(raw, image.size, image.mode)
        if self._scale != 1:
            surface = pygame.transform.scale(surface, self._screen.get_size())
        self._screen.blit(surface, (0, 0))
        pygame.display.flip()

    def should_quit(self) -> bool:
        return self._quit

    def cleanup(self) -> None:
        pygame.quit()
