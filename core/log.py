"""Voxel logging — clean, colored, with personality.

Log levels:
    DEBUG    — per-frame details, animation params, protocol messages
    INFO     — state transitions, mood changes, service lifecycle, config
    WARNING  — fallbacks, degraded functionality, missing optional config
    ERROR    — failures affecting user experience
    CRITICAL — service cannot start

Configuration:
    --verbose / -v       → DEBUG level (CLI flag)
    VOXEL_LOG_LEVEL env  → DEBUG, INFO, WARNING, ERROR (overrides default)
    VOXEL_LOG_FILE env   → path to additional log file (always appended)
"""

import logging
import os
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


class SafeHandler(logging.StreamHandler):
    """StreamHandler that never raises on encoding errors.

    On Windows with cp1252 stderr, non-ASCII characters (arrows, emoji)
    can cause '--- Logging error ---' lines.  This handler catches the
    UnicodeEncodeError, replaces the problematic chars, and retries.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            # Replace non-ASCII chars and retry
            record.msg = record.msg.encode("ascii", errors="replace").decode("ascii")
            try:
                super().emit(record)
            except Exception:
                pass  # give up silently
        except Exception:
            pass  # never crash on logging


class PlainFormatter(logging.Formatter):
    """Plain text formatter for file output (no ANSI codes)."""

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.fromtimestamp(record.created)
        ts = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"

        label, _ = _LEVEL_STYLES.get(record.levelno, ("???", ""))

        name = record.name
        if name.startswith("voxel."):
            name = name[6:]

        msg = record.getMessage()

        if record.exc_info and record.exc_info[0] is not None:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            msg = f"{msg}\n{record.exc_text}"

        return f"{ts}  [{name}]  {label}  {msg}"


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

# Fun ready messages (ASCII-safe — emoji cause encoding errors on Windows)
_READY_MESSAGES = [
    "Ready! Let's go.",
    "All systems nominal. Hi!",
    "Fully awake. What's up?",
    "Online and feeling cute.",
    "Cube mode: activated.",
    "Present and accounted for!",
]

# Shutdown messages
_SHUTDOWN_MESSAGES = [
    "Going to sleep... zzz",
    "Powering down. See you soon!",
    "Saving memories... goodnight.",
    "Cube mode: deactivated.",
]


def _pick(messages: list[str]) -> str:
    """Pick a random message."""
    import random
    return random.choice(messages)


# ── Public API ───────────────────────────────────────────────────────────────

_initialized = False


def _resolve_level(explicit_level: int | None = None) -> int:
    """Resolve log level from: explicit arg > VOXEL_LOG_LEVEL env > INFO default."""
    if explicit_level is not None:
        return explicit_level

    env = os.environ.get("VOXEL_LOG_LEVEL", "").upper()
    level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
                 "WARNING": logging.WARNING, "ERROR": logging.ERROR}
    return level_map.get(env, logging.INFO)


def setup(level: int | None = None, show_banner: bool = True) -> None:
    """Initialize the Voxel logging system.

    Call once at startup before any logging.

    Args:
        level: Explicit log level. If None, reads VOXEL_LOG_LEVEL env
               or defaults to INFO.
        show_banner: Show the ASCII art banner on stderr.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    resolved_level = _resolve_level(level)

    # Root "voxel" logger
    root = logging.getLogger("voxel")
    root.setLevel(resolved_level)

    # Console handler (stderr, colored, UTF-8 safe)
    # On Windows the default stderr encoding (cp1252) can't handle unicode
    # emoji/symbols, causing "--- Logging error ---" lines.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
        # Always rewrap stderr on Windows — even if encoding claims utf-8,
        # the underlying stream may still be cp1252.
        import io
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8',
                                          errors='replace', line_buffering=True)
    elif hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', '') != 'utf-8':
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8',
                                      errors='replace', line_buffering=True)

    console = SafeHandler(sys.stderr)
    console.setFormatter(VoxelFormatter())
    root.addHandler(console)

    # Patch lastResort AND the root logger so ANY logger (third-party
    # libraries, http.server, etc.) uses our safe handler.
    logging.lastResort = SafeHandler(sys.stderr)
    py_root = logging.getLogger()
    if not py_root.handlers:
        py_root.addHandler(SafeHandler(sys.stderr))

    # Optional file handler (VOXEL_LOG_FILE env or /var/log/voxel.log on Pi)
    log_file = os.environ.get("VOXEL_LOG_FILE")
    if log_file:
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(PlainFormatter())
            # File always gets DEBUG so we can diagnose after the fact
            fh.setLevel(logging.DEBUG)
            root.addHandler(fh)
        except OSError:
            pass  # non-critical: can't write log file

    # Prevent propagation to root logger (avoids duplicate output)
    root.propagate = False

    if show_banner and not os.environ.get("VOXEL_NO_BANNER"):
        sys.stderr.write(_BANNER)
        sys.stderr.flush()

    # Log the effective level so it's visible in output
    root.info("Log level: %s", logging.getLevelName(resolved_level))


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
