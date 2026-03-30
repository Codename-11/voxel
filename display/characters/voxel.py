"""VoxelCharacter — the signature Voxel face.

Eyes only. Solid glowing pill shapes on the dark visor. No pupils, no
highlights, no mouth. All expression through shape and cuts:

    neutral    →  full pill shapes
    happy      →  bottom half cut (upward crescents ^_^)
    angry      →  diagonal top cut (inner edge lower)
    sad        →  diagonal top cut (outer edge lower, droopy)
    surprised  →  taller rounder pills
    sleepy     →  thin horizontal slits
    thinking   →  asymmetric (one open, one narrowed)
    error      →  red X

Inspired by Deskimon/EMO desktop companions.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from shared import Expression, FaceStyle
from display.characters.base import Character
from display.layout import SCREEN_W, SCREEN_H, STATUS_H

# ── Viewport ──────────────────────────────────────────────────────────────

FACE_AREA_H = SCREEN_H - STATUS_H          # 232
CX = SCREEN_W // 2                          # 120
CY = STATUS_H + int(FACE_AREA_H * 0.46)    # ~155

# ── Eye geometry ──────────────────────────────────────────────────────────

EYE_SPACING  = 30        # center-to-center half-distance
EYE_BASE_W   = 40        # base width
EYE_BASE_H   = 72        # base height — tall vertical pill
EYE_RADIUS   = 0.50      # corner radius = 50% of width → true capsule ends
GLOW_PAD     = 6         # subtle halo padding

# ── Background (must match renderer) ──────────────────────────────────────

BG = (10, 10, 15)


def _hex_to_rgb(hex_str: str | None) -> tuple[int, int, int] | None:
    if not hex_str:
        return None
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return None


def _scale_color(c: tuple, f: float) -> tuple:
    return tuple(min(255, int(v * f)) for v in c)


# ══════════════════════════════════════════════════════════════════════════

class VoxelCharacter(Character):
    """Eyes only — solid glowing pills with emotion cuts."""

    name = "voxel"

    def idle_quirk(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float) -> None:
        pass  # glow pulse handled in draw()

    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float,
             compact: bool = False) -> None:
        from display.modifiers import apply_modifiers

        body = expr.body
        scale = body.scale

        # Compact mode: shift face up and scale down for chat drawer
        compact_cy_offset = -35 if compact else 0
        compact_scale = 0.80 if compact else 1.0
        scale *= compact_scale

        # ── Apply modifiers (data-driven, replaces hardcoded per-mood) ─
        mods = apply_modifiers(expr, expr.modifiers, now)
        bounce_amt = body.bounce_amount * mods.get("bounce_factor", 1.0)
        tilt = body.tilt + mods.get("extra_tilt", 0.0)
        shake_x = mods.get("shake_x", 0)
        shake_y = mods.get("shake_y", 0)

        if amplitude > 0:
            scale *= 1.0 + amplitude * 0.015

        # ── Position ──────────────────────────────────────────────────
        bounce_y = math.sin(now * body.bounce_speed * 2 * math.pi) * bounce_amt
        face_cy = int(CY + bounce_y) + shake_y + compact_cy_offset
        face_cx = CX + int(math.sin(math.radians(tilt)) * 3) + shake_x

        self._last_face_cx = face_cx
        self._last_face_cy = face_cy

        # ── Glow pulse ────────────────────────────────────────────────
        glow_t = (math.sin(now * 0.5) + 1.0) / 2.0
        glow = 0.85 + glow_t * 0.15

        if amplitude > 0.1:
            glow = min(1.0, glow + amplitude * 0.2)

        # ── Color ─────────────────────────────────────────────────────
        accent = self._accent
        override_color = _hex_to_rgb(expr.eye_color_override)
        base = override_color if override_color else accent

        # ── Error: X eyes ─────────────────────────────────────────────
        if expr.name == "error":
            for side in (-1, 1):
                ex = face_cx + side * int(EYE_SPACING * scale)
                self._draw_x(draw, ex, face_cy, scale)
            self._last_left_eye = (face_cx - int(EYE_SPACING * scale), face_cy)
            self._last_right_eye = (face_cx + int(EYE_SPACING * scale), face_cy)
            return

        # ── Compute shared eye state ──────────────────────────────────
        eyes = expr.eyes
        openness = eyes.openness * blink_factor * (1.0 - eyes.squint * 0.5)
        smile = expr.mouth.smile if hasattr(expr, 'mouth') else 0.0

        # Modifier gaze influence (eye_swap uses this for natural look)
        gx = max(-1.0, min(1.0, eyes.gaze_x + gaze_x + mods.get("gaze_x_offset", 0.0)))
        gy = max(-1.0, min(1.0, eyes.gaze_y + gaze_y))

        # ── Gaze: position shift + size asymmetry ─────────────────────
        gaze_shift_x = int(gx * 35 * scale)
        gaze_shift_y = int(gy * 16 * scale)

        per_eye = [expr.left_eye, expr.right_eye]
        swap_blend = mods.get("swap_blend", 0.0)

        for idx, (side, ovr_orig) in enumerate(zip((-1, 1), per_eye)):
            ex = face_cx + side * int(EYE_SPACING * scale) + gaze_shift_x
            ey = face_cy + gaze_shift_y

            # Per-eye values (start from shared base)
            ew_m = eyes.width
            eh_m = eyes.height
            eo = openness
            eye_tilt = 0.0

            # Resolve per-eye overrides, blending if eye_swap is active.
            # swap_blend smoothly lerps between original and swapped
            # override sets so there's no hard pop at the crossover.
            ovr_swap = per_eye[1 - idx]  # the other eye's override

            if swap_blend < 0.01:
                ovr = ovr_orig
            elif swap_blend > 0.99:
                ovr = ovr_swap
            else:
                # Blend the two override sets
                ovr = self._blend_overrides(ovr_orig, ovr_swap, swap_blend)

            if ovr is not None:
                if ovr.width is not None:
                    ew_m = ovr.width
                if ovr.height is not None:
                    eh_m = ovr.height
                if ovr.openness is not None:
                    eo = ovr.openness * blink_factor
                    sq = ovr.squint if ovr.squint is not None else eyes.squint
                    eo *= (1.0 - sq * 0.5)
                if ovr.tilt is not None:
                    eye_tilt = ovr.tilt

            # Size asymmetry: eye on the gaze side is taller
            # side=-1 is left, side=1 is right. gx>0 = looking right.
            # Height changes more than width for dramatic pill effect
            height_bias = 1.0 + gx * side * 0.35   # ±35% height diff
            width_bias  = 1.0 + gx * side * 0.08   # ±8% width diff (subtle)

            ew = int(EYE_BASE_W * scale * ew_m * width_bias)
            eh = int(EYE_BASE_H * scale * eh_m * max(eo, 0.04) * height_bias)
            fill = _scale_color(base, glow)

            self._draw_eye(draw, ex, ey, ew, eh, eo, eye_tilt * side,
                           smile, scale, fill, base, glow, side)

            # Store eye centers for decoration positioning
            if side == -1:
                self._last_left_eye = (ex, ey)
            else:
                self._last_right_eye = (ex, ey)

    def _draw_eye(self, draw: ImageDraw.ImageDraw,
                  cx: int, cy: int, ew: int, eh: int,
                  openness: float, tilt: float, smile: float,
                  scale: float, fill: tuple, base: tuple,
                  glow: float, side: int = 1) -> None:
        """Render one solid pill eye with optional cuts.

        Args:
            side: -1 for left eye, +1 for right eye (used for tilt direction)
        """

        # Enforce minimum pill aspect ratio — prevents circular eyes
        # on moods with low height * openness (frustrated, focused, etc.)
        # Skip when openness is low — sleepy/drowsy eyes are meant to be
        # flat narrow slits, not tall pills.
        if openness > 0.4:
            eh = max(eh, int(ew * 1.35))

        x0 = cx - ew // 2
        y0 = cy - eh // 2
        x1 = x0 + ew
        y1 = y0 + eh
        # Width-based radius keeps capsule ends consistent
        radius = ew // 2

        # ── Subtle glow halo (pill-shaped, not circular) ─────────────
        gp = int(GLOW_PAD * scale)
        glow_c = _scale_color(base, 0.12 * glow)
        glow_r = min(ew // 2 + gp, (eh + 2 * gp) // 2)
        draw.rounded_rectangle(
            [x0 - gp, y0 - gp, x1 + gp, y1 + gp],
            radius=glow_r, fill=glow_c,
        )

        # ── Closed states ─────────────────────────────────────────────
        if openness < 0.15:
            if smile > 0.3:
                # Happy close: upward crescent arcs (^_^)
                self._draw_happy_arc(draw, cx, cy, ew, scale, fill)
            else:
                # Flat closed: thin horizontal pill
                lh = max(3, int(4 * scale))
                r = max(2, lh)
                draw.rounded_rectangle(
                    [x0, cy - lh // 2, x1, cy + lh // 2],
                    radius=r, fill=fill,
                )
            return

        # ── Open eye: solid pill ──────────────────────────────────────
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)

        # ── Emotion cuts (mask with BG color) ─────────────────────────
        # Overshoots (-3/+3) ensure clean masking over rounded corners.

        # Happy squint: cut bottom portion (upward crescent)
        if smile > 0.4 and openness < 0.8:
            cut_h = int(eh * 0.35 * min(smile, 1.0))
            draw.rectangle([x0 - 3, y1 - cut_h, x1 + 3, y1 + 3], fill=BG)

        # Tilt cuts (angry/sad eyebrow angles)
        # tilt > 0 → angry V-brow (cut inner top corner)
        # tilt < 0 → sad/droopy (cut outer top corner)
        # "inner" = closer to center, "outer" = farther from center
        if abs(tilt) > 2.0:
            tilt_px = int(abs(tilt) * 0.8 * scale)
            tilt_px = min(tilt_px, eh // 2)

            if tilt > 0:
                # Angry: cut inner top corner
                if side > 0:
                    draw.polygon([
                        (x0 - 3, y0 - 3),
                        (x0 + ew * 2 // 3, y0 - 3),
                        (x0 - 3, y0 + tilt_px),
                    ], fill=BG)
                else:
                    draw.polygon([
                        (x1 + 3, y0 - 3),
                        (x1 - ew * 2 // 3, y0 - 3),
                        (x1 + 3, y0 + tilt_px),
                    ], fill=BG)
            else:
                # Sad/droopy: cut outer top corner
                if side > 0:
                    draw.polygon([
                        (x1 + 3, y0 - 3),
                        (x1 - ew * 2 // 3, y0 - 3),
                        (x1 + 3, y0 + tilt_px),
                    ], fill=BG)
                else:
                    draw.polygon([
                        (x0 - 3, y0 - 3),
                        (x0 + ew * 2 // 3, y0 - 3),
                        (x0 - 3, y0 + tilt_px),
                    ], fill=BG)

    @staticmethod
    def _blend_overrides(a, b, t: float):
        """Lerp two PerEyeOverride objects (either may be None)."""
        from shared import PerEyeOverride

        if a is None and b is None:
            return None
        a = a or PerEyeOverride()
        b = b or PerEyeOverride()

        def _lo(av, bv):
            if av is None and bv is None:
                return None
            fa = av if av is not None else 1.0
            fb = bv if bv is not None else 1.0
            return fa + (fb - fa) * t

        return PerEyeOverride(
            openness=_lo(a.openness, b.openness),
            height=_lo(a.height, b.height),
            width=_lo(a.width, b.width),
            squint=_lo(a.squint, b.squint),
            tilt=_lo(a.tilt, b.tilt),
        )

    def _draw_happy_arc(self, draw: ImageDraw.ImageDraw,
                        cx: int, cy: int, width: int,
                        scale: float, fill: tuple) -> None:
        """Draw upward crescent for happy-closed eyes (^_^)."""
        hw = width // 2
        arc_h = int(10 * scale)
        thick = max(3, int(5 * scale))
        steps = 20

        pts_top = []
        pts_bot = []
        for i in range(steps + 1):
            t = i / steps
            x = cx - hw + int(t * width)
            curve = math.sin(t * math.pi) * arc_h
            pts_top.append((x, int(cy - curve - thick // 2)))
            pts_bot.append((x, int(cy - curve + thick // 2)))

        poly = pts_top + list(reversed(pts_bot))
        if len(poly) >= 3:
            draw.polygon(poly, fill=fill)

    def _draw_x(self, draw: ImageDraw.ImageDraw,
                cx: int, cy: int, scale: float) -> None:
        """Red X for error state — pill-shaped glow to match eye proportions."""
        half_w = int(16 * scale)
        half_h = int(24 * scale)  # taller to maintain pill proportion
        w = max(4, int(5 * scale))
        color = (255, 60, 60)
        # Pill-shaped glow
        gw = half_w + int(4 * scale)
        gh = half_h + int(4 * scale)
        gr = min(gw, gh)
        draw.rounded_rectangle(
            [cx - gw, cy - gh, cx + gw, cy + gh],
            radius=gr, fill=(50, 8, 8),
        )
        draw.line([(cx - half_w, cy - half_h), (cx + half_w, cy + half_h)],
                  fill=color, width=w)
        draw.line([(cx - half_w, cy + half_h), (cx + half_w, cy - half_h)],
                  fill=color, width=w)
