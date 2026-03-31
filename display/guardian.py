"""Voxel Display Guardian — watchdog, WiFi onboarding, crash recovery.

A minimal, robust process that starts before all other Voxel services.
It owns the display and LED during boot, handles WiFi AP mode onboarding,
monitors service health, and shows recovery screens on crash.

Design principles:
  - NO asyncio, NO WebSocket, NO complex state machines
  - Minimal imports — PIL for rendering, subprocess for systemd/nmcli
  - Catches ALL exceptions in the main loop (must never crash)
  - Simple file-based IPC for display handoff and WiFi setup trigger

Run: python -m display.guardian
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [guardian] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("voxel.guardian")

# ── Constants ──────────────────────────────────────────────────────────────

SCREEN_W = 240
SCREEN_H = 280

LOCK_FILE = Path("/tmp/voxel-display.lock")
WIFI_SETUP_FLAG = Path("/tmp/voxel-wifi-setup")

# Colors
BG = (12, 12, 18)
CYAN = (0, 212, 210)
CYAN_DIM = (0, 100, 96)
DIM = (100, 100, 120)
TEXT = (200, 200, 220)
RED = (255, 60, 60)
GREEN = (52, 211, 81)
ORANGE = (255, 180, 0)
MAGENTA = (255, 0, 255)
WHITE = (255, 255, 255)

# LED colors (RGB tuples, full brightness only — no PWM dimming)
LED_OFF = (0, 0, 0)
LED_WHITE = (255, 255, 255)
LED_CYAN = (0, 255, 255)
LED_RED = (255, 0, 0)
LED_MAGENTA = (255, 0, 255)
LED_GREEN = (0, 255, 0)

# Timing
HEALTH_CHECK_INTERVAL = 5.0   # seconds between service health checks
WIFI_CHECK_INTERVAL = 10.0    # seconds between WiFi status checks
BOOT_HOLD_SECONDS = 1.0       # how long to hold the boot splash
CONFIG_SERVER_PORT = 8083      # lightweight config server for WiFi setup (8082 is MCP)

# Font path (relative to repo root)
ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "assets" / "fonts" / "DejaVuSans.ttf"


# ── Display driver (minimal, no dependency on display.backends) ────────────

class GuardianDisplay:
    """Minimal SPI display driver for the guardian.

    Loads the WhisPlay driver directly, converts PIL images to RGB565,
    and pushes frames. No dependency on the display.backends module.
    """

    def __init__(self) -> None:
        self._board = None

    def init(self) -> bool:
        """Initialize the WhisPlay board. Returns True on success."""
        try:
            self._board = _load_whisplay_board()
            self._board.set_backlight(100)
            log.info("Display initialized (SPI LCD)")
            return True
        except Exception as e:
            log.error("Failed to initialize display: %s", e)
            return False

    def push_frame(self, img) -> None:
        """Push a PIL Image to the LCD."""
        if self._board is None:
            return
        try:
            import numpy as np
            arr = np.array(img.convert("RGB"), dtype=np.uint16)
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            data = rgb565.astype(">u2").tobytes()
            self._board.set_window(0, 0, SCREEN_W - 1, SCREEN_H - 1)
            self._board._send_data(data)
        except Exception as e:
            log.warning("Frame push failed: %s", e)

    def set_led(self, r: int, g: int, b: int) -> None:
        """Set the RGB LED color."""
        if self._board is None:
            return
        try:
            self._board.set_rgb(r, g, b)
        except Exception:
            pass

    def cleanup(self) -> None:
        """Release hardware resources."""
        if self._board is not None:
            try:
                self._board.set_rgb(0, 0, 0)
                self._board.cleanup()
            except Exception:
                pass


def _load_whisplay_board():
    """Load WhisPlay module, patch GPIO, create board. Standalone — no display.backends dependency."""
    import importlib

    module = None

    # Try direct import first
    try:
        module = importlib.import_module("WhisPlay")
    except ImportError:
        pass

    if module is None:
        home = Path.home()
        candidates = [
            Path(os.getenv("VOXEL_WHISPLAY_DRIVER", "")),
            home / "Whisplay" / "Driver",
            home / "voxel" / ".cache" / "whisplay" / "Driver",
            Path.cwd() / "Whisplay" / "Driver",
            ROOT / ".cache" / "whisplay" / "Driver",
        ]
        for p in candidates:
            if p.is_dir() and (p / "WhisPlay.py").exists():
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
                module = importlib.import_module("WhisPlay")
                break

    if module is None:
        raise RuntimeError("WhisPlay driver not found")

    # Patch GPIO edge detect to avoid RuntimeError on busy pins
    gpio = getattr(module, "GPIO", None)
    if gpio and hasattr(gpio, "add_event_detect"):
        orig = gpio.add_event_detect
        def _safe(*a, **k):
            try:
                return orig(*a, **k)
            except RuntimeError:
                pass
        gpio.add_event_detect = _safe

    return module.WhisPlayBoard()


# ── PIL rendering helpers ──────────────────────────────────────────────────

def _get_font(size: int = 14):
    """Load a font at the given size. Falls back to default if TTF missing."""
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception:
        return ImageFont.load_default()


def _text_width(font, text: str) -> int:
    """Get pixel width of text."""
    try:
        return int(font.getlength(text))
    except AttributeError:
        return len(text) * 6


def _center_x(font, text: str) -> int:
    """Get X position to center text on the 240px screen."""
    return max(0, (SCREEN_W - _text_width(font, text)) // 2)


def _get_version() -> str:
    """Read version from importlib metadata or pyproject.toml."""
    try:
        from importlib.metadata import version
        return version("voxel")
    except Exception:
        pass
    try:
        toml = ROOT / "pyproject.toml"
        for line in toml.read_text().splitlines():
            if line.strip().startswith("version"):
                return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "0.1.0"


# ── Screen renderers ──────────────────────────────────────────────────────

def render_boot_screen(status: str = "Starting...", extra_lines: list[tuple[str, str]] | None = None):
    """Render the boot splash screen."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(20)
    font_sub = _get_font(14)
    font_ver = _get_font(11)

    # Title: V O X E L with glow
    title = "V O X E L"
    tx = _center_x(font_title, title)
    ty = 50
    glow = (0, 80, 78)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        draw.text((tx + dx, ty + dy), title, fill=glow, font=font_title)
    draw.text((tx, ty), title, fill=CYAN, font=font_title)

    # Version
    ver = f"v{_get_version()}"
    draw.text((_center_x(font_ver, ver), ty + 28), ver, fill=(60, 60, 80), font=font_ver)

    # Divider
    draw.line([(40, ty + 46), (SCREEN_W - 40, ty + 46)], fill=(40, 40, 60), width=1)

    # Status text
    draw.text((_center_x(font_sub, status), ty + 58), status, fill=DIM, font=font_sub)

    # Extra status lines (label, status_text)
    if extra_lines:
        font_line = _get_font(11)
        line_y = ty + 82
        for label, st in extra_lines:
            color = GREEN if st == "OK" else (ORANGE if st in ("SKIP", "WAIT") else RED if st == "FAIL" else DIM)
            line_text = f"> {label}"
            # Pad with dots
            max_w = 140
            dots = ""
            while _text_width(font_line, line_text + dots) < max_w:
                dots += "."
            draw.text((30, line_y), line_text + dots, fill=DIM, font=font_line)
            draw.text((30 + _text_width(font_line, line_text + dots) + 6, line_y), st, fill=color, font=font_line)
            line_y += 18

    return img


