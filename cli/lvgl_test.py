"""Build and run a basic LVGL proof of concept on desktop or Whisplay hardware."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

from cli.display import fail, header, info, ok, warn
from cli.display_test import _load_whisplay_board
from hardware.platform import probe_hardware


ROOT = Path(__file__).resolve().parent.parent
POC_DIR = ROOT / "native" / "lvgl_poc"
BUILD_DIR = ROOT / ".cache" / "lvgl-poc-build"
FRAME_DIR = ROOT / ".cache" / "lvgl-poc-frames"
LVGL_DIR = ROOT / ".cache" / "lvgl-src"
LVGL_VERSION = "v8.3.11"
LVGL_URL = f"https://github.com/lvgl/lvgl/archive/refs/tags/{LVGL_VERSION}.tar.gz"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def _ensure_lvgl_source() -> Path:
    cmakelists = LVGL_DIR / "CMakeLists.txt"
    if cmakelists.exists():
        return LVGL_DIR

    archive_path = ROOT / ".cache" / f"lvgl-{LVGL_VERSION}.tar.gz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    info(f"Downloading LVGL {LVGL_VERSION} source...")
    urllib.request.urlretrieve(LVGL_URL, archive_path)

    extract_root = ROOT / ".cache"
    if LVGL_DIR.exists():
        shutil.rmtree(LVGL_DIR)

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(extract_root)

    extracted = extract_root / f"lvgl-{LVGL_VERSION.lstrip('v')}"
    if not extracted.exists():
        candidates = sorted(extract_root.glob("lvgl-*"))
        if not candidates:
            raise RuntimeError("LVGL archive extracted but source directory was not found")
        extracted = candidates[-1]

    extracted.rename(LVGL_DIR)
    return LVGL_DIR


def _build_native_poc() -> Path:
    cmake = shutil.which("cmake")
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cmake or not cc:
        raise RuntimeError("cmake and a C compiler are required (install: sudo apt install cmake build-essential)")

    lvgl_source = _ensure_lvgl_source()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    _run([
        cmake,
        "-S",
        str(POC_DIR),
        "-B",
        str(BUILD_DIR),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DLVGL_SOURCE_DIR={lvgl_source}",
    ])
    _run([cmake, "--build", str(BUILD_DIR), "--config", "Release", "-j2"])
    binary = BUILD_DIR / "voxel_lvgl_poc"
    if not binary.exists():
        raise RuntimeError(f"Build completed but binary missing: {binary}")
    return binary


def _cached_binary_path() -> Path:
    return BUILD_DIR / "voxel_lvgl_poc"


def _render_frames(binary: Path, frames: int, frames_dir: Path) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    for path in frames_dir.glob("frame-*.rgb565"):
        path.unlink()

    _run([str(binary), str(frames_dir), str(frames)])
    rendered = sorted(frames_dir.glob("frame-*.rgb565"))
    if not rendered:
        raise RuntimeError("LVGL PoC did not render any frames")
    return rendered


def _frames_dir(value: str | Path | None) -> Path:
    if not value:
        return FRAME_DIR
    return Path(value).expanduser().resolve()


def _load_frame_paths(frames_dir: Path) -> list[Path]:
    frame_paths = sorted(frames_dir.glob("frame-*.rgb565"))
    if not frame_paths:
        raise RuntimeError(f"No LVGL frame files found in {frames_dir}")
    return frame_paths


def build(args) -> int:
    header("Voxel LVGL Build")
    info("Building the native LVGL proof of concept.")

    try:
        binary = _build_native_poc()
        ok(f"Built LVGL PoC: {binary}")
        return 0
    except Exception as exc:
        fail(f"LVGL build failed: {exc}")
        return 1


def render(args) -> int:
    header("Voxel LVGL Render")
    info("Rendering LVGL frames without playback.")

    binary = _cached_binary_path()
    frames_dir = _frames_dir(getattr(args, "frames_dir", None))
    try:
        if getattr(args, "rebuild", False) or not binary.exists():
            if not binary.exists():
                warn("No cached LVGL PoC binary found; building first.")
            binary = _build_native_poc()
            ok(f"Built LVGL PoC: {binary}")
        else:
            ok(f"Using cached LVGL PoC: {binary}")

        frame_paths = _render_frames(binary, args.frames, frames_dir)
        ok(f"Rendered {len(frame_paths)} LVGL frame(s) to {frames_dir}")
        return 0
    except Exception as exc:
        fail(f"LVGL render failed: {exc}")
        return 1


def play(args) -> int:
    header("Voxel LVGL Play")
    info("Replaying pre-rendered LVGL frames on the display.")

    frames_dir = _frames_dir(getattr(args, "frames_dir", None))
    try:
        frame_paths = _load_frame_paths(frames_dir)
        ok(f"Loaded {len(frame_paths)} LVGL frame(s) from {frames_dir}")
    except Exception as exc:
        fail(f"LVGL frame load failed: {exc}")
        return 1

    probe = probe_hardware()
    if probe.is_pi:
        try:
            return _show_whisplay_frames(frame_paths, args.backlight, args.frame_delay)
        except Exception as exc:
            fail(f"Whisplay playback failed: {exc}")
            return 1

    warn("Desktop mode: frames rendered only; no Whisplay playback available.")
    info(f"Frames loaded from: {frames_dir}")
    return 0


def sync(args) -> int:
    header("Voxel LVGL Sync")
    info("Syncing pre-rendered LVGL frames to the Pi.")

    frames_dir = _frames_dir(getattr(args, "frames_dir", None))
    try:
        frame_paths = _load_frame_paths(frames_dir)
    except Exception as exc:
        fail(f"LVGL frame load failed: {exc}")
        return 1

    try:
        import paramiko
    except Exception:
        fail("paramiko is required for lvgl-sync. Run: uv sync")
        return 1

    remote_dir = getattr(args, "remote_dir", "~/voxel/.cache/lvgl-poc-frames")
    remote_dir = remote_dir.replace("~", "/home/pi", 1) if remote_dir.startswith("~/") else remote_dir

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {
        "hostname": args.host,
        "username": args.user,
        "timeout": 20,
    }
    if getattr(args, "password", None):
        connect_kwargs["password"] = args.password

    try:
        client.connect(**connect_kwargs)
        sftp = client.open_sftp()
        try:
            client.exec_command(f"mkdir -p {remote_dir}")[1].channel.recv_exit_status()
            for path in frame_paths:
                remote_path = f"{remote_dir}/{path.name}"
                sftp.put(str(path), remote_path)
                info(f"Synced {path.name}")
            ok(f"Synced {len(frame_paths)} frame(s) to {args.user}@{args.host}:{remote_dir}")
            return 0
        finally:
            sftp.close()
    except Exception as exc:
        fail(f"LVGL sync failed: {exc}")
        return 1
    finally:
        client.close()


def _show_whisplay_frames(frame_paths: list[Path], backlight: int, delay: float) -> int:
    module = _load_whisplay_board()
    gpio_module = getattr(module, "GPIO", None)
    original_add_event_detect = None
    if gpio_module is not None and hasattr(gpio_module, "add_event_detect"):
        original_add_event_detect = gpio_module.add_event_detect

        def _safe_add_event_detect(*event_args, **event_kwargs):
            try:
                return original_add_event_detect(*event_args, **event_kwargs)
            except Exception as exc:
                warn(f"Button edge detect unavailable during LVGL playback; continuing without button events ({exc})")
                return False

        gpio_module.add_event_detect = _safe_add_event_detect

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
        if gpio_module is not None and original_add_event_detect is not None:
            gpio_module.add_event_detect = original_add_event_detect
        try:
            board.cleanup()
        except Exception:
            pass


def run(args) -> int:
    header("Voxel LVGL Test")
    info("Building a tiny native LVGL app, rendering RGB565 frames, and replaying them on the display.")

    render_result = render(args)
    if render_result != 0:
        return render_result

    args.frames_dir = getattr(args, "frames_dir", None)
    return play(args)
