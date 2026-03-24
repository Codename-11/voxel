"""Terminal display helpers — colors, tables, status indicators."""

from __future__ import annotations

import io
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── ANSI colors ──────────────────────────────────────────────────────────────

_NO_COLOR = os.environ.get("NO_COLOR") or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(t: str) -> str:    return _c("36", t)
def green(t: str) -> str:   return _c("32", t)
def yellow(t: str) -> str:  return _c("33", t)
def red(t: str) -> str:     return _c("31", t)
def dim(t: str) -> str:     return _c("2", t)
def bold(t: str) -> str:    return _c("1", t)


# ── Status indicators ────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  {green('✓')} {msg}")


def warn(msg: str) -> None:
    print(f"  {yellow('⚠')} {msg}")


def fail(msg: str) -> None:
    print(f"  {red('✕')} {msg}")


def info(msg: str) -> None:
    print(f"  {cyan('▸')} {msg}")


def step(msg: str) -> None:
    print(f"\n  {bold(msg)}")


# ── Box drawing ──────────────────────────────────────────────────────────────

def header(title: str) -> None:
    w = 40
    print()
    print(f"  {cyan('╔' + '═' * w + '╗')}")
    print(f"  {cyan('║')}  {bold(title):<{w+len(bold(''))-len('')}}{cyan('║')}")
    print(f"  {cyan('╚' + '═' * w + '╝')}")
    print()


def section(title: str) -> None:
    print(f"\n  {cyan('──')} {bold(title)} {cyan('─' * (34 - len(title)))}")


def kv(key: str, value: str, width: int = 20) -> None:
    """Print a key-value pair."""
    print(f"    {dim(key):<{width}} {value}")


def table_row(cols: list[str], widths: list[int]) -> None:
    parts = []
    for col, w in zip(cols, widths):
        parts.append(f"{col:<{w}}")
    print(f"    {'  '.join(parts)}")
