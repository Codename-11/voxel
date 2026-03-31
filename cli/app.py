"""Voxel CLI — main entry point and command routing."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cli.display import header, section, info, ok, warn, fail, kv, cyan, bold, dim, console, banner, print_commands
from hw.detect import probe_hardware

VOXEL_DIR = Path(__file__).resolve().parent.parent
SERVICES = ["voxel-splash", "voxel-guardian", "voxel", "voxel-display"]


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
    """Return list of service names that should be managed.

    Production stack:
      - voxel          (server.py — backend, WebSocket, AI pipelines)
      - voxel-display  (display/service.py — PIL renderer, SPI LCD, config UI)
    """
    return list(SERVICES)


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_doctor(args: argparse.Namespace) -> int:
    from cli.doctor import run
    return run()


def cmd_display_test(args: argparse.Namespace) -> int:
    from cli.display_test import run

    return run(args)


def cmd_lvgl_test(args: argparse.Namespace) -> int:
    from cli.lvgl_test import run

    return run(args)


def cmd_lvgl_build(args: argparse.Namespace) -> int:
    from cli.lvgl_test import build

    return build(args)


def cmd_lvgl_play(args: argparse.Namespace) -> int:
    from cli.lvgl_test import play

    return play(args)


def cmd_lvgl_render(args: argparse.Namespace) -> int:
    from cli.lvgl_test import render

    return render(args)


def cmd_lvgl_sync(args: argparse.Namespace) -> int:
    from cli.lvgl_test import sync

    return sync(args)


def cmd_lvgl_deploy(args: argparse.Namespace) -> int:
    from cli.lvgl_test import deploy

    return deploy(args)


def cmd_lvgl_preview(args: argparse.Namespace) -> int:
    from cli.lvgl_test import preview

    return preview(args)


def cmd_lvgl_dev(args: argparse.Namespace) -> int:
    from cli.lvgl_test import dev

    return dev(args)


def _setup_state_path() -> Path:
    return VOXEL_DIR / "config" / ".setup-state"


def _load_setup_state() -> dict:
    """Load the setup state checkpoint file."""
    path = _setup_state_path()
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def _save_setup_state(update: dict) -> None:
    """Merge updates into the setup state checkpoint file."""
    import yaml
    state = _load_setup_state()
    state.update(update)
    _setup_state_path().write_text(yaml.dump(state, default_flow_style=False))


def cmd_configure(args: argparse.Namespace) -> int:
    """Launch the interactive configuration wizard."""
    from cli.setup_wizard import run_wizard
    return run_wizard()


def cmd_setup(args: argparse.Namespace) -> int:
    header("Voxel Setup")

    from hw.detect import IS_PI

    # System packages
    section("System Dependencies")
    info("Installing system dependencies...")
    _run("sudo apt update", shell=True)
    _run("sudo apt install -y git portaudio19-dev libasound2-dev python3-dev ffmpeg", shell=True)

    # Node.js
    if not shutil.which("node"):
        info("Installing Node.js...")
        _run("curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -", shell=True)
        _run("sudo apt install -y nodejs", shell=True)
    else:
        ok("Node.js already installed")

    _save_setup_state({"system_deps": True})

    # Hardware drivers (Pi only — includes Whisplay HAT, config.txt, swap)
    if IS_PI:
        section("Hardware Drivers")
        cmd_hw(args)
        _save_setup_state({"drivers_installed": True})

    # Build
    cmd_build(args)
    _save_setup_state({"build_complete": True})

    # Config
    local_yaml = VOXEL_DIR / "config" / "local.yaml"
    if not local_yaml.exists():
        shutil.copy(VOXEL_DIR / "config" / "default.yaml", local_yaml)
        info("Created config/local.yaml")
    else:
        ok("config/local.yaml exists")
    _save_setup_state({"config_created": True})

    # Services
    cmd_install_services(args)
    _save_setup_state({"services_installed": True})

    ok("Setup complete!")
    console.print()

    # Launch interactive configuration wizard (unless --no-configure)
    if not getattr(args, "no_configure", False):
        from cli.setup_wizard import run_wizard
        run_wizard()
    else:
        if IS_PI:
            info("Reboot to activate hardware drivers:")
            console.print(f"    {cyan('sudo reboot')}")
            console.print()
            info("After reboot, the device will auto-start and guide you through:")
            console.print(f"    {dim('1.')} WiFi setup  {dim('(if not connected)')}")
            console.print(f"    {dim('2.')} Configuration  {dim('(scan QR on screen)')}")
            console.print(f"    {dim('3.')} Ready to use!")
        else:
            info("Next steps:")
            console.print(f"    {dim('1.')} Preview display: {cyan('uv run dev')}")
            console.print(f"    {dim('2.')} Check health:    {cyan('voxel doctor')}")
        console.print()
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build Python deps + React app."""
    section("Build")

    info("Python dependencies...")
    from hw.detect import IS_PI
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

    # Kernel headers (needed for DKMS driver compilation)
    r = _run("dpkg -s raspberrypi-kernel-headers >/dev/null 2>&1", shell=True)
    if r.returncode != 0:
        info("Installing kernel headers for driver compilation...")
        kernel = _run("uname -r", shell=True, capture_output=True, text=True).stdout.strip()
        header_pkg = f"linux-headers-{kernel}"
        r2 = _run(f"sudo apt-get install -y -qq {header_pkg}", shell=True)
        if r2.returncode == 0:
            ok(f"Kernel headers installed ({header_pkg})")
        else:
            warn(f"Could not install {header_pkg} — driver compilation may fail")

    # WhisPlay.py display driver — vendored in hw/WhisPlay.py
    vendored_driver = VOXEL_DIR / "hw" / "WhisPlay.py"
    if vendored_driver.exists():
        ok("WhisPlay.py display driver: vendored in hw/")
    else:
        warn("WhisPlay.py display driver missing from hw/ — display may not work")

    # WM8960 audio codec kernel module (requires cloning the Whisplay repo)
    # Check if wm8960 is already loaded
    code = _run("grep -qi wm8960 /proc/asound/cards 2>/dev/null", shell=True).returncode
    if code == 0:
        ok("WM8960 audio codec already installed")
    else:
        info("Installing WM8960 audio codec driver...")
        tmp = VOXEL_DIR / ".tmp-whisplay"
        _run(f"git clone --depth 1 https://github.com/PiSugar/Whisplay.git {tmp}", shell=True)

        # Install WM8960 audio codec kernel module
        driver_script = tmp / "Driver" / "install_wm8960_drive.sh"
        if driver_script.exists():
            # Pipe 'y' to accept the interactive prompt
            _run(f"echo y | sudo bash {driver_script}", shell=True, cwd=tmp / "Driver")
        else:
            warn("Whisplay driver script not found in repo")
        shutil.rmtree(tmp, ignore_errors=True)

    # config.txt tuning
    config_txt = Path("/boot/firmware/config.txt")
    if not config_txt.exists():
        config_txt = Path("/boot/config.txt")

    if config_txt.exists():
        content = config_txt.read_text()

        # Display / GPU settings
        if "gpu_mem=128" not in content:
            info(f"Tuning {config_txt}...")
            _run(
                f'sudo tee -a {config_txt} > /dev/null <<EOF\n\n# ── Voxel display settings ──\ngpu_mem=128\nhdmi_blanking=2\nEOF',
                shell=True,
            )
            ok("Added gpu_mem=128, hdmi_blanking=2")
        else:
            ok(f"{config_txt} display settings already configured")

        # Early boot GPIO directives — processed by GPU firmware ~1.5s after
        # power-on, before Linux starts.  LED turns cyan immediately; backlight
        # stays off (no blue screen flash) until the guardian writes a frame.
        #   RGB LED: active-LOW (common-anode) — dl = on, dh = off
        #     GPIO 25 (red)   = dh → off
        #     GPIO 24 (green) = dl → on
        #     GPIO 23 (blue)  = dl → on  → cyan
        #   LCD backlight: active-LOW — dh = off
        #     GPIO 22 = dh → backlight off until splash ready
        content = config_txt.read_text()  # re-read after possible append above
        if "gpio=25=op,dh" not in content:
            info("Adding early boot GPIO directives...")
            gpio_block = "\n".join([
                "",
                "# ── Voxel early boot indicators ──",
                "# RGB LED cyan at firmware time (active-LOW: dl=on, dh=off)",
                "gpio=25=op,dh",
                "gpio=24=op,dl",
                "gpio=23=op,dl",
                "# LCD backlight OFF until splash ready (active-LOW: dh=off)",
                "gpio=22=op,dh",
            ])
            _run(
                f"sudo tee -a {config_txt} > /dev/null <<'EOF'\n{gpio_block}\nEOF",
                shell=True,
            )
            ok("Added early boot GPIO: cyan LED + backlight off")
        else:
            ok(f"{config_txt} early boot GPIO already configured")

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

    # ALSA mixer levels for WM8960 (speaker volume, mic boost, capture gain)
    if shutil.which("amixer"):
        info("Configuring WM8960 audio levels...")
        alsa_cmds = [
            ("Speaker", "121"),              # speaker output (~80%)
            ("Playback", "230"),             # DAC playback level
            ("Capture", "45"),               # ADC capture level
            ("Left Input Boost Mixer LINPUT1", "2"),   # mic boost +20dB
            ("Right Input Boost Mixer RINPUT1", "2"),  # mic boost +20dB
        ]
        for control, value in alsa_cmds:
            result = subprocess.run(
                ["amixer", "sset", control, value],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                info(f"  {control} = {value}")
            else:
                # Controls may not exist if driver not loaded yet
                pass
        ok("Audio levels configured (effective after reboot if drivers were just installed)")

    # Boot splash (C program for instant LCD image at boot)
    section("Boot Splash")
    splash_dir = VOXEL_DIR / "native" / "boot_splash"
    splash_bin = Path("/usr/local/bin/voxel-splash")
    splash_frame = Path("/boot/voxel-splash.rgb565")

    # Generate the splash frame if not present
    gen_script = splash_dir / "generate_splash.py"
    frame_src = splash_dir / "splash.rgb565"
    if gen_script.exists() and not frame_src.exists():
        info("Generating splash frame...")
        _run(f"python3 {gen_script} --output-dir {splash_dir}", shell=True, cwd=splash_dir)

    # Install the frame
    if frame_src.exists():
        _run(f"sudo cp {frame_src} {splash_frame}", shell=True)
        ok(f"Splash frame installed to {splash_frame}")
    else:
        warn("Splash frame not found — run 'python3 native/boot_splash/generate_splash.py'")

    # Compile and install the C splash binary
    splash_src = splash_dir / "splash.c"
    if shutil.which("gcc") and splash_src.exists():
        info("Compiling boot splash...")
        result = _run(
            f"gcc -O2 -Wall -o {splash_dir / 'splash'} {splash_src}",
            shell=True,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            _run(f"sudo cp {splash_dir / 'splash'} {splash_bin}", shell=True)
            _run(f"sudo chmod 755 {splash_bin}", shell=True)
            ok(f"Boot splash compiled and installed to {splash_bin}")
        else:
            warn(f"Splash compilation failed: {result.stderr.strip()}")
    elif splash_bin.exists():
        ok("Boot splash binary already installed")
    else:
        warn("gcc not available — skipping splash compilation (install with: sudo apt install gcc)")

    # ── Optional: fbtft framebuffer overlay ────────────────────────────────
    if getattr(args, "fbtft", False):
        section("fbtft Framebuffer (Experimental)")
        warn("This is EXPERIMENTAL and may conflict with the WhisPlay SPI driver.")
        warn("When the fbtft overlay is active, /dev/spidev0.0 disappears.")
        warn("The display service must use --backend framebuffer instead.")
        console.print()

        fb_config_txt = Path("/boot/firmware/config.txt")
        if not fb_config_txt.exists():
            fb_config_txt = Path("/boot/config.txt")

        if not fb_config_txt.exists():
            fail("Cannot find config.txt — is this a Raspberry Pi?")
        else:
            fb_content = fb_config_txt.read_text()

            # Add fbtft overlay if not already present
            if "mipi-dbi-spi" not in fb_content:
                info(f"Adding mipi-dbi-spi overlay to {fb_config_txt}...")
                fbtft_block = "\n".join([
                    "",
                    "# ── Voxel LCD Framebuffer (experimental — boot console on LCD) ──",
                    "# WARNING: This makes the kernel own the SPI display.",
                    "# The Python display service needs --backend framebuffer.",
                    "dtoverlay=mipi-dbi-spi,speed=32000000",
                    "dtparam=compatible=panel-mipi-dbi-spi",
                    "dtparam=write-only",
                    "dtparam=width=240,height=280",
                    "dtparam=y-offset=20",
                    "dtparam=reset-gpio=4,dc-gpio=27,backlight-gpio=22",
                ])
                _run(
                    f"sudo tee -a {fb_config_txt} > /dev/null <<'EOF'\n{fbtft_block}\nEOF",
                    shell=True,
                )
                ok("Added mipi-dbi-spi overlay to config.txt")
            else:
                ok("mipi-dbi-spi overlay already in config.txt")

            # Add fbcon=map:10 to cmdline.txt
            cmdline_txt = Path("/boot/firmware/cmdline.txt")
            if not cmdline_txt.exists():
                cmdline_txt = Path("/boot/cmdline.txt")

            if cmdline_txt.exists():
                cmdline = cmdline_txt.read_text().strip()
                additions = []
                if "fbcon=map:10" not in cmdline:
                    additions.append("fbcon=map:10")
                if "logo.nologo" not in cmdline:
                    additions.append("logo.nologo")

                if additions:
                    new_cmdline = cmdline + " " + " ".join(additions)
                    info(f"Adding {' '.join(additions)} to {cmdline_txt}...")
                    _run(
                        f"echo '{new_cmdline}' | sudo tee {cmdline_txt} > /dev/null",
                        shell=True,
                    )
                    ok("Updated cmdline.txt")
                else:
                    ok("cmdline.txt already has fbcon and logo settings")
            else:
                warn("Cannot find cmdline.txt — skipping console routing")

        console.print()
        info("After reboot, boot console will appear on the LCD.")
        info("Start the display service with: --backend framebuffer")
        warn("To revert, remove the mipi-dbi-spi lines from config.txt")
        warn("and remove 'fbcon=map:10 logo.nologo' from cmdline.txt.")
        console.print()

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
    svc_dir = VOXEL_DIR / "services"
    for svc_file in ["voxel-splash.service", "voxel-guardian.service", "voxel.service", "voxel-display.service"]:
        src = svc_dir / svc_file
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
    nuke = getattr(args, "nuke", False)

    if nuke:
        warn("NUKE MODE — will remove everything including repo, config, and drivers")

    if not getattr(args, "yes", False):
        prompt = "  Remove ALL Voxel data from this system? [y/N] " if nuke else "  Remove Voxel services? [y/N] "
        confirm = input(prompt).strip().lower()
        if confirm not in ("y", "yes"):
            info("Cancelled.")
            return 0

    # Stop and disable all services (including first-boot)
    info("Stopping services...")
    all_services = SERVICES + ["voxel-first-boot"]
    for svc in all_services:
        _run(f"sudo systemctl stop {svc}", shell=True, capture_output=True)
        _run(f"sudo systemctl disable {svc}", shell=True, capture_output=True)

    info("Removing unit files...")
    for svc in all_services:
        _run(f"sudo rm -f /etc/systemd/system/{svc}.service", shell=True)
    _run("sudo systemctl daemon-reload", shell=True)

    info("Removing voxel commands...")
    _run("sudo rm -f /usr/local/bin/voxel /usr/local/bin/voxel-splash", shell=True)

    # Remove boot splash frame
    for splash_path in ["/boot/voxel-splash.rgb565", "/boot/firmware/voxel-splash.rgb565"]:
        if Path(splash_path).exists():
            _run(f"sudo rm -f {splash_path}", shell=True)
            info(f"Removed {splash_path}")

    # Remove setup state
    setup_state = VOXEL_DIR / "config" / ".setup-state"
    if setup_state.exists():
        setup_state.unlink()
        info("Removed setup state")

    # Remove local config
    local_yaml = VOXEL_DIR / "config" / "local.yaml"
    if local_yaml.exists():
        local_yaml.unlink()
        info("Removed config/local.yaml")

    # Remove display lock/flag files
    for tmp_file in ["/tmp/voxel-display.lock", "/tmp/voxel-wifi-setup"]:
        if Path(tmp_file).exists():
            _run(f"rm -f {tmp_file}", shell=True)

    home = Path.home()
    cache = home / ".cache" / "uv"
    if cache.exists():
        info("Cleaning uv cache...")
        shutil.rmtree(cache, ignore_errors=True)

    if nuke:
        # Remove the entire repo
        info(f"Removing {VOXEL_DIR}...")
        # Can't rmtree ourselves while running, use a detached rm
        _run(f"nohup bash -c 'sleep 1 && rm -rf {VOXEL_DIR}' >/dev/null 2>&1 &", shell=True)
        ok("Nuke complete — repo will be removed momentarily")
    else:
        ok("Uninstall complete")
        console.print()
        info("Kept: repo, system packages, Whisplay audio drivers")
        info(f"Repo still at: {VOXEL_DIR}")
        info("To fully remove: voxel uninstall --nuke")

    console.print()
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    """Export or import device backup, or factory reset."""
    action = getattr(args, "backup_command", None)

    if action == "export":
        from config.settings import export_backup
        import json
        backup = export_backup()
        out_path = getattr(args, "output", None) or "voxel-backup.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)
        ok(f"Backup exported to {out_path}")
        info(f"Contains {len(backup.get('local_settings', {}))} setting sections")
        return 0

    elif action == "import":
        import json
        path = args.file
        if not Path(path).exists():
            fail(f"File not found: {path}")
            return 1
        with open(path, "r", encoding="utf-8") as f:
            backup = json.load(f)
        from config.settings import import_backup
        import_backup(backup)
        ok(f"Backup restored from {path}")
        info("Restart services for changes to take effect")
        return 0

    elif action == "factory-reset":
        if not getattr(args, "yes", False):
            console.print("  [bold red]WARNING:[/] This will delete ALL user settings.")
            confirm = input("  Continue with factory reset? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                info("Cancelled.")
                return 0
        from config.settings import factory_reset
        factory_reset()
        ok("Factory reset complete")
        info("Device will need reconfiguration (WiFi, gateway token, etc.)")
        return 0

    else:
        header("Backup & Restore")
        info("voxel backup export [-o file]    Export settings to JSON")
        info("voxel backup import <file>       Restore from backup file")
        info("voxel backup factory-reset [-y]  Delete all user config")
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


def cmd_dev_push(args: argparse.Namespace) -> int:
    from cli.dev_push import push, push_watch, _resolve_ssh, _save_dev_ssh, _load_dev_ssh

    if getattr(args, "save_ssh", False):
        host, user, password = _resolve_ssh(args)
        _save_dev_ssh(host, user, password)
        return 0

    if getattr(args, "watch", False):
        return push_watch(args)
    return push(args)


def cmd_dev_ssh(args: argparse.Namespace) -> int:
    """SSH into Pi using saved credentials."""
    from cli.dev_push import _resolve_ssh

    host, user, _password = _resolve_ssh(args)
    info(f"Connecting to {user}@{host}...")
    subprocess.run(["ssh", f"{user}@{host}"])
    return 0


def cmd_dev_logs(args: argparse.Namespace) -> int:
    """Tail Pi display logs remotely."""
    from cli.dev_push import _resolve_ssh, _ssh_client, _tail_logs_paramiko

    host, user, password = _resolve_ssh(args)
    info(f"Connecting to {user}@{host}...")
    try:
        client = _ssh_client(host, user, password)
    except Exception as e:
        fail(f"SSH connection failed: {e}")
        return 1
    _tail_logs_paramiko(client)
    return 0


def cmd_dev_restart(args: argparse.Namespace) -> int:
    """Restart display service on Pi remotely."""
    from cli.dev_push import _resolve_ssh, _ssh_client, REMOTE_DIR

    host, user, password = _resolve_ssh(args)
    info(f"Connecting to {user}@{host}...")
    try:
        client = _ssh_client(host, user, password)
    except Exception as e:
        fail(f"SSH connection failed: {e}")
        return 1

    try:
        # Detect if systemd service is installed
        _, stdout, _ = client.exec_command(
            "systemctl is-enabled voxel-display 2>/dev/null"
        )
        use_systemd = stdout.read().decode().strip() == "enabled"

        if use_systemd:
            info("Restarting services...")
            # Restart backend first (display depends on it)
            _, stdout, _ = client.exec_command(
                "systemctl is-enabled voxel 2>/dev/null"
            )
            if stdout.read().decode().strip() == "enabled":
                client.exec_command("sudo systemctl restart voxel")
                import time; time.sleep(1.0)
            _, stdout, stderr = client.exec_command(
                "sudo systemctl restart voxel-display"
            )
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                warn(f"Restart failed: {stderr.read().decode().strip()}")
        else:
            info("Restarting display service (manual)...")
            client.exec_command(
                "pkill -f 'python.*server\\.py' || true; "
                "pkill -f 'python.*display\\.service' || true"
            )
            import time; time.sleep(0.5)
            client.exec_command(
                f"cd {REMOTE_DIR} && "
                f"nohup ~/.local/bin/uv run python -m display.service "
                f"--backend whisplay "
                f"> /tmp/voxel-display.log 2>&1 &"
            )

        import time; time.sleep(1.0)
        _, stdout, _ = client.exec_command("pgrep -f 'python.*display\\.service' | head -1")
        pid = stdout.read().decode().strip()
        if pid:
            ok(f"Display service restarted (PID {pid})")
        else:
            warn("Display service may not have started — check logs")
    except Exception as e:
        fail(f"Restart failed: {e}")
        return 1
    finally:
        client.close()
    return 0


def cmd_dev_pair(args: argparse.Namespace) -> int:
    """Pair with a Voxel device — auto-discover or specify IP, enter PIN."""
    from cli.dev_push import _save_dev_ssh
    from display.advertiser import discover_devices

    host = getattr(args, "host", None)
    config_port = getattr(args, "port", None) or 8081

    if not host:
        # Auto-discover
        info("Scanning for Voxel devices on network...")
        devices = discover_devices(timeout=5.0)

        if not devices:
            warn("No Voxel devices found. Make sure the device is on and connected to the same network.")
            info("You can also specify the IP manually: voxel dev-pair --host <ip>")
            return 1

        if len(devices) == 1:
            device = devices[0]
            host = device["ip"]
            config_port = device.get("port", config_port)
            info(f"Found: {device['name']} at {host} (v{device.get('version', '?')})")
        else:
            # Multiple devices — let user pick
            for i, d in enumerate(devices):
                info(f"  [{i+1}] {d['name']} at {d['ip']} (v{d.get('version', '?')})")
            choice = input("  Select device [1]: ").strip() or "1"
            try:
                device = devices[int(choice) - 1]
            except (ValueError, IndexError):
                fail("Invalid selection")
                return 1
            host = device["ip"]
            config_port = device.get("port", config_port)

    # Request pairing approval on device
    import json
    import urllib.request

    from display.config_server import get_local_ip
    dev_ip = get_local_ip()

    info("Requesting approval on device...")
    info("  Tap the button on Voxel to approve, or hold to deny")

    approved = False
    try:
        pair_req_url = f"http://{host}:{config_port}/api/dev/pair/request"
        req_pair = urllib.request.Request(
            pair_req_url,
            data=json.dumps({"dev_host": dev_ip}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req_pair, timeout=35)
        result = json.loads(resp.read())
        approved = result.get("approved", False)
        if result.get("timeout"):
            warn("Approval timed out on device")
            return 1
    except Exception as e:
        warn(f"Could not reach device: {e}")
        info("Falling back to manual PIN entry")
        approved = True  # skip approval if device doesn't support it

    if not approved:
        fail("Pairing denied on device")
        return 1

    ok("Approved on device!")

    # Get PIN from user
    pin = input(f"  Enter PIN shown on device display: ").strip()

    if not pin:
        fail("No PIN entered")
        return 1

    # Call pairing API
    import json
    import urllib.request

    from display.config_server import get_local_ip

    url = f"http://{host}:{config_port}/api/dev/pair"
    req = urllib.request.Request(
        url,
        data=json.dumps({"pin": pin, "dev_host": get_local_ip()}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
    except Exception as e:
        fail(f"Pairing failed: {e}")
        return 1

    if not result.get("ok"):
        fail(f"Pairing failed: {result.get('error', 'unknown')}")
        return 1

    # Save SSH credentials locally
    _save_dev_ssh(result["host"], result["user"], result.get("password"))

    ok(f"Paired with Voxel at {result['host']}")
    info(f"  SSH: {result['user']}@{result['host']}")
    info(f"  Config: http://{result['host']}:{result.get('config_port', 8081)}")
    info(f"  Dev mode enabled on device")
    info("")
    info("  You can now use:")
    info("    voxel dev-push         -- sync + run on device")
    info("    voxel dev-logs         -- tail device logs")
    info("    voxel dev-ssh          -- SSH into device")

    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Start the MCP server for AI agent integration."""
    cmd = [sys.executable, "-m", "mcp"]

    transport = getattr(args, "transport", None) or "sse"
    cmd.extend(["--transport", transport])

    port = getattr(args, "port", None) or 8082
    cmd.extend(["--port", str(port)])

    ws_url = getattr(args, "ws_url", None) or "ws://localhost:8080"
    cmd.extend(["--ws-url", ws_url])

    info(f"Starting Voxel MCP server ({transport} on :{port})...")
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_dev_setup(args: argparse.Namespace) -> int:
    """One-time dev setup — save SSH creds + enable dev mode on Pi."""
    from cli.dev_push import _resolve_ssh, _save_dev_ssh, _ssh_client

    host, user, password = _resolve_ssh(args)
    _save_dev_ssh(host, user, password)

    info(f"Connecting to {user}@{host} to enable dev mode...")
    try:
        client = _ssh_client(host, user, password)
    except Exception as e:
        fail(f"SSH connection failed: {e}")
        return 1

    try:
        # Enable dev mode in local.yaml on Pi
        cmd = (
            "cd /home/pi/voxel && "
            "python3 -c \""
            "from config.settings import save_local_settings; "
            "save_local_settings({'dev': {'enabled': True}}); "
            "print('ok')\""
        )
        _, stdout, stderr = client.exec_command(cmd)
        result = stdout.read().decode().strip()
        if "ok" in result:
            ok("Dev mode enabled on Pi (dev.enabled: true in local.yaml)")
        else:
            err_out = stderr.read().decode().strip()
            warn(f"Could not set dev mode on Pi: {err_out or 'unknown error'}")
    except Exception as e:
        fail(f"Dev setup failed: {e}")
        return 1
    finally:
        client.close()

    ok("Dev setup complete!")
    info("  SSH credentials saved to config/local.yaml")
    info("  Dev mode enabled on Pi")
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
    p_lvgl_test = sub.add_parser("lvgl-test", help="Build and run a basic LVGL proof of concept")
    p_lvgl_test.add_argument("--frames", type=int, default=24, help="Number of LVGL frames to render")
    p_lvgl_test.add_argument("--frame-delay", type=float, default=0.18, help="Seconds to display each rendered frame")
    p_lvgl_test.add_argument("--backlight", type=int, default=70, help="Backlight percent for Whisplay playback")
    p_lvgl_build = sub.add_parser("lvgl-build", help="Build the LVGL proof of concept once")
    p_lvgl_render = sub.add_parser("lvgl-render", help="Render LVGL frames without playback")
    p_lvgl_render.add_argument("--frames", type=int, default=24, help="Number of LVGL frames to render")
    p_lvgl_render.add_argument("--frames-dir", help="Directory to write rendered RGB565 frames")
    p_lvgl_render.add_argument("--rebuild", action="store_true", help="Force a rebuild before rendering frames")
    p_lvgl_play = sub.add_parser("lvgl-play", help="Render and play the cached LVGL proof of concept")
    p_lvgl_play.add_argument("--frames-dir", help="Directory containing pre-rendered RGB565 frames")
    p_lvgl_play.add_argument("--frame-delay", type=float, default=0.18, help="Seconds to display each rendered frame")
    p_lvgl_play.add_argument("--backlight", type=int, default=70, help="Backlight percent for Whisplay playback")
    p_lvgl_play.add_argument("--interactive-preview", action="store_true", help="Keep the preview running and use the hardware button to pause/step/exit")
    p_lvgl_play.add_argument("--hold-to-exit", type=float, default=1.2, help="Seconds to hold the button before exiting interactive preview")
    p_lvgl_sync = sub.add_parser("lvgl-sync", help="Sync rendered LVGL frames to a Pi over SSH")
    p_lvgl_sync.add_argument("--frames-dir", help="Directory containing pre-rendered RGB565 frames")
    p_lvgl_sync.add_argument("--host", default="voxel", help="SSH host for the Pi")
    p_lvgl_sync.add_argument("--user", default="pi", help="SSH user for the Pi")
    p_lvgl_sync.add_argument("--password", help="SSH password for the Pi (optional if keys are configured)")
    p_lvgl_sync.add_argument("--remote-dir", default="~/voxel/.cache/lvgl-poc-frames", help="Remote directory for synced frames")
    p_lvgl_deploy = sub.add_parser("lvgl-deploy", help="Render locally, sync to the Pi, and play remotely")
    p_lvgl_deploy.add_argument("--frames", type=int, default=24, help="Number of LVGL frames to render")
    p_lvgl_deploy.add_argument("--frames-dir", help="Directory to write rendered RGB565 frames")
    p_lvgl_deploy.add_argument("--rebuild", action="store_true", help="Force a rebuild before rendering frames")
    p_lvgl_deploy.add_argument("--frame-delay", type=float, default=0.18, help="Seconds to display each rendered frame on the Pi")
    p_lvgl_deploy.add_argument("--backlight", type=int, default=70, help="Backlight percent for Whisplay playback")
    p_lvgl_deploy.add_argument("--host", default="voxel", help="SSH host for the Pi")
    p_lvgl_deploy.add_argument("--user", default="pi", help="SSH user for the Pi")
    p_lvgl_deploy.add_argument("--password", help="SSH password for the Pi (optional if keys are configured)")
    p_lvgl_deploy.add_argument("--remote-dir", default="~/voxel/.cache/lvgl-poc-frames", help="Remote directory for synced frames")
    p_lvgl_deploy.add_argument("--no-play-remote", action="store_true", help="Only render and sync; do not trigger playback on the Pi")
    p_lvgl_deploy.add_argument("--preview-local", action="store_true", help="Generate and open a local preview GIF before syncing")
    p_lvgl_deploy.add_argument("--interactive-preview", action="store_true", help="After syncing, keep playback running on the Pi and use the hardware button to pause/step/exit")
    p_lvgl_deploy.add_argument("--hold-to-exit", type=float, default=1.2, help="Seconds to hold the button before exiting interactive preview")
    p_lvgl_deploy.add_argument("--update-pi", action="store_true", help="Run git pull and uv sync on the Pi before playback")
    p_lvgl_preview = sub.add_parser("lvgl-preview", help="Generate a local preview GIF from rendered LVGL frames")
    p_lvgl_preview.add_argument("--frames-dir", help="Directory containing pre-rendered RGB565 frames")
    p_lvgl_preview.add_argument("--frame-delay", type=float, default=0.18, help="Frame delay in seconds for the preview GIF")
    p_lvgl_preview.add_argument("--no-open-preview", action="store_true", help="Write the preview GIF without opening it")
    p_lvgl_dev = sub.add_parser("lvgl-dev", help="Opinionated default LVGL dev loop")
    p_lvgl_dev.add_argument("--frames", type=int, help="Number of LVGL frames to render")
    p_lvgl_dev.add_argument("--frames-dir", help="Directory to write rendered RGB565 frames")
    p_lvgl_dev.add_argument("--rebuild", action="store_true", help="Force a rebuild before rendering frames")
    p_lvgl_dev.add_argument("--frame-delay", type=float, help="Seconds to display each rendered frame on the Pi")
    p_lvgl_dev.add_argument("--backlight", type=int, help="Backlight percent for Whisplay playback")
    p_lvgl_dev.add_argument("--host", help="SSH host for the Pi")
    p_lvgl_dev.add_argument("--user", help="SSH user for the Pi")
    p_lvgl_dev.add_argument("--password", help="SSH password for the Pi")
    p_lvgl_dev.add_argument("--remote-dir", help="Remote directory for synced frames")
    p_lvgl_dev.add_argument("--preview-local", action="store_true", help="Generate and open a local preview GIF before syncing")
    p_lvgl_dev.add_argument("--hold-to-exit", type=float, help="Seconds to hold the button before exiting interactive preview")
    p_lvgl_dev.add_argument("--update-pi", action="store_true", help="Run git pull and uv sync on the Pi before playback")
    # ── Dev push commands ──
    p_dp = sub.add_parser("dev-push", help="Sync full runtime to Pi over SSH and run it")
    p_dp.add_argument("--host", help="Pi SSH host (set via dev-pair or provide here)")
    p_dp.add_argument("--user", help="Pi SSH user (default: pi)")
    p_dp.add_argument("--password", help="Pi SSH password")
    p_dp.add_argument("--backlight", type=int, default=70, help="Backlight percent")
    p_dp.add_argument("--update", action="store_true", help="git pull + uv sync on Pi first")
    p_dp.add_argument("--watch", action="store_true", help="Watch for changes and re-push automatically")
    p_dp.add_argument("--logs", action="store_true", help="Attach to live display logs after push")
    p_dp.add_argument("--save-ssh", action="store_true", help="Save SSH config to local.yaml for future use")
    p_dp.add_argument("--install-service", action="store_true", help="Install systemd service for auto-start on boot")

    # ── Dev convenience commands ──
    _dev_ssh_flags = [
        ("--host", {"help": "Pi SSH host"}),
        ("--user", {"help": "Pi SSH user"}),
        ("--password", {"help": "Pi SSH password"}),
    ]

    p_dev_ssh = sub.add_parser("dev-ssh", help="SSH into Pi using saved credentials")
    for flag, kw in _dev_ssh_flags:
        p_dev_ssh.add_argument(flag, **kw)

    p_dev_logs = sub.add_parser("dev-logs", help="Tail Pi display logs remotely")
    for flag, kw in _dev_ssh_flags:
        p_dev_logs.add_argument(flag, **kw)

    p_dev_restart = sub.add_parser("dev-restart", help="Restart display service on Pi remotely")
    for flag, kw in _dev_ssh_flags:
        p_dev_restart.add_argument(flag, **kw)

    p_dev_pair = sub.add_parser("dev-pair", help="Pair with a Voxel device (auto-discover + PIN)")
    p_dev_pair.add_argument("--host", help="Device IP (skip auto-discovery)")
    p_dev_pair.add_argument("--port", type=int, default=8081, help="Config server port")

    p_dev_setup = sub.add_parser("dev-setup", help="One-time dev setup — save SSH creds + enable dev mode")
    for flag, kw in _dev_ssh_flags:
        p_dev_setup.add_argument(flag, **kw)

    p_setup = sub.add_parser("setup", help="First-time setup (install deps, build, configure services)")
    p_setup.add_argument("--no-configure", action="store_true",
                         help="Skip the interactive configuration wizard after setup")
    sub.add_parser("configure", help="Interactive configuration wizard")
    sub.add_parser("build", help="Build Python deps + React app")
    sub.add_parser("update", help="Pull latest, rebuild, restart services")
    p_hw = sub.add_parser("hw", help="Install Whisplay HAT drivers + tune config.txt")
    p_hw.add_argument("--fbtft", action="store_true",
                       help="(Experimental) Enable fbtft framebuffer overlay for boot console on LCD")
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
    p_uninstall.add_argument("--nuke", action="store_true", help="Remove everything including repo, config, and drivers")

    p_backup = sub.add_parser("backup", help="Backup, restore, or factory reset")
    backup_sub = p_backup.add_subparsers(dest="backup_command")
    p_bk_export = backup_sub.add_parser("export", help="Export settings to JSON file")
    p_bk_export.add_argument("-o", "--output", help="Output file (default: voxel-backup.json)")
    p_bk_import = backup_sub.add_parser("import", help="Restore from backup file")
    p_bk_import.add_argument("file", help="Backup JSON file to import")
    p_bk_reset = backup_sub.add_parser("factory-reset", help="Delete all user configuration")
    p_bk_reset.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    sub.add_parser("version", help="Show version")

    p_mcp = sub.add_parser("mcp", help="Start MCP server (AI agent integration)")
    p_mcp.add_argument("--transport", choices=["stdio", "sse"], default="sse")
    p_mcp.add_argument("--port", type=int, default=8082)
    p_mcp.add_argument("--ws-url", default="ws://localhost:8080")

    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "display-test": cmd_display_test,
    "lvgl-test": cmd_lvgl_test,
    "lvgl-build": cmd_lvgl_build,
    "lvgl-render": cmd_lvgl_render,
    "lvgl-play": cmd_lvgl_play,
    "lvgl-sync": cmd_lvgl_sync,
    "lvgl-deploy": cmd_lvgl_deploy,
    "lvgl-preview": cmd_lvgl_preview,
    "lvgl-dev": cmd_lvgl_dev,
    "dev-push": cmd_dev_push,
    "dev-ssh": cmd_dev_ssh,
    "dev-logs": cmd_dev_logs,
    "dev-restart": cmd_dev_restart,
    "dev-pair": cmd_dev_pair,
    "dev-setup": cmd_dev_setup,
    "configure": cmd_configure,
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
    "backup": cmd_backup,
    "version": cmd_version,
    "mcp": cmd_mcp,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "logs":
        args.follow = not getattr(args, "no_follow", False)
    if args.command == "lvgl-deploy":
        args.play_remote = not getattr(args, "no_play_remote", False)
    if args.command == "lvgl-preview":
        args.open_preview = not getattr(args, "no_open_preview", False)

    if args.command in COMMANDS:
        sys.exit(COMMANDS[args.command](args))
    else:
        # No command — show branded TUI welcome
        banner(_get_version())
        print_commands()
        sys.exit(0)
