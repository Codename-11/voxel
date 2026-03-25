"""Build and run a basic LVGL proof of concept on desktop or Whisplay hardware."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from cli.display import fail, header, info, ok, warn
from cli.display_test import _load_whisplay_board
from hardware.platform import probe_hardware


ROOT = Path(__file__).resolve().parent.parent
POC_DIR = ROOT / "native" / "lvgl_poc"
BUILD_DIR = ROOT / ".cache" / "lvgl-poc-build"
FRAME_DIR = ROOT / ".cache" / "lvgl-poc-frames"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def _build_native_poc() -> Path:
    cmake = shutil.which("cmake")
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cmake or not cc:
        raise RuntimeError("cmake and a C compiler are required (install: sudo apt install cmake build-essential)")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    _run([cmake, "-S", str(POC_DIR), "-B", str(BUILD_DIR), "-DCMAKE_BUILD_TYPE=Release"])
    _run([cmake, "--build", str(BUILD_DIR), "--config", "Release", "-j2"])
    binary = BUILD_DIR / "voxel_lvgl_poc"
    if not binary.exists():
        raise RuntimeError(f"Build completed but binary missing: {binary}")
    return binary


def _render_frames(binary: Path, frames: int) -> list[Path]:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    for path in FRAME_DIR.glob("frame-*.rgb565"):
        path.unlink()

    _run([str(binary), str(FRAME_DIR), str(frames)])
    rendered = sorted(FRAME_DIR.glob("frame-*.rgb565"))
    if not rendered:
        raise RuntimeError("LVGL PoC did not render any frames")
    return rendered


def _show_whisplay_frames(frame_paths: list[Path], backlight: int, delay: float) -> int:
    module = _load_whisplay_board()
    board = module.WhisPlayBoard()
    board.set_backlight(backlight)
    try:
        ok(f"Whisplay board initialized at backlight {backlight}%")
        for path in frame_paths:
            data = path.read_bytes()
            pixel_data = list(data)
            board.draw_image(0, 0, board.LCD_WIDTH, board.LCD_HEIGHT, pixel_data)
            info(f"Displayed {path.name}")
            time.sleep(delay)
        ok("LVGL PoC playback complete")
        return 0
    finally:
        try:
            board.cleanup()
        except Exception:
            pass


def run(args) -> int:
    header("Voxel LVGL Test")
    info("Building a tiny native LVGL app, rendering RGB565 frames, and replaying them on the display.")

    try:
        binary = _build_native_poc()
        ok(f"Built LVGL PoC: {binary}")
        frame_paths = _render_frames(binary, args.frames)
        ok(f"Rendered {len(frame_paths)} LVGL frame(s)")
    except Exception as exc:
        fail(f"LVGL build/render failed: {exc}")
        return 1

    probe = probe_hardware()
    if probe.is_pi:
        try:
            return _show_whisplay_frames(frame_paths, args.backlight, args.frame_delay)
        except Exception as exc:
            fail(f"Whisplay playback failed: {exc}")
            return 1

    warn("Desktop mode: frames rendered only; no Whisplay playback available.")
    info(f"Frames written to: {FRAME_DIR}")
    return 0
