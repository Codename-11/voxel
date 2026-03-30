"""System health stats for the Voxel config web server.

Collects CPU, memory, disk, network, and display stats with graceful
fallbacks for both Pi (Linux) and desktop (Windows/macOS).  Every stat
collection is wrapped in try/except so this module never crashes the
caller.  Results are cached for 2 seconds to avoid thrashing the
filesystem on rapid requests.

Usage::

    from display.system_stats import get_system_stats, set_display_fps
    stats = get_system_stats()  # -> dict safe for JSON serialization
    set_display_fps(18.5)       # called from render loop
"""

from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("voxel.system_stats")

# ---------------------------------------------------------------------------
# FPS reporting (set by the render loop)
# ---------------------------------------------------------------------------

_display_fps: float = 0.0
_target_fps: int = 30


def set_display_fps(fps: float) -> None:
    """Called by the render loop to report measured FPS."""
    global _display_fps
    _display_fps = fps


def set_target_fps(target: int) -> None:
    """Called once at startup to record the target frame rate."""
    global _target_fps
    _target_fps = target


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict = {}
_cache_time: float = 0.0
_CACHE_TTL = 2.0

# ---------------------------------------------------------------------------
# Individual collectors — each returns a value or None on failure
# ---------------------------------------------------------------------------


def _cpu_percent() -> float | None:
    """CPU usage percent (0-100)."""
    try:
        if hasattr(os, "getloadavg"):
            # Linux / macOS — 1-min load average normalised to core count
            load1 = os.getloadavg()[0]
            cores = os.cpu_count() or 1
            return round(min(load1 / cores * 100, 100.0), 1)
        # Windows — try psutil
        import psutil

        return psutil.cpu_percent(interval=0)
    except Exception:
        log.debug("cpu_percent unavailable", exc_info=True)
        return None


def _cpu_temp_c() -> float | None:
    """CPU temperature in Celsius (Pi thermal zone)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        log.debug("cpu_temp_c unavailable", exc_info=True)
        return None


def _cpu_freq_mhz() -> int | None:
    """Current CPU frequency in MHz."""
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
            return int(f.read().strip()) // 1000
    except Exception:
        pass
    # Fallback: psutil
    try:
        import psutil

        freq = psutil.cpu_freq()
        if freq and freq.current:
            return int(freq.current)
    except Exception:
        pass
    log.debug("cpu_freq_mhz unavailable")
    return None


def _throttled() -> bool | None:
    """Pi throttle flag via vcgencmd."""
    import subprocess

    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            # Output: "throttled=0x0"
            val = result.stdout.strip().split("=")[-1]
            return val != "0x0"
    except Exception:
        log.debug("throttled unavailable", exc_info=True)
    return None


def _memory() -> tuple[int, int, float]:
    """Return (used_mb, total_mb, percent).  Falls back to psutil."""
    # Try /proc/meminfo first (Linux)
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    info[parts[0]] = int(parts[1])  # kB
                if len(info) == 2:
                    break
        total_kb = info["MemTotal:"]
        avail_kb = info["MemAvailable:"]
        used_mb = (total_kb - avail_kb) // 1024
        total_mb = total_kb // 1024
        pct = round(used_mb / total_mb * 100, 1) if total_mb else 0.0
        return used_mb, total_mb, pct
    except Exception:
        pass
    # Fallback: psutil
    try:
        import psutil

        vm = psutil.virtual_memory()
        return (
            int(vm.used / 1024 / 1024),
            int(vm.total / 1024 / 1024),
            round(vm.percent, 1),
        )
    except Exception:
        log.debug("memory stats unavailable")
        return 0, 0, 0.0


def _process_rss_mb() -> float | None:
    """RSS of the current process in MB."""
    # Try /proc/self/status (Linux)
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        pass
    # Fallback: psutil
    try:
        import psutil

        rss = psutil.Process().memory_info().rss
        return round(rss / 1024 / 1024, 1)
    except Exception:
        log.debug("process_rss_mb unavailable")
        return None


def _disk() -> tuple[float, float, float]:
    """Return (used_gb, total_gb, percent)."""
    import shutil

    try:
        usage = shutil.disk_usage("/")
        total_gb = round(usage.total / 1024**3, 1)
        used_gb = round(usage.used / 1024**3, 1)
        pct = round(used_gb / total_gb * 100, 1) if total_gb else 0.0
        return used_gb, total_gb, pct
    except Exception:
        log.debug("disk stats unavailable", exc_info=True)
        return 0.0, 0.0, 0.0


def _wifi() -> tuple[int | None, str | None]:
    """Return (signal_dbm, ssid) or (None, None)."""
    import subprocess

    # Try nmcli first
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SIGNAL,SSID,IN-USE", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 3 and parts[2].strip() == "*":
                    signal_pct = int(parts[0])
                    ssid = parts[1]
                    # Convert percent (0-100) to approximate dBm
                    # nmcli SIGNAL is a percentage; rough mapping:
                    # 100% ~ -30 dBm, 0% ~ -100 dBm
                    dbm = int(-100 + signal_pct * 0.7)
                    return dbm, ssid
    except Exception:
        pass
    # Try iwconfig as fallback
    try:
        result = subprocess.run(
            ["iwconfig", "wlan0"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            output = result.stdout
            ssid = None
            dbm = None
            for token in output.split():
                if token.startswith('ESSID:"'):
                    ssid = token.split('"')[1]
                if token.startswith("level="):
                    try:
                        dbm = int(token.split("=")[1].split()[0])
                    except (ValueError, IndexError):
                        pass
            if ssid or dbm is not None:
                return dbm, ssid
    except Exception:
        pass
    log.debug("wifi stats unavailable")
    return None, None


def _ip_address() -> str | None:
    """Local IP address."""
    import socket

    # Preferred: connect to a remote address (doesn't actually send data)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        pass
    # Fallback: hostname resolution
    try:
        addr = socket.gethostbyname(socket.gethostname())
        if addr and not addr.startswith("127."):
            return addr
    except Exception:
        pass
    log.debug("ip_address unavailable")
    return None


def _uptime_seconds() -> int:
    """System uptime in seconds."""
    # Linux: /proc/uptime
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        pass
    # Fallback: psutil
    try:
        import psutil

        return int(time.time() - psutil.boot_time())
    except Exception:
        pass
    log.debug("uptime unavailable")
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_system_stats() -> dict:
    """Collect system stats.  Returns a dict safe for JSON serialization.

    All fields are present; hardware-specific ones are ``None`` when
    unavailable.  Results are cached for 2 seconds.
    """
    global _cache, _cache_time

    now = time.time()
    if now - _cache_time < _CACHE_TTL and _cache:
        return _cache

    mem_used, mem_total, mem_pct = _memory()
    disk_used, disk_total, disk_pct = _disk()
    wifi_dbm, wifi_ssid = _wifi()

    stats: dict = {
        "cpu_percent": _cpu_percent(),
        "cpu_temp_c": _cpu_temp_c(),
        "cpu_freq_mhz": _cpu_freq_mhz(),
        "throttled": _throttled(),
        "mem_used_mb": mem_used,
        "mem_total_mb": mem_total,
        "mem_percent": mem_pct,
        "process_rss_mb": _process_rss_mb(),
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "disk_percent": disk_pct,
        "wifi_signal_dbm": wifi_dbm,
        "wifi_ssid": wifi_ssid,
        "ip": _ip_address(),
        "uptime_seconds": _uptime_seconds(),
        "display_fps": round(_display_fps, 1),
        "target_fps": _target_fps,
    }

    _cache = stats
    _cache_time = now
    log.debug("system stats collected: %s", stats)
    return stats
