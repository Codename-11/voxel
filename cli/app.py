"""Voxel CLI — main entry point and command routing."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cli.display import header, section, info, ok, warn, fail, kv, cyan, bold, dim, console, banner, print_commands
from hardware.platform import probe_hardware

VOXEL_DIR = Path(__file__).resolve().parent.parent
SERVICES = ["voxel", "voxel-ui", "voxel-web"]


def _run(cmd: list[str] | str, check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command."""
    kwargs.pop("shell", None)  # _run handles shell based on cmd type
    if isinstance(cmd, str):
        return subprocess.run(cmd, shell=True, check=check, **kwargs)
    return subprocess.run(cmd, check=check, **kwargs)


def _svc_state(name: str) -> str:
    try:
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def _active_services() -> list[str]:
    """Return list of service names that should be managed."""
    active = ["voxel"]

    # Respect explicit config first, then fall back to auto-detection.
    mode = "auto"
    try:
        from config.settings import load_settings

        mode = str(load_settings().get("display", {}).get("mode", "auto")).lower()
    except Exception:
        pass

    probe = probe_hardware()

    if mode == "cog":
        active.append("voxel-ui")
    elif mode == "remote":
        active.append("voxel-web")
    elif probe.recommended_display_mode == "cog":
        active.append("voxel-ui")
    else:
        active.append("voxel-web")
    return active


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_doctor(args: argparse.Namespace) -> int:
    from cli.doctor import run
    return run()


def cmd_display_test(args: argparse.Namespace) -> int:
    from cli.display_test import run

    return run(args)


