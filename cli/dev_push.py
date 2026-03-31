"""Push full runtime to Pi and run it — fast dev loop.

Syncs display, backend, state machine, MCP, CLI, config, and shared
data to the Pi over SSH, then starts the display service.

Usage:
    voxel dev-push              # sync + run on Pi
    voxel dev-push --watch      # sync on every local file change
    voxel dev-push --update     # git pull + uv sync on Pi first
"""

from __future__ import annotations

import time
from pathlib import Path

from cli.display import header, info, ok, fail, warn, dim

ROOT = Path(__file__).resolve().parent.parent
REMOTE_DIR = "/home/pi/voxel"

# Files/dirs to sync
SYNC_PATHS = [
    "display/",
    "hw/",
    "shared/",
    "assets/fonts/",
    "config/",
    "core/",
    "states/",
    "server.py",
    "mcp/",
    "cli/",
    "scripts/boot_splash.py",
    "services/",
    "pyproject.toml",
]

DEFAULT_HOST = ""   # set via dev-pair or --host
DEFAULT_USER = "pi"
DEFAULT_PASSWORD = ""  # set via dev-pair or --password


def _load_dev_ssh() -> dict:
    """Load saved SSH config from config/local.yaml dev section."""
    try:
        from config.settings import _read_yaml, LOCAL_PATH
        local = _read_yaml(LOCAL_PATH)
        return local.get("dev", {}).get("ssh", {})
    except Exception:
        return {}


def _save_dev_ssh(host: str, user: str, password: str | None) -> None:
    """Save SSH config to config/local.yaml for future use."""
    from config.settings import save_local_settings
    ssh_cfg: dict = {"host": host, "user": user}
    if password:
        ssh_cfg["password"] = password
    save_local_settings({"dev": {"ssh": ssh_cfg}})
    ok(f"SSH config saved to config/local.yaml (dev.ssh)")


def _resolve_ssh(args) -> tuple[str, str, str | None]:
    """Resolve SSH params: CLI flags > saved config > defaults."""
    saved = _load_dev_ssh()

    host = getattr(args, "host", None) or saved.get("host") or DEFAULT_HOST
    user = getattr(args, "user", None) or saved.get("user") or DEFAULT_USER
    password = getattr(args, "password", None) or saved.get("password") or DEFAULT_PASSWORD

    # Save if user provided explicit flags (so they don't have to repeat)
    if getattr(args, "host", None) or getattr(args, "user", None) or getattr(args, "password", None):
        _save_dev_ssh(host, user, password)

    return host, user, password


def _ssh_client(host: str, user: str, password: str | None = None):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = {"hostname": host, "username": user, "timeout": 20}
    if password:
        kw["password"] = password
    client.connect(**kw)
    return client


def _sftp_sync_dir(sftp, local_dir: Path, remote_base: str, quiet: bool = False) -> int:
    """Recursively sync a local directory to Pi via SFTP. Returns file count."""
    count = 0
    for local_path in sorted(local_dir.rglob("*")):
        if local_path.is_dir():
            continue
        if "__pycache__" in str(local_path) or local_path.suffix == ".pyc":
            continue
        rel = local_path.relative_to(ROOT)
        remote_path = f"{remote_base}/{rel.as_posix()}"

        # Ensure remote directory exists
        remote_dir = "/".join(remote_path.split("/")[:-1])
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            _sftp_makedirs(sftp, remote_dir)

        sftp.put(str(local_path), remote_path)
        count += 1
        if not quiet:
            info(f"  {rel.as_posix()}")
    return count


def _sftp_makedirs(sftp, path: str) -> None:
    """Recursively create remote directories."""
    parts = path.split("/")
    current = ""
    for part in parts:
        if not part:
            current = "/"
            continue
        current = f"{current}/{part}" if current != "/" else f"/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def _sync_file(sftp, local_path: Path, remote_base: str) -> None:
    """Sync a single file."""
    rel = local_path.relative_to(ROOT)
    remote_path = f"{remote_base}/{rel.as_posix()}"
    remote_dir = "/".join(remote_path.split("/")[:-1])
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        _sftp_makedirs(sftp, remote_dir)
    sftp.put(str(local_path), remote_path)


