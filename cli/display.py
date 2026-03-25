"""Terminal display helpers — Rich-based TUI for Voxel CLI."""

from __future__ import annotations

import io
import sys

# Force UTF-8 on Windows before Rich touches stdout
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

# ── Theme ────────────────────────────────────────────────────────────────────

VX_THEME = Theme({
    "vx.cyan": "cyan",
    "vx.accent": "bold bright_cyan",
    "vx.dim": "dim",
    "vx.ok": "green",
    "vx.warn": "yellow",
    "vx.fail": "red",
})

console = Console(theme=VX_THEME, highlight=False)

# ── ASCII Logo ───────────────────────────────────────────────────────────────

LOGO = (
    " ╦  ╦ ╔═╗ ═╗ ╦ ╔═╗ ╦  \n"
    " ╚╗╔╝ ║ ║ ╔╩╦╝ ║╣  ║  \n"
    "  ╚╝  ╚═╝ ╩ ╚═ ╚═╝ ╩═╝"
)

LOGO_COMPACT = "⬡ Voxel"


def banner(version: str = "0.1.0", compact: bool = False) -> None:
    """Print the Voxel startup banner with ASCII art."""
    cols = console.width or 80
    console.print()
    if compact or cols < 40:
        console.print(f"  [bold cyan]{LOGO_COMPACT}[/]  [dim]v{version}[/]")
    else:
        for line in LOGO.strip().splitlines():
            console.print(f"[bold cyan]{line}[/]")
        console.print(f" [dim]Pocket AI Companion · v{version}[/]")
    console.print()


def print_commands() -> None:
    """Print a styled command list (shown when no command is given)."""
    tbl = Table(
        show_header=False, box=None, padding=(0, 2, 0, 4),
        row_styles=["", "dim"],
    )
    tbl.add_column("cmd", style="bold cyan", min_width=12)
    tbl.add_column("desc")

    cmds = [
        ("doctor",   "🩺  Run system health diagnostics"),
        ("display-test", "🖥️  Run direct display sanity test"),
        ("lvgl-test", "🧪  Build and play back a tiny LVGL PoC"),
        ("lvgl-build", "🔨  Build the LVGL PoC once"),
        ("lvgl-render", "🖼️  Render LVGL frames without playback"),
        ("lvgl-play", "🎞️  Play the cached LVGL PoC"),
        ("lvgl-sync", "📡  Sync rendered LVGL frames to a Pi"),
        ("lvgl-deploy", "🚀  Render, sync, and play on the Pi"),
        ("setup",    "📦  First-time install & configure"),
        ("build",    "🔨  Build Python deps + React app"),
        ("update",   "🔄  Pull latest, rebuild, restart"),
        ("hw",       "🔧  Install Whisplay HAT drivers"),
        ("start",    "▶️   Start services"),
        ("stop",     "⏹️   Stop services"),
        ("restart",  "🔁  Restart services"),
        ("logs",     "📋  Tail service logs"),
        ("status",   "📊  Show service & system status"),
        ("config",   "⚙️   Show / get / set configuration"),
        ("uninstall","🗑️   Remove services & caches"),
        ("version",  "🏷️   Show version"),
    ]
    for cmd, desc in cmds:
        tbl.add_row(cmd, desc)

    console.print(Panel(
        tbl,
        title="[bold]Commands[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 1),
    ))
    console.print("  [dim]Run[/] [cyan]voxel <command> --help[/] [dim]for details[/]")
    console.print()


# ── Status indicators ────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    console.print(f"  [green]✅[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"  [yellow]⚠️ [/] {msg}")


def fail(msg: str) -> None:
    console.print(f"  [red]❌[/] {msg}")


def info(msg: str) -> None:
    console.print(f"  [cyan]▸[/]  {msg}")


def step(msg: str) -> None:
    console.print(f"\n  [bold]{msg}[/]")


# ── Box drawing ──────────────────────────────────────────────────────────────

def header(title: str) -> None:
    console.print()
    console.print(Panel(
        f"[bold]{title}[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    console.print()


def section(title: str) -> None:
    console.print()
    console.rule(f"[bold cyan]{title}[/]", style="dim cyan")


def kv(key: str, value: str, width: int = 20) -> None:
    console.print(f"    [dim]{key:<{width}}[/] {value}")


def table_row(cols: list[str], widths: list[int]) -> None:
    parts = []
    for col, w in zip(cols, widths):
        parts.append(f"{col:<{w}}")
    console.print(f"    {'  '.join(parts)}")


# ── Color helpers (return Rich markup strings for use in f-strings) ──────────

def cyan(t: str) -> str:   return f"[cyan]{t}[/cyan]"
def green(t: str) -> str:  return f"[green]{t}[/green]"
def yellow(t: str) -> str: return f"[yellow]{t}[/yellow]"
def red(t: str) -> str:    return f"[red]{t}[/red]"
def dim(t: str) -> str:    return f"[dim]{t}[/dim]"
def bold(t: str) -> str:   return f"[bold]{t}[/bold]"
