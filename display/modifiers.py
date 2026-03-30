"""Expression modifiers — data-driven animation behaviors.

Modifiers are small functions that adjust rendering parameters over time.
They're defined per-expression in ``shared/expressions.yaml`` and applied
by character draw() methods, replacing hardcoded per-mood if/else blocks.

Each modifier receives its YAML config dict, the current Expression, the
current time, and a mutable *overrides* dict it can write to.  Characters
read the overrides to adjust bounce, tilt, gaze, shake, etc.

Adding a new modifier:
  1. Write an ``_apply_<name>(cfg, expr, now, out)`` function here.
  2. Register it in ``_REGISTRY``.
  3. Add it to the expression's ``modifiers:`` list in expressions.yaml.
"""

from __future__ import annotations

import math
import random
from shared import Expression


# ── Override keys ──────────────────────────────────────────────────────────
# Characters should read these from the dict returned by apply_modifiers().
#
#   bounce_factor   float   multiply bounce_amount (default 1.0)
#   extra_tilt      float   add to body.tilt (degrees)
#   shake_x         int     random pixel offset X
#   shake_y         int     random pixel offset Y
#   gaze_x_offset   float   add to gaze_x (-1..1 range)
#   swap_eyes       bool    swap left/right per-eye overrides


def apply_modifiers(
    expr: Expression,
    modifiers: list[dict],
    now: float,
) -> dict:
    """Apply all modifiers for *expr*, returning an overrides dict.

    Characters call this once per frame and read the keys they care about.
    Unknown modifier types are silently skipped (forward-compatible).
    """
    out: dict = {}
    for mod in modifiers:
        fn = _REGISTRY.get(mod.get("type", ""))
        if fn is not None:
            fn(mod, expr, now, out)
    return out


# ── Modifier implementations ──────────────────────────────────────────────

def _apply_bounce_boost(cfg: dict, expr: Expression,
                        now: float, out: dict) -> None:
    """Multiply bounce amplitude by a factor.

    YAML: ``- type: bounce_boost``
          ``  factor: 1.4``
    """
    factor = cfg.get("factor", 1.4)
    out["bounce_factor"] = out.get("bounce_factor", 1.0) * factor


def _apply_tilt_oscillation(cfg: dict, expr: Expression,
                            now: float, out: dict) -> None:
    """Sinusoidal tilt variation.

    YAML: ``- type: tilt_oscillation``
          ``  speed: 1.2``
          ``  amount: 3.5``
    """
    speed = cfg.get("speed", 1.2)
    amount = cfg.get("amount", 3.5)
    out["extra_tilt"] = out.get("extra_tilt", 0.0) + math.sin(now * speed) * amount


def _apply_eye_swap(cfg: dict, expr: Expression,
                    now: float, out: dict) -> None:
    """Periodically swap which eye is big/small (thinking look).

    Uses the *rate of change* of the swap curve as a gaze offset so the
    character naturally glances in the direction of the lid transition —
    similar to how curious works with gaze asymmetry.

    YAML: ``- type: eye_swap``
          ``  cycle: 7.0``
          ``  gaze_influence: 0.3``
    """
    cycle = cfg.get("cycle", 7.0)
    gaze_inf = cfg.get("gaze_influence", 0.3)

    phase = (now % cycle) / cycle
    # Smooth sinusoidal blend: 0→1→0 over the cycle.
    # 0.0 = original eye arrangement, 1.0 = fully swapped.
    swap_blend = (math.sin(phase * 2 * math.pi - math.pi / 2) + 1.0) / 2.0
    out["swap_blend"] = swap_blend

    # Derivative of swap curve — peaks at crossover where eye heights
    # change fastest.  This ties the lateral "look" to the lid transition.
    swap_rate = math.cos(phase * 2 * math.pi - math.pi / 2)
    out["gaze_x_offset"] = out.get("gaze_x_offset", 0.0) + swap_rate * gaze_inf


def _apply_shake(cfg: dict, expr: Expression,
                 now: float, out: dict) -> None:
    """Random per-frame position jitter (error/glitch).

    YAML: ``- type: shake``
          ``  range: 2``
    """
    r = cfg.get("range", 2)
    out["shake_x"] = random.randint(-r, r)
    out["shake_y"] = random.randint(-r, r)


def _apply_squint_pulse(cfg: dict, expr: Expression,
                        now: float, out: dict) -> None:
    """Slow squint modulation (focused concentration).

    YAML: ``- type: squint_pulse``
          ``  speed: 0.8``
          ``  amount: 0.15``
    """
    speed = cfg.get("speed", 0.8)
    amount = cfg.get("amount", 0.15)
    out["squint_offset"] = amount * (0.5 + 0.5 * math.sin(now * speed))


def _apply_gaze_wander(cfg: dict, expr: Expression,
                       now: float, out: dict) -> None:
    """Slow lateral gaze drift (curious scanning).

    YAML: ``- type: gaze_wander``
          ``  speed: 0.6``
          ``  range: 0.25``
    """
    speed = cfg.get("speed", 0.6)
    r = cfg.get("range", 0.25)
    out["gaze_x_offset"] = out.get("gaze_x_offset", 0.0) + math.sin(now * speed) * r


# ── Registry ──────────────────────────────────────────────────────────────

_REGISTRY: dict[str, callable] = {
    "bounce_boost": _apply_bounce_boost,
    "tilt_oscillation": _apply_tilt_oscillation,
    "eye_swap": _apply_eye_swap,
    "shake": _apply_shake,
    "squint_pulse": _apply_squint_pulse,
    "gaze_wander": _apply_gaze_wander,
}
