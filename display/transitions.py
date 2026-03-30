"""View transition manager — smooth cross-fade between display views.

Manages transitions between face, chat_drawer, and chat_full views,
plus fade-in for overlays (menu, pairing, shutdown).

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


class DrawerSlide:
    """Animates a vertical slide for the chat drawer.

    Slides from hidden_y (off-screen) to rest_y (open position) and back.
    Uses ease-out for opening (decelerates) and ease-in for closing (accelerates).
    """

    def __init__(self, rest_y: int = 140, hidden_y: int = 280,
                 duration: float = 0.25) -> None:
        self._rest_y = rest_y
        self._hidden_y = hidden_y
        self._duration = duration
        self._is_open = False
        self._start_time: float = 0.0
        self._progress: float = 0.0  # 0=hidden, 1=open

    def set_open(self, is_open: bool, now: float) -> None:
        """Signal the drawer to open or close."""
        if is_open == self._is_open:
            return
        self._is_open = is_open
        self._start_time = now
        # Invert progress so animation continues from current position
        self._progress = 1.0 - self._progress

    def update(self, now: float) -> int:
        """Update and return the current top Y position."""
        if self._duration <= 0:
            return self._rest_y if self._is_open else self._hidden_y

        elapsed = now - self._start_time
        raw = min(1.0, elapsed / self._duration)
        self._progress = raw

        if self._is_open:
            # Opening: ease-out (decelerate into rest position)
            t = 1.0 - (1.0 - raw) ** 2
            return int(self._hidden_y + (self._rest_y - self._hidden_y) * t)
        else:
            # Closing: ease-in (accelerate off-screen)
            t = raw * raw
            return int(self._rest_y + (self._hidden_y - self._rest_y) * t)

    @property
    def is_animating(self) -> bool:
        return self._progress < 1.0


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