def cmd_setup(args: argparse.Namespace) -> int:
    header("Voxel Setup")

    # System packages
    info("Installing system dependencies...")
    _run("sudo apt update", shell=True)
    _run("sudo apt install -y git portaudio19-dev libasound2-dev python3-dev ffmpeg", shell=True)

    # Check if cog is available (Pi-specific)
    try:
        _run(["apt-cache", "show", "cog"], capture_output=True, check=True)
        _run("sudo apt install -y cog", shell=True)
    except subprocess.CalledProcessError:
        info("cog package not available (normal on desktop)")

    # Node.js
    if not shutil.which("node"):
        info("Installing Node.js...")
        _run("curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -", shell=True)
        _run("sudo apt install -y nodejs", shell=True)
    else:
        ok(f"Node.js already installed")

    # Build
    cmd_build(args)

    # Config
    local_yaml = VOXEL_DIR / "config" / "local.yaml"
    if not local_yaml.exists():
        shutil.copy(VOXEL_DIR / "config" / "default.yaml", local_yaml)
        info("Created config/local.yaml")
    else:
        ok("config/local.yaml exists")

    # Services
    cmd_install_services(args)

    ok("Setup complete!")
    console.print()
    info("Next steps:")
    console.print(f"    {dim('1.')} Edit config:  {cyan('nano config/local.yaml')}")
    console.print(f"    {dim('2.')} Check health:  {cyan('voxel doctor')}")
    console.print(f"    {dim('3.')} Start:         {cyan('voxel start')}")
    console.print()
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build Python deps + React app."""
    section("Build")

    info("Python dependencies...")
    from hardware.platform import IS_PI
    extra = " --extra pi" if IS_PI else ""
    _run(f"uv sync{extra}", shell=True, cwd=VOXEL_DIR)

    info("React app...")
    _run("npm install", shell=True, cwd=VOXEL_DIR / "app")
    _run("npm run build", shell=True, cwd=VOXEL_DIR / "app")
    ok("Built → app/dist/")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    header("Voxel Update")

    info("Pulling latest...")
    _run(["git", "pull", "origin", "main"], cwd=VOXEL_DIR)

    cmd_build(args)
    cmd_install_services(args)

    info("Restarting services...")
    svcs = " ".join(_active_services())
    _run(f"sudo systemctl restart {svcs}", shell=True)

    ok("Update complete!")
    console.print()
    cmd_status(args)
    return 0


def cmd_hw(args: argparse.Namespace) -> int:
    header("Hardware Setup")

    # Whisplay drivers
    if not Path("/dev/fb1").exists():
        info("Installing Whisplay HAT drivers...")
        tmp = VOXEL_DIR / ".tmp-whisplay"
        _run(f"git clone --depth 1 https://github.com/PiSugar/Whisplay.git {tmp}", shell=True)
        driver_script = tmp / "Driver" / "install_wm8960_drive.sh"
        if driver_script.exists():
            _run(f"sudo bash {driver_script}", shell=True, cwd=tmp / "Driver")
        else:
            warn("Whisplay driver script not found in repo")
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        ok("Whisplay drivers already installed")

    # config.txt tuning
    config_txt = Path("/boot/firmware/config.txt")
    if not config_txt.exists():
        config_txt = Path("/boot/config.txt")

    if config_txt.exists():
        content = config_txt.read_text()
        if "gpu_mem=128" not in content:
            info(f"Tuning {config_txt}...")
            _run(
                f'sudo tee -a {config_txt} > /dev/null <<EOF\n\n# ── Voxel display settings ──\ngpu_mem=128\nhdmi_blanking=2\nEOF',
                shell=True,
            )
            ok("Added gpu_mem=128, hdmi_blanking=2")
        else:
            ok(f"{config_txt} already configured")

    # Swap
    swapfile = Path("/etc/dphys-swapfile")
    if swapfile.exists():
        content = swapfile.read_text()
        for line in content.split("\n"):
            if line.startswith("CONF_SWAPSIZE="):
                current = int(line.split("=")[1])
                if current < 256:
                    info("Increasing swap to 256MB...")
                    _run("sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=256/' /etc/dphys-swapfile", shell=True)
                    _run("sudo systemctl restart dphys-swapfile", shell=True)
                else:
                    ok(f"Swap already {current}MB")
                break

    ok("Hardware setup complete")
    console.print()
    warn("Reboot to activate drivers: sudo reboot")
    console.print()
    return 0


def cmd_install_services(args: argparse.Namespace) -> int:
    """Install systemd unit files."""
    if not shutil.which("systemctl"):
        info("systemd not available — skipping service install")
        return 0

    section("Services")
    for svc_file in ["voxel.service", "voxel-ui.service", "voxel-web.service"]:
        src = VOXEL_DIR / svc_file
        if src.exists():
            _run(f"sudo cp {src} /etc/systemd/system/", shell=True)
    _run("sudo systemctl daemon-reload", shell=True)

    svcs = _active_services()
    _run(f"sudo systemctl enable {' '.join(svcs)}", shell=True)
    ok(f"Services installed: {', '.join(svcs)}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    svcs = " ".join(_active_services())
    info("Starting Voxel...")
    _run(f"sudo systemctl start {svcs}", shell=True)
    import time; time.sleep(2)
    cmd_status(args)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    info("Stopping Voxel...")
    _run(f"sudo systemctl stop {' '.join(SERVICES)}", shell=True)
    cmd_status(args)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    svcs = " ".join(_active_services())
    info("Restarting Voxel...")
    _run(f"sudo systemctl restart {svcs}", shell=True)
    import time; time.sleep(2)
    cmd_status(args)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    svc_args = " ".join(f"-u {s}" for s in SERVICES)
    lines = getattr(args, "lines", 50)
    follow = getattr(args, "follow", True)
    follow_flag = "-f" if follow else ""
    os.execvp("journalctl", ["journalctl", *svc_args.split(), follow_flag, f"-n{lines}", "--no-hostname", "-o", "short-iso"])
    return 0  # unreachable


def cmd_status(args: argparse.Namespace) -> int:
    header("Voxel Status")

    # Services
    section("Services")
    for svc in SERVICES:
        state = _svc_state(svc)
        if state == "active":
            ok(f"{svc}: {state}")
        elif state == "inactive":
            kv(svc, dim(state))
        else:
            kv(svc, state)

    # System
    section("System")
    try:
        r = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    kv("Memory", f"{parts[2]}MB / {parts[1]}MB")
    except Exception:
        pass

    try:
        usage = shutil.disk_usage("/")
        kv("Disk", f"{usage.free / (1024**3):.1f}GB free / {usage.total / (1024**3):.1f}GB total")
    except Exception:
        pass

    # Battery
    try:
        import requests
        resp = requests.get("http://localhost:8421/api/battery", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            kv("Battery", f"{data.get('battery', '?')}%  charging: {data.get('charging', '?')}")
    except Exception:
        pass

    # Hardware
    section("Hardware")
    probe = probe_hardware()
    kv("Whisplay", "detected" if probe.whisplay_detected else "not detected")
    kv("Display", "/dev/fb1" if probe.has_fb1 else "no framebuffer device")
    kv("DRM", "available" if probe.has_drm else "not found")
    kv("Audio", "WM8960" if probe.has_wm8960_audio else "no WM8960")
    kv("UI auto mode", probe.recommended_display_mode)

    console.print()
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    sub = getattr(args, "config_command", None)

    if sub == "set":
        key = args.key
        value = args.value
        parts = key.split(".", 1)
        if len(parts) != 2:
            fail(f"Key must be section.key format (e.g., gateway.token)")
            return 1

        section_name, key_name = parts

        from config.settings import load_settings, save_local_settings
        save_local_settings({section_name: {key_name: value}})
        ok(f"Set {key} = {value[:20]}{'...' if len(value) > 20 else ''}")
        return 0

    elif sub == "get":
        key = args.key
        from config.settings import load_settings
        settings = load_settings()

        current = settings
        for part in key.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break

        if current is not None:
            if isinstance(current, dict):
                import yaml
                console.print(yaml.dump(current, default_flow_style=False))
            else:
                console.print(str(current))
        else:
            warn(f"Key not found: {key}")
            return 1
        return 0

    else:
        # Show current config
        header("Configuration")
        from config.settings import load_settings
        settings = load_settings()
        import yaml
        console.print(yaml.dump(settings, default_flow_style=False, sort_keys=False))
        return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    header("Voxel Uninstall")

    if not getattr(args, "yes", False):
        confirm = input(f"  Remove Voxel from this system? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            info("Cancelled.")
            return 0

    info("Stopping services...")
    for svc in SERVICES:
        _run(f"sudo systemctl stop {svc}", shell=True, capture_output=True)
        _run(f"sudo systemctl disable {svc}", shell=True, capture_output=True)

    info("Removing unit files...")
    for svc in SERVICES:
        _run(f"sudo rm -f /etc/systemd/system/{svc}.service", shell=True)
    _run("sudo systemctl daemon-reload", shell=True)

    info("Removing voxel command...")
    _run("sudo rm -f /usr/local/bin/voxel", shell=True)

    home = Path.home()
    cache = home / ".cache" / "uv"
    if cache.exists():
        info("Cleaning uv cache...")
        shutil.rmtree(cache, ignore_errors=True)

    ok("Uninstall complete")
    console.print()
    info("Kept: Node.js, uv, cog, system packages, Whisplay drivers")
    info(f"Repo still at: {VOXEL_DIR}")
    console.print()
    return 0


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("voxel")
    except Exception:
        return "0.1.0-dev"


def cmd_version(args: argparse.Namespace) -> int:
    banner(_get_version())
    return 0


# ── Argument parser ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voxel",
        description="Voxel Relay — setup, manage, and diagnose your pocket AI companion",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Diagnose system health")
    p_display_test = sub.add_parser("display-test", help="Run a direct display sanity test")
    p_display_test.add_argument("--hold", type=float, default=2.0, help="Seconds to hold the main test pattern")
    p_display_test.add_argument("--color-hold", type=float, default=0.5, help="Seconds to hold each color fill")
    p_display_test.add_argument("--backlight", type=int, default=60, help="Backlight percent for Whisplay tests")
    p_display_test.add_argument("--button-cycle", action="store_true", help="After the auto test, let the hardware button cycle patterns")
    p_display_test.add_argument("--button-timeout", type=float, default=20.0, help="Seconds to keep button cycle mode active")
    sub.add_parser("setup", help="First-time setup (install deps, build, configure services)")
    sub.add_parser("build", help="Build Python deps + React app")
    sub.add_parser("update", help="Pull latest, rebuild, restart services")
    sub.add_parser("hw", help="Install Whisplay HAT drivers + tune config.txt")
    sub.add_parser("start", help="Start Voxel services")
    sub.add_parser("stop", help="Stop Voxel services")
    sub.add_parser("restart", help="Restart Voxel services")

    p_logs = sub.add_parser("logs", help="Tail service logs")
    p_logs.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")
    p_logs.add_argument("--no-follow", action="store_true", help="Don't follow (just print)")

    sub.add_parser("status", help="Show service and system status")

    p_config = sub.add_parser("config", help="Show or modify configuration")
    config_sub = p_config.add_subparsers(dest="config_command")
    p_set = config_sub.add_parser("set", help="Set a config value")
    p_set.add_argument("key", help="Config key (e.g., gateway.token)")
    p_set.add_argument("value", help="Value to set")
    p_get = config_sub.add_parser("get", help="Get a config value")
    p_get.add_argument("key", help="Config key (e.g., gateway.url)")

    p_uninstall = sub.add_parser("uninstall", help="Remove Voxel services and caches")
    p_uninstall.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    sub.add_parser("version", help="Show version")

    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "display-test": cmd_display_test,
    "setup": cmd_setup,
    "build": cmd_build,
    "update": cmd_update,
    "hw": cmd_hw,
    "start": cmd_start,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "logs": cmd_logs,
    "status": cmd_status,
    "config": cmd_config,
    "uninstall": cmd_uninstall,
    "version": cmd_version,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "logs":
        args.follow = not getattr(args, "no_follow", False)

    if args.command in COMMANDS:
        sys.exit(COMMANDS[args.command](args))
    else:
        # No command — show branded TUI welcome
        banner(_get_version())
        print_commands()
        sys.exit(0)
