"""BMOCharacter — BMO from Adventure Time.

Two modes:
- "bmo": Full-screen face (screen fills display, like looking at BMO's screen)
- "bmo-full": Shows the full game console body with controls

BMO's eyes are oval black dots placed wide apart. The mouth is a small
simple line/curve. Both variants use shared drawing functions with a
scale parameter.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from shared import Expression, FaceStyle
from display.characters.base import Character
from display.layout import SCREEN_W, SCREEN_H, STATUS_H

# ── BMO Colors (Adventure Time palette) ────────────────────────────────────

BMO_BODY       = (0, 196, 160)
BMO_BODY_DARK  = (0, 156, 128)
BMO_BODY_LIGHT = (20, 216, 180)
BMO_SCREEN_BG  = (168, 216, 176)
BMO_BEZEL      = (0, 140, 115)
BMO_FACE       = (20, 20, 20)
BMO_HIGHLIGHT  = (200, 230, 205)   # eye highlight dot
BMO_DPAD       = (40, 60, 55)
BMO_DPAD_LIGHT = (60, 80, 75)
BMO_BTN_RED    = (220, 60, 60)
BMO_BTN_BLUE   = (80, 110, 220)
BMO_SPEAKER    = (0, 140, 115)

FACE_AREA_TOP = STATUS_H
FACE_AREA_H = SCREEN_H - STATUS_H
CX = SCREEN_W // 2
CY = FACE_AREA_TOP + FACE_AREA_H // 2

# ── Module-level state for idle effects ────────────────────────────────────

_game_state = {
    "x": 20.0, "dir": 1, "y": 0.0, "jumping": False,
    "coin_x": 35, "coin_visible": True, "coin_timer": 0.0,
    "last_time": 0.0,
}
_glitch_state = {"next_glitch": 0.0, "glitch_until": 0.0, "offset": 0}
_cursor_state = {"visible": True, "next_toggle": 0.0}
_heart_particles: list[dict] = []
_spinner_state = {"index": 0, "next_advance": 0.0}


def _bezier(p0: tuple, p1: tuple, p2: tuple, steps: int = 20) -> list[tuple]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        inv = 1.0 - t
        x = inv * inv * p0[0] + 2 * inv * t * p1[0] + t * t * p2[0]
        y = inv * inv * p0[1] + 2 * inv * t * p1[1] + t * t * p2[1]
        pts.append((int(x), int(y)))
    return pts


# ═══════════════════════════════════════════════════════════════════════════
# BMO Face-only (fills screen — like looking at BMO's display)
# ═══════════════════════════════════════════════════════════════════════════

class BMOCharacter(Character):
    """BMO face filling the screen — large eyes, expressive, clean."""

    name = "bmo"

    def idle_quirk(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float) -> None:
        """Pixel game, screen glitch, and cursor blink — BMO's personality."""
        global _game_state, _glitch_state, _cursor_state

        # ── Pixel game simulation (bottom-right ~40x30 area) ──────────
        gs = _game_state
        dt = now - gs["last_time"] if gs["last_time"] > 0 else 0.05
        gs["last_time"] = now
        dt = min(dt, 0.1)  # clamp to avoid jumps

        game_ox = SCREEN_W - 48  # game area origin x
        game_oy = SCREEN_H - 36  # game area origin y

        # Move pixel character left/right
        gs["x"] += gs["dir"] * 18 * dt
        if gs["x"] > 38:
            gs["x"] = 38
            gs["dir"] = -1
        elif gs["x"] < 4:
            gs["x"] = 4
            gs["dir"] = 1

        # Occasional jump
        if not gs["jumping"] and random.random() < 0.01:
            gs["jumping"] = True
            gs["y"] = 0.0
        if gs["jumping"]:
            gs["y"] += dt * 4.0
            jump_h = math.sin(gs["y"] * math.pi) * 8
            if gs["y"] >= 1.0:
                gs["jumping"] = False
                gs["y"] = 0.0
                jump_h = 0.0
        else:
            jump_h = 0.0

        # Draw tiny ground line
        draw.line(
            [(game_ox, game_oy + 24), (game_ox + 40, game_oy + 24)],
            fill=BMO_FACE, width=1,
        )

        # Draw pixel character (3x5 rectangle)
        px = game_ox + int(gs["x"])
        py = game_oy + 19 - int(jump_h)
        draw.rectangle([px, py, px + 3, py + 5], fill=BMO_FACE)

        # Coin (blinking dot)
        gs["coin_timer"] += dt
        if gs["coin_timer"] > 3.0:
            gs["coin_timer"] = 0.0
            gs["coin_visible"] = True
            gs["coin_x"] = random.randint(8, 34)
        if gs["coin_visible"]:
            # Blink the coin at 3Hz
            if int(now * 3) % 2 == 0:
                cx_coin = game_ox + gs["coin_x"]
                cy_coin = game_oy + 17
                draw.rectangle([cx_coin, cy_coin, cx_coin + 2, cy_coin + 2], fill=BMO_FACE)
            # Check collection
            if abs(gs["x"] - gs["coin_x"]) < 5 and jump_h < 2:
                gs["coin_visible"] = False

        # ── Screen glitch (every 15-20s, lasts 2-3 frames) ───────────
        gl = _glitch_state
        if now >= gl["next_glitch"] and now >= gl["glitch_until"]:
            gl["next_glitch"] = now + 15.0 + random.random() * 5.0
            gl["glitch_until"] = now + 0.15  # ~3 frames at 20fps
            gl["offset"] = random.choice([-2, -1, 1, 2])

        if now < gl["glitch_until"]:
            # Draw a few offset scan lines in the middle band
            band_y = SCREEN_H // 2 - 10
            for sy in range(band_y, band_y + 20, 3):
                draw.line(
                    [(gl["offset"], sy), (SCREEN_W - 1 + gl["offset"], sy)],
                    fill=(158, 206, 166), width=1,
                )

        # ── Cursor blink (bottom-left terminal prompt) ────────────────
        cs = _cursor_state
        if now >= cs["next_toggle"]:
            cs["visible"] = not cs["visible"]
            cs["next_toggle"] = now + 0.5
        if cs["visible"]:
            cur_x = 12
            cur_y = SCREEN_H - 14
            draw.rectangle([cur_x, cur_y, cur_x + 8, cur_y + 2], fill=BMO_FACE)

    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float) -> None:
        body = expr.body
        bounce_y = math.sin(now * body.bounce_speed * 2 * math.pi) * body.bounce_amount * 0.5

        # ── Screen background (mood-reactive) ─────────────────────────
        mood = expr.name
        screen_bg = BMO_SCREEN_BG

        if mood == "excited":
            # Flicker slightly brighter green
            boost = int(10 * (0.5 + 0.5 * math.sin(now * 8)))
            screen_bg = (BMO_SCREEN_BG[0], min(255, BMO_SCREEN_BG[1] + boost), BMO_SCREEN_BG[2])
        elif mood == "sleepy":
            # Dim the screen
            screen_bg = (BMO_SCREEN_BG[0] - 20, BMO_SCREEN_BG[1] - 20, BMO_SCREEN_BG[2] - 20)

        draw.rectangle([0, FACE_AREA_TOP, SCREEN_W - 1, SCREEN_H - 1], fill=screen_bg)
        draw.rectangle([0, FACE_AREA_TOP, SCREEN_W - 1, SCREEN_H - 1], outline=BMO_BEZEL, width=3)

        face_cy = int(CY + bounce_y)

        # Store face center for decoration alignment
        self._last_face_cx = CX
        self._last_face_cy = face_cy

        # Face-only mode: larger scale for eyes/mouth since they fill the screen
        eye_scale = 2.2
        mouth_scale = 2.0
        _draw_bmo_eyes(draw, CX, face_cy - 20, expr, blink_factor, gaze_x, gaze_y, scale=eye_scale)
        _draw_bmo_mouth(draw, CX, face_cy + 30, expr, amplitude, scale=mouth_scale)

        # ── Scan lines (mood + amplitude reactive) ────────────────────
        scan_step = 4
        scan_offset = 0
        if mood == "sleepy":
            scan_step = 6  # fewer, more visible lines
        if amplitude > 0:
            scan_step = 3  # shimmer faster when speaking
            scan_offset = int(amplitude * 2)

        scan_color = (158, 206, 166)
        if mood == "error":
            # Red-tinted static noise band
            band_top = FACE_AREA_TOP + (SCREEN_H - FACE_AREA_TOP) // 3
            band_bot = band_top + 40
            for sy in range(band_top, band_bot, 2):
                for sx in range(0, SCREEN_W, 3):
                    if random.random() < 0.4:
                        c = random.choice([(180, 40, 40), (100, 20, 20), (60, 10, 10)])
                        draw.rectangle([sx, sy, sx + 2, sy + 1], fill=c)
        else:
            for y in range(FACE_AREA_TOP, SCREEN_H, scan_step):
                draw.line(
                    [(scan_offset, y), (SCREEN_W - 1 + scan_offset, y)],
                    fill=scan_color, width=1,
                )

        # ── Happy: pixel hearts floating up ───────────────────────────
        if mood == "happy":
            _update_heart_particles(draw, now)

        # ── Thinking: loading spinner in top-right corner ─────────────
        if mood == "thinking":
            _draw_spinner(draw, now)