def render_wifi_setup_screen(ap_ssid: str, ap_password: str, ap_ip: str,
                              pin: str = "", qr_url: str = ""):
    """Render the WiFi AP mode setup screen."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(20)
    font_main = _get_font(18)
    font_sm = _get_font(14)
    font_pin = _get_font(24)

    # Title
    title = "WiFi Setup"
    draw.text((_center_x(font_title, title), 12), title, fill=CYAN, font=font_title)

    y = 44
    draw.text((20, y), "1. Join WiFi:", fill=DIM, font=font_sm)
    y += 18
    draw.text((_center_x(font_main, ap_ssid), y), ap_ssid, fill=(64, 255, 248), font=font_main)
    y += 22
    draw.text((24, y), f"Pass: {ap_password}", fill=TEXT, font=font_sm)

    y += 28
    draw.text((20, y), "2. Open in browser:", fill=DIM, font=font_sm)
    y += 18
    url = f"http://{ap_ip}:{CONFIG_SERVER_PORT}"
    url_short = url.replace("http://", "")
    draw.text((max(10, _center_x(font_main, url_short)), y), url_short, fill=(64, 255, 248), font=font_main)

    if pin:
        y += 28
        draw.text((20, y), "3. Enter PIN:", fill=DIM, font=font_sm)
        y += 18
        draw.text((_center_x(font_pin, pin), y), pin, fill=(64, 255, 248), font=font_pin)

    # QR code (optional)
    if qr_url:
        y += 34
        try:
            import qrcode
            qr = qrcode.QRCode(box_size=2, border=2)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color=BG)
            qr_img = qr_img.convert("RGB")
            qr_size = min(80, SCREEN_H - y - 10)
            qr_w, qr_h = qr_img.size
            if qr_w != qr_size:
                qr_img = qr_img.resize((qr_size, qr_size))
            qr_x = (SCREEN_W - qr_size) // 2
            img.paste(qr_img, (qr_x, y))
        except Exception:
            pass  # qrcode not installed — skip

    return img


def render_error_screen(title: str = "Service Error", message: str = "",
                         detail: str = ""):
    """Render a service crash / error recovery screen."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(18)
    font_msg = _get_font(14)
    font_detail = _get_font(11)

    # Red warning icon
    draw.text((_center_x(font_title, "!"), 30), "!", fill=RED, font=_get_font(28))

    # Title
    draw.text((_center_x(font_title, title), 68), title, fill=RED, font=font_title)

    # Message
    y = 100
    if message:
        # Word wrap
        words = message.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if _text_width(font_msg, test) > 220:
                if current:
                    lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        for line in lines[:4]:
            draw.text((10, y), line, fill=TEXT, font=font_msg)
            y += 18

    # Detail (e.g. journalctl snippet)
    if detail:
        y += 8
        draw.line([(20, y), (220, y)], fill=(40, 40, 60), width=1)
        y += 8
        for line in detail.split("\n")[:5]:
            truncated = line[:38]
            draw.text((10, y), truncated, fill=DIM, font=font_detail)
            y += 14

    # Recovery hint
    draw.text((_center_x(font_msg, "Restarting..."), SCREEN_H - 32),
              "Restarting...", fill=CYAN_DIM, font=font_msg)

    return img


