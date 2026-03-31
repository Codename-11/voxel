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

EYE_SPACING  = 39        # center-to-center half-distance
EYE_BASE_W   = 46        # base width (larger for presence on 240px screen)
EYE_BASE_H   = 88        # base height — tall vertical pill (closer to excited height)
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
             amplitude: float, now: float) -> None:
        from display.modifiers import apply_modifiers

        body = expr.body
        scale = body.scale

        # ── Apply modifiers (data-driven, replaces hardcoded per-mood) ─
        mods = apply_modifiers(expr, expr.modifiers, now)
        bounce_amt = body.bounce_amount * mods.get("bounce_factor", 1.0)
        tilt = body.tilt + mods.get("extra_tilt", 0.0)
        shake_x = mods.get("shake_x", 0)
        shake_y = mods.get("shake_y", 0)

        if amplitude > 0:
            scale *= 1.0 + amplitude * 0.015

        # ── Position (float precision, round once at draw time) ─────
        bounce_y = math.sin(now * body.bounce_speed * 2 * math.pi) * bounce_amt
        face_cy_f = CY + bounce_y + shake_y
        face_cx_f = CX + math.sin(math.radians(tilt)) * 3 + shake_x
        face_cy = round(face_cy_f)
        face_cx = round(face_cx_f)

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
                ex = round(face_cx_f + side * EYE_SPACING * scale)
                self._draw_x(draw, ex, face_cy, scale)
            self._last_left_eye = (round(face_cx_f - EYE_SPACING * scale), face_cy)
            self._last_right_eye = (round(face_cx_f + EYE_SPACING * scale), face_cy)
            return

        # ── Compute shared eye state ──────────────────────────────────
        eyes = expr.eyes
        openness = eyes.openness * blink_factor * (1.0 - eyes.squint * 0.5)
        smile = expr.mouth.smile if hasattr(expr, 'mouth') else 0.0

        # Modifier gaze influence (eye_swap uses this for natural look)
        gx = max(-1.0, min(1.0, eyes.gaze_x + gaze_x + mods.get("gaze_x_offset", 0.0)))
        gy = max(-1.0, min(1.0, eyes.gaze_y + gaze_y))

        # ── Gaze: compute in float, round per-eye at draw time ────────
        gaze_shift_x_f = gx * 35 * scale
        gaze_shift_y_f = gy * 16 * scale
        eye_spacing_f = EYE_SPACING * scale

        per_eye = [expr.left_eye, expr.right_eye]
        swap_blend = mods.get("swap_blend", 0.0)

        for idx, (side, ovr_orig) in enumerate(zip((-1, 1), per_eye)):
            # Both eyes translate as a rigid unit — same gaze shift
            ex = round(face_cx_f + side * eye_spacing_f + gaze_shift_x_f)
            ey = round(face_cy_f + gaze_shift_y_f)

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

            # Gaze-proportional eye sizing: width-only perspective.
            # The eye on the gaze side shrinks slightly, opposite grows.
            # Height stays uniform — height differences caused visible
            # twitching when combined with per-eye overrides and modifiers.
            gaze_perspective = gx * side  # positive when this eye is on gaze side
            perspective_w = 1.0 - gaze_perspective * 0.10   # ±10% width

            ew = round(EYE_BASE_W * scale * ew_m * perspective_w)
            eh = round(EYE_BASE_H * scale * eh_m * max(eo, 0.04))
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

        Features:
        - Sleepy bar eyes: when openness < 0.3, maintain wide bar shape
          with rounded ends instead of shrinking to a circle.
        - Happy curve cutout: when smiling, the bottom of the eye gets a
          curved mask (like FluxGarage RoboEyes happy expression).
        - Tilt cuts for angry/sad brow angles.

        Args:
            side: -1 for left eye, +1 for right eye (used for tilt direction)
        """

        # ── Sleepy bar-shaped eyes ────────────────────────────────────
        # When openness is low (sleepy, low_battery, critical_battery),
        # keep the width at full and only reduce height. This produces
        # an elongated horizontal bar with rounded ends, not a small circle.
        # The minimum height ensures the bar is always visible.
        if openness <= 0.3 and openness > 0.0:
            # Preserve full pill width, clamp height to a bar shape.
            # Min height = 40% of width for a nice rounded-end bar.
            min_bar_h = max(int(ew * 0.4), 6)
            eh = max(eh, min_bar_h)
            # Clamp to bar-like proportions: if height < 50% of width,
            # it should look like a flat bar, not an ellipse.
            # This flag tells the renderer to use a small fillet radius.
            self._bar_mode = eh < ew * 0.5

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
        # Bar mode: small fillet radius for flat bar shape.
        # Normal mode: width-based radius for capsule/pill ends.
        bar_mode = getattr(self, '_bar_mode', False)
        if bar_mode and eh < ew * 0.5:
            radius = max(3, eh // 3)  # small fillet, straight edges
        else:
            radius = ew // 2  # full capsule ends
        self._bar_mode = False  # reset for next frame

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
                # Flat closed: horizontal bar with small filleted ends.
                # NOT a capsule — straight top/bottom edges with small
                # corner radii, like a rounded rectangle bar.
                bar_h = max(5, int(7 * scale))
                fillet = max(2, int(3 * scale))  # small fillet, not semicircle
                draw.rounded_rectangle(
                    [x0, cy - bar_h // 2, x1, cy + bar_h // 2],
                    radius=fillet, fill=fill,
                )
            return

        # ── Open eye: solid pill ──────────────────────────────────────
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)

        # ── Emotion cuts (mask with BG color) ─────────────────────────
        # Overshoots (-3/+3) ensure clean masking over rounded corners.

        # Happy eye curve cutout: instead of a flat rectangle cut,
        # draw a curved (smile-shaped) mask at the bottom of the eye.
        # This creates the FluxGarage RoboEyes "happy eye" look where
        # the bottom of the eye has an upward arc, like ^_^.
        if smile > 0.3 and openness < 0.85:
            self._draw_happy_cutout(draw, x0, y0, x1, y1, ew, eh,
                                    smile, scale)

        # Tilt cuts (angry/sad eyebrow angles)
        # tilt > 0 → angry V-brow (sharp triangle, cut inner top corner)
        # tilt < 0 → sad/droopy (curved arc, cut outer top corner)
        # "inner" = closer to center, "outer" = farther from center
        if abs(tilt) > 2.0:
            tilt_px = int(abs(tilt) * 0.8 * scale)
            tilt_px = min(tilt_px, eh // 2)

            if tilt > 0:
                # Angry: sharp triangle cut on inner top corner (V-brow)
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
                # Sad/droopy: curved arc eyelid on outer top corner.
                # Softer than a triangle — feels heavy/weighed-down.
                # The arc sweeps from the inner edge (flat, at y0) down
                # to the outer edge (droops by tilt_px).
                self._draw_sad_eyelid(draw, x0, y0, x1, ew, tilt_px, side)

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

    def _draw_happy_cutout(self, draw: ImageDraw.ImageDraw,
                           x0: int, y0: int, x1: int, y1: int,
                           ew: int, eh: int,
                           smile: float, scale: float) -> None:
        """Draw a curved bottom cutout on open eyes for happy/excited moods.

        Instead of a flat rectangle cut, this draws a smile-shaped curve
        at the bottom of the pill eye, creating the "happy eye" effect
        inspired by FluxGarage RoboEyes. The curve depth is proportional
        to the smile amount for smooth transitions.

        The mask is drawn in BG color to "erase" the bottom of the pill,
        leaving the pill shape visible above the curve — like looking
        through a smile-shaped window.
        """
        # How much of the eye's bottom to cut — scales with smile amount.
        # At smile=1.0, cut up to 40% of eye height. At smile=0.3, ~12%.
        cut_fraction = 0.40 * min(smile, 1.0)
        cut_h = int(eh * cut_fraction)
        if cut_h < 3:
            return

        # The curve baseline is at the bottom of the eye.
        # The arc rises upward from the bottom-left and bottom-right corners.
        curve_y_base = y1
        steps = 16
        points = []

        for i in range(steps + 1):
            t = i / steps
            px = x0 + int(t * ew)
            # Sinusoidal arc: peaks in the center, zero at edges.
            # This creates the upward-curve smile shape.
            curve_rise = math.sin(t * math.pi) * cut_h
            py = int(curve_y_base - curve_rise)
            points.append((px, py))

        # Close the polygon along the bottom edge (below the curve)
        points.append((x1 + 3, y1 + 3))
        points.append((x0 - 3, y1 + 3))

        if len(points) >= 3:
            draw.polygon(points, fill=BG)

    def _draw_sad_eyelid(self, draw: ImageDraw.ImageDraw,
                         x0: int, y0: int, x1: int,
                         ew: int, droop_px: int, side: int) -> None:
        """Draw a curved droopy eyelid overlay for sad moods.

        Unlike the sharp triangle used for angry, this draws a smooth
        arc that curves from flat on the inner edge to drooping on
        the outer edge — like a heavy, weighed-down eyelid.

        Uses quadratic (t^2) curve: flat near inner edge, increasing
        droop toward outer edge.

        Left eye (side=-1):  outer=left(x0),  inner=right(x1) — droops left
        Right eye (side=+1): outer=right(x1), inner=left(x0)  — droops right
        """
        steps = 14
        curve_pts = []
        pad = 3  # overshoot for clean masking over rounded corners

        # Iterate left-to-right across the eye
        for i in range(steps + 1):
            t = i / steps  # 0.0 = left edge, 1.0 = right edge
            px = (x0 - pad) + int(t * (ew + 2 * pad))

            if side < 0:
                # Left eye: outer is LEFT (t=0), inner is RIGHT (t=1)
                # Droop high at t=0, flat at t=1
                droop = (1.0 - t) ** 2 * droop_px
            else:
                # Right eye: outer is RIGHT (t=1), inner is LEFT (t=0)
                # Flat at t=0, droop high at t=1
                droop = t * t * droop_px

            py = int(y0 - pad + droop)
            curve_pts.append((px, py))

        # Close polygon: curve defines bottom edge of mask,
        # top edge runs along the top of the eye.
        points = curve_pts + [
            (x1 + pad, y0 - pad),
            (x0 - pad, y0 - pad),
        ]

        if len(points) >= 3:
            draw.polygon(points, fill=BG)

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
