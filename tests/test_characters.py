"""Tests for the Voxel character rendering system.

Covers the character registry, all character x expression rendering,
Voxel-specific eye geometry (tilt cuts, blink, error X, happy arcs),
accent color, face center tracking, Cube idle quirk, and BMO variants.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from PIL import Image, ImageDraw

from shared import load_expressions, load_styles, Expression, FaceStyle
from display.characters import get_character, character_names, CHARACTERS
from display.characters.base import Character
from display.characters.voxel import VoxelCharacter
from display.characters.cube import CubeCharacter
from display.characters.bmo import BMOCharacter, BMOFullCharacter
from display.layout import SCREEN_W, SCREEN_H


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def canvas():
    """Create a fresh 240x280 canvas (RGB)."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
    draw = ImageDraw.Draw(img)
    return img, draw


@pytest.fixture
def style():
    """Load the default kawaii face style."""
    styles = load_styles()
    return styles.get("kawaii") or next(iter(styles.values()))


@pytest.fixture
def expressions():
    """Load all expression definitions."""
    return load_expressions()


@pytest.fixture
def neutral_expr(expressions):
    """Return the neutral expression."""
    return expressions["neutral"]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _draw_character(char: Character, img: Image.Image, draw: ImageDraw.ImageDraw,
                    expr: Expression, style: FaceStyle, *,
                    blink_factor: float = 1.0,
                    gaze_x: float = 0.0,
                    gaze_y: float = 0.0,
                    amplitude: float = 0.0) -> None:
    """Draw a character with sensible defaults."""
    char.draw(draw, img, expr, style, blink_factor, gaze_x, gaze_y,
              amplitude, now=time.time())


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Character registry
# ═══════════════════════════════════════════════════════════════════════════════


class TestCharacterRegistry:
    """Tests for get_character and the CHARACTERS dict."""

    def test_get_character_returns_correct_types(self):
        assert isinstance(get_character("voxel"), VoxelCharacter)
        assert isinstance(get_character("cube"), CubeCharacter)
        assert isinstance(get_character("bmo"), BMOCharacter)
        assert isinstance(get_character("bmo-full"), BMOFullCharacter)

    def test_get_character_fallback_to_voxel(self):
        """Unknown names fall back to the 'voxel' character."""
        char = get_character("nonexistent")
        assert isinstance(char, VoxelCharacter)

    def test_get_character_returns_same_instance(self):
        """Characters are cached singletons."""
        a = get_character("cube")
        b = get_character("cube")
        assert a is b

    def test_all_registry_entries_are_character_subclasses(self):
        for name, cls in CHARACTERS.items():
            assert issubclass(cls, Character), f"{name} is not a Character subclass"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. character_names()
# ═══════════════════════════════════════════════════════════════════════════════