def render_recovery_screen(service: str, attempt: int = 1):
    """Render a brief recovery screen while waiting for a service to restart."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(16)
    font_sub = _get_font(14)
    font_sm = _get_font(12)

    # Spinner-like dots based on time
    dots = "." * ((attempt % 3) + 1)

    title = "Recovering"
    draw.text((_center_x(font_title, title), 80), title, fill=CYAN, font=font_title)

    msg = f"{service}{dots}"
    draw.text((_center_x(font_sub, msg), 110), msg, fill=DIM, font=font_sub)

    hint = f"Attempt {attempt}"
    draw.text((_center_x(font_sm, hint), 140), hint, fill=CYAN_DIM, font=font_sm)

    return img


# ── System helpers ─────────────────────────────────────────────────────────

def _run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run a command and return (exit_code, stdout). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except FileNotFoundError:
        return 127, ""
    except Exception:
        return 1, ""


def is_service_active(name: str) -> bool:
    """Check if a systemd service is active."""
    code, out = _run_cmd(["systemctl", "is-active", name])
    return out == "active"


def get_service_error(name: str, lines: int = 5) -> str:
    """Get recent journal lines for a failed service."""
    code, out = _run_cmd(
        ["journalctl", "-u", name, "-n", str(lines), "--no-pager", "-o", "short-monotonic"],
        timeout=5,
    )
    return out


def is_wifi_connected() -> bool:
    """Check if WiFi is connected via ip route."""
    code, out = _run_cmd(["ip", "route", "show", "default"])
    return bool(out.strip())


def get_ip_address() -> str:
    """Get the device's current IP address."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def start_ap_mode() -> bool:
    """Start WiFi AP mode for onboarding. Returns True on success."""
    from display.wifi import AP_SSID, AP_PASSWORD, AP_CON_NAME

    log.info("Starting AP mode: %s", AP_SSID)

    # Remove existing AP connection if any
    _run_cmd(["nmcli", "connection", "delete", AP_CON_NAME])

    code, out = _run_cmd([
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
    ], timeout=15)

    if code != 0:
        log.error("Failed to create AP: %s", out)
        return False

    code, out = _run_cmd(["nmcli", "connection", "up", AP_CON_NAME], timeout=15)
    if code != 0:
        log.error("Failed to activate AP: %s", out)
        return False

    log.info("AP active: %s (password: %s)", AP_SSID, AP_PASSWORD)
    return True


