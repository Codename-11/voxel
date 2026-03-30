"""Shared YAML data layer — single source of truth for expressions, styles, and moods.

Loads YAML files once, caches them as typed dataclass objects for Python consumers.
JS/React consumers read the same YAML files via their own loader.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# ── Path to this package's YAML files ────────────────────────────────────────

_SHARED_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

# ── Caches ───────────────────────────────────────────────────────────────────

_expressions_cache: Optional[dict[str, Expression]] = None
_styles_cache: Optional[dict[str, FaceStyle]] = None
_moods_cache: Optional[dict] = None


# ── Expression dataclasses ───────────────────────────────────────────────────

@dataclass
class EyeConfig:
    """Defines how the eyes look for a given expression."""
    width: float = 1.0
    height: float = 1.0
    openness: float = 1.0
    pupil_size: float = 0.4
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    blink_rate: float = 3.0
    squint: float = 0.0


@dataclass
class MouthConfig:
    """Defines how the mouth looks for a given expression."""
    openness: float = 0.0
    smile: float = 0.3
    width: float = 1.0


@dataclass
class BodyConfig:
    """Defines body language for a given expression."""
    bounce_speed: float = 0.5
    bounce_amount: float = 2.0
    tilt: float = 0.0
    scale: float = 1.0


@dataclass
class PerEyeOverride:
    """Optional per-eye overrides layered on top of EyeConfig."""
    openness: Optional[float] = None
    height: Optional[float] = None
    width: Optional[float] = None
    squint: Optional[float] = None
    tilt: Optional[float] = None


@dataclass
class Expression:
    """Complete expression definition.

    Supports composition:
      - ``modifiers``: list of animation modifier configs applied per-frame
        (see ``display/modifiers.py`` for available types).
      - ``extends``: name of a base expression to inherit from.
      - ``blend``: dict of ``{mood_name: weight}`` to lerp on top of
        the base, enabling composed expressions like
        ``surprised_by_sound = surprised + 35% curious``.
    """
    name: str = ""
    eyes: EyeConfig = field(default_factory=EyeConfig)
    mouth: MouthConfig = field(default_factory=MouthConfig)
    body: BodyConfig = field(default_factory=BodyConfig)
    left_eye: Optional[PerEyeOverride] = None
    right_eye: Optional[PerEyeOverride] = None
    eye_color_override: Optional[str] = None
    modifiers: list[dict] = field(default_factory=list)


# ── Style dataclasses ────────────────────────────────────────────────────────

def _parse_radius(value) -> float:
    """Parse a CSS border-radius value to a float fraction.

    Handles: 0.28, "40%", "35% / 50%" (takes first value).
    Percentages are converted to 0.0-1.0 fractions.
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # "35% / 50%" -> take first part
    if "/" in s:
        s = s.split("/")[0].strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s)


def _parse_color(value: str) -> tuple:
    """Convert a color string to an (r, g, b) or (r, g, b, a) tuple.

    Supports:
      - '#rrggbb' hex strings -> (r, g, b)
      - 'rgba(r, g, b, a)' strings -> (r, g, b, a_int)  where a is 0.0-1.0 -> 0-255
      - 'transparent' / 'rgba(0, 0, 0, 0)' -> (0, 0, 0, 0)
    """
    if not isinstance(value, str):
        return value

    value = value.strip()

    if value.lower() == "transparent":
        return (0, 0, 0, 0)

    if value.startswith("#"):
        h = value.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    if value.startswith("rgba("):
        inner = value[5:].rstrip(")")
        parts = [p.strip() for p in inner.split(",")]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(float(parts[3]) * 255)
        return (r, g, b, a)

    if value.startswith("rgb("):
        inner = value[4:].rstrip(")")
        parts = [p.strip() for p in inner.split(",")]
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    return value


@dataclass
class EyeStyle:
    """Defines how eyes are rendered for a given style."""
    type: str = "roundrect"
    base_width: int = 30
    base_height: int = 38
    highlight_size: int = 0
    highlight_color: tuple = (255, 255, 255, 230)
    fill_color: tuple = (240, 240, 240)
    glow_color: tuple = (240, 240, 240, 38)
    border_radius: float = 0.28
    closed_radius: float = 0.35
    iris_color: tuple = (10, 10, 18)
    iris_size: float = 0.55


@dataclass
class MouthStyle:
    """Defines how the mouth is rendered for a given style."""
    type: str = "offset"
    base_width: int = 30
    stroke_width: int = 3
    color: tuple = (240, 240, 240)
    teeth_color: tuple = (255, 255, 255)
    lip_color: tuple = (18, 18, 32)


@dataclass
class XEyeStyle:
    """Defines X_X error eye appearance."""
    color: tuple = (255, 60, 60)
    thickness: int = 3
    size: int = 22


