"""LED controller for the display service.

Drives the WhisPlay HAT RGB LED based on device state. On desktop (no board),
all operations are no-ops.

IMPORTANT: The WhisPlay driver uses Python-thread-based SoftPWM for the LED.
Any brightness value other than 0 or 255 causes visible flicker from scheduler
jitter — same issue as the backlight. Therefore ALL patterns use full-on (255)
or full-off (0) per channel — NO dimming. Expressiveness comes from color
choice and blink/pulse timing instead.

Pattern types:
  solid   — constant color (on)
  blink   — on/off at a regular interval
  pulse   — quick on-flash then off (heartbeat-like)
  double  — two quick flashes then pause
  off     — LED off

Standardised activity indicator patterns (matches screen indicators):

    State             Color         Pattern                     Screen
    ---------------   -----------   -------------------------   ----------------
    IDLE              Off           LED off                     Face
    IDLE + ambient    Cyan          Brief flash on spike        Pulsing mic dot
    LISTENING         Cyan          Solid on                    Pulse ring "Talk"
    THINKING          Blue          Double blink (every 1s)     Thinking dots
    SPEAKING          Green         Fast blink synced to amp    Waveform pill
    ERROR             Red           Fast blink (0.2s on/off)    X eyes
    SLEEPING          Off           LED off                     Zzz
    MENU              White         Solid on                    Menu overlay
    WiFi AP mode      Magenta       Slow blink (1s on/off)      WiFi setup
    Update available  Yellow        Single pulse every 30s      —
    Shutdown confirm  Red           Solid on                    Shutdown overlay
    Button held       White         Solid on                    Progress ring
"""

from __future__ import annotations

from typing import Any

from display.state import DisplayState


# ── Color constants (full brightness only: 0 or 255 per channel) ─────────

CYAN    = (0, 255, 255)
BLUE    = (0, 0, 255)
GREEN   = (0, 255, 0)
RED     = (255, 0, 0)
WHITE   = (255, 255, 255)
MAGENTA = (255, 0, 255)
YELLOW  = (255, 255, 0)
OFF     = (0, 0, 0)


class LEDController:
    """Drives the WhisPlay RGB LED with on/off patterns (no dimming).

    Created with the WhisPlay board instance (or None on desktop).
    Call update() once per frame from the render loop.
    """

    def __init__(self, board: Any = None, **_kwargs) -> None:
        self._board = board
        self._last_color: tuple[int, int, int] = (0, 0, 0)
        self._enabled: bool = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self.off()

    def update(self, state: DisplayState, now: float) -> None:
        """Set LED color based on current state. Called once per frame (~20 FPS)."""
        if self._board is None or not self._enabled:
            return

        color = self._compute_color(state, now)

        if color != self._last_color:
            try:
                self._board.set_rgb(*color)
            except Exception:
                pass
            self._last_color = color

    def off(self) -> None:
        """Turn the LED off immediately."""
        if self._board is not None:
            try:
                self._board.set_rgb(0, 0, 0)
            except Exception:
                pass
            self._last_color = OFF

    def _compute_color(self, state: DisplayState, now: float) -> tuple[int, int, int]:
        """Determine LED color using on/off patterns only."""

        # ── Priority overrides ──

        # Shutdown: solid red
        if state.shutdown_confirm:
            return RED

        # Button held: solid white (feedback)
        if state.button_pressed:
            return WHITE

        # WiFi AP mode: slow blink magenta (1s on / 1s off)
        if state.wifi_ap_mode:
            return MAGENTA if (now % 2.0) < 1.0 else OFF

        # ── State-based patterns ──

        device_state = (state.state or "IDLE").upper()

        if device_state == "SLEEPING":
            return OFF

        if device_state == "ERROR":
            # Fast blink red (0.2s on / 0.2s off)
            return RED if (now % 0.4) < 0.2 else OFF

        if device_state == "LISTENING":
            # Solid cyan — always on while listening
            return CYAN

        if device_state == "THINKING":
            # Double-blink blue: two quick flashes then pause
            # Pattern over 1.2s: flash(0-0.1), off(0.1-0.2), flash(0.2-0.3), off(0.3-1.2)
            phase = now % 1.2
            if phase < 0.1 or (0.2 <= phase < 0.3):
                return BLUE
            return OFF

        if device_state == "SPEAKING":
            # Green blink synced to audio amplitude
            amp = max(0.0, min(1.0, state.amplitude))
            if amp > 0.1:
                # Fast blink when speaking (higher amp = longer on-time)
                cycle = 0.15  # base cycle
                on_ratio = 0.3 + amp * 0.5  # 30-80% duty
                return GREEN if (now % cycle) < (cycle * on_ratio) else OFF
            # Quiet moment during speaking — slow pulse
            return GREEN if (now % 1.0) < 0.1 else OFF

        if device_state == "MENU":
            return WHITE

        # ── IDLE (default) — LED off, screen shows the face ──

        # Ambient noise spike: brief cyan flash (mirrors screen mic dot)
        if state.ambient_active and state.ambient_amplitude > 0.5:
            return CYAN

        # Update available: single yellow blink every 30s
        if state.update_available:
            if (now % 30.0) < 0.15:
                return YELLOW

        return OFF
