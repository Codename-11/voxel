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


def print_commands(show_all: bool = False) -> None:
    """Print a styled command list (shown when no command is given)."""
    tbl = Table(
        show_header=False, box=None, padding=(0, 2, 0, 4),
        row_styles=["", "dim"],
    )
    tbl.add_column("cmd", style="bold cyan", min_width=14)
    tbl.add_column("desc")

    # ── Setup & Maintenance ──
    tbl.add_row("[bold dim]Setup[/]", "")
    for cmd, desc in [
        ("setup",     "First-time install & configure"),
        ("configure", "Interactive configuration wizard"),
        ("doctor",    "Run system health diagnostics"),
        ("update",    "Pull latest, rebuild, restart"),
        ("hw",        "Install Whisplay HAT drivers"),
    ]:
        tbl.add_row(cmd, desc)

    # ── Services ──
    tbl.add_row("", "")
    tbl.add_row("[bold dim]Services[/]", "")
    for cmd, desc in [
        ("start",    "Start services"),
        ("stop",     "Stop services"),
        ("restart",  "Restart services"),
        ("logs",     "Tail service logs"),
        ("status",   "Show service & system status"),
    ]:
        tbl.add_row(cmd, desc)

    # ── Configuration ──
    tbl.add_row("", "")
    tbl.add_row("[bold dim]Configuration[/]", "")
    for cmd, desc in [
        ("config",    "Show / get / set configuration"),
        ("backup",    "Export, import, or factory reset"),
        ("uninstall", "Remove services (--nuke for full)"),
        ("version",   "Show version"),
    ]:
        tbl.add_row(cmd, desc)

    # ── Dev Tools ──
    tbl.add_row("", "")
    tbl.add_row("[bold dim]Development[/]", "")
    for cmd, desc in [
        ("dev-pair",    "Discover & pair with a device"),
        ("dev-push",    "Sync runtime to Pi + run"),
        ("dev-logs",    "Tail remote Pi logs"),
        ("dev-restart", "Restart services on Pi"),
        ("dev-ssh",     "SSH into paired Pi"),
    ]:
        tbl.add_row(cmd, desc)

    # ── Experimental (only with --all) ──
    if show_all:
        tbl.add_row("", "")
        tbl.add_row("[bold dim]Experimental[/]", "")
        for cmd, desc in [
            ("display-test", "Direct display sanity test"),
            ("mcp",          "Start MCP server (SSE :8082)"),
            ("lvgl-build",   "Build the LVGL PoC"),
            ("lvgl-render",  "Render LVGL frames"),
            ("lvgl-deploy",  "Render, sync, play on Pi"),
            ("lvgl-dev",     "LVGL dev loop"),
        ]:
            tbl.add_row(cmd, desc)

    console.print(Panel(
        tbl,
        title="[bold]Commands[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 1),
    ))
    hint = "  [dim]Run[/] [cyan]voxel <command> --help[/] [dim]for details[/]"
    if not show_all:
        hint += "\n  [dim]Run[/] [cyan]voxel --all[/] [dim]to see experimental commands[/]"
    console.print(hint)
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
