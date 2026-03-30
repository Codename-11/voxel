"""Display layout constants — screen dimensions and corner-safe areas.

The Whisplay HAT's 1.69" IPS LCD has rounded corners with a ~40px radius
bevel. Content in the corners gets clipped by the physical bezel. All UI
components should respect the safe area to avoid placing text/icons in
the clipped corners.

Reference: Adafruit 1.69" 280x240 ST7789 CORNER_RADIUS = 43px.
PiSugar WhisPlay.py CornerHeight = 20px (conservative estimate).
We use 40px as a practical middle ground matching the physical bevel.
"""

# ── Screen dimensions ───────────────────────────────────────────────────────

SCREEN_W = 240
SCREEN_H = 280

# ── Corner radius (physical LCD bevel) ──────────────────────────────────────

CORNER_RADIUS = 40  # pixels — content in corners beyond this gets clipped

# ── Status bar ──────────────────────────────────────────────────────────────

STATUS_H = 48       # top bar height

# ── Decoration icon zones ──────────────────────────────────────────────────
# Above-face area used for mood/status overlay icons.  Keep mood and
# status decorations on separate rows to avoid visual collision.

ICON_Y = STATUS_H + 22          # mood decoration row (thinking dots, "!!", "???", etc.)
STATUS_ICON_Y = STATUS_H + 42   # status decoration row (WiFi arcs, battery icon)

# ── Safe content insets (accounts for rounded corners) ──────────────────────
# The corners are rounded, so content near edges needs horizontal inset
# that varies by Y position. Near the top/bottom edges, inset more.

SAFE_PAD_X = 6      # minimum horizontal padding (mid-screen)
CORNER_PAD_X = 24   # horizontal padding at top/bottom corners


def safe_left(y: int) -> int:
    """Get the safe left X position for a given Y coordinate."""
    # Top corners
    if y < CORNER_RADIUS:
        # Circle equation: x = R - sqrt(R^2 - (R-y)^2)
        dy = CORNER_RADIUS - y
        import math
        inset = CORNER_RADIUS - int(math.sqrt(max(0, CORNER_RADIUS**2 - dy**2)))
        return max(inset, SAFE_PAD_X)
    # Bottom corners
    if y > SCREEN_H - CORNER_RADIUS:
        dy = y - (SCREEN_H - CORNER_RADIUS)
        import math
        inset = CORNER_RADIUS - int(math.sqrt(max(0, CORNER_RADIUS**2 - dy**2)))
        return max(inset, SAFE_PAD_X)
    return SAFE_PAD_X


def safe_right(y: int) -> int:
    """Get the safe right X position for a given Y coordinate."""
    return SCREEN_W - safe_left(y)
