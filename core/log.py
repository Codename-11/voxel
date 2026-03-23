"""Voxel logging — clean, colored, with personality."""

import logging
import sys
import time
import threading
from datetime import datetime
from typing import Optional


# ── ANSI Colors ──────────────────────────────────────────────────────────────

class _C:
    """ANSI color codes."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Foreground
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # Bright foreground
    BR_BLACK  = "\033[90m"
    BR_RED    = "\033[91m"
    BR_GREEN  = "\033[92m"
    BR_YELLOW = "\033[93m"
    BR_BLUE   = "\033[94m"
    BR_MAGENTA= "\033[95m"
    BR_CYAN   = "\033[96m"
    BR_WHITE  = "\033[97m"


# Level → (label, color)
_LEVEL_STYLES = {
    logging.DEBUG:    ("DBG", _C.BR_BLACK),
    logging.INFO:     ("INF", _C.BR_CYAN),
    logging.WARNING:  ("WRN", _C.BR_YELLOW),
    logging.ERROR:    ("ERR", _C.BR_RED),
    logging.CRITICAL: ("CRT", f"{_C.BOLD}{_C.BR_RED}"),
}


# ── Formatter ────────────────────────────────────────────────────────────────

class VoxelFormatter(logging.Formatter):
    """
    Format: MM-DD-YY HH:MM:SS.ms AM/PM  [module.name]  LEVEL  message
    Colored by level. Module name in cyan. Timestamp dim.
    """

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.fromtimestamp(record.created)
        ts = now.strftime("%m-%d-%y %I:%M:%S.") + f"{now.microsecond // 1000:03d}" + now.strftime(" %p")

        label, color = _LEVEL_STYLES.get(record.levelno, ("???", _C.WHITE))

        # Shorten module names for readability
        name = record.name
        if name.startswith("voxel."):
            name = name[6:]

        msg = record.getMessage()

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            msg = f"{msg}\n{record.exc_text}"

        return (
            f"{_C.BR_BLACK}{ts}{_C.RESET}  "
            f"{_C.CYAN}[{name}]{_C.RESET}  "
            f"{color}{label}{_C.RESET}  "
            f"{msg}"
        )


# ── Spinner ──────────────────────────────────────────────────────────────────

class Spinner:
    """Animated terminal spinner for async operations."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str, color: str = _C.BR_CYAN):
        self._message = message
        self._color = color
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "Spinner":
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self) -> None:
        i = 0
        while self._running:
            frame = self._FRAMES[i % len(self._FRAMES)]
            sys.stderr.write(f"\r{self._color}{frame}{_C.RESET} {self._message}")
            sys.stderr.flush()
            i += 1
            time.sleep(0.08)

    def stop(self, final: str = "") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
        # Clear spinner line
        sys.stderr.write(f"\r\033[K")
        if final:
            sys.stderr.write(f"{final}\n")
        sys.stderr.flush()

    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, *args) -> None:
        self.stop()


# ── Startup Banner ───────────────────────────────────────────────────────────

_BANNER = f"""\
{_C.BR_CYAN}{_C.BOLD}
  ██╗   ██╗ ██████╗ ██╗  ██╗███████╗██╗
  ██║   ██║██╔═══██╗╚██╗██╔╝██╔════╝██║
  ██║   ██║██║   ██║ ╚███╔╝ █████╗  ██║
  ╚██╗ ██╔╝██║   ██║ ██╔██╗ ██╔══╝  ██║
   ╚████╔╝ ╚██████╔╝██╔╝ ██╗███████╗███████╗
    ╚═══╝   ╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝{_C.RESET}
{_C.BR_BLACK}  ─────────────────────────────────────────{_C.RESET}
"""


# Fun startup messages — one picked at random
_BOOT_MESSAGES = [
    "Waking up... *yawns*",
    "Booting personality module...",
    "Loading charm.dll...",
    "Cube consciousness: online",
    "Good vibes initializing...",
    "Stretching pixels...",
    "Polishing edges...",
    "Warming up the glow...",
    "Finding my face...",
    "Remembering how to smile...",
]

# Fun ready messages
_READY_MESSAGES = [
    "Ready! Let's go ✨",
    "All systems nominal. Hi! 👋",
    "Fully awake. What's up?",
    "Online and feeling cute 💎",
    "Cube mode: activated ▣",
    "Present and accounted for!",
]

# Shutdown messages
_SHUTDOWN_MESSAGES = [
    "Going to sleep... zzz",
    "Powering down. See you soon! 👋",
    "Saving memories... goodnight.",
    "Cube mode: deactivated ▣",
]


def _pick(messages: list[str]) -> str:
    """Pick a random message."""
    import random
    return random.choice(messages)


# ── Public API ───────────────────────────────────────────────────────────────

_initialized = False


def setup(level: int = logging.INFO, show_banner: bool = True) -> None:
    """Initialize the Voxel logging system.

    Call once at startup before any logging.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Root "voxel" logger
    root = logging.getLogger("voxel")
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(VoxelFormatter())
    root.addHandler(handler)

    # Prevent propagation to root logger (avoids duplicate output)
    root.propagate = False

    if show_banner:
        sys.stderr.write(_BANNER)
        sys.stderr.flush()


def boot_message() -> None:
    """Log a fun boot message."""
    log = logging.getLogger("voxel.core")
    log.info(_pick(_BOOT_MESSAGES))


def ready_message() -> None:
    """Log a fun ready message."""
    log = logging.getLogger("voxel.core")
    log.info(_pick(_READY_MESSAGES))


def shutdown_message() -> None:
    """Log a fun shutdown message."""
    log = logging.getLogger("voxel.core")
    log.info(_pick(_SHUTDOWN_MESSAGES))