# ═══════════════════════════════════════════════════════════════════════════
# BMO Full body (shows the game console with controls)
# ═══════════════════════════════════════════════════════════════════════════

BODY_W = 160
BODY_H = 190
BODY_RADIUS = 16
SCREEN_INSET_X = 18
SCREEN_INSET_TOP = 14
SCREEN_H_SIZE = 95


class BMOFullCharacter(Character):
    """BMO full body — the complete game console with screen, D-pad, buttons."""

    name = "bmo-full"

    def idle_quirk(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                   now: float) -> None:
        """Button glow + speaker hum — full-body BMO idle personality."""
        # Button glow is drawn in _draw_controls via now parameter.
        # Speaker vibration is drawn in _draw_controls via now parameter.
        # idle_quirk is called after draw(), so we store the timestamp
        # for the next frame's controls. The effects are integrated
        # directly into _draw_controls instead.
        pass

    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float) -> None:
        body = expr.body
        scale = body.scale

        bounce_y = math.sin(now * body.bounce_speed * 2 * math.pi) * body.bounce_amount
        body_cy = int(CY + bounce_y)
        tilt_offset_x = int(math.sin(math.radians(body.tilt)) * 4)
        bmo_cx = CX + tilt_offset_x

        self._draw_body(draw, bmo_cx, body_cy, scale)
        self._draw_screen(draw, bmo_cx, body_cy, scale)

        # Face inside screen
        bh = int(BODY_H * scale)
        bt = body_cy - bh // 2
        screen_cy = bt + int(SCREEN_INSET_TOP * scale) + int(SCREEN_H_SIZE * scale / 2)

        # Store face center for decoration alignment
        self._last_face_cx = bmo_cx
        self._last_face_cy = screen_cy

        # Full-body: slightly larger than before (was 0.85)
        _draw_bmo_eyes(draw, bmo_cx, screen_cy - 8, expr, blink_factor, gaze_x, gaze_y, scale=scale * 1.1)
        _draw_bmo_mouth(draw, bmo_cx, screen_cy + 14, expr, amplitude, scale=scale * 1.0)

        # Controls below screen (with idle effects and mood reactions)
        controls_y = bt + int((SCREEN_INSET_TOP + SCREEN_H_SIZE + 10) * scale)
        mood = expr.name
        self._draw_controls(draw, bmo_cx, controls_y, scale, now, mood, amplitude)

    def _draw_body(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float) -> None:
        bw = int(BODY_W * scale)
        bh = int(BODY_H * scale)
        r = int(BODY_RADIUS * scale)
        bl = cx - bw // 2
        bt = cy - bh // 2

        draw.rounded_rectangle([bl, bt, bl + bw, bt + bh], radius=r, fill=BMO_BODY)
        draw.line([(bl + 3, bt + r), (bl + 3, bt + bh - r)], fill=BMO_BODY_LIGHT, width=2)
        draw.line([(bl + bw - 3, bt + r), (bl + bw - 3, bt + bh - r)], fill=BMO_BODY_DARK, width=2)

    def _draw_screen(self, draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float) -> None:
        bw = int(BODY_W * scale)
        bh = int(BODY_H * scale)
        bl = cx - bw // 2
        bt = cy - bh // 2

        sx = int(SCREEN_INSET_X * scale)
        sy = int(SCREEN_INSET_TOP * scale)
        sh = int(SCREEN_H_SIZE * scale)
        sr = int(6 * scale)

        sl = bl + sx
        st = bt + sy
        sr_r = bl + bw - sx
        sb = st + sh

        draw.rounded_rectangle([sl - 2, st - 2, sr_r + 2, sb + 2], radius=sr + 2, fill=BMO_BEZEL)
        draw.rounded_rectangle([sl, st, sr_r, sb], radius=sr, fill=BMO_SCREEN_BG)

    def _draw_controls(self, draw: ImageDraw.ImageDraw, cx: int, cy: int,
                       scale: float, now: float = 0.0,
                       mood: str = "", amplitude: float = 0.0) -> None:
        # D-pad
        dpad_cx = cx - int(30 * scale)
        dpad_cy = cy + int(10 * scale)
        ds = int(8 * scale)
        dw = int(6 * scale)
        draw.rounded_rectangle([dpad_cx - ds, dpad_cy - dw // 2, dpad_cx + ds, dpad_cy + dw // 2],
                               radius=max(1, int(scale)), fill=BMO_DPAD)
        draw.rounded_rectangle([dpad_cx - dw // 2, dpad_cy - ds, dpad_cx + dw // 2, dpad_cy + ds],
                               radius=max(1, int(scale)), fill=BMO_DPAD)
        cd = max(1, int(2 * scale))

        # Excited mood: D-pad center dot pulses brighter
        if mood == "excited":
            pulse = 0.5 + 0.5 * math.sin(now * 4)
            bright = int(60 + pulse * 60)
            dpad_center_color = (bright, bright + 20, bright + 15)
        else:
            dpad_center_color = BMO_DPAD_LIGHT
        draw.ellipse([dpad_cx - cd, dpad_cy - cd, dpad_cx + cd, dpad_cy + cd], fill=dpad_center_color)

        # Buttons with idle glow (alternating pulse)
        btn_r = int(5 * scale)
        btn_cx = cx + int(28 * scale)
        btn_cy_red = cy + int(4 * scale)
        btn_cx2 = btn_cx + int(4 * scale)
        btn_cy_blue = cy + int(18 * scale)

        # Slow alternating pulse cycle (~4s per button)
        pulse_phase = (now % 8.0) / 8.0
        red_glow = max(0.0, math.sin(pulse_phase * 2 * math.pi)) * 0.3
        blue_glow = max(0.0, math.sin((pulse_phase + 0.5) * 2 * math.pi)) * 0.3

        red_color = (
            min(255, int(BMO_BTN_RED[0] + red_glow * 35)),
            min(255, int(BMO_BTN_RED[1] + red_glow * 20)),
            min(255, int(BMO_BTN_RED[2] + red_glow * 20)),
        )
        blue_color = (
            min(255, int(BMO_BTN_BLUE[0] + blue_glow * 20)),
            min(255, int(BMO_BTN_BLUE[1] + blue_glow * 20)),
            min(255, int(BMO_BTN_BLUE[2] + blue_glow * 35)),
        )

        draw.ellipse([btn_cx - btn_r, btn_cy_red - btn_r,
                      btn_cx + btn_r, btn_cy_red + btn_r], fill=red_color)
        draw.ellipse([btn_cx2 - btn_r, btn_cy_blue - btn_r,
                      btn_cx2 + btn_r, btn_cy_blue + btn_r], fill=blue_color)

        # Speaker grille (vibrates when idle or speaking)
        speaker_y = cy + int(34 * scale)
        speaker_w = int(30 * scale)

        # Speaking: vigorous vibration; idle: subtle hum
        if mood == "speaking" or amplitude > 0.1:
            vibrate = int(math.sin(now * 30) * 2)
        else:
            vibrate = int(math.sin(now * 3) * 0.8)

        for i in range(4):
            ly = speaker_y + i * int(4 * scale)
            v = vibrate if (i % 2 == 0) else -vibrate
            draw.line([(cx - speaker_w // 2 + v, ly), (cx + speaker_w // 2 + v, ly)],
                      fill=BMO_SPEAKER, width=1)


# ═══════════════════════════════════════════════════════════════════════════
# Mood-specific effect helpers (face-only mode)
# ═══════════════════════════════════════════════════════════════════════════

def _update_heart_particles(draw: ImageDraw.ImageDraw, now: float) -> None:
    """Spawn and draw tiny pixel hearts floating upward from screen edges."""
    global _heart_particles

    # Spawn new hearts occasionally (up to 4 at a time)
    if len(_heart_particles) < 4 and random.random() < 0.03:
        side = random.choice(["left", "right"])
        _heart_particles.append({
            "x": random.randint(8, 30) if side == "left" else random.randint(SCREEN_W - 30, SCREEN_W - 8),
            "y": float(SCREEN_H - 40),
            "born": now,
        })

    alive = []
    for p in _heart_particles:
        age = now - p["born"]
        if age > 3.0:
            continue  # expired
        p["y"] -= 0.6  # float upward
        px = int(p["x"] + math.sin(age * 2) * 3)
        py = int(p["y"])

        # Tiny pixel heart: 5 pixels arranged as a heart shape
        #  X X
        # X X X
        #  X X
        #   X
        c = BMO_FACE
        draw.point((px - 1, py), fill=c)
        draw.point((px + 1, py), fill=c)
        draw.point((px - 2, py + 1), fill=c)
        draw.point((px, py + 1), fill=c)
        draw.point((px + 2, py + 1), fill=c)
        draw.point((px - 1, py + 2), fill=c)
        draw.point((px + 1, py + 2), fill=c)
        draw.point((px, py + 3), fill=c)
        alive.append(p)

    _heart_particles = alive


def _draw_spinner(draw: ImageDraw.ImageDraw, now: float) -> None:
    """Draw a small rotating dash loading spinner in the top-right corner."""
    global _spinner_state
    if now >= _spinner_state["next_advance"]:
        _spinner_state["index"] = (_spinner_state["index"] + 1) % 4
        _spinner_state["next_advance"] = now + 0.15

    # Draw the spinner character as small pixel art
    sx = SCREEN_W - 20
    sy = FACE_AREA_TOP + 12
    idx = _spinner_state["index"]

    if idx == 0:  # -
        draw.line([(sx - 3, sy), (sx + 3, sy)], fill=BMO_FACE, width=1)
    elif idx == 1:  # backslash
        draw.line([(sx - 2, sy - 2), (sx + 2, sy + 2)], fill=BMO_FACE, width=1)
    elif idx == 2:  # |
        draw.line([(sx, sy - 3), (sx, sy + 3)], fill=BMO_FACE, width=1)
    elif idx == 3:  # /
        draw.line([(sx - 2, sy + 2), (sx + 2, sy - 2)], fill=BMO_FACE, width=1)


# ═══════════════════════════════════════════════════════════════════════════
# Shared face drawing (used by both variants)
# ═══════════════════════════════════════════════════════════════════════════

def _draw_bmo_eyes(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   expr: Expression, blink_factor: float,
                   gaze_x: float, gaze_y: float, scale: float = 1.0) -> None:
    """BMO's eyes: oval black dots with highlight, reactive to expression."""
    eyes = expr.eyes
    openness = eyes.openness * blink_factor * (1.0 - eyes.squint * 0.4)
    gx = max(-1.0, min(1.0, eyes.gaze_x + gaze_x))
    gy = max(-1.0, min(1.0, eyes.gaze_y + gaze_y))

    spacing = int(26 * scale)

    # Error: X eyes
    if expr.name == "error":
        for side in (-1, 1):
            ex = cx + side * spacing
            h = int(10 * scale)
            w = max(2, int(3 * scale))
            draw.line([(ex - h, cy - h), (ex + h, cy + h)], fill=(220, 50, 50), width=w)
            draw.line([(ex - h, cy + h), (ex + h, cy - h)], fill=(220, 50, 50), width=w)
        return

    per_eye = [expr.left_eye, expr.right_eye]
    for side, override in zip((-1, 1), per_eye):
        ex = cx + side * spacing + int(gx * 4 * scale)
        ey = cy + int(gy * 3 * scale)

        ew = eyes.width
        eh = eyes.height
        eo = openness

        if override:
            if override.width is not None: ew = override.width
            if override.height is not None: eh = override.height
            if override.openness is not None:
                eo = override.openness * blink_factor
                sq = override.squint if override.squint is not None else eyes.squint
                eo = eo * (1.0 - sq * 0.4)

        # Base eye size — bigger than before
        base_w = int(12 * scale * ew)
        base_h = int(14 * scale * eh * max(eo, 0.06))

        draw.ellipse([ex - base_w // 2, ey - base_h // 2,
                      ex + base_w // 2, ey + base_h // 2], fill=BMO_FACE)

        # Highlight dot (glossy reflection)
        if eo > 0.3 and base_h > 6:
            hr = max(2, int(3 * scale))
            hx = ex + base_w // 2 - int(3 * scale)
            hy = ey - base_h // 2 + int(3 * scale)
            draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=BMO_HIGHLIGHT)


def _draw_bmo_mouth(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                    expr: Expression, amplitude: float, scale: float = 1.0) -> None:
    """BMO's mouth: simple line/curve, opens with amplitude."""
    mouth = expr.mouth
    half_w = int(14 * scale * mouth.width)
    total_open = min(mouth.openness + amplitude * 0.6, 1.0)
    smile_offset = int(mouth.smile * 6 * scale)
    line_w = max(2, int(2.5 * scale))

    p0 = (cx - half_w, cy)
    p2 = (cx + half_w, cy)
    p1 = (cx, cy - smile_offset)
    pts = _bezier(p0, p1, p2)

    if total_open > 0.1:
        open_h = int(total_open * 10 * scale)
        p1b = (cx, cy - smile_offset + open_h)
        pts_b = _bezier(p0, p1b, p2)
        outline = pts + list(reversed(pts_b))
        if len(outline) >= 3:
            draw.polygon(outline, fill=BMO_FACE)
    else:
        if len(pts) >= 2:
            draw.line(pts, fill=BMO_FACE, width=line_w)
