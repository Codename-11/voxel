"""Application state machine for Voxel."""

from enum import Enum, auto
from typing import Callable, Optional
import logging

log = logging.getLogger("voxel.states")


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()
    SLEEPING = auto()
    MENU = auto()


class StateMachine:
    """Drives the companion through its behavioral states."""

    def __init__(self):
        self._state = State.IDLE
        self._previous = State.IDLE
        self._on_change: list[Callable[[State, State], None]] = []
        self._error_message: Optional[str] = None

    @property
    def state(self) -> State:
        return self._state

    @property
    def previous(self) -> State:
        return self._previous

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message

    def on_change(self, callback: Callable[[State, State], None]):
        """Register a callback for state transitions."""
        self._on_change.append(callback)

    def transition(self, new_state: State, error_msg: str = ""):
        if new_state == self._state:
            return
        old = self._state
        self._previous = old
        self._state = new_state
        self._error_message = error_msg if new_state == State.ERROR else None
        log.info(f"State: {old.name} → {new_state.name}")
        for cb in self._on_change:
            try:
                cb(old, new_state)
            except Exception as e:
                log.error(f"State change callback error: {e}")

    def to_idle(self):
        self.transition(State.IDLE)

    def to_listening(self):
        self.transition(State.LISTENING)

    def to_thinking(self):
        self.transition(State.THINKING)

    def to_speaking(self):
        self.transition(State.SPEAKING)

    def to_error(self, message: str = "Something went wrong"):
        self.transition(State.ERROR, error_msg=message)

    def to_sleeping(self):
        self.transition(State.SLEEPING)

    def to_menu(self):
        self.transition(State.MENU)