def stop_ap_mode() -> None:
    """Stop AP mode and clean up."""
    from display.wifi import AP_CON_NAME
    _run_cmd(["nmcli", "connection", "down", AP_CON_NAME])
    _run_cmd(["nmcli", "connection", "delete", AP_CON_NAME])
    log.info("AP stopped")


def nmcli_available() -> bool:
    """Check if nmcli is available."""
    code, _ = _run_cmd(["nmcli", "--version"])
    return code == 0


# ── Display lock (file-based handoff) ─────────────────────────────────────

def acquire_display_lock() -> None:
    """Create the display lock file — guardian owns the display."""
    try:
        LOCK_FILE.write_text(str(os.getpid()))
        log.debug("Display lock acquired (pid %d)", os.getpid())
    except Exception as e:
        log.warning("Could not create lock file: %s", e)


def release_display_lock() -> None:
    """Remove the display lock file — hand off to voxel-display."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
        log.debug("Display lock released")
    except Exception as e:
        log.warning("Could not remove lock file: %s", e)


def display_is_locked() -> bool:
    """Check if the guardian currently holds the display lock."""
    return LOCK_FILE.exists()


# ── WiFi setup trigger (file-based signal from menu) ──────────────────────

def wifi_setup_requested() -> bool:
    """Check if the menu requested WiFi setup mode."""
    return WIFI_SETUP_FLAG.exists()


def clear_wifi_setup_flag() -> None:
    """Clear the WiFi setup request flag."""
    try:
        WIFI_SETUP_FLAG.unlink(missing_ok=True)
    except Exception:
        pass


# ── Lightweight WiFi config server (runs during AP mode) ──────────────────

def _start_wifi_config_server(pin: str) -> None:
    """Start a minimal HTTP server for WiFi configuration during AP mode.

    This is a stripped-down version of config_server.py that only handles
    WiFi scan/connect. Runs in a daemon thread so it doesn't block the
    main guardian loop.
    """
    import json
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from threading import Thread

    class WiFiHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            log.debug("HTTP: %s", format % args)

        def do_GET(self):
            if self.path == "/wifi/scan":
                try:
                    from display.wifi import scan_networks
                    nets = scan_networks()
                    data = [{"ssid": n.ssid, "signal": n.signal,
                             "security": n.security, "connected": n.connected}
                            for n in nets]
                    self._json(200, data)
                except Exception as e:
                    self._json(500, {"error": str(e)})
                return

            if self.path == "/health":
                self._json(200, {"ok": True, "service": "guardian"})
                return

            # Serve a minimal WiFi setup page
            self._serve_setup_page()

        def do_POST(self):
            if self.path == "/wifi/connect":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    ssid = body.get("ssid", "")
                    password = body.get("password", "")
                    if not ssid:
                        self._json(400, {"ok": False, "error": "No SSID"})
                        return
                    from display.wifi import connect_to_network
                    ok, error = connect_to_network(ssid, password)
                    self._json(200, {"ok": ok, "error": error})
                except Exception as e:
                    self._json(500, {"ok": False, "error": str(e)})
                return
            self._json(404, {"error": "Not found"})

        def _json(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_setup_page(self):
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voxel WiFi Setup</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui;background:#0c0c12;color:#c8c8dc;padding:20px}}
h1{{color:#00d4d2;font-size:20px;margin-bottom:16px}}
.btn{{background:#00d4d2;color:#0c0c12;border:none;padding:10px 20px;
border-radius:6px;cursor:pointer;font-size:14px;margin:8px 0}}
.btn:disabled{{opacity:0.5}}
.net{{padding:12px;border:1px solid #333;border-radius:8px;margin:6px 0;
cursor:pointer;display:flex;justify-content:space-between}}
.net:hover{{border-color:#00d4d2}}
input{{background:#1a1a24;color:#c8c8dc;border:1px solid #333;
padding:10px;border-radius:6px;width:100%;margin:8px 0;font-size:14px}}
#status{{margin:12px 0;padding:8px;border-radius:6px;display:none}}
.ok{{background:#1a2a1a;color:#34d351}}.err{{background:#2a1a1a;color:#ff3c3c}}
</style></head><body>
<h1>Voxel WiFi Setup</h1>
<p style="color:#646480;margin-bottom:16px">PIN: <strong style="color:#00d4d2">{pin}</strong></p>
<div id="nets"><span style="color:#646480">Tap Scan to find networks</span></div>
<button class="btn" id="scanBtn" onclick="scan()">Scan Networks</button>
<div id="form" style="display:none">
<p>Network: <strong id="ssid" style="color:#00d4d2"></strong></p>
<input id="pass" type="password" placeholder="Password (leave empty if open)">
<button class="btn" onclick="connect()">Connect</button>
</div>
<div id="status"></div>
<script>
let sel='';
async function scan(){{
  const b=document.getElementById('scanBtn');b.textContent='Scanning...';b.disabled=true;
  try{{const r=await fetch('/wifi/scan');const d=await r.json();
  document.getElementById('nets').innerHTML=d.map(n=>
    '<div class="net" onclick="pick(\\''+n.ssid.replace(/'/g,"\\\\'")+'\\')">'+
    '<span>'+n.ssid+'</span><span style="color:#646480">'+n.signal+'%</span></div>'
  ).join('')||'<span style="color:#646480">No networks found</span>';
  }}catch(e){{document.getElementById('nets').innerHTML='<span style="color:#ff3c3c">Scan failed</span>';}}
  b.textContent='Scan Networks';b.disabled=false;
}}
function pick(s){{sel=s;document.getElementById('ssid').textContent=s;
document.getElementById('form').style.display='block';document.getElementById('pass').focus();}}
async function connect(){{if(!sel)return;const st=document.getElementById('status');
st.style.display='block';st.className='ok';st.textContent='Connecting to '+sel+'...';
try{{const r=await fetch('/wifi/connect',{{method:'POST',
headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{ssid:sel,password:document.getElementById('pass').value}})}});
const d=await r.json();if(d.ok){{st.className='ok';st.textContent='Connected! Device will resume boot.';}}
else{{st.className='err';st.textContent='Failed: '+(d.error||'unknown');}}
}}catch(e){{st.className='err';st.textContent='Connection error — reconnect to new network.';}}}}
</script></body></html>"""
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("0.0.0.0", CONFIG_SERVER_PORT), WiFiHandler)
        server.timeout = 1.0
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        log.info("WiFi config server started on port %d", CONFIG_SERVER_PORT)
    except Exception as e:
        log.warning("Could not start WiFi config server: %s", e)


