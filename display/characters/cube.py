"""CubeCharacter — the original isometric cube mascot.

Extracted from display/components/face.py into the character interface.
All drawing logic is preserved exactly as-is.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from PIL import Image, ImageDraw

from shared import Expression, FaceStyle, EyeStyle, XEyeStyle
from display.characters.base import Character

# ── Layout constants (from face/character.py) ───────────────────────────────

from display.layout import SCREEN_W, SCREEN_H, STATUS_H

FACE_AREA_H = SCREEN_H - STATUS_H

CX = SCREEN_W // 2           # 120
CY = FACE_AREA_H // 2 - 4    # ~124

BODY_W = 160
BODY_H = 150
BODY_RADIUS = 20

EYE_SPACING = 28
EYE_Y_OFFSET = -10
MOUTH_Y_OFFSET = 28
EDGE_INSET = 12

# ── Colors ──────────────────────────────────────────────────────────────────

BODY_FILL  = (26, 26, 46)
BODY_LIGHT = (28, 28, 48)
BODY_DARK  = (16, 16, 28)
EDGE_GLOW  = (0, 212, 210)
ERROR_RED  = (255, 60, 60)

# ── Shimmer phase offsets for each edge ────────────────────────────────────
# front: top, bottom, left, right; top-face: left-diag, right-diag, back
_EDGE_PHASE_OFFSETS = (0.0, 1.2, 2.4, 3.6, 0.8, 2.0, 3.2)


# ── Bezier helper ───────────────────────────────────────────────────────────

def _quadratic_bezier(p0: tuple, p1: tuple, p2: tuple, steps: int = 16) -> list[tuple]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        inv = 1.0 - t
        x = inv * inv * p0[0] + 2 * inv * t * p1[0] + t * t * p2[0]
        y = inv * inv * p0[1] + 2 * inv * t * p1[1] + t * t * p2[1]
        pts.append((int(x), int(y)))
    return pts


def _parse_eye_color(hex_str: Optional[str]) -> Optional[tuple[int, int, int]]:
    if not hex_str:
        return None
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return None


class CubeCharacter(Character):
    """The original dark charcoal isometric cube with glowing cyan edges."""

    name = "cube"

    # _accent is set by the renderer from config; used for edge glow
    # _glow_base falls back to _accent for shimmer/pulse effects

    # Last drawn body center — updated by draw(), used by idle_quirk()
    _last_cx: int = CX
    _last_cy: int = CY + STATUS_H
    _last_scale: float = 1.0

    def idle_quirk(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float) -> None:
        """Edge shimmer during idle.

        Each edge gets its own sine phase so the glow appears to travel
        around the cube like light catching different surfaces.
        """
        # ── Use the actual bounced body position from draw() ──────────
        body_cy = self._last_cy
        cube_cx = self._last_cx
        scale = self._last_scale
        fw = int(BODY_W * scale)
        fh = int(BODY_H * scale)
        dx = int(28 * scale)
        dy = int(22 * scale)
        fl = cube_cx - fw // 2 - dx // 3
        ft = body_cy - fh // 2 + dy // 3
        inset = int(EDGE_INSET * scale)
        gw = 2

        # ── Base glow pulse (kept as foundation) ──────────────────────
        base_t = (math.sin(now * 0.8) + 1.0) / 2.0
        base_factor = 0.6 + base_t * 0.4

        # ── Edge shimmer — each edge has its own phase offset ─────────
        def _shimmer_color(edge_idx: int) -> tuple[int, int, int]:
            phase = _EDGE_PHASE_OFFSETS[edge_idx]
            t = (math.sin(now * 1.2 + phase) + 1.0) / 2.0
            factor = 0.45 + t * 0.55  # wider range than base pulse
            # Blend with the base pulse for coherence
            blended = (factor + base_factor) * 0.5
            return (
                int(self._accent[0] * blended),
                int(self._accent[1] * blended),
                int(self._accent[2] * blended),
            )

        # Front face edges: top(0), bottom(1), left(2), right(3)
        draw.line([(fl + inset, ft), (fl + fw - inset, ft)],
                  fill=_shimmer_color(0), width=gw)
        draw.line([(fl + inset, ft + fh - 1), (fl + fw - inset, ft + fh - 1)],
                  fill=_shimmer_color(1), width=gw)
        draw.line([(fl, ft + inset), (fl, ft + fh - inset)],
                  fill=_shimmer_color(2), width=gw)
        draw.line([(fl + fw - 1, ft + inset), (fl + fw - 1, ft + fh - inset)],
                  fill=_shimmer_color(3), width=gw)

        # Top face edges: left-diag(4), right-diag(5), back(6)
        draw.line([(fl + inset, ft), (fl + inset + dx, ft - dy)],
                  fill=_shimmer_color(4), width=gw)
        draw.line([(fl + fw - inset, ft), (fl + fw - inset + dx, ft - dy)],
                  fill=_shimmer_color(5), width=gw)
        draw.line([(fl + inset + dx, ft - dy), (fl + fw - inset + dx, ft - dy)],
                  fill=_shimmer_color(6), width=gw)


    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float,
             compact: bool = False) -> None:
        body = expr.body
        scale = body.scale

        # Compact mode: shift face up and scale down for chat drawer
        compact_cy_offset = -35 if compact else 0
        compact_scale = 0.80 if compact else 1.0
        scale *= compact_scale
        bounce_amount = body.bounce_amount

        # ── Character-specific expression tweaks ───────────────────────
        tilt_val = body.tilt

        if expr.name == "excited":
            # Extra bounce for excitement
            bounce_amount = bounce_amount * 1.5

        if expr.name == "thinking":
            # Slow tilt oscillation — thoughtful head-rock
            tilt_val = tilt_val + math.sin(now * 1.5) * 4.0

        shake_x = 0
        shake_y = 0
        if expr.name == "error":
            # Subtle screen-shake
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        # ── Speaking body pulse — amplitude drives subtle scale ────────
        if amplitude > 0:
            scale = scale * (1.0 + amplitude * 0.03)

        # Bounce animation
        bounce_y = math.sin(now * body.bounce_speed * 2 * math.pi) * bounce_amount
        body_cy = int(CY + bounce_y) + STATUS_H + shake_y + compact_cy_offset

        # Tilt
        tilt_rad = math.radians(tilt_val)
        tilt_offset_x = int(math.sin(tilt_rad) * 4)
        cube_cx = CX + tilt_offset_x + shake_x

        # Store for idle_quirk() to use the correct bounced position
        self._last_cx = cube_cx
        self._last_cy = body_cy
        self._last_scale = scale

        self._draw_body(draw, cube_cx, body_cy, scale)

        # Face features on front face
        dx = int(28 * scale)
        dy = int(22 * scale)
        face_cx = cube_cx - dx // 3
        face_cy = body_cy + dy // 3

        # Store face center for decoration alignment
        self._last_face_cx = face_cx
        self._last_face_cy = face_cy

        self._draw_eyes(draw, face_cx, face_cy, expr, style, blink_factor, gaze_x, gaze_y)
        self._draw_mouth(draw, face_cx, face_cy, expr, style, amplitude)

        # ── Speaking overlay effects ───────────────────────────────────
        if amplitude > 0.05:
            self._apply_speaking_effects(draw, cube_cx, body_cy, face_cx, face_cy,
                                         scale, amplitude, now)

    def _apply_speaking_effects(self, draw: ImageDraw.ImageDraw,
                                cx: int, cy: int,
                                face_cx: int, face_cy: int,
                                scale: float, amplitude: float,
                                now: float) -> None:
        """Post-draw overlay effects when amplitude > 0 (speaking state).

        - Edge glow intensifies proportionally to amplitude
        - Subtle highlight behind eye area when amplitude is high
        """
        fw = int(BODY_W * scale)
        fh = int(BODY_H * scale)
        dx_3d = int(28 * scale)
        dy_3d = int(22 * scale)
        fl = cx - fw // 2 - dx_3d // 3
        ft = cy - fh // 2 + dy_3d // 3
        inset = int(EDGE_INSET * scale)

        # ── Edge glow intensification ──────────────────────────────────
        # Brighten edge glow proportionally to amplitude
        intensity = min(amplitude * 1.5, 1.0)
        bright_r = int(self._accent[0] + (255 - self._accent[0]) * intensity * 0.4)
        bright_g = int(self._accent[1] + (255 - self._accent[1]) * intensity * 0.4)
        bright_b = int(self._accent[2] + (255 - self._accent[2]) * intensity * 0.4)
        bright_color = (bright_r, bright_g, bright_b)

        # Redraw front top and bottom edges brighter
        draw.line([(fl + inset, ft), (fl + fw - inset, ft)],
                  fill=bright_color, width=2)
        draw.line([(fl + inset, ft + fh - 1), (fl + fw - inset, ft + fh - 1)],
                  fill=bright_color, width=2)

        # ── Eye glow highlight when amplitude is high ──────────────────
        if amplitude > 0.3:
            glow_a = (amplitude - 0.3) / 0.7  # 0..1 over the 0.3-1.0 range
            glow_r = int(6 + glow_a * 4)
            # Soft cyan glow behind each eye
            for side in (-1, 1):
                ex = face_cx + side * EYE_SPACING
                ey = face_cy + EYE_Y_OFFSET
                c = (
                    int(self._accent[0] * glow_a * 0.3),
                    int(self._accent[1] * glow_a * 0.3),
                    int(self._accent[2] * glow_a * 0.3),
                )
                draw.ellipse(
                    [ex - glow_r, ey - glow_r, ex + glow_r, ey + glow_r],
                    fill=c,
                )

    def _draw_body(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float) -> None:
        fw = int(BODY_W * scale)
        fh = int(BODY_H * scale)
        r = int(BODY_RADIUS * scale)
        dx = int(28 * scale)
        dy = int(22 * scale)

        fl = cx - fw // 2 - dx // 3
        ft = cy - fh // 2 + dy // 3

        # Top face (parallelogram)
        top_pts = [
            (fl + r, ft),
            (fl + fw - r, ft),
            (fl + fw - r + dx, ft - dy),
            (fl + r + dx, ft - dy),
        ]
        draw.polygon(top_pts, fill=BODY_LIGHT)

        # Right face (parallelogram)
        right_pts = [
            (fl + fw, ft + r),
            (fl + fw + dx, ft + r - dy),
            (fl + fw + dx, ft + fh - r - dy),
            (fl + fw, ft + fh - r),
        ]
        draw.polygon(right_pts, fill=BODY_DARK)

        # Front face (rounded rect)
        draw.rounded_rectangle(
            [fl, ft, fl + fw, ft + fh],
            radius=r, fill=BODY_FILL,
        )

        # Edge glow lines
        inset = int(EDGE_INSET * scale)
        gw = 2

        # Front face edges
        draw.line([(fl + inset, ft), (fl + fw - inset, ft)], fill=self._accent, width=gw)
        draw.line([(fl + inset, ft + fh - 1), (fl + fw - inset, ft + fh - 1)], fill=self._accent, width=gw)
        draw.line([(fl, ft + inset), (fl, ft + fh - inset)], fill=self._accent, width=gw)
        draw.line([(fl + fw - 1, ft + inset), (fl + fw - 1, ft + fh - inset)], fill=self._accent, width=gw)

        # Top face edges
        draw.line([(fl + inset, ft), (fl + inset + dx, ft - dy)], fill=self._accent, width=gw)
        draw.line([(fl + fw - inset, ft), (fl + fw - inset + dx, ft - dy)], fill=self._accent, width=gw)
        draw.line([(fl + inset + dx, ft - dy), (fl + fw - inset + dx, ft - dy)], fill=self._accent, width=gw)

        # Right face edges
        draw.line([(fl + fw - 1, ft + inset), (fl + fw - 1 + dx, ft + inset - dy)], fill=self._accent, width=gw)
        draw.line([(fl + fw - 1, ft + fh - inset), (fl + fw - 1 + dx, ft + fh - inset - dy)], fill=self._accent, width=gw)

    def _draw_eyes(self, draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   expr: Expression, style: FaceStyle,
                   blink_factor: float, gaze_x: float, gaze_y: float) -> None:
        eyes = expr.eyes
        s = style.eye

        openness = eyes.openness * blink_factor
        openness = openness * (1.0 - eyes.squint * 0.4)

        gx = max(-1.0, min(1.0, eyes.gaze_x + gaze_x))
        gy = max(-1.0, min(1.0, eyes.gaze_y + gaze_y))

        eye_y = cy + EYE_Y_OFFSET
        eye_color = _parse_eye_color(expr.eye_color_override)

        # Error mood: X eyes
        if expr.name == "error":
            for side in (-1, 1):
                ex = cx + side * EYE_SPACING
                self._draw_x_eye(draw, ex, eye_y, style.x_eye)
            return

        per_eye_overrides = [expr.left_eye, expr.right_eye]

        for side, override in zip((-1, 1), per_eye_overrides):
            ex = cx + side * EYE_SPACING

            eye_width = eyes.width
            eye_height = eyes.height
            eye_openness = openness

            if override is not None:
                if override.width is not None:
                    eye_width = override.width
                if override.height is not None:
                    eye_height = override.height
                if override.openness is not None:
                    eye_openness = override.openness * blink_factor
                    sq = override.squint if override.squint is not None else eyes.squint
                    eye_openness = eye_openness * (1.0 - sq * 0.4)

            ew = int(s.base_width * eye_width)
            eh = int(s.base_height * eye_height * max(eye_openness, 0.08))

            fill = eye_color if eye_color else s.fill_color

            if eye_openness < 0.3:
                radius_frac = s.closed_radius
            else:
                radius_frac = s.border_radius
            radius = int(min(ew, eh) * radius_frac)

            x0 = ex - ew // 2
            y0 = eye_y - eh // 2

            if s.type == "roundrect":
                draw.rounded_rectangle([x0, y0, x0 + ew, y0 + eh], radius=radius, fill=fill)
            elif s.type == "iris":
                draw.rounded_rectangle([x0, y0, x0 + ew, y0 + eh], radius=radius, fill=fill)
                min_dim = min(ew, eh)
                iris_r = int(min_dim * s.iris_size * 0.5)
                iris_cx = int(ex + gx * 5)
                iris_cy = int(eye_y + gy * 4)
                iris_color = s.iris_color
                draw.ellipse(
                    [iris_cx - iris_r, iris_cy - iris_r, iris_cx + iris_r, iris_cy + iris_r],
                    fill=iris_color,
                )
                if s.highlight_size > 0 and eye_openness > 0.3:
                    hl_r = s.highlight_size // 2
                    hl_x = x0 + ew - 6 - hl_r
                    hl_y = y0 + 4 + hl_r
                    draw.ellipse(
                        [hl_x - hl_r, hl_y - hl_r, hl_x + hl_r, hl_y + hl_r],
                        fill=s.highlight_color[:3],
                    )
            elif s.type == "dot":
                draw.ellipse([x0, y0, x0 + ew, y0 + eh], fill=fill)

    def _draw_x_eye(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, xs: XEyeStyle) -> None:
        half = xs.size // 2
        draw.line([(cx - half, cy - half), (cx + half, cy + half)],
                  fill=xs.color, width=xs.thickness)
        draw.line([(cx - half, cy + half), (cx + half, cy - half)],
                  fill=xs.color, width=xs.thickness)

    def _draw_mouth(self, draw: ImageDraw.ImageDraw, cx: int, cy: int,
                    expr: Expression, style: FaceStyle, amplitude: float) -> None:
        mouth = expr.mouth
        s = style.mouth

        mouth_y = cy + MOUTH_Y_OFFSET
        half_w = int(s.base_width * mouth.width * 0.5)

        total_open = mouth.openness + amplitude * 0.6
        total_open = min(total_open, 1.0)

        smile_offset = int(mouth.smile * 8)

        p0 = (cx - half_w, mouth_y)
        p2 = (cx + half_w, mouth_y)
        p1 = (cx, mouth_y - smile_offset)

        pts = _quadratic_bezier(p0, p1, p2)
        color = s.color[:3] if len(s.color) > 3 else s.color

        if total_open > 0.05:
            bottom_offset = int(total_open * 12)
            p1_bottom = (cx, mouth_y - smile_offset + bottom_offset)
            pts_bottom = _quadratic_bezier(p0, p1_bottom, p2)
            outline = pts + list(reversed(pts_bottom))
            if len(outline) >= 3:
                draw.polygon(outline, fill=color)
        else:
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=s.stroke_width)
