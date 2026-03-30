"""Speaking waveform pill + listening pulse ring + ambient mic indicator.

Standardised activity indicators at the bottom of the screen:

  State        Visual                  Position       LED
  ----------   ---------------------   ------------   ----------------
  SPEAKING     Waveform bar in pill    Bottom-center  Green blink
  LISTENING    Pulse ring + "Talk"     Bottom-center  Solid cyan
  Ambient      Subtle pulsing dot      Bottom-right   Dim cyan pulse
"""

from __future__ import annotations

import math

from PIL import ImageDraw

from display.layout import SCREEN_W, SCREEN_H
from display.state import DisplayState

# ── Layout ──────────────────────────────────────────────────────────────────

PILL_W = 140
PILL_H = 18
PILL_X = (SCREEN_W - PILL_W) // 2
PILL_Y = SCREEN_H - 52  # above the button indicator area
PILL_R = PILL_H // 2     # corner radius for rounded pill

# Pulse ring for listening mode
RING_CX = SCREEN_W // 2
RING_CY = PILL_Y + PILL_H // 2
RING_R = 12
RING_THICKNESS = 2

# Ambient mic indicator (bottom-right, out of the way)
AMBIENT_CX = SCREEN_W - 28
AMBIENT_CY = SCREEN_H - 48

# ── Waveform bars ───────────────────────────────────────────────────────────