# ── Main guardian loop ─────────────────────────────────────────────────────

class Guardian:
    """The main guardian process.

    Lifecycle:
      1. Initialize display + LED
      2. Show boot splash
      3. Check WiFi — start AP mode if needed
      4. Wait for voxel-display to come up
      5. Hand off display, enter monitoring mode
      6. If voxel-display crashes, reclaim display and show error
    """

    def __init__(self) -> None:
        self.display = GuardianDisplay()
        self.running = True
        self.ap_mode = False
        self._ap_pin = ""
        self._last_led_color = LED_OFF
        self._display_service_was_active = False
        self._recovery_attempt = 0

    def run(self) -> None:
        """Main entry point — runs the full guardian lifecycle."""
        # Register signal handlers for clean shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._boot()
            self._monitor_loop()
        except Exception as e:
            log.error("Guardian fatal error: %s", e)
        finally:
            self._cleanup()

    def _handle_signal(self, signum, frame):
        log.info("Received signal %d — shutting down", signum)
        self.running = False

    def _boot(self) -> None:
        """Boot sequence: display init, WiFi check, AP mode if needed."""
        # Step 1: Initialize display
        if not self.display.init():
            log.error("Display init failed — running in headless mode")
            # Continue anyway — we can still monitor services
            self._wait_for_services()
            return

        # Step 2: LED white solid (booting)
        self._set_led(LED_WHITE)

        # Step 3: Boot splash
        acquire_display_lock()
        img = render_boot_screen("Starting...", [])
        self.display.push_frame(img)

        # Step 4: LED cyan flash
        self._set_led(LED_CYAN)
        time.sleep(0.2)
        self._set_led(LED_OFF)
        time.sleep(0.2)
        self._set_led(LED_CYAN)

        # Step 5: Check WiFi
        boot_lines: list[tuple[str, str]] = []

        if nmcli_available():
            if is_wifi_connected():
                ip = get_ip_address()
                boot_lines.append(("WiFi", "OK"))
                boot_lines.append(("IP", ip))
                log.info("WiFi connected: %s", ip)
                img = render_boot_screen("WiFi connected", boot_lines)
                self.display.push_frame(img)
                self._set_led(LED_CYAN)
                time.sleep(0.3)
                self._set_led(LED_OFF)
            else:
                log.info("No WiFi — entering AP mode")
                boot_lines.append(("WiFi", "FAIL"))
                img = render_boot_screen("No WiFi detected", boot_lines)
                self.display.push_frame(img)
                time.sleep(0.5)

                self._enter_ap_mode()
                if self.ap_mode:
                    self._run_ap_mode_loop()
                    # After AP loop exits, WiFi should be connected
                    boot_lines = [("WiFi", "OK"), ("IP", get_ip_address())]
                    img = render_boot_screen("WiFi connected!", boot_lines)
                    self.display.push_frame(img)
                    time.sleep(0.5)
        else:
            boot_lines.append(("WiFi", "SKIP"))
            log.info("nmcli not available — skipping WiFi check")

        # Step 6: Show "Waiting for services..."
        boot_lines.append(("Services", "WAIT"))
        img = render_boot_screen("Starting services...", boot_lines)
        self.display.push_frame(img)

        # Wait briefly for systemd to start the other services
        self._wait_for_services()

    def _enter_ap_mode(self) -> None:
        """Start AP mode and config server."""
        if start_ap_mode():
            self.ap_mode = True
            self._ap_pin = f"{__import__('random').randint(0, 999999):06d}"
            self._set_led(LED_MAGENTA)
            _start_wifi_config_server(self._ap_pin)
            log.info("AP mode active, PIN: %s", self._ap_pin)

    def _run_ap_mode_loop(self) -> None:
        """Show WiFi setup screen and wait for WiFi to connect."""
        from display.wifi import AP_SSID, AP_PASSWORD, AP_IP

        log.info("Entering AP mode loop — waiting for WiFi configuration")
        qr_url = f"http://{AP_IP}:{CONFIG_SERVER_PORT}/"

        check_interval = 3.0
        last_check = 0.0

        while self.running and self.ap_mode:
            now = time.time()

            # Render WiFi setup screen
            img = render_wifi_setup_screen(
                ap_ssid=AP_SSID,
                ap_password=AP_PASSWORD,
                ap_ip=AP_IP,
                pin=self._ap_pin,
                qr_url=qr_url,
            )
            self.display.push_frame(img)

            # LED: magenta slow blink
            if (now % 2.0) < 1.0:
                self._set_led(LED_MAGENTA)
            else:
                self._set_led(LED_OFF)

            # Check if WiFi connected
            if now - last_check > check_interval:
                if is_wifi_connected():
                    log.info("WiFi connected during AP mode!")
                    self.ap_mode = False
                    stop_ap_mode()
                    self._set_led(LED_GREEN)
                    time.sleep(0.5)
                    self._set_led(LED_OFF)
                    break
                last_check = now

            time.sleep(0.5)

    def _wait_for_services(self) -> None:
        """Wait for voxel-display to become active, then hand off."""
        log.info("Waiting for voxel-display to start...")
        wait_start = time.time()
        max_wait = 60.0  # don't wait forever

        while self.running and (time.time() - wait_start) < max_wait:
            if is_service_active("voxel-display"):
                log.info("voxel-display is active — handing off display")
                self._display_service_was_active = True
                self._recovery_attempt = 0
                release_display_lock()
                self._set_led(LED_OFF)
                return
            time.sleep(2.0)

        log.warning("voxel-display did not start within %ds", int(max_wait))
        # Keep the lock — we'll stay on the boot/error screen

    def _monitor_loop(self) -> None:
        """Main monitoring loop — check service health, react to crashes."""
        log.info("Entering monitoring loop")

        last_health_check = 0.0
        last_wifi_check = 0.0

        while self.running:
            try:
                now = time.time()

                # Check for WiFi setup request from menu
                if wifi_setup_requested():
                    log.info("WiFi setup requested from menu")
                    clear_wifi_setup_flag()
                    acquire_display_lock()
                    self._enter_ap_mode()
                    if self.ap_mode:
                        self._run_ap_mode_loop()
                    release_display_lock()

                # Service health check
                if now - last_health_check > HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    self._check_service_health()

                # Periodic WiFi check
                if now - last_wifi_check > WIFI_CHECK_INTERVAL:
                    last_wifi_check = now
                    if nmcli_available() and not self.ap_mode:
                        wifi_ok = is_wifi_connected()
                        if not wifi_ok and self._display_service_was_active:
                            log.warning("WiFi lost during operation")
                            # Don't auto-enter AP mode here — the display
                            # service handles reconnection. Only log it.

                time.sleep(1.0)

            except Exception as e:
                log.error("Monitor loop error: %s", e)
                time.sleep(5.0)

    def _check_service_health(self) -> None:
        """Check if voxel-display is running. Show error screen if crashed."""
        display_active = is_service_active("voxel-display")

        if display_active:
            # Service is healthy
            if not self._display_service_was_active:
                log.info("voxel-display came up")
                self._display_service_was_active = True
                self._recovery_attempt = 0
                release_display_lock()
                self._set_led(LED_OFF)
            return

        # Service is NOT active
        if self._display_service_was_active:
            # It was running before — it crashed
            self._display_service_was_active = False
            self._recovery_attempt += 1
            log.warning("voxel-display crashed! (recovery attempt %d)",
                        self._recovery_attempt)

            # Reclaim display
            acquire_display_lock()

            # Show error screen with recent logs
            error_log = get_service_error("voxel-display", lines=5)
            img = render_error_screen(
                title="Display Crashed",
                message=f"voxel-display stopped unexpectedly (attempt {self._recovery_attempt})",
                detail=error_log,
            )
            try:
                self.display.push_frame(img)
            except Exception:
                pass

            # LED: red blink
            self._set_led(LED_RED)
            time.sleep(0.3)
            self._set_led(LED_OFF)
            time.sleep(0.3)
            self._set_led(LED_RED)

        elif display_is_locked():
            # We own the display and service hasn't come back yet
            # Show a recovery screen with animation
            self._recovery_attempt += 1
            try:
                img = render_recovery_screen("voxel-display",
                                              attempt=self._recovery_attempt)
                self.display.push_frame(img)
            except Exception:
                pass

            # LED: red slow blink
            if (time.time() % 2.0) < 1.0:
                self._set_led(LED_RED)
            else:
                self._set_led(LED_OFF)

    def _set_led(self, color: tuple[int, int, int]) -> None:
        """Set LED color, avoiding redundant writes."""
        if color != self._last_led_color:
            self.display.set_led(*color)
            self._last_led_color = color

    def _cleanup(self) -> None:
        """Clean shutdown."""
        log.info("Guardian shutting down")
        release_display_lock()
        clear_wifi_setup_flag()
        self.display.set_led(0, 0, 0)
        self.display.cleanup()


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    """Guardian entry point."""
    # Only run on Pi — on desktop, guardian is not needed
    from hw.detect import IS_PI
    if not IS_PI:
        log.info("Not running on Pi — guardian not needed")
        print("Guardian is a Pi-only service. Use 'uv run dev' for desktop preview.")
        return

    guardian = Guardian()
    guardian.run()


if __name__ == "__main__":
    main()
