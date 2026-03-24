"""voxel doctor — diagnose system health."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from cli.display import ok, warn, fail, info, header, section, kv


def _run(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    """Run a command and return (returncode, stdout)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except FileNotFoundError:
        return -1, ""
    except subprocess.TimeoutExpired:
        return -2, "timeout"
    except Exception as e:
        return -3, str(e)


def _svc_status(name: str) -> str:
    """Get systemd service status."""
    code, out = _run(["systemctl", "is-active", name])
    return out if code == 0 else "not found"


def run() -> int:
    """Run all health checks. Returns number of failures."""
    header("Voxel Doctor")
    failures = 0

    # ── Platform ──────────────────────────────────────────────

    section("Platform")
    arch = platform.machine()
    is_pi = arch.startswith(("aarch64", "arm"))
    kv("Architecture", arch)
    kv("OS", f"{platform.system()} {platform.release()}")
    kv("Platform", "Raspberry Pi" if is_pi else "Desktop")

    # ── Python ────────────────────────────────────────────────

    section("Python")
    py_ver = platform.python_version()
    py_major, py_minor = sys.version_info[:2]
    if py_major >= 3 and py_minor >= 11:
        ok(f"Python {py_ver}")
    else:
        fail(f"Python {py_ver} — need 3.11+")
        failures += 1

    # ── Tools ─────────────────────────────────────────────────

    section("Tools")

    # Node.js
    code, out = _run(["node", "--version"])
    if code == 0:
        ok(f"Node.js {out}")
    else:
        fail("Node.js not installed")
        failures += 1

    # npm
    code, out = _run(["npm", "--version"])
    if code == 0:
        ok(f"npm {out}")
    else:
        warn("npm not installed")

    # uv
    code, out = _run(["uv", "--version"])
    if code == 0:
        ok(f"uv {out}")
    else:
        fail("uv not installed")
        failures += 1

    # ffmpeg (needed for TTS MP3→WAV)
    if shutil.which("ffmpeg"):
        code, out = _run(["ffmpeg", "-version"])
        version_line = out.split("\n")[0] if out else "unknown"
        ok(f"ffmpeg ({version_line[:40]})")
    else:
        warn("ffmpeg not installed — TTS will fail (sudo apt install ffmpeg)")
        failures += 1

    # git
    code, out = _run(["git", "--version"])
    if code == 0:
        ok(f"git {out.replace('git version ', '')}")
    else:
        fail("git not installed")
        failures += 1

    # ── Config ────────────────────────────────────────────────

    section("Configuration")

    config_dir = Path(__file__).resolve().parent.parent / "config"
    default_path = config_dir / "default.yaml"
    local_path = config_dir / "local.yaml"

    if default_path.exists():
        ok("config/default.yaml exists")
    else:
        fail("config/default.yaml missing!")
        failures += 1

    if local_path.exists():
        ok("config/local.yaml exists")
    else:
        warn("config/local.yaml missing — run: cp config/default.yaml config/local.yaml")

    # Load and validate config
    try:
        from config.settings import load_settings
        settings = load_settings()

        # Gateway
        gw_url = settings.get("gateway", {}).get("url", "")
        gw_token = settings.get("gateway", {}).get("token", "")
        if gw_url:
            ok(f"Gateway URL: {gw_url}")
        else:
            warn("Gateway URL not configured")

        if gw_token:
            ok(f"Gateway token: {'*' * 8}...{gw_token[-4:]}" if len(gw_token) > 4 else "Gateway token: set")
        else:
            warn("Gateway token not set (config gateway.token or OPENCLAW_TOKEN env)")

        # STT
        stt_key = settings.get("stt", {}).get("whisper", {}).get("api_key", "")
        if stt_key:
            ok(f"OpenAI API key: {'*' * 8}...{stt_key[-4:]}" if len(stt_key) > 4 else "OpenAI API key: set")
        else:
            warn("OpenAI API key not set (STT disabled — set stt.whisper.api_key or OPENAI_API_KEY env)")

        # TTS provider
        tts_provider = settings.get("audio", {}).get("tts_provider", "edge")
        ok(f"TTS provider: {tts_provider}")

        if tts_provider == "elevenlabs":
            el_key = settings.get("tts", {}).get("elevenlabs", {}).get("api_key", "")
            if el_key:
                ok("ElevenLabs API key: set")
            else:
                warn("ElevenLabs key not set — will fall back to edge-tts")

    except Exception as e:
        fail(f"Config load error: {e}")
        failures += 1

    # ── Gateway connectivity ──────────────────────────────────

    section("Gateway")

    try:
        from config.settings import load_settings
        settings = load_settings()
        gw_url = settings.get("gateway", {}).get("url", "")
        gw_token = settings.get("gateway", {}).get("token", "")

        if gw_url and gw_token:
            from core.gateway import OpenClawClient
            client = OpenClawClient(gw_url, gw_token)
            if client.health_check():
                ok(f"Gateway reachable at {gw_url}")
            else:
                warn(f"Gateway not reachable at {gw_url}")
        else:
            info("Skipping gateway check (not configured)")
    except Exception as e:
        warn(f"Gateway check failed: {e}")

    # ── Hardware (Pi-specific) ────────────────────────────────

    section("Hardware")

    # Display
    if Path("/dev/fb1").exists():
        ok("Display: /dev/fb1 present (ST7789 SPI LCD)")
    elif is_pi:
        warn("Display: /dev/fb1 not found — run: voxel hw")
    else:
        info("Display: N/A (desktop)")

    # Audio device
    if is_pi:
        code, out = _run(["arecord", "-l"])
        if "WM8960" in out or "wm8960" in out:
            ok("Audio: WM8960 codec detected")
        else:
            warn("Audio: WM8960 not found — Whisplay drivers may not be installed")
    else:
        # Desktop: check for any audio
        try:
            import pyaudio  # type: ignore
            pa = pyaudio.PyAudio()
            count = pa.get_device_count()
            pa.terminate()
            ok(f"Audio: {count} device(s) via PyAudio")
        except ImportError:
            try:
                import sounddevice as sd  # type: ignore
                devices = sd.query_devices()
                ok(f"Audio: {len(devices)} device(s) via sounddevice")
            except ImportError:
                warn("Audio: no backend (install pyaudio or sounddevice)")
            except Exception:
                warn("Audio: sounddevice error")
        except Exception:
            warn("Audio: PyAudio error")

    # Battery
    if is_pi:
        try:
            import requests
            resp = requests.get("http://localhost:8421/api/battery", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                ok(f"Battery: {data.get('battery', '?')}% (charging: {data.get('charging', '?')})")
            else:
                warn("PiSugar API responded but with error")
        except Exception:
            info("PiSugar battery API not reachable (normal if not using PiSugar)")
    else:
        info("Battery: N/A (desktop)")

    # ── Services ──────────────────────────────────────────────

    section("Services")

    if shutil.which("systemctl"):
        for svc in ["voxel", "voxel-ui", "voxel-web"]:
            status = _svc_status(svc)
            if status == "active":
                ok(f"{svc}: {status}")
            elif status == "inactive":
                info(f"{svc}: {status}")
            elif status == "not found":
                info(f"{svc}: not installed")
            else:
                warn(f"{svc}: {status}")
    else:
        info("systemd not available (not on Pi?)")

    # ── React app build ───────────────────────────────────────

    section("Frontend")

    dist = Path(__file__).resolve().parent.parent / "app" / "dist" / "index.html"
    if dist.exists():
        ok(f"app/dist/ built ({dist.stat().st_size} bytes)")
    else:
        warn("app/dist/ not built — run: voxel update")

    # ── System resources ──────────────────────────────────────

    section("System")

    # Memory
    try:
        code, out = _run(["free", "-m"])
        if code == 0:
            for line in out.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    total, used = int(parts[1]), int(parts[2])
                    pct = used * 100 // total
                    if pct > 85:
                        warn(f"Memory: {used}MB / {total}MB ({pct}%) — high!")
                    else:
                        ok(f"Memory: {used}MB / {total}MB ({pct}%)")
    except Exception:
        pass

    # Disk
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        if free_gb < 1:
            warn(f"Disk: {free_gb:.1f}GB free / {total_gb:.1f}GB total — low!")
            failures += 1
        else:
            ok(f"Disk: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
    except Exception:
        pass

    # ── Summary ───────────────────────────────────────────────

    print()
    if failures == 0:
        ok("All checks passed!")
    else:
        fail(f"{failures} issue(s) found")
    print()

    return failures
