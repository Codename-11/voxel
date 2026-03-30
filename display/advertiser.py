"""Device advertiser — broadcasts Voxel presence on LAN via UDP.

Sends a small JSON heartbeat every 5s on UDP port 41234.
Dev machines listen for these to auto-discover the device.

Protocol: JSON payload with service="voxel", device name, IP, config port, version.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time

log = logging.getLogger("voxel.advertiser")

BROADCAST_PORT = 41234  # custom port for Voxel discovery
BROADCAST_INTERVAL = 5  # seconds

_running = False


def start_advertiser(
    device_name: str = "voxel",
    config_port: int = 8081,
    version: str = "0.1.0",
) -> None:
    """Start broadcasting device presence in a background thread."""
    global _running
    if _running:
        return
    _running = True

    def _broadcast() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        from display.config_server import get_local_ip

        while _running:
            try:
                ip = get_local_ip()
                payload = json.dumps({
                    "service": "voxel",
                    "name": device_name,
                    "ip": ip,
                    "port": config_port,
                    "version": version,
                    "time": int(time.time()),
                }).encode()
                sock.sendto(payload, ("255.255.255.255", BROADCAST_PORT))
            except Exception as e:
                log.debug(f"Broadcast failed: {e}")
            time.sleep(BROADCAST_INTERVAL)
        sock.close()

    thread = threading.Thread(target=_broadcast, daemon=True)
    thread.start()
    log.info(f"Device advertiser started (UDP :{BROADCAST_PORT})")


def stop_advertiser() -> None:
    """Stop the background advertiser thread."""
    global _running
    _running = False


def discover_devices(timeout: float = 5.0) -> list[dict]:
    """Listen for Voxel device broadcasts. Returns list of discovered devices.

    This runs on the dev machine side — listens on the broadcast port for
    heartbeat packets from any Voxel devices on the same LAN.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", BROADCAST_PORT))
    except OSError as e:
        log.debug(f"Could not bind to broadcast port {BROADCAST_PORT}: {e}")
        sock.close()
        return []
    sock.settimeout(1.0)

    devices: dict[str, dict] = {}
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            data, addr = sock.recvfrom(1024)
            info = json.loads(data)
            if info.get("service") == "voxel":
                key = info.get("ip", addr[0])
                devices[key] = info
        except socket.timeout:
            continue
        except Exception:
            continue

    sock.close()
    return list(devices.values())
