"""Build and run a basic LVGL proof of concept on desktop or Whisplay hardware."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

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
DEFAULT_DEV_PI_HOST = "172.16.24.33"
DEFAULT_DEV_PI_USER = "pi"
DEFAULT_DEV_PI_PASSWORD = "voxel"
DEFAULT_DEV_FRAMES_DIR = "./out/lvgl-frames"


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


def _rgb565_to_image(frame_path: Path) -> Image.Image:
    data = frame_path.read_bytes()
    expected = 240 * 280 * 2
    if len(data) != expected:
        raise RuntimeError(f"Unexpected frame size for {frame_path.name}: {len(data)} bytes")

    img = Image.new("RGB", (240, 280))
    pixels = []
    for i in range(0, len(data), 2):
        value = (data[i] << 8) | data[i + 1]
        r = ((value >> 11) & 0x1F) * 255 // 31
        g = ((value >> 5) & 0x3F) * 255 // 63
        b = (value & 0x1F) * 255 // 31
        pixels.append((r, g, b))
    img.putdata(pixels)
    return img


def preview(args) -> int:
    header("Voxel LVGL Preview")
    info("Opening a local preview for pre-rendered LVGL frames.")

    frames_dir = _frames_dir(getattr(args, "frames_dir", None))
    try:
        frame_paths = _load_frame_paths(frames_dir)
        images = [_rgb565_to_image(path) for path in frame_paths]
    except Exception as exc:
        fail(f"LVGL preview failed: {exc}")
        return 1

    gif_path = frames_dir / "preview.gif"
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=max(1, int(getattr(args, "frame_delay", 0.18) * 1000)),
        loop=0,
    )
    ok(f"Wrote preview GIF: {gif_path}")

    if not getattr(args, "open_preview", True):
        return 0

    try:
        if shutil.which("wslview"):
            subprocess.run(["wslview", str(gif_path)], check=False)
        elif shutil.which("xdg-open"):
            subprocess.run(["xdg-open", str(gif_path)], check=False)
        else:
            warn("No preview opener found (tried wslview and xdg-open).")
    except Exception as exc:
        warn(f"Could not open preview automatically ({exc})")

    return 0


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
            return _show_whisplay_frames(
                frame_paths,
                args.backlight,
                args.frame_delay,
                interactive=getattr(args, "interactive_preview", False),
                hold_to_exit=getattr(args, "hold_to_exit", 1.2),
            )
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

    client = _ssh_client(args)

    try:
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


def deploy(args) -> int:
    header("Voxel LVGL Deploy")
    info("Rendering LVGL frames locally, syncing them to the Pi, and optionally starting playback.")

    render_result = render(args)
    if render_result != 0:
        return render_result

    if getattr(args, "preview_local", False):
        preview_result = preview(args)
        if preview_result != 0:
            return preview_result

    sync_result = sync(args)
    if sync_result != 0:
        return sync_result

    if not getattr(args, "play_remote", True):
        return 0

    remote_dir = getattr(args, "remote_dir", "~/voxel/.cache/lvgl-poc-frames")
    remote_dir = remote_dir.replace("~", "/home/pi", 1) if remote_dir.startswith("~/") else remote_dir

    try:
        client = _ssh_client(args)
        try:
            command = (
                f"cd /home/pi/voxel && "
                f"voxel lvgl-play --frames-dir {remote_dir} "
                f"--frame-delay {args.frame_delay} --backlight {args.backlight}"
            )
            if getattr(args, "interactive_preview", False):
                command += f" --interactive-preview --hold-to-exit {args.hold_to_exit}"
            _, stdout, stderr = client.exec_command(command, timeout=600)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if out.strip():
                info(out.strip())
            if err.strip():
                warn(err.strip())
            if code != 0:
                fail(f"Remote playback failed with exit code {code}")
                return code
            ok("Remote playback completed")
            return 0
        finally:
            client.close()
    except Exception as exc:
        fail(f"Remote playback failed: {exc}")
        return 1


def dev(args) -> int:
    header("Voxel LVGL Dev")
    info("Using the default LVGL dev loop: render locally, sync to the Pi, and keep interactive preview enabled.")

    if not getattr(args, "frames_dir", None):
        args.frames_dir = DEFAULT_DEV_FRAMES_DIR
    if not getattr(args, "host", None):
        args.host = DEFAULT_DEV_PI_HOST
    if not getattr(args, "user", None):
        args.user = DEFAULT_DEV_PI_USER
    if not getattr(args, "password", None):
        args.password = DEFAULT_DEV_PI_PASSWORD

    if not hasattr(args, "frames") or args.frames is None:
        args.frames = 24
    if not hasattr(args, "frame_delay") or args.frame_delay is None:
        args.frame_delay = 0.18
    if not hasattr(args, "backlight") or args.backlight is None:
        args.backlight = 70
    if not hasattr(args, "hold_to_exit") or args.hold_to_exit is None:
        args.hold_to_exit = 1.2

    args.play_remote = True
    args.interactive_preview = True
    if not hasattr(args, "preview_local"):
        args.preview_local = False
    if not hasattr(args, "rebuild"):
        args.rebuild = False
    if not hasattr(args, "remote_dir") or args.remote_dir is None:
        args.remote_dir = "~/voxel/.cache/lvgl-poc-frames"

    return deploy(args)


def _ssh_client(args):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {
        "hostname": args.host,
        "username": args.user,
        "timeout": 20,
    }
    if getattr(args, "password", None):
        connect_kwargs["password"] = args.password
    client.connect(**connect_kwargs)
    return client


def _draw_frame(board, frame_path: Path) -> None:
    data = frame_path.read_bytes()
    pixel_data = list(data)
    board.draw_image(0, 0, board.LCD_WIDTH, board.LCD_HEIGHT, pixel_data)


def _show_whisplay_frames(
    frame_paths: list[Path],
    backlight: int,
    delay: float,
    interactive: bool = False,
    hold_to_exit: float = 1.2,
) -> int:
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
        if interactive:
            info("Interactive preview: short press pauses/steps, hold exits.")
            idx = 0
            auto_play = True
            last_tick = time.monotonic()
            was_pressed = False
            press_started = 0.0

            _draw_frame(board, frame_paths[idx])
            info(f"Displayed {frame_paths[idx].name}")

            while True:
                now = time.monotonic()
                pressed = bool(board.button_pressed())

                if auto_play and now - last_tick >= delay:
                    idx = (idx + 1) % len(frame_paths)
                    _draw_frame(board, frame_paths[idx])
                    last_tick = now

                if pressed and not was_pressed:
                    press_started = now

                if pressed and press_started and now - press_started >= hold_to_exit:
                    ok("Interactive preview exit requested")
                    return 0

                if not pressed and was_pressed:
                    held = now - press_started
                    if held < hold_to_exit:
                        if auto_play:
                            auto_play = False
                            info("Preview paused")
                        else:
                            idx = (idx + 1) % len(frame_paths)
                            _draw_frame(board, frame_paths[idx])
                            info(f"Stepped to {frame_paths[idx].name}")
                    press_started = 0.0

                was_pressed = pressed
                time.sleep(0.03)

        for path in frame_paths:
            _draw_frame(board, path)
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
