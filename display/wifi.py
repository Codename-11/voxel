"""WiFi management via nmcli — AP mode onboarding and network connection.

On Pi Zero 2W (single radio), AP and client modes are mutually exclusive.
Flow: scan networks → cache results → start AP → user picks network via
web UI → tear down AP → connect → verify → fallback to AP if failed.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

log = logging.getLogger("voxel.wifi")

AP_SSID = "Voxel-Setup"
AP_PASSWORD = "voxel1234"
AP_CON_NAME = "voxel-setup"
AP_IP = "10.42.0.1"


@dataclass
class WifiNetwork:
    ssid: str
    signal: int      # 0-100
    security: str    # "WPA2", "WPA3", "OWE", "--" (open)
    connected: bool = False


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    """Run a command and return (exit_code, stdout)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except FileNotFoundError:
        return 127, ""


def is_nmcli_available() -> bool:
    """Check if nmcli is available (Pi with NetworkManager)."""
    code, _ = _run(["nmcli", "--version"])
    return code == 0


def is_wifi_connected() -> bool:
    """Check if any WiFi connection is active."""
    code, out = _run(["nmcli", "-t", "-f", "TYPE,STATE", "connection", "show", "--active"])
    for line in out.split("\n"):
        if "wifi" in line.lower() and "activated" in line.lower():
            return True
    # Fallback: check for default route
    code, out = _run(["ip", "route", "show", "default"])
    return bool(out.strip())


def get_current_ssid() -> str:
    """Get the SSID of the currently connected network."""
    code, out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
    for line in out.split("\n"):
        if line.startswith("yes:"):
            return line.split(":", 1)[1]
    return ""


def scan_networks() -> list[WifiNetwork]:
    """Scan for available WiFi networks. Must NOT be in AP mode."""
    _run(["nmcli", "device", "wifi", "rescan"])
    code, out = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "device", "wifi", "list"])
    if code != 0:
        return []

    current = get_current_ssid()
    seen: set[str] = set()
    networks: list[WifiNetwork] = []

    for line in out.split("\n"):
        if not line.strip():
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid = parts[0].strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)

        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0

        security = parts[2] if len(parts) > 2 else "--"
        connected = ssid == current

        networks.append(WifiNetwork(
            ssid=ssid, signal=signal, security=security, connected=connected,
        ))

    # Sort by signal strength descending
    networks.sort(key=lambda n: n.signal, reverse=True)
    log.debug("WiFi scan: %d networks found", len(networks))
    return networks


def start_ap() -> bool:
    """Start WiFi AP mode for onboarding. Returns True on success."""
    log.info(f"Starting AP: {AP_SSID}")

    # Remove existing AP connection if any
    _run(["nmcli", "connection", "delete", AP_CON_NAME])

    code, out = _run([
        "nmcli", "connection", "add",
        "type", "wifi", "ifname", "wlan0",
        "con-name", AP_CON_NAME,
        "autoconnect", "no",
        "ssid", AP_SSID,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "ipv4.method", "shared",
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.psk", AP_PASSWORD,
    ])

    if code != 0:
        log.error(f"Failed to create AP: {out}")
        return False

    code, out = _run(["nmcli", "connection", "up", AP_CON_NAME])
    if code != 0:
        log.error(f"Failed to activate AP: {out}")
        return False

    log.info(f"AP active: {AP_SSID} (password: {AP_PASSWORD}, IP: {AP_IP})")
    return True


def stop_ap() -> None:
    """Stop AP mode and clean up the connection."""
    _run(["nmcli", "connection", "down", AP_CON_NAME])
    _run(["nmcli", "connection", "delete", AP_CON_NAME])
    log.info("AP stopped")


def connect_to_network(ssid: str, password: str = "") -> tuple[bool, str]:
    """Connect to a WiFi network. Returns (success, error_message)."""
    log.info(f"Connecting to: {ssid}")

    # Tear down AP first (single radio)
    stop_ap()

    import time
    time.sleep(2)

    # Attempt connection
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]

    code, out = _run(cmd, timeout=30)

    if code == 0:
        log.info(f"Connected to {ssid}")
        return True, ""

    error = out or "Connection failed"
    log.warning(f"Failed to connect to {ssid}: {error}")

    # Fall back to AP mode
    log.info("Falling back to AP mode")
    start_ap()

    return False, error


def get_ap_status() -> dict:
    """Get current AP/WiFi status for display."""
    code, out = _run(["nmcli", "-t", "-f", "NAME,TYPE,STATE", "connection", "show", "--active"])
    for line in out.split("\n"):
        if AP_CON_NAME in line:
            return {
                "mode": "ap",
                "ssid": AP_SSID,
                "password": AP_PASSWORD,
                "ip": AP_IP,
            }

    ssid = get_current_ssid()
    if ssid:
        return {"mode": "client", "ssid": ssid, "ip": ""}

    return {"mode": "disconnected", "ssid": "", "ip": ""}
