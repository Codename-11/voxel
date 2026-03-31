"""View transition manager — smooth cross-fade between display views.

Manages transitions between face and chat views, plus fade-in for
overlays (menu, pairing, shutdown).

At 20 FPS, a 0.3s transition = ~6 frames — enough for visible smoothness.
"""

from __future__ import annotations

from PIL import Image


def ease_in_out(t: float) -> float:
    """Smooth-step easing: slow start and end, fast middle."""
    return t * t * (3.0 - 2.0 * t)


class ViewTransition:
    """Manages smooth cross-fade transitions between display views."""

    def __init__(self, duration: float = 0.3, enabled: bool = True) -> None:
        self._current_view: str = "face"
        self._target_view: str = "face"
        self._progress: float = 1.0  # 0=start, 1=complete
        self._transition_start: float = 0.0
        self._duration: float = duration
        self._prev_frame: Image.Image | None = None
        self.enabled: bool = enabled

    @property
    def current_view(self) -> str:
        return self._current_view

    @property
    def target_view(self) -> str:
        return self._target_view

    def set_view(self, view: str, now: float) -> None:
        """Start transition to a new view.

        If transitions are disabled or the view hasn't changed, does nothing.
        """
        if view == self._current_view and self._progress >= 1.0:
            return
        if view == self._target_view:
            return
        self._target_view = view
        self._progress = 0.0
        self._transition_start = now

    def is_transitioning(self) -> bool:
        """True while a transition is in progress."""
        return self.enabled and self._progress < 1.0

    def update(self, now: float) -> float:
        """Update and return eased transition progress (0.0-1.0)."""
        if self._progress >= 1.0:
            return 1.0
        if self._duration <= 0:
            self._progress = 1.0
            self._current_view = self._target_view
            return 1.0

        elapsed = now - self._transition_start
        raw = min(1.0, elapsed / self._duration)
        self._progress = raw
        if raw >= 1.0:
            self._current_view = self._target_view
        return ease_in_out(raw)

    def capture(self, frame: Image.Image) -> None:
        """Store the current frame as the 'previous' frame for blending."""
        self._prev_frame = frame.copy()

    def blend(self, new_frame: Image.Image, progress: float) -> Image.Image:
        """Blend previous frame with new frame based on progress.

        Both images must be the same size and mode (RGB).
        Returns the blended image, or new_frame if no previous frame exists.
        """
        if self._prev_frame is None or progress >= 1.0:
            return new_frame
        if progress <= 0.0:
            return self._prev_frame
        return Image.blend(self._prev_frame, new_frame, alpha=progress)

    def finish(self) -> None:
        """Force-complete any in-progress transition."""
        self._progress = 1.0
        self._current_view = self._target_view


class OverlayFade:
    """Tracks fade-in progress for an overlay (menu, pairing, etc.).

    Call update() each frame with the overlay's open/visible state.
    The returned alpha (0.0-1.0) controls blend opacity for the overlay.
    Fade-out is intentionally not supported — when an overlay closes,
    the underlying view is drawn immediately (instant dismiss).
    """

    def __init__(self, duration: float = 0.15, enabled: bool = True) -> None:
        self._was_open: bool = False
        self._fade_start: float = 0.0
        self._duration: float = duration
        self._alpha: float = 0.0
        self.enabled: bool = enabled

    @property
    def alpha(self) -> float:
        return self._alpha

    def update(self, is_open: bool, now: float) -> float:
        """Update fade state and return current alpha (0.0-1.0).

        When the overlay first opens, alpha ramps from 0 to 1 over duration.
        When fully faded in, returns 1.0.
        When closed, returns 0.0 and resets.
        """
        if not is_open:
            self._was_open = False
            self._alpha = 0.0
            return 0.0

        if not self.enabled:
            self._was_open = True
            self._alpha = 1.0
            return 1.0

        # Just opened — start fade
        if not self._was_open:
            self._was_open = True
            self._fade_start = now
            self._alpha = 0.0

        # Calculate fade progress
        if self._duration <= 0:
            self._alpha = 1.0
        else:
            elapsed = now - self._fade_start
            raw = min(1.0, elapsed / self._duration)
            self._alpha = ease_in_out(raw)

        return self._alpha