def push(args) -> int:
    """Sync display files to Pi and run the display service."""
    header("Display Push")

    host, user, password = _resolve_ssh(args)
    backlight = getattr(args, "backlight", 70)

    pid = ""
    info(f"Connecting to {user}@{host}")
    try:
        client = _ssh_client(host, user, password)
    except Exception as e:
        fail(f"SSH connection failed: {e}")
        return 1

    try:
        sftp = client.open_sftp()

        # Optional: update Pi repo first
        if getattr(args, "update", False):
            info("Updating Pi (git pull + uv sync)...")
            _, stdout, stderr = client.exec_command(
                f"cd {REMOTE_DIR} && git pull && ~/.local/bin/uv sync --extra pi"
            )
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                warn(f"Pi update had issues: {stderr.read().decode().strip()}")
            else:
                ok("Pi updated")

        # Ensure system libraries are present (only installs if missing)
        _REQUIRED_PKGS = "libportaudio2 portaudio19-dev libasound2-dev ffmpeg"
        _, stdout, _ = client.exec_command(
            f"dpkg -s {_REQUIRED_PKGS} >/dev/null 2>&1 && echo OK || echo MISSING"
        )
        if stdout.read().decode().strip() != "OK":
            info("Installing missing system libraries...")
            _, stdout, stderr = client.exec_command(
                f"sudo apt-get install -y -qq {_REQUIRED_PKGS} 2>&1 | tail -3"
            )
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                ok("System libraries installed")
            else:
                warn(f"System library install issue: {stderr.read().decode().strip()}")

        # Ensure Pi deps are in sync (qrcode, spidev, RPi.GPIO, etc.)
        info("Syncing Pi dependencies...")
        _, stdout, _ = client.exec_command(
            f"cd {REMOTE_DIR} && ~/.local/bin/uv sync --extra pi 2>&1 | tail -2"
        )
        dep_out = stdout.read().decode().strip()
        if dep_out:
            info(f"  {dep_out}")

        # Stop running services (both backend and display)
        info("Stopping services...")
        client.exec_command(
            "sudo systemctl stop voxel-display 2>/dev/null || true; "
            "sudo systemctl stop voxel 2>/dev/null || true; "
            "pkill -f 'python.*display\\.service' 2>/dev/null || true; "
            "pkill -f 'python.*server\\.py' 2>/dev/null || true"
        )
        time.sleep(0.5)

        # Sync files
        info("Syncing files:")
        t0 = time.time()
        total = 0
        for sync_path in SYNC_PATHS:
            local = ROOT / sync_path
            if local.is_dir():
                total += _sftp_sync_dir(sftp, local, REMOTE_DIR)
            elif local.is_file():
                _sync_file(sftp, local, REMOTE_DIR)
                info(f"  {sync_path}")
                total += 1
        elapsed = time.time() - t0
        ok(f"Synced {total} files in {elapsed:.1f}s")

        sftp.close()

        # Install systemd service if requested
        if getattr(args, "install_service", False):
            info("Installing systemd service...")
            cmds = [
                f"sudo cp {REMOTE_DIR}/services/voxel-display.service /etc/systemd/system/",
                "sudo systemctl daemon-reload",
                "sudo systemctl enable voxel-display",
                "sudo systemctl restart voxel-display",
            ]
            for cmd in cmds:
                _, stdout, stderr = client.exec_command(cmd)
                exit_code = stdout.channel.recv_exit_status()
                if exit_code != 0:
                    err = stderr.read().decode().strip()
                    warn(f"  {cmd}: {err}")
                else:
                    info(f"  {cmd}: OK")
            ok("Systemd service installed (auto-starts on boot)")
            use_systemd = True
        else:
            # Check if systemd service is already installed and enabled
            _, stdout, _ = client.exec_command(
                "systemctl is-enabled voxel-display 2>/dev/null"
            )
            is_enabled = stdout.read().decode().strip()
            use_systemd = is_enabled == "enabled"

            if use_systemd:
                info("Restarting services...")
                # Restart backend first (display depends on it)
                _, stdout, _ = client.exec_command(
                    "systemctl is-enabled voxel 2>/dev/null"
                )
                if stdout.read().decode().strip() == "enabled":
                    client.exec_command("sudo systemctl restart voxel")
                    time.sleep(1.0)  # let backend start before display
                client.exec_command("sudo systemctl restart voxel-display")
            else:
                info("Starting display service (manual)...")
                command = (
                    f"cd {REMOTE_DIR} && "
                    f"nohup ~/.local/bin/uv run python -m display.service "
                    f"--backend whisplay "
                    f"> /tmp/voxel-display.log 2>&1 &"
                )
                client.exec_command(command)

        # Wait for service to come up (Pi Zero needs ~10-15s: boot splash + uv build + Python start)
        pid = ""
        for attempt in range(15):
            time.sleep(1.0)
            if use_systemd:
                _, stdout, _ = client.exec_command(
                    "systemctl is-active voxel-display 2>/dev/null"
                )
                if stdout.read().decode().strip() == "active":
                    _, stdout, _ = client.exec_command(
                        "systemctl show -p MainPID voxel-display --value"
                    )
                    pid = stdout.read().decode().strip()
                    break
            else:
                _, stdout, _ = client.exec_command(
                    "pgrep -f 'python.*display\\.service' | head -1"
                )
                pid = stdout.read().decode().strip()
                if pid:
                    break

        if pid and pid != "0":
            ok(f"Display service running (PID {pid})")
        else:
            warn("Display service may not have started — check logs")
            log_cmd = (
                "journalctl -u voxel-display -n 5 --no-pager 2>/dev/null || "
                "tail -5 /tmp/voxel-display.log"
            )
            _, stdout, _ = client.exec_command(log_cmd)
            log_tail = stdout.read().decode().strip()
            if log_tail:
                info(f"Last log lines:\n{log_tail}")

    except Exception as e:
        fail(f"Push failed: {e}")
        return 1
    finally:
        if not (getattr(args, "logs", False) and pid):
            client.close()

    # Attach to live logs using the existing paramiko connection (no re-auth)
    if getattr(args, "logs", False) and pid:
        _tail_logs_paramiko(client)

    return 0