class TestCharacterNames:

    def test_returns_sorted_list(self):
        names = character_names()
        assert names == sorted(names)

    def test_contains_all_registered_characters(self):
        names = character_names()
        for key in CHARACTERS:
            assert key in names

    def test_returns_list_of_strings(self):
        names = character_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. All characters render all moods without crash
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllCharactersAllMoods:

    @pytest.fixture(params=sorted(CHARACTERS.keys()), ids=lambda n: f"char={n}")
    def char_name(self, request):
        return request.param

    @pytest.fixture
    def all_expression_names(self, expressions):
        return sorted(expressions.keys())

    def test_render_all_moods(self, char_name, expressions, style):
        """Every character x every expression renders without error
        and produces a valid PIL Image."""
        char = get_character(char_name)
        for mood_name, expr in expressions.items():
            img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
            draw = ImageDraw.Draw(img)
            # Should not raise
            _draw_character(char, img, draw, expr, style)
            assert img.size == (SCREEN_W, SCREEN_H)
            assert img.mode == "RGB"

    def test_render_with_amplitude(self, char_name, neutral_expr, style, canvas):
        """Characters handle non-zero amplitude (speaking state)."""
        img, draw = canvas
        char = get_character(char_name)
        _draw_character(char, img, draw, neutral_expr, style, amplitude=0.8)

    def test_render_with_gaze(self, char_name, neutral_expr, style, canvas):
        """Characters handle extreme gaze values."""
        img, draw = canvas
        char = get_character(char_name)
        _draw_character(char, img, draw, neutral_expr, style,
                        gaze_x=1.0, gaze_y=-1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Voxel tilt cuts
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoxelTiltCuts:

    @pytest.fixture
    def voxel(self):
        return VoxelCharacter()

    def test_frustrated_renders_without_crash(self, voxel, expressions, style, canvas):
        """Frustrated expression has tilt overrides that produce V-brow cuts."""
        img, draw = canvas
        expr = expressions["frustrated"]
        # frustrated has left_eye.tilt=-12, right_eye.tilt=12
        assert expr.left_eye is not None
        assert expr.right_eye is not None
        assert expr.left_eye.tilt is not None
        assert expr.right_eye.tilt is not None
        # Inner-edge angry V: tilts have opposite signs
        assert expr.left_eye.tilt * expr.right_eye.tilt < 0
        _draw_character(voxel, img, draw, expr, style)

    def test_sad_renders_without_crash(self, voxel, expressions, style, canvas):
        """Sad expression has droopy outer-corner tilt cuts."""
        img, draw = canvas
        expr = expressions["sad"]
        assert expr.left_eye is not None
        assert expr.right_eye is not None
        assert expr.left_eye.tilt is not None
        assert expr.right_eye.tilt is not None
        # Droopy: left tilt positive, right tilt negative (outer corners drop)
        assert expr.left_eye.tilt > 0
        assert expr.right_eye.tilt < 0
        _draw_character(voxel, img, draw, expr, style)

    def test_thinking_asymmetric_eyes(self, voxel, expressions, style, canvas):
        """Thinking expression has per-eye overrides for asymmetric look."""
        img, draw = canvas
        expr = expressions["thinking"]
        assert expr.left_eye is not None
        assert expr.right_eye is not None
        # Left eye is more open than right
        assert expr.left_eye.openness is not None
        assert expr.right_eye.openness is not None
        assert expr.left_eye.openness > expr.right_eye.openness
        _draw_character(voxel, img, draw, expr, style)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Voxel eye geometry
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoxelEyeGeometry:

    @pytest.fixture
    def voxel(self):
        return VoxelCharacter()

    def test_blink_factor_zero_closes_eyes(self, voxel, neutral_expr, style):
        """With blink_factor=0 the eyes should be fully closed (minimal height)."""
        # We verify it doesn't crash; the visual result is thin slits or arcs.
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
        draw = ImageDraw.Draw(img)
        _draw_character(voxel, img, draw, neutral_expr, style, blink_factor=0.0)

    def test_eye_dimensions_scale_with_expression(self, voxel, expressions, style):
        """Surprised expression (height=1.25) should produce taller eyes than
        sleepy (height=0.7). We can't check pixels but we verify the expression
        data feeds into draw without error."""
        surprised = expressions["surprised"]
        sleepy = expressions["sleepy"]
        assert surprised.eyes.height > sleepy.eyes.height

        for expr in (surprised, sleepy):
            img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
            draw = ImageDraw.Draw(img)
            _draw_character(voxel, img, draw, expr, style)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Voxel error state
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoxelError:

    def test_error_renders_x_marks(self, expressions, style, canvas):
        """Error expression triggers _draw_x (returns early, no normal eyes)."""
        img, draw = canvas
        voxel = VoxelCharacter()
        expr = expressions["error"]
        assert expr.name == "error"
        _draw_character(voxel, img, draw, expr, style)
        # The image should contain red pixels (X marks are drawn in (255, 60, 60))
        arr = np.array(img)
        red_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] < 100) & (arr[:, :, 2] < 100)
        assert red_mask.sum() > 0, "Error state should render red X marks"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Voxel happy state
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoxelHappy:

    def test_happy_renders_without_crash(self, expressions, style, canvas):
        """Happy expression (smile=1.0) triggers bottom cuts or ^_^ arcs."""
        img, draw = canvas
        voxel = VoxelCharacter()
        expr = expressions["happy"]
        assert expr.mouth.smile > 0.4
        _draw_character(voxel, img, draw, expr, style)

    def test_happy_closed_eyes_draw_arcs(self, expressions, style, canvas):
        """When blink_factor is very low and smile is high, _draw_happy_arc is used."""
        img, draw = canvas
        voxel = VoxelCharacter()
        expr = expressions["happy"]
        # Force blink closed — this should trigger the happy arc path (openness < 0.15)
        _draw_character(voxel, img, draw, expr, style, blink_factor=0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Accent color
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccentColor:

    def test_default_accent(self):
        """Default accent is teal/cyan."""
        voxel = VoxelCharacter()
        assert voxel._accent == (0, 212, 210)

    def test_custom_accent_applied(self, neutral_expr, style, canvas):
        """Setting _accent changes the character's eye/edge color."""
        img, draw = canvas
        voxel = VoxelCharacter()
        voxel._accent = (255, 100, 50)
        _draw_character(voxel, img, draw, neutral_expr, style)
        # Orange-ish pixels should appear (from the accent color)
        arr = np.array(img)
        orange_mask = (
            (arr[:, :, 0] > 180) & (arr[:, :, 1] > 50) & (arr[:, :, 2] < 100)
            & (arr[:, :, 0] > arr[:, :, 1]) & (arr[:, :, 1] > arr[:, :, 2])
        )
        assert orange_mask.sum() > 0, "Custom accent color should produce tinted pixels"

    def test_cube_accent(self, neutral_expr, style, canvas):
        """Cube character also respects _accent for edge glow."""
        img, draw = canvas
        cube = CubeCharacter()
        cube._accent = (255, 0, 0)
        _draw_character(cube, img, draw, neutral_expr, style)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Face center tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceCenterTracking:

    @pytest.fixture(params=sorted(CHARACTERS.keys()), ids=lambda n: f"char={n}")
    def char_name(self, request):
        return request.param

    def test_face_center_set_after_draw(self, char_name, neutral_expr, style, canvas):
        """After draw(), _last_face_cx/_last_face_cy are within screen bounds."""
        img, draw = canvas
        char = get_character(char_name)
        _draw_character(char, img, draw, neutral_expr, style)
        # Face center should be within the screen bounds (with some margin
        # for bounce/shake, allow a bit outside)
        assert -20 <= char._last_face_cx <= SCREEN_W + 20, \
            f"face_cx={char._last_face_cx} out of range for {char_name}"
        assert -20 <= char._last_face_cy <= SCREEN_H + 20, \
            f"face_cy={char._last_face_cy} out of range for {char_name}"

    def test_face_center_reasonable_position(self, char_name, neutral_expr, style, canvas):
        """Face center should be roughly centered horizontally and in the
        middle/lower portion of the screen."""
        img, draw = canvas
        char = get_character(char_name)
        _draw_character(char, img, draw, neutral_expr, style)
        # Horizontally near center (within 60px)
        assert abs(char._last_face_cx - SCREEN_W // 2) < 60, \
            f"face_cx={char._last_face_cx} too far from center for {char_name}"
        # Vertically in the display area (below status bar, above bottom)
        assert 40 <= char._last_face_cy <= SCREEN_H, \
            f"face_cy={char._last_face_cy} out of expected range for {char_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Cube idle quirk
# ═══════════════════════════════════════════════════════════════════════════════


class TestCubeIdleQuirk:

    def test_idle_quirk_no_crash(self, neutral_expr, style, canvas):
        """idle_quirk draws edge shimmer without crashing."""
        img, draw = canvas
        cube = CubeCharacter()
        # Must draw first so _last_cx/_last_cy are set
        _draw_character(cube, img, draw, neutral_expr, style)
        # Now call idle_quirk
        cube.idle_quirk(draw, img, now=time.time())

    def test_idle_quirk_changes_pixels(self, neutral_expr, style):
        """idle_quirk should draw shimmer lines that modify the image."""
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
        draw = ImageDraw.Draw(img)
        cube = CubeCharacter()
        _draw_character(cube, img, draw, neutral_expr, style)

        # Snapshot pixel data before idle_quirk
        before = img.copy()
        cube.idle_quirk(draw, img, now=time.time())

        # At least some pixels should differ (shimmer lines redraw edges)
        arr_before = np.array(before)
        arr_after = np.array(img)
        diff_count = int((arr_before != arr_after).any(axis=2).sum())
        assert diff_count > 0, "idle_quirk should modify at least some pixels"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Cube body rendering
# ═══════════════════════════════════════════════════════════════════════════════


class TestCubeBody:

    def test_body_renders_at_various_scales(self, expressions, style):
        """Cube body draws without crash at different scale values."""
        cube = CubeCharacter()
        for scale_val in (0.8, 1.0, 1.05):
            img = Image.new("RGB", (SCREEN_W, SCREEN_H), (10, 10, 15))
            draw = ImageDraw.Draw(img)
            # Use an expression that exercises different scales
            expr = expressions["neutral"]
            # Manually set scale to test
            from dataclasses import replace
            from shared import BodyConfig
            tweaked_body = replace(expr.body, scale=scale_val)
            tweaked_expr = replace(expr, body=tweaked_body)
            _draw_character(cube, img, draw, tweaked_expr, style)

    def test_body_draws_isometric_faces(self, neutral_expr, style, canvas):
        """The cube body rendering produces non-blank output."""
        img, draw = canvas
        cube = CubeCharacter()
        _draw_character(cube, img, draw, neutral_expr, style)
        # Should have body-colored pixels (BODY_FILL = (26, 26, 46))
        arr = np.array(img)
        body_mask = (arr[:, :, 0] == 26) & (arr[:, :, 1] == 26) & (arr[:, :, 2] == 46)
        assert body_mask.sum() > 100, "Cube body should fill a significant area"


# ═══════════════════════════════════════════════════════════════════════════════
# 12. BMO variants
# ═══════════════════════════════════════════════════════════════════════════════


class TestBMOVariants:

    def test_bmo_face_renders(self, neutral_expr, style, canvas):
        """BMOCharacter (face-only) renders without crash."""
        img, draw = canvas
        bmo = BMOCharacter()
        _draw_character(bmo, img, draw, neutral_expr, style)
        # Should have the BMO screen background color (168, 216, 176)
        arr = np.array(img)
        screen_mask = (arr[:, :, 0] == 168) & (arr[:, :, 1] == 216) & (arr[:, :, 2] == 176)
        assert screen_mask.sum() > 100, "BMO face should fill screen with green background"

    def test_bmo_full_renders(self, neutral_expr, style, canvas):
        """BMOFullCharacter renders the complete console body."""
        img, draw = canvas
        bmo_full = BMOFullCharacter()
        _draw_character(bmo_full, img, draw, neutral_expr, style)
        # Should have BMO body color (0, 196, 160)
        arr = np.array(img)
        body_mask = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 196) & (arr[:, :, 2] == 160)
        assert body_mask.sum() > 50, "BMO full should draw the console body"

    def test_bmo_idle_quirk(self, neutral_expr, style, canvas):
        """BMO idle_quirk (pixel game, glitch, cursor) runs without crash."""
        img, draw = canvas
        bmo = BMOCharacter()
        _draw_character(bmo, img, draw, neutral_expr, style)
        bmo.idle_quirk(draw, img, now=time.time())

    def test_bmo_full_idle_quirk(self, neutral_expr, style, canvas):
        """BMOFullCharacter idle_quirk is a no-op but should not crash."""
        img, draw = canvas
        bmo_full = BMOFullCharacter()
        _draw_character(bmo_full, img, draw, neutral_expr, style)
        bmo_full.idle_quirk(draw, img, now=time.time())

    def test_bmo_error_state(self, expressions, style, canvas):
        """BMO renders X eyes in error state."""
        img, draw = canvas
        bmo = BMOCharacter()
        _draw_character(bmo, img, draw, expressions["error"], style)
        # Should have red X mark pixels
        arr = np.array(img)
        red_mask = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 80)
        assert red_mask.sum() > 0, "BMO error should draw red X eyes"

    def test_both_bmo_variants_are_distinct(self):
        """BMOCharacter and BMOFullCharacter are different classes."""
        assert BMOCharacter is not BMOFullCharacter
        assert BMOCharacter().name == "bmo"
        assert BMOFullCharacter().name == "bmo-full"