NUM_BARS = 10
BAR_GAP = 2
BAR_W = max(2, (PILL_W - 20 - (NUM_BARS - 1) * BAR_GAP) // NUM_BARS)
BARS_TOTAL_W = NUM_BARS * BAR_W + (NUM_BARS - 1) * BAR_GAP
BARS_X_START = PILL_X + (PILL_W - BARS_TOTAL_W) // 2

# ── Colors ──────────────────────────────────────────────────────────────────

PILL_BG = (14, 14, 24)
PILL_BORDER = (0, 52, 50)        # subtle cyan border
CYAN = (0, 212, 210)
CYAN_DIM = (0, 60, 58)
CYAN_BRIGHT = (64, 255, 248)

# ── Wave config (mirroring React AudioWaveform WAVE_CONFIG) ─────────────────

_WAVE_LAYERS = [
    {"freq": 0.8, "mult": 2.0, "phase": 0.0},
    {"freq": 1.0, "mult": 1.7, "phase": 0.85},
    {"freq": 1.25, "mult": 1.3, "phase": 1.7},
]

TAU = math.pi * 2


def _bar_height(bar_index: int, now: float, amplitude: float) -> float:
    """Compute the height of a single waveform bar."""
    max_h = PILL_H - 4
    min_h = 2.0

    if amplitude < 0.01:
        return min_h

    t = bar_index / max(NUM_BARS - 1, 1)
    combined = 0.0
    for layer in _WAVE_LAYERS:
        phase_speed = 4.0 + layer["freq"] * 2.0
        theta = layer["freq"] * t * TAU + now * phase_speed + layer["phase"]
        combined += math.sin(theta) * layer["mult"]

    normalised = (combined / 5.0) * 0.5 + 0.5
    normalised = max(0.0, min(1.0, normalised))
    h = min_h + (max_h - min_h) * normalised * min(amplitude * 1.5, 1.0)
    return h


def _lerp_color(a: tuple, b: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _scale_color(color: tuple, alpha: float) -> tuple:
    alpha = max(0.0, min(1.0, alpha))
    return (int(color[0] * alpha), int(color[1] * alpha), int(color[2] * alpha))


# ── Speaking waveform pill ─────────────────────────────────────────────────

def draw_speaking_pill(draw: ImageDraw.ImageDraw, state: DisplayState, now: float) -> None:
    """Draw a waveform animation pill at the bottom during SPEAKING state."""
    amplitude = state.amplitude

    draw.rounded_rectangle(
        [PILL_X, PILL_Y, PILL_X + PILL_W, PILL_Y + PILL_H],
        radius=PILL_R, fill=PILL_BG, outline=PILL_BORDER,
    )

    bar_cy = PILL_Y + PILL_H // 2

    for i in range(NUM_BARS):
        h = _bar_height(i, now, amplitude)
        x = BARS_X_START + i * (BAR_W + BAR_GAP)
        y_top = int(bar_cy - h / 2)
        y_bot = int(bar_cy + h / 2)

        center_factor = 1.0 - abs(i - (NUM_BARS - 1) / 2) / ((NUM_BARS - 1) / 2)
        brightness = 0.3 + 0.7 * center_factor * min(amplitude * 1.8, 1.0)
        color = _lerp_color(CYAN_DIM, CYAN, brightness)

        if h > 4:
            draw.rounded_rectangle(
                [x, y_top, x + BAR_W, y_bot], radius=1, fill=color,
            )
        else:
            draw.rectangle([x, y_top, x + BAR_W, y_bot], fill=color)


# ── Listening pulse ring + "Talk" label ──────────────────────────────────

def draw_listening_indicator(draw: ImageDraw.ImageDraw, state: DisplayState, now: float) -> None:
    """Draw a listening indicator — pulse ring with expanding outer rings.

    Visual language: concentric rings pulsing outward = actively receiving.
    Matches the "Talk" flash badge style but persistent during LISTENING.
    """
    cx = RING_CX
    cy = RING_CY

    # Core pulse (2 Hz)
    pulse = math.sin(now * 4.0) * 0.5 + 0.5  # 0..1

    # Inner filled dot — solid cyan, breathing radius
    dot_r = int(4 + 2 * pulse)
    dot_color = _lerp_color(CYAN, CYAN_BRIGHT, pulse)
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=dot_color)

    # Two expanding pulse rings
    for i in range(2):
        ring_phase = (now * 1.5 + i * 0.5) % 1.0  # staggered
        ring_r = int(RING_R + ring_phase * 10)
        ring_alpha = 1.0 - ring_phase  # fades as it expands
        if ring_alpha > 0.05:
            ring_color = _scale_color(CYAN, ring_alpha * 0.6)
            bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
            draw.arc(bbox, 0, 360, fill=ring_color, width=RING_THICKNESS)

    # "Talk" label below
    from display.fonts import get_font, text_width
    font = get_font(11)
    label = "Talk"
    tw = text_width(font, label)
    label_alpha = 0.6 + 0.3 * pulse
    label_color = _scale_color(CYAN, label_alpha)
    draw.text((cx - tw // 2, cy + RING_R + 10), label, fill=label_color, font=font)


# ── Ambient mic activity indicator ───────────────────────────────────────

def draw_ambient_indicator(draw: ImageDraw.ImageDraw, state: DisplayState, now: float) -> None:
    """Draw a subtle mic activity dot when ambient monitor is hearing sound.

    Small pulsing dot in the bottom-right — indicates the mic is active
    and detecting sound without being distracting. Radius scales with
    amplitude so louder sounds are more visible.
    """
    if not state.ambient_active:
        return

    cx = AMBIENT_CX
    cy = AMBIENT_CY
    amp = min(state.ambient_amplitude, 1.0)

    # Base pulse (slow, subtle)
    pulse = math.sin(now * 3.0) * 0.5 + 0.5

    # Dot radius: 2px minimum, scales with amplitude
    r = int(2 + amp * 3 + pulse * 1.5)
    alpha = 0.3 + amp * 0.5 + pulse * 0.2
    color = _scale_color(CYAN_DIM, min(alpha, 1.0))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Brief glow ring on louder sounds
    if amp > 0.3:
        glow_r = r + 3
        glow_alpha = (amp - 0.3) * 0.8
        glow_color = _scale_color(CYAN_DIM, glow_alpha)
        draw.ellipse(
            [cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r],
            outline=glow_color, width=1,
        )