def _tail_logs_paramiko(client) -> None:
    """Stream logs via the existing paramiko SSH connection."""

    info("Attaching to live logs (Ctrl+C to stop)...\n")

    try:
        # Use journalctl if services are installed, tailing both backend + display
        _, stdout, _ = client.exec_command(
            "journalctl -u voxel -u voxel-display -f --no-pager -n 50 2>/dev/null || "
            "tail -f /tmp/voxel-display.log"
        )
        channel = stdout.channel

        while not channel.exit_status_ready():
            if channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="replace")
                print(data, end="", flush=True)
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        info("\nDetached from logs")
    finally:
        try:
            client.close()
        except Exception:
            pass


def push_watch(args) -> int:
    """Watch local files and re-push on changes."""
    try:
        from watchfiles import watch
    except ImportError:
        fail("watchfiles required: uv add watchfiles")
        return 1

    header("Display Push — Watch Mode")
    info("Watching display/, hw/, shared/ for changes...")
    info("Press Ctrl+C to stop\n")

    watch_paths = [str(ROOT / p.rstrip("/")) for p in SYNC_PATHS]

    # Initial push
    push(args)

    try:
        for changes in watch(*watch_paths):
            changed = [Path(c[1]).relative_to(ROOT).as_posix() for c in changes
                       if "__pycache__" not in c[1]]
            if not changed:
                continue
            info(f"\nChanged: {', '.join(changed[:5])}")
            push(args)
    except KeyboardInterrupt:
        info("\nWatch stopped")

    return 0