@dataclass
class FaceStyle:
    """Complete face style theme."""
    name: str = "Kawaii"
    description: str = ""
    eye: EyeStyle = field(default_factory=EyeStyle)
    mouth: MouthStyle = field(default_factory=MouthStyle)
    x_eye: XEyeStyle = field(default_factory=XEyeStyle)


# ── YAML loaders ─────────────────────────────────────────────────────────────

def _load_yaml(filename: str) -> dict:
    """Load and parse a YAML file from the shared directory."""
    filepath = _SHARED_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_per_eye(data: Optional[dict]) -> Optional[PerEyeOverride]:
    """Build a PerEyeOverride from a dict, or return None."""
    if data is None:
        return None
    return PerEyeOverride(
        openness=data.get("openness"),
        height=data.get("height"),
        width=data.get("width"),
        squint=data.get("squint"),
        tilt=data.get("tilt"),
    )


def _build_expression(mood_name: str, data: dict) -> Expression:
    """Build a single Expression from raw YAML data (no extends/blend)."""
    eyes_d = data.get("eyes", {})
    mouth_d = data.get("mouth", {})
    body_d = data.get("body", {})

    return Expression(
        name=mood_name,
        eyes=EyeConfig(
            width=float(eyes_d.get("width", 1.0)),
            height=float(eyes_d.get("height", 1.0)),
            openness=float(eyes_d.get("openness", 1.0)),
            pupil_size=float(eyes_d.get("pupil_size", 0.4)),
            gaze_x=float(eyes_d.get("gaze_x", 0.0)),
            gaze_y=float(eyes_d.get("gaze_y", 0.0)),
            blink_rate=float(eyes_d.get("blink_rate", 3.0)),
            squint=float(eyes_d.get("squint", 0.0)),
        ),
        mouth=MouthConfig(
            openness=float(mouth_d.get("openness", 0.0)),
            smile=float(mouth_d.get("smile", 0.3)),
            width=float(mouth_d.get("width", 1.0)),
        ),
        body=BodyConfig(
            bounce_speed=float(body_d.get("bounce_speed", 0.5)),
            bounce_amount=float(body_d.get("bounce_amount", 2.0)),
            tilt=float(body_d.get("tilt", 0.0)),
            scale=float(body_d.get("scale", 1.0)),
        ),
        left_eye=_build_per_eye(data.get("left_eye")),
        right_eye=_build_per_eye(data.get("right_eye")),
        eye_color_override=data.get("eye_color_override"),
        modifiers=data.get("modifiers", []),
    )


