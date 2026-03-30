"""Character registry — maps character names to their renderer classes.

Usage:
    from display.characters import get_character, CHARACTERS

    char = get_character("bmo")
    char.draw(draw, img, expr, style, ...)
"""

from __future__ import annotations

from display.characters.base import Character
from display.characters.cube import CubeCharacter
from display.characters.bmo import BMOCharacter, BMOFullCharacter
from display.characters.voxel import VoxelCharacter

CHARACTERS: dict[str, type[Character]] = {
    "voxel": VoxelCharacter,
    "cube": CubeCharacter,
    "bmo": BMOCharacter,
    "bmo-full": BMOFullCharacter,
}

# Pre-instantiated singletons (characters are stateless)
_instances: dict[str, Character] = {}


def get_character(name: str) -> Character:
    """Get a character instance by name.

    Falls back to 'cube' if the name is not recognized.
    """
    if name not in CHARACTERS:
        name = "voxel"
    if name not in _instances:
        _instances[name] = CHARACTERS[name]()
    return _instances[name]


def character_names() -> list[str]:
    """Return sorted list of available character names."""
    return sorted(CHARACTERS.keys())