def _lerp_field(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _blend_expression(base: Expression, overlay: Expression,
                      weight: float) -> Expression:
    """Blend *overlay* onto *base* by *weight* (0..1).

    Used for composed expressions like ``surprised_by_sound``.
    Modifiers from both expressions are concatenated.
    """
    w = max(0.0, min(1.0, weight))

    def _le(a, b):
        return _lerp_field(a, b, w)

    eyes = EyeConfig(
        width=_le(base.eyes.width, overlay.eyes.width),
        height=_le(base.eyes.height, overlay.eyes.height),
        openness=_le(base.eyes.openness, overlay.eyes.openness),
        pupil_size=_le(base.eyes.pupil_size, overlay.eyes.pupil_size),
        gaze_x=_le(base.eyes.gaze_x, overlay.eyes.gaze_x),
        gaze_y=_le(base.eyes.gaze_y, overlay.eyes.gaze_y),
        blink_rate=_le(base.eyes.blink_rate, overlay.eyes.blink_rate),
        squint=_le(base.eyes.squint, overlay.eyes.squint),
    )
    mouth = MouthConfig(
        openness=_le(base.mouth.openness, overlay.mouth.openness),
        smile=_le(base.mouth.smile, overlay.mouth.smile),
        width=_le(base.mouth.width, overlay.mouth.width),
    )
    body = BodyConfig(
        bounce_speed=_le(base.body.bounce_speed, overlay.body.bounce_speed),
        bounce_amount=_le(base.body.bounce_amount, overlay.body.bounce_amount),
        tilt=_le(base.body.tilt, overlay.body.tilt),
        scale=_le(base.body.scale, overlay.body.scale),
    )
    # Blend per-eye: take overlay's if present, else base's
    left_eye = overlay.left_eye if overlay.left_eye else base.left_eye
    right_eye = overlay.right_eye if overlay.right_eye else base.right_eye
    # Eye color: overlay wins if set
    eye_color = overlay.eye_color_override or base.eye_color_override
    # Modifiers: concat (base first, overlay second)
    mods = list(base.modifiers) + list(overlay.modifiers)

    return Expression(
        name=base.name,
        eyes=eyes,
        mouth=mouth,
        body=body,
        left_eye=left_eye,
        right_eye=right_eye,
        eye_color_override=eye_color,
        modifiers=mods,
    )


def load_expressions() -> dict[str, Expression]:
    """Load all expression/mood definitions from expressions.yaml.

    Returns a dict keyed by mood name (snake_case lowercase),
    e.g. {"neutral": Expression(...), "happy": Expression(...), ...}.

    Supports composition via YAML keys:
      - ``extends: <mood>`` — inherit from another expression
      - ``blend: {<mood>: <weight>}`` — lerp toward another expression

    Results are cached after the first call.
    """
    global _expressions_cache
    if _expressions_cache is not None:
        return _expressions_cache

    raw = _load_yaml("expressions.yaml")

    # First pass: build standalone expressions (no extends/blend)
    standalone: dict[str, Expression] = {}
    deferred: list[tuple[str, dict]] = []

    for mood_name, data in raw.items():
        if data.get("extends") or data.get("blend"):
            deferred.append((mood_name, data))
        else:
            standalone[mood_name] = _build_expression(mood_name, data)

    result = dict(standalone)

    # Second pass: resolve extends/blend
    for mood_name, data in deferred:
        base_name = data.get("extends")
        if base_name and base_name in result:
            expr = result[base_name]
            # Copy base, rename
            expr = Expression(
                name=mood_name,
                eyes=expr.eyes,
                mouth=expr.mouth,
                body=expr.body,
                left_eye=expr.left_eye,
                right_eye=expr.right_eye,
                eye_color_override=expr.eye_color_override,
                modifiers=list(expr.modifiers),
            )
        else:
            expr = _build_expression(mood_name, data)

        # Apply blends
        blend_cfg = data.get("blend", {})
        if isinstance(blend_cfg, dict):
            for overlay_name, weight in blend_cfg.items():
                overlay = result.get(overlay_name)
                if overlay:
                    expr = _blend_expression(expr, overlay, float(weight))
                    expr.name = mood_name  # preserve name after blend

        # Override modifiers from the composed expression's own YAML
        own_mods = data.get("modifiers")
        if own_mods:
            expr.modifiers = list(expr.modifiers) + own_mods

        result[mood_name] = expr

    _expressions_cache = result
    return result


def load_styles() -> dict[str, FaceStyle]:
    """Load all face style themes from styles.yaml.

    Returns a dict keyed by style name (lowercase),
    e.g. {"kawaii": FaceStyle(...), "retro": FaceStyle(...), ...}.

    Color strings (hex, rgba) are converted to tuples for Pygame.
    Results are cached after the first call.
    """
    global _styles_cache
    if _styles_cache is not None:
        return _styles_cache

    raw = _load_yaml("styles.yaml")
    result: dict[str, FaceStyle] = {}

    for style_key, data in raw.items():
        eye_d = data.get("eye", {})
        mouth_d = data.get("mouth", {})
        x_d = data.get("x_eye", {})

        style = FaceStyle(
            name=data.get("name", style_key),
            description=data.get("description", ""),
            eye=EyeStyle(
                type=eye_d.get("type", "roundrect"),
                base_width=int(eye_d.get("base_width", 30)),
                base_height=int(eye_d.get("base_height", 38)),
                highlight_size=int(eye_d.get("highlight_size", 0)),
                highlight_color=_parse_color(eye_d.get("highlight_color", "rgba(255, 255, 255, 0.9)")),
                fill_color=_parse_color(eye_d.get("fill_color", "#f0f0f0")),
                glow_color=_parse_color(eye_d.get("glow_color", "rgba(240, 240, 240, 0.15)")),
                border_radius=_parse_radius(eye_d.get("border_radius", 0.28)),
                closed_radius=_parse_radius(eye_d.get("closed_radius", 0.35)),
                iris_color=_parse_color(eye_d.get("iris_color", "#0a0a12")),
                iris_size=float(eye_d.get("iris_size", 0.55)),
            ),
            mouth=MouthStyle(
                type=mouth_d.get("type", "offset"),
                base_width=int(mouth_d.get("base_width", 30)),
                stroke_width=int(mouth_d.get("stroke_width", 3)),
                color=_parse_color(mouth_d.get("color", "#f0f0f0")),
                teeth_color=_parse_color(mouth_d.get("teeth_color", "#ffffff")),
                lip_color=_parse_color(mouth_d.get("lip_color", "#121220")),
            ),
            x_eye=XEyeStyle(
                color=_parse_color(x_d.get("color", "#ff3c3c")),
                thickness=int(x_d.get("thickness", 3)),
                size=int(x_d.get("size", 22)),
            ),
        )
        result[style_key] = style

    _styles_cache = result
    return result


def load_moods() -> dict:
    """Load mood icons, state-to-mood mappings, and LED config from moods.yaml.

    Returns the raw dict with keys: 'icons', 'state_map', 'led_map', 'status_colors'.
    LED colors are kept as lists [r, g, b]; status_colors as lists [r, g, b].

    Results are cached after the first call.
    """
    global _moods_cache
    if _moods_cache is not None:
        return _moods_cache

    _moods_cache = _load_yaml("moods.yaml")
    return _moods_cache
