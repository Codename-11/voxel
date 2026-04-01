"""Lightweight web config server for Voxel.

Serves a simple HTML form to configure gateway token, API keys, and settings.
Runs on an available port (default 8081) alongside the display service.
Shows QR code on the LCD so the user can scan to open the config page.

Auth: a 6-digit PIN is generated on each boot and shown on the LCD.
The web UI requires this PIN before showing settings. Auth can be disabled
via config: `web.auth_enabled: false` in local.yaml.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import socket
import subprocess
import time as _time
from html import escape
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("voxel.config_server")

PREFERRED_PORT = 8081

# ── Branding ──────────────────────────────────────────────────────────────
# Inline SVG logo — Voxel's eyes: two cyan pill shapes with subtle glow on dark background
_LOGO_SVG = '<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg"><rect class="logo-bg" width="120" height="120" rx="24" fill="#0a0a0f"/><rect x="25" y="28" width="26" height="64" rx="13" fill="#00d4d2" opacity="0.12"/><rect x="69" y="28" width="26" height="64" rx="13" fill="#00d4d2" opacity="0.12"/><rect x="27" y="30" width="22" height="60" rx="11" fill="#00d4d2"/><rect x="71" y="30" width="22" height="60" rx="11" fill="#00d4d2"/></svg>'

# Data URI favicon (same SVG, URL-encoded for <link> tag)
_FAVICON_LINK = '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' + _LOGO_SVG.replace('#', '%23').replace('"', "'").replace('<', '%3C').replace('>', '%3E').replace(' ', '%20') + '">'

# ── Server port (set when the server starts, used by advertiser + pair API) ──
_server_port: int = PREFERRED_PORT

# ── Dev mode ───────────────────────────────────────────────────────────────
_dev_mode: bool = False
_display_state = None  # module-level reference to DisplayState (set by start_config_server)

# ── Chat — lazy OpenClaw client ───────────────────────────────────────────
_chat_client = None  # OpenClawClient instance, created on first chat message

# ── Auth ────────────────────────────────────────────────────────────────────

_access_pin: str = ""
_auth_enabled: bool = True
# Authenticated sessions: token -> expiry timestamp
_sessions: dict[str, float] = {}
SESSION_DURATION = 3600  # 1 hour
_SESSION_CLEANUP_INTERVAL = 60  # seconds between expired-session sweeps
_last_session_cleanup: float = 0.0


def _generate_pin() -> str:
    """Generate a random 6-digit PIN."""
    return f"{random.randint(0, 999999):06d}"


def get_access_pin() -> str:
    """Get the current access PIN (shown on LCD)."""
    return _access_pin


def _create_session() -> str:
    """Create an authenticated session token."""
    token = hashlib.sha256(f"{_time.time()}{random.random()}".encode()).hexdigest()[:24]
    _sessions[token] = _time.time() + SESSION_DURATION
    return token


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions if enough time has passed since the last sweep."""
    global _last_session_cleanup
    now = _time.time()
    if now - _last_session_cleanup < _SESSION_CLEANUP_INTERVAL:
        return
    _last_session_cleanup = now
    expired = [tok for tok, exp in _sessions.items() if exp <= now]
    for tok in expired:
        _sessions.pop(tok, None)
    if expired:
        log.debug("Session cleanup: removed %d expired session(s)", len(expired))


def _check_session(cookie_header: str | None, query_token: str | None = None) -> bool:
    """Check if the request has a valid session cookie or query token."""
    if _dev_mode:
        return True
    if not _auth_enabled:
        return True

    # Periodically sweep expired sessions
    _cleanup_expired_sessions()

    # Check query parameter token (from QR code direct access)
    if query_token:
        expiry = _sessions.get(query_token, 0)
        if expiry > _time.time():
            return True
        _sessions.pop(query_token, None)
    # Check cookie
    if not cookie_header:
        return False
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("voxel_session="):
            token = part.split("=", 1)[1]
            expiry = _sessions.get(token, 0)
            if expiry > _time.time():
                return True
            _sessions.pop(token, None)
    return False


# Token pre-created at boot for QR code direct access
_direct_token: str = ""


def get_direct_url(base_url: str) -> str:
    """Return config URL with an embedded session token for QR code scanning.

    Scanning the QR gives instant access (physical presence = trusted).
    The token is created once at boot and reused for the session duration.
    """
    global _direct_token
    if not _direct_token or _sessions.get(_direct_token, 0) <= _time.time():
        _direct_token = _create_session()
    return f"{base_url}/?token={_direct_token}"


def get_local_ip() -> str:
    """Get the Pi's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _start_speaking(text: str, state: "DisplayState") -> None:
    """Speak text with TTS audio playback + waveform animation.

    Tries real TTS (edge-tts → miniaudio decode → sounddevice playback)
    with live amplitude tracking. Falls back to amplitude simulation
    if TTS or audio isn't available.

    Runs in a background thread so the render loop isn't blocked.
    """
    import math
    import threading

    state.state = "SPEAKING"
    state.speaking = True

    def _run():
        spoken = False

        # Try real TTS + audio playback
        try:
            import asyncio
            from core.tts import synthesize
            from config.settings import load_settings

            settings = load_settings()
            provider = settings.get("audio", {}).get("tts_provider", "edge")

            loop = asyncio.new_event_loop()
            wav_bytes = loop.run_until_complete(
                synthesize(text, provider=provider, settings=settings)
            )
            loop.close()

            if wav_bytes:
                from core.audio import play_audio, get_amplitude, is_playing
                play_audio(wav_bytes)
                log.info("Speaking with TTS audio (%d bytes)", len(wav_bytes))

                # Track amplitude from real audio playback
                while is_playing():
                    state.amplitude = get_amplitude()
                    _time.sleep(0.05)

                spoken = True
        except Exception as e:
            log.debug("TTS playback unavailable, using simulation: %s", e)

        # Fallback: simulate amplitude (no audio)
        if not spoken:
            words = len(text.split())
            duration = max(1.5, min(words * 0.15, 12.0))
            start = _time.time()
            while _time.time() - start < duration:
                elapsed = _time.time() - start
                wave1 = abs(math.sin(elapsed * 8.0))
                wave2 = abs(math.sin(elapsed * 3.1))
                wave3 = abs(math.sin(elapsed * 13.7))
                state.amplitude = 0.25 + 0.45 * wave1 * wave2 + 0.1 * wave3
                _time.sleep(0.05)

        # Wind down
        state.amplitude = 0.0
        state.speaking = False
        state.state = "IDLE"
        _time.sleep(2.0)
        if state.state == "IDLE":
            state.mood = "neutral"

    threading.Thread(target=_run, daemon=True).start()


# Legacy alias for backward compatibility
_start_speaking_simulation = _start_speaking


def _start_error_recovery(state: "DisplayState", delay: float = 3.0) -> None:
    """Auto-recover from ERROR state to IDLE after a delay.

    Called when chat/gateway operations fail so the face shows the error
    expression briefly, then returns to normal.
    """
    import threading

    def _run():
        _time.sleep(delay)
        if state.state == "ERROR":
            state.state = "IDLE"
            state.mood = "neutral"
            state.speaking = False
            state.amplitude = 0.0

    threading.Thread(target=_run, daemon=True).start()


def get_wifi_status() -> dict:
    """Get current wifi connection info. Returns {connected, ssid, ip}."""
    info = {"connected": False, "ssid": "", "ip": get_local_ip()}
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            if line.startswith("yes:"):
                info["connected"] = True
                info["ssid"] = line.split(":", 1)[1]
                break
    except Exception:
        # Fallback: check if wlan0 has an IP
        try:
            result = subprocess.run(
                ["ip", "addr", "show", "wlan0"],
                capture_output=True, text=True, timeout=5,
            )
            if "inet " in result.stdout:
                info["connected"] = True
        except Exception:
            pass
    return info


def _load_settings() -> dict[str, Any]:
    from config.settings import load_settings
    return load_settings()


def _save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    from config.settings import save_local_settings
    return save_local_settings(updates)


def _reset_settings(sections: list[str] | None = None) -> dict[str, Any]:
    from config.settings import reset_to_defaults
    return reset_to_defaults(sections)


def _get_settings_diff() -> dict[str, Any]:
    from config.settings import get_diff_from_defaults
    return get_diff_from_defaults()


def _validate_settings(settings: dict[str, Any]) -> list[str]:
    from config.settings import validate_settings
    return validate_settings(settings)


def _build_login_html() -> str:
    """Build the PIN login page."""
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Voxel — Enter PIN</title>
{_FAVICON_LINK}
<style>
  :root, [data-theme="dark"] {{
    --bg: #0a0a0f; --bg-card: #12121a; --bg-input: #16161c;
    --border: #1e1e30; --border-input: #282840;
    --text: #e0e0e8; --text-dim: #666680; --text-muted: #555570;
    --accent: #00d4d2; --accent-hover: #00e8e6; --accent-active: #00b0ae;
    --danger: #ff5c5c; --danger-bg: rgba(255,60,60,0.08);
    --success: #34d381; --warning: #ff7700;
    --scrollbar-thumb: #282840; --logo-body: #1a1a2e;
    --req-btn-bg: #282840; --req-btn-text: #a0a0b4;
  }}
  [data-theme="light"] {{
    --bg: #f5f5f7; --bg-card: #ffffff; --bg-input: #f0f0f4;
    --border: #e0e0e8; --border-input: #d0d0dc;
    --text: #1a1a2e; --text-dim: #666680; --text-muted: #888898;
    --accent: #008886; --accent-hover: #00a5a3; --accent-active: #007070;
    --danger: #dc3545; --danger-bg: rgba(220,53,69,0.08);
    --success: #28a745; --warning: #fd7e14;
    --scrollbar-thumb: #c0c0cc; --logo-body: #1a1a2e;
    --req-btn-bg: #e8e8f0; --req-btn-text: #555570;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; min-height: 100dvh;
    padding: 16px; transition: background 0.2s ease, color 0.2s ease;
  }}
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 3px; }}
  html {{ scrollbar-color: var(--scrollbar-thumb) var(--bg); }}
  .card {{ width: 100%; max-width: 360px; text-align: center; }}
  .logo {{
    width: 56px; height: 56px;
    margin: 0 auto 16px;
  }}
  .logo svg {{ width: 100%; height: 100%; }}
  .logo svg rect.logo-bg {{ fill: var(--logo-body); transition: fill 0.2s ease; }}
  h1 {{ color: var(--accent); font-size: 24px; margin-bottom: 8px; }}
  p {{ color: var(--text-dim); font-size: 14px; margin-bottom: 32px; line-height: 1.4; }}
  .pin-wrap {{ display: flex; gap: 8px; justify-content: center; margin-bottom: 8px; }}
  .pin-digit {{
    width: 44px; height: 56px;
    border: 2px solid var(--border-input); border-radius: 8px;
    background: var(--bg-input); color: var(--text);
    font-size: 24px; text-align: center;
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
    transition: border-color 0.15s ease, background 0.15s ease;
    -webkit-appearance: none;
  }}
  .pin-digit:focus {{ outline: none; border-color: var(--accent); background: var(--bg-card); }}
  .pin-digit.filled {{ border-color: var(--accent); }}
  button {{
    background: var(--accent); color: var(--bg); border: none;
    padding: 14px 32px; border-radius: 8px;
    font-size: 16px; font-weight: 600; cursor: pointer;
    margin-top: 16px; min-height: 48px;
    transition: background 0.15s ease, opacity 0.15s ease;
  }}
  button:hover {{ background: var(--accent-hover); }}
  button:active {{ background: var(--accent-active); }}
  .err {{
    color: var(--danger); font-size: 13px; margin-top: 16px;
    display: none; padding: 8px 12px;
    background: var(--danger-bg); border-radius: 6px;
  }}
  .submitting {{ opacity: 0.6; pointer-events: none; }}
  .theme-toggle {{
    position: absolute; top: 16px; right: 16px;
    background: none; border: 1px solid var(--border);
    color: var(--text-dim); cursor: pointer; padding: 6px 8px;
    border-radius: 6px; font-size: 16px; min-height: auto;
    margin: 0; width: auto;
    transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
  }}
  .theme-toggle:hover {{ color: var(--text); background: var(--bg-card); }}
</style>
</head>
<body>
<button type="button" class="theme-toggle" onclick="toggleTheme()" id="theme-btn" aria-label="Toggle theme"></button>
<div class="card">
  <div class="logo">{_LOGO_SVG}</div>
  <h1>Voxel</h1>
  <p>Enter the 6-digit PIN shown on the device display</p>
  <form id="login">
    <div class="pin-wrap">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="0" autofocus autocomplete="off">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="1" autocomplete="off">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="2" autocomplete="off">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="3" autocomplete="off">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="4" autocomplete="off">
      <input class="pin-digit" type="text" inputmode="numeric" maxlength="1" data-idx="5" autocomplete="off">
    </div>
    <button type="submit" id="unlock-btn">Unlock</button>
  </form>
  <div class="err" id="err">Incorrect PIN</div>

  <div style="margin-top:24px;border-top:1px solid var(--border);padding-top:16px">
    <p style="color:var(--text-muted);font-size:12px;margin-bottom:8px">Don't have the PIN?</p>
    <button type="button" id="req-btn" onclick="requestAccess()" style="background:var(--req-btn-bg);color:var(--req-btn-text);font-size:14px;padding:12px 24px">Request Access on Device</button>
    <div id="req-status" style="margin-top:8px;font-size:13px;display:none"></div>
  </div>
</div>
<script>
/* ── Theme ──────────────────────────────────────────────────── */
function applyTheme(t) {{
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-btn').textContent = t === 'dark' ? '\u2600' : '\u263D';
}}
function toggleTheme() {{
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  localStorage.setItem('voxel-theme', next);
  applyTheme(next);
}}
applyTheme(localStorage.getItem('voxel-theme') || 'dark');

(function() {{
  const digits = document.querySelectorAll('.pin-digit');
  const form = document.getElementById('login');
  const errEl = document.getElementById('err');
  const btn = document.getElementById('unlock-btn');

  function getPin() {{
    return Array.from(digits).map(d => d.value).join('');
  }}

  async function submitPin() {{
    const pin = getPin();
    if (pin.length !== 6) return;
    btn.classList.add('submitting');
    btn.textContent = 'Verifying...';
    try {{
      const r = await fetch('/auth', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{pin}})
      }});
      const d = await r.json();
      if (d.ok) {{ location.reload(); }}
      else {{
        errEl.style.display = 'block';
        errEl.textContent = 'Incorrect PIN';
        digits.forEach(d => {{ d.value = ''; d.classList.remove('filled'); }});
        digits[0].focus();
      }}
    }} catch(e) {{
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }} finally {{
      btn.classList.remove('submitting');
      btn.textContent = 'Unlock';
    }}
  }}

  digits.forEach((input, idx) => {{
    input.addEventListener('input', (e) => {{
      const val = e.target.value.replace(/[^0-9]/g, '');
      e.target.value = val.slice(0, 1);
      e.target.classList.toggle('filled', val.length > 0);
      errEl.style.display = 'none';
      if (val && idx < 5) digits[idx + 1].focus();
      // Auto-submit when all 6 digits entered
      if (getPin().length === 6) submitPin();
    }});
    input.addEventListener('keydown', (e) => {{
      if (e.key === 'Backspace' && !e.target.value && idx > 0) {{
        digits[idx - 1].focus();
        digits[idx - 1].value = '';
        digits[idx - 1].classList.remove('filled');
      }}
    }});
    // Handle paste
    input.addEventListener('paste', (e) => {{
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData('text').replace(/[^0-9]/g, '');
      for (let i = 0; i < 6 && i < text.length; i++) {{
        digits[i].value = text[i];
        digits[i].classList.toggle('filled', true);
      }}
      if (text.length >= 6) submitPin();
      else if (text.length > 0) digits[Math.min(text.length, 5)].focus();
    }});
  }});

  form.addEventListener('submit', (e) => {{
    e.preventDefault();
    submitPin();
  }});
}})();

async function requestAccess() {{
  const btn = document.getElementById('req-btn');
  const status = document.getElementById('req-status');
  btn.disabled = true;
  btn.textContent = 'Waiting for approval on device...';
  status.style.display = 'block';
  status.style.color = 'var(--accent)';
  status.textContent = 'Check the Voxel device — tap to approve, hold to deny';
  try {{
    const r = await fetch('/api/dev/pair/request', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{dev_host: 'browser'}})
    }});
    const d = await r.json();
    if (d.approved && d.authenticated) {{
      status.style.color = 'var(--success)';
      status.textContent = 'Approved! Redirecting...';
      setTimeout(() => location.reload(), 500);
    }} else if (d.approved) {{
      status.style.color = 'var(--success)';
      status.textContent = 'Approved! Enter the PIN shown on device.';
      document.querySelector('.pin-digit').focus();
    }} else if (d.timeout) {{
      status.style.color = 'var(--warning)';
      status.textContent = 'No response from device — try again';
    }} else {{
      status.style.color = 'var(--danger)';
      status.textContent = 'Access denied on device';
    }}
  }} catch(e) {{
    status.style.color = 'var(--danger)';
    status.textContent = 'Connection failed: ' + e.message;
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Request Access on Device';
  }}
}}
</script>
</body>
</html>"""


def _build_html(settings: dict) -> str:
    """Build the settings page HTML with proper UTF-8 encoding."""
    gw = settings.get("gateway", {})
    stt = settings.get("stt", {}).get("whisper", {})
    tts_cfg = settings.get("tts", {}).get("elevenlabs", {})
    audio = settings.get("audio", {})
    display = settings.get("display", {})
    led_cfg = settings.get("led", {})
    agents = settings.get("agents", [])
    wifi = get_wifi_status()
    dev_checked = "checked" if settings.get("dev", {}).get("enabled", False) else ""
    adv_checked = "checked" if settings.get("dev", {}).get("advertise", True) else ""
    led_checked = "checked" if led_cfg.get("enabled", True) else ""

    char_cfg = settings.get("character", {})
    sys_context = char_cfg.get("system_context", "").strip()
    sys_context_checked = "checked" if char_cfg.get("system_context_enabled", True) else ""
    idle_personality_checked = "checked" if char_cfg.get("idle_personality", True) else ""
    demo_checked = "checked" if char_cfg.get("demo_mode", False) else ""
    power = settings.get("power", {})

    # Character select options
    from display.characters import character_names as _char_names
    current_char = char_cfg.get("default", "cube")
    char_options = ""
    for cn in _char_names():
        sel = "selected" if cn == current_char else ""
        char_options += f'  <option value="{cn}" {sel}>{cn.title()}</option>\n'

    # Accent color presets
    accent_color = char_cfg.get("accent_color", "#00d4d2")
    accent_presets = [
        ("#00d4d2", "Cyan"), ("#00e080", "Green"), ("#6090ff", "Blue"),
        ("#c060ff", "Purple"), ("#ff6080", "Pink"), ("#ffa030", "Orange"),
        ("#ffdd40", "Yellow"), ("#f0f0f0", "White"),
    ]
    accent_options = ""
    for hex_val, name in accent_presets:
        sel = "selected" if hex_val == accent_color else ""
        accent_options += f'  <option value="{hex_val}" {sel}>{name}</option>\n'

    current_agent = gw.get("default_agent", "daemon")
    agent_options = ""
    for a in agents:
        sel = "selected" if a["id"] == current_agent else ""
        name = escape(a.get("name", a["id"]))
        desc = escape(a.get("description", ""))
        agent_options += f'  <option value="{a["id"]}" {sel}>{name} — {desc}</option>\n'

    tts_provider = audio.get("tts_provider", "edge")
    edge_sel = "selected" if tts_provider == "edge" else ""
    openai_tts_sel = "selected" if tts_provider == "openai" else ""
    eleven_sel = "selected" if tts_provider == "elevenlabs" else ""
    openai_tts_cfg = settings.get("tts", {}).get("openai", {})

    wifi_badge = ""
    if wifi["connected"]:
        wifi_badge = f'<div class="badge ok">WiFi: {escape(wifi["ssid"])} ({wifi["ip"]})</div>'
    else:
        wifi_badge = '<div class="badge err">No WiFi — connect below or join Voxel-Setup hotspot</div>'

    # Validation warnings
    warnings = _validate_settings(settings)
    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{escape(w)}</li>" for w in warnings)
        warnings_html = f'<div class="badge warn"><strong>Warnings:</strong><ul>{items}</ul></div>'

    # MCP / Integration status
    mcp_cfg = settings.get("mcp", {})
    mcp_port = mcp_cfg.get("port", 8082)
    mcp_enabled = mcp_cfg.get("enabled", False)

    mcp_running = False
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _sock.settimeout(0.3)
        _sock.connect(("127.0.0.1", mcp_port))
        _sock.close()
        mcp_running = True
    except Exception:
        pass

    device_ip = get_local_ip()
    config_port = _server_port

    mcp_status_text = "Running" if mcp_running else "Stopped"
    mcp_status_class = "running" if mcp_running else "stopped"
    mcp_checked = "checked" if mcp_enabled else ""
    mcp_display = "" if mcp_enabled else 'style="display:none"'
    mcp_class = "enabled" if mcp_enabled else "disabled"

    wh_cfg = settings.get("webhook", {})
    webhook_url = escape(wh_cfg.get("url", ""))
    webhook_checked = "checked" if wh_cfg.get("enabled") else ""
    webhook_class = "enabled" if wh_cfg.get("enabled") else "disabled"

    claude_config = json.dumps({"mcpServers": {"voxel": {"url": f"http://{device_ip}:{mcp_port}/sse"}}}, indent=2)
    claude_stdio = json.dumps({"mcpServers": {"voxel": {"command": "uv", "args": ["run", "python", "-m", "mcp"], "cwd": "/path/to/voxel"}}}, indent=2)
    setup_url = f"http://{device_ip}:{config_port}/setup"
    skill_url = f"http://{device_ip}:{config_port}/skill"
    mcp_sse_url = f"http://{device_ip}:{mcp_port}/sse"
    discovery_url = f"http://{device_ip}:{config_port}/.well-known/mcp"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Voxel Settings</title>
{_FAVICON_LINK}
<style>
  /* ── Theme variables ──────────────────────────────────────────── */
  :root, [data-theme="dark"] {{
    --bg: #0a0a0f; --bg-card: #12121a; --bg-input: #0e0e16;
    --bg-input-focus: #10101a; --bg-hover: #16161e;
    --border: #1e1e30; --border-input: #282840;
    --text: #e0e0e8; --text-dim: #666680; --text-muted: #555570;
    --text-label: #b0b0c4;
    --accent: #00d4d2; --accent-hover: #00e8e6; --accent-active: #00b0ae;
    --accent-text: #00d4d2;
    --danger: #ff5c5c; --danger-bg: #200a0a; --danger-border: #401a1a;
    --success: #34d381; --success-bg: #0a201a; --success-border: #1a4030;
    --warning: #e8b840; --warning-bg: #201a0a; --warning-border: #403018;
    --warning-strong: #f0c850;
    --scrollbar-thumb: #282840; --logo-body: #1a1a2e;
    --btn-secondary-bg: #1e1e30; --btn-secondary-border: #282840;
    --btn-secondary-hover: #262640; --btn-secondary-active: #1a1a2c;
    --code-bg: #0a0a10; --toast-ok-bg: #0a2020; --toast-ok-border: #1a4030;
    --toast-err-bg: #2a1010; --toast-err-border: #401a1a;
    --save-bar-bg: #12121aee; --range-track: #282840;
    --slider-border: #0a0a0f;
    --status-dot-ok: #34d381; --status-dot-err: #ff5c5c;
    --pin-text: #40fff8;
  }}
  [data-theme="light"] {{
    --bg: #f5f5f7; --bg-card: #ffffff; --bg-input: #f8f8fc;
    --bg-input-focus: #ffffff; --bg-hover: #f0f0f5;
    --border: #e0e0e8; --border-input: #d0d0dc;
    --text: #1a1a2e; --text-dim: #666680; --text-muted: #888898;
    --text-label: #555570;
    --accent: #008886; --accent-hover: #00a5a3; --accent-active: #007070;
    --accent-text: #007070;
    --danger: #dc3545; --danger-bg: #fff0f0; --danger-border: #f0c0c0;
    --success: #28a745; --success-bg: #f0fff4; --success-border: #c0e8c8;
    --warning: #c08800; --warning-bg: #fffbf0; --warning-border: #e8d8a0;
    --warning-strong: #a07000;
    --scrollbar-thumb: #c0c0cc; --logo-body: #1a1a2e;
    --btn-secondary-bg: #f0f0f5; --btn-secondary-border: #d0d0dc;
    --btn-secondary-hover: #e8e8f0; --btn-secondary-active: #e0e0ea;
    --code-bg: #f8f8fc; --toast-ok-bg: #f0fff4; --toast-ok-border: #c0e8c8;
    --toast-err-bg: #fff0f0; --toast-err-border: #f0c0c0;
    --save-bar-bg: #ffffffee; --range-track: #d0d0dc;
    --slider-border: #ffffff;
    --status-dot-ok: #28a745; --status-dot-err: #dc3545;
    --pin-text: #008886;
  }}

  /* ── Reset & base ─────────────────────────────────────────────── */
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 16px 16px 120px; max-width: 520px; margin: 0 auto;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
    transition: background 0.2s ease, color 0.2s ease;
  }}

  /* ── Scrollbar ────────────────────────────────────────────────── */
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 3px; }}
  html {{ scrollbar-color: var(--scrollbar-thumb) var(--bg); }}

  /* ── Header ───────────────────────────────────────────────────── */
  .page-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
  .logo {{
    width: 40px; height: 40px; flex-shrink: 0;
  }}
  .logo svg {{ width: 100%; height: 100%; }}
  .logo svg rect.logo-bg {{ fill: var(--logo-body); transition: fill 0.2s ease; }}
  h1 {{ color: var(--accent); font-size: 22px; }}
  .subtitle {{ font-size: 13px; color: var(--text-dim); margin-bottom: 16px; }}
  .header-actions {{ display: flex; align-items: center; gap: 6px; margin-left: auto; }}
  .nav-link {{
    color: var(--text-dim); font-size: 13px; text-decoration: none;
    padding: 6px 10px; border-radius: 6px;
    transition: color 0.15s ease, background 0.15s ease;
  }}
  .nav-link:hover {{ color: var(--text); background: var(--bg-card); }}
  .theme-toggle {{
    background: none; border: 1px solid var(--border);
    color: var(--text-dim); cursor: pointer; padding: 5px 8px;
    border-radius: 6px; font-size: 15px; min-height: auto;
    width: auto; margin: 0; line-height: 1;
    transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
  }}
  .theme-toggle:hover {{ color: var(--text); background: var(--bg-card); }}
  .status-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--status-dot-err); display: inline-block;
    margin-right: 4px; transition: background 0.3s ease;
  }}
  .status-dot.ok {{ background: var(--status-dot-ok); }}
  .conn-indicator {{
    display: flex; align-items: center; font-size: 11px;
    color: var(--text-muted); padding: 4px 8px; border-radius: 6px;
    border: 1px solid var(--border);
  }}

  /* ── Cards ────────────────────────────────────────────────────── */
  .card {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; margin-bottom: 12px;
    transition: background 0.2s ease, border-color 0.2s ease;
  }}

  /* ── Details/Summary (collapsible sections) ───────────────────── */
  details {{ margin-bottom: 12px; }}
  details > summary {{
    display: flex; align-items: center; justify-content: space-between;
    cursor: pointer; list-style: none; padding: 14px 16px;
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    font-size: 15px; font-weight: 600; color: var(--text);
    min-height: 48px; transition: background 0.15s ease, border-color 0.2s ease;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
  }}
  details > summary::-webkit-details-marker {{ display: none; }}
  details > summary::after {{
    content: ''; width: 8px; height: 8px; flex-shrink: 0;
    border-right: 2px solid var(--text-dim); border-bottom: 2px solid var(--text-dim);
    transform: rotate(45deg); transition: transform 0.15s ease;
    margin-left: 8px;
  }}
  details[open] > summary::after {{ transform: rotate(-135deg); }}
  details[open] > summary {{ border-radius: 12px 12px 0 0; border-bottom-color: transparent; }}
  details > summary:hover {{ background: var(--bg-hover); }}
  details > .card-body {{
    background: var(--bg-card); border: 1px solid var(--border); border-top: none;
    border-radius: 0 0 12px 12px; padding: 16px;
    transition: background 0.2s ease, border-color 0.2s ease;
  }}
  .section-icon {{ margin-right: 8px; font-size: 16px; opacity: 0.7; }}
  .section-title {{ flex: 1; }}
  .section-reset {{
    font-size: 11px; color: var(--text-dim); padding: 4px 8px;
    border-radius: 4px; transition: color 0.15s ease;
    text-decoration: none; cursor: pointer;
  }}
  .section-reset:hover {{ color: var(--danger); }}

  /* ── Typography ───────────────────────────────────────────────── */
  h2 {{ color: var(--accent); font-size: 15px; margin-bottom: 12px; }}

  /* ── Form elements ────────────────────────────────────────────── */
  label {{
    display: block; font-size: 13px; font-weight: 500;
    color: var(--text-label); margin: 12px 0 4px;
  }}
  label:first-child {{ margin-top: 0; }}
  input[type="text"], input[type="password"], input[type="url"], select {{
    width: 100%; padding: 12px; min-height: 48px;
    border: 1px solid var(--border-input); border-radius: 8px;
    background: var(--bg-input); color: var(--text);
    font-size: 15px; font-family: inherit;
    transition: border-color 0.15s ease, background 0.15s ease;
  }}
  input[type="text"]:focus, input[type="password"]:focus, input[type="url"]:focus, select:focus {{
    outline: none; border-color: var(--accent); background: var(--bg-input-focus);
  }}
  .hint {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; line-height: 1.4; }}

  /* ── Password toggle ──────────────────────────────────────────── */
  .pw-wrap {{ position: relative; }}
  .pw-wrap input {{ padding-right: 48px; }}
  .pw-wrap input[data-secret] {{ -webkit-text-security: disc; text-security: disc; }}
  .pw-wrap input[data-secret].revealed {{ -webkit-text-security: none; text-security: none; }}
  .pw-toggle {{
    position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--text-dim); cursor: pointer;
    padding: 8px; font-size: 18px; line-height: 1; min-height: auto;
    width: auto; margin: 0; transition: color 0.15s ease;
  }}
  .pw-toggle:hover {{ color: var(--text); }}

  /* ── Range sliders ────────────────────────────────────────────── */
  .range-row {{ display: flex; align-items: center; gap: 12px; }}
  .range-row input[type="range"] {{ flex: 1; min-height: 48px; }}
  .range-val {{
    min-width: 40px; text-align: right; font-size: 14px;
    color: var(--accent-text); font-weight: 600;
    font-family: 'SF Mono', 'Cascadia Code', monospace;
  }}
  input[type="range"] {{
    -webkit-appearance: none; appearance: none;
    height: 6px; background: var(--range-track); border-radius: 3px;
    border: none; outline: none;
  }}
  input[type="range"]::-webkit-slider-thumb {{
    -webkit-appearance: none; width: 24px; height: 24px;
    background: var(--accent); border-radius: 50%; cursor: pointer;
    border: 2px solid var(--slider-border);
  }}
  input[type="range"]::-moz-range-thumb {{
    width: 24px; height: 24px; background: var(--accent);
    border-radius: 50%; cursor: pointer; border: 2px solid var(--slider-border);
  }}

  /* ── Checkboxes ───────────────────────────────────────────────── */
  .check-row {{
    display: flex; align-items: center; gap: 10px; cursor: pointer;
    min-height: 44px; padding: 4px 0;
  }}
  .check-row input[type="checkbox"] {{
    width: 20px; height: 20px; accent-color: var(--accent);
    flex-shrink: 0; cursor: pointer;
  }}
  .check-label {{ font-size: 14px; color: var(--text); }}

  /* ── Buttons ──────────────────────────────────────────────────── */
  button, .btn {{
    display: inline-flex; align-items: center; justify-content: center;
    border: none; border-radius: 8px; font-size: 15px; font-weight: 600;
    cursor: pointer; min-height: 48px; padding: 12px 20px;
    width: 100%; font-family: inherit;
    transition: background 0.15s ease, opacity 0.15s ease, transform 0.1s ease;
    -webkit-tap-highlight-color: transparent;
  }}
  button:active {{ transform: scale(0.98); }}
  button:disabled {{ opacity: 0.5; pointer-events: none; }}
  .btn-primary {{ background: var(--accent); color: var(--bg); }}
  .btn-primary:hover {{ background: var(--accent-hover); }}
  .btn-primary:active {{ background: var(--accent-active); }}
  .btn-secondary {{ background: var(--btn-secondary-bg); color: var(--text); border: 1px solid var(--btn-secondary-border); }}
  .btn-secondary:hover {{ background: var(--btn-secondary-hover); }}
  .btn-secondary:active {{ background: var(--btn-secondary-active); }}
  .agent-tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .btn-destructive {{
    background: transparent; color: var(--danger);
    border: 1px solid color-mix(in srgb, var(--danger) 25%, transparent);
  }}
  .btn-destructive:hover {{ background: color-mix(in srgb, var(--danger) 6%, transparent); border-color: color-mix(in srgb, var(--danger) 50%, transparent); }}
  .btn-destructive:active {{ background: color-mix(in srgb, var(--danger) 10%, transparent); }}

  /* ── Status messages ──────────────────────────────────────────── */
  .status {{
    padding: 12px; border-radius: 8px; margin-top: 12px;
    font-size: 14px; display: none; line-height: 1.4;
  }}
  .status.ok {{ display: block; background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); }}
  .status.err {{ display: block; background: var(--danger-bg); color: var(--danger); border: 1px solid var(--danger-border); }}

  /* ── Badges / banners ─────────────────────────────────────────── */
  .badge {{
    padding: 12px 16px; border-radius: 8px; font-size: 13px;
    margin-bottom: 12px; line-height: 1.4;
  }}
  .badge.ok {{ background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); }}
  .badge.warn {{
    background: var(--warning-bg); color: var(--warning);
    border: 1px solid var(--warning-border);
  }}
  .badge.warn strong {{ color: var(--warning-strong); }}
  .badge.warn ul {{ margin: 6px 0 0 16px; padding: 0; list-style: disc; }}
  .badge.warn li {{ margin: 2px 0; }}
  .badge.err {{ background: var(--danger-bg); color: var(--danger); border: 1px solid var(--danger-border); }}

  /* ── Integration section ──────────────────────────────────────── */
  .mode-cards {{ display: flex; gap: 8px; margin: 12px 0; }}
  .mode-card {{
    flex: 1; padding: 10px; border-radius: 8px; text-align: center;
    background: var(--bg-input); border: 1px solid var(--border);
    font-size: 13px;
  }}
  .mode-card strong {{ display: block; font-size: 14px; margin-bottom: 4px; }}
  .mode-card p {{ color: var(--text-dim); font-size: 11px; margin: 0; }}
  .mode-card.active {{ border-color: var(--accent); }}
  .mode-card.enabled {{ border-color: var(--success); }}
  .mode-card.disabled {{ opacity: 0.5; }}

  .status-row {{ display: flex; align-items: center; gap: 8px; margin: 8px 0; }}
  .status-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
  .status-badge.running {{ background: rgba(52,211,129,0.15); color: var(--success); }}
  .status-badge.stopped {{ background: rgba(255,92,92,0.1); color: var(--text-dim); }}

  .connect-info {{ margin-top: 12px; }}
  .connect-info h3 {{ font-size: 13px; color: var(--text-dim); margin: 12px 0 4px; }}
  .code-block {{
    background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 12px; font-family: 'SF Mono', 'Cascadia Code', monospace;
    font-size: 12px; word-break: break-all; cursor: pointer;
    position: relative; white-space: pre-wrap;
  }}
  .code-block:hover::after {{
    content: 'Click to copy'; position: absolute; right: 8px; top: 50%;
    transform: translateY(-50%); font-size: 10px; color: var(--accent);
    font-family: system-ui;
  }}

  /* ── WiFi network list ────────────────────────────────────────── */
  .wifi-net {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px; border: 1px solid var(--border); border-radius: 8px;
    margin-bottom: 6px; cursor: pointer; min-height: 48px;
    transition: border-color 0.15s ease, background 0.15s ease;
    -webkit-tap-highlight-color: transparent;
  }}
  .wifi-net:hover {{ border-color: var(--accent); background: color-mix(in srgb, var(--accent) 5%, var(--bg)); }}
  .wifi-net .ssid {{ font-size: 15px; font-weight: 500; }}
  .wifi-net .meta {{ font-size: 12px; color: var(--text-dim); }}
  .wifi-net.active {{ border-color: var(--success); background: color-mix(in srgb, var(--success) 5%, var(--bg)); }}
  .wifi-signal {{
    display: inline-flex; align-items: flex-end; gap: 2px; height: 16px;
    margin-right: 6px; vertical-align: middle;
  }}
  .wifi-signal .bar {{
    width: 3px; background: var(--border-input); border-radius: 1px;
    transition: background 0.15s ease;
  }}
  .wifi-signal .bar.active {{ background: var(--accent); }}
  .wifi-signal .bar:nth-child(1) {{ height: 4px; }}
  .wifi-signal .bar:nth-child(2) {{ height: 8px; }}
  .wifi-signal .bar:nth-child(3) {{ height: 12px; }}
  .wifi-signal .bar:nth-child(4) {{ height: 16px; }}
  .wifi-net.active .wifi-signal .bar.active {{ background: var(--success); }}

  /* ── Code blocks (copyable) ───────────────────────────────────── */
  .code-block {{
    position: relative; background: var(--code-bg); border: 1px solid var(--border);
    padding: 12px 44px 12px 12px; border-radius: 8px; margin-bottom: 8px;
    cursor: pointer; transition: border-color 0.15s ease;
  }}
  .code-block:hover {{ border-color: var(--border-input); }}
  .code-block:active {{ background: var(--bg-hover); }}
  .code-block .code-hint {{ font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }}
  .code-block code {{
    color: var(--accent-text); font-size: 13px; word-break: break-all;
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  }}
  .copy-btn {{
    position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--text-muted); cursor: pointer;
    padding: 6px; font-size: 16px; min-height: auto; width: auto;
    transition: color 0.15s ease;
  }}
  .copy-btn:hover {{ color: var(--text); }}
  .copy-btn.copied {{ color: var(--success); }}

  /* ── Sticky save bar ──────────────────────────────────────────── */
  .save-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--save-bar-bg); backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-top: 1px solid var(--border);
    padding: 12px 16px; z-index: 100;
  }}
  .save-bar-inner {{
    max-width: 520px; margin: 0 auto;
    display: flex; gap: 8px; align-items: center;
  }}
  .save-bar button {{ flex: 1; margin: 0; }}
  #status {{
    max-width: 520px; margin: 0 auto; padding: 0 16px;
  }}
  /* When status shown in save bar */
  .save-bar .status {{ margin: 0; flex: 2; font-size: 13px; padding: 8px; }}

  /* ── Spacing helpers ──────────────────────────────────────────── */
  .mt-2 {{ margin-top: 8px; }}
  .mt-3 {{ margin-top: 12px; }}
  .mt-4 {{ margin-top: 16px; }}
  .mb-2 {{ margin-bottom: 8px; }}
  .mb-3 {{ margin-bottom: 12px; }}
  .gap-2 {{ gap: 8px; }}

  /* ── Media queries ────────────────────────────────────────────── */
  @media (min-width: 480px) {{
    body {{ padding: 24px 24px 120px; }}
    .card {{ padding: 20px; }}
    details > .card-body {{ padding: 20px; }}
  }}
</style>
</head>
<body>

<!-- Header -->
<div class="page-header">
  <div class="logo">{_LOGO_SVG}</div>
  <h1>Voxel Settings</h1>
  <div class="header-actions">
    <div class="conn-indicator" id="conn-indicator">
      <span class="status-dot" id="conn-dot"></span>
      <span id="conn-text">Checking...</span>
    </div>
    <a href="/chat" class="nav-link">Chat</a>
    <a href="/diagnostics" class="nav-link">Diagnostics</a>
    <button type="button" class="theme-toggle" onclick="toggleTheme()" id="theme-btn" aria-label="Toggle theme"></button>
  </div>
</div>
<div class="subtitle">Pocket AI companion configuration</div>

<!-- Status banners -->
{wifi_badge}
{warnings_html}

<!-- WiFi -->
<details open>
  <summary>
    <span class="section-icon">&#128225;</span><span class="section-title">WiFi</span>
  </summary>
  <div class="card-body">
    <div id="wifi-networks" class="mb-3"><span style="color:var(--text-muted)">Tap Scan to find networks</span></div>
    <button type="button" id="wifi-scan" onclick="wifiScan()" class="btn-secondary mb-3">Scan Networks</button>
    <div id="wifi-connect-form" style="display:none" class="mt-3">
      <label>Network: <strong id="wifi-selected-ssid" style="color:var(--accent)"></strong></label>
      <div class="pw-wrap">
        <input id="wifi-pass" type="text" autocomplete="off" data-secret placeholder="Password (leave empty if open)">
        <button type="button" class="pw-toggle" onclick="togglePw(this)" aria-label="Show password">&#128065;</button>
      </div>
      <button type="button" onclick="wifiConnect()" class="btn-primary mt-3">Connect</button>
    </div>
    <div id="wifi-status"></div>
  </div>
</details>

<form id="f" autocomplete="off">

<!-- OpenClaw Gateway -->
<details open>
  <summary>
    <span class="section-icon">&#127760;</span><span class="section-title">OpenClaw Gateway</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('gateway')">reset</span>
  </summary>
  <div class="card-body">
    <label>Gateway URL</label>
    <input name="gateway.url" type="url" value="{escape(gw.get('url', ''))}" placeholder="http://gateway-host:18789">
    <div class="hint">OpenClaw gateway server address</div>

    <label>Gateway Token</label>
    <div class="pw-wrap">
      <input name="gateway.token" type="text" autocomplete="off" data-secret value="{escape(gw.get('token', ''))}" placeholder="Enter token">
      <button type="button" class="pw-toggle" onclick="togglePw(this)" aria-label="Show password">&#128065;</button>
    </div>
    <div class="hint">Authentication token for the gateway</div>

    <label>Default Agent</label>
    <select name="gateway.default_agent">
    {agent_options}</select>
  </div>
</details>

<!-- Speech-to-Text -->
<details>
  <summary>
    <span class="section-icon">&#127908;</span><span class="section-title">Speech-to-Text</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('stt')">reset</span>
  </summary>
  <div class="card-body">
    <label>OpenAI API Key (Whisper)</label>
    <div class="pw-wrap">
      <input name="stt.whisper.api_key" type="text" autocomplete="off" data-secret value="{escape(stt.get('api_key', ''))}" placeholder="sk-...">
      <button type="button" class="pw-toggle" onclick="togglePw(this)" aria-label="Show password">&#128065;</button>
    </div>
    <div class="hint">Required for voice input</div>
  </div>
</details>

<!-- Text-to-Speech -->
<details>
  <summary>
    <span class="section-icon">&#128264;</span><span class="section-title">Text-to-Speech</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('tts')">reset</span>
  </summary>
  <div class="card-body">
    <label>TTS Provider</label>
    <select name="audio.tts_provider">
      <option value="edge" {edge_sel}>Edge TTS (free)</option>
      <option value="openai" {openai_tts_sel}>OpenAI TTS</option>
      <option value="elevenlabs" {eleven_sel}>ElevenLabs</option>
    </select>

    <label>OpenAI TTS Voice</label>
    <select name="tts.openai.voice">
      <option value="nova" {"selected" if openai_tts_cfg.get("voice", "nova") == "nova" else ""}>Nova (warm female)</option>
      <option value="alloy" {"selected" if openai_tts_cfg.get("voice") == "alloy" else ""}>Alloy (neutral)</option>
      <option value="ash" {"selected" if openai_tts_cfg.get("voice") == "ash" else ""}>Ash (conversational male)</option>
      <option value="coral" {"selected" if openai_tts_cfg.get("voice") == "coral" else ""}>Coral (warm female)</option>
      <option value="echo" {"selected" if openai_tts_cfg.get("voice") == "echo" else ""}>Echo (deep male)</option>
      <option value="fable" {"selected" if openai_tts_cfg.get("voice") == "fable" else ""}>Fable (British male)</option>
      <option value="onyx" {"selected" if openai_tts_cfg.get("voice") == "onyx" else ""}>Onyx (deep male)</option>
      <option value="sage" {"selected" if openai_tts_cfg.get("voice") == "sage" else ""}>Sage (calm female)</option>
      <option value="shimmer" {"selected" if openai_tts_cfg.get("voice") == "shimmer" else ""}>Shimmer (cheerful female)</option>
    </select>
    <div class="hint">Uses same API key as STT (Whisper). Falls back to Edge TTS if no key set.</div>

    <label>ElevenLabs API Key</label>
    <div class="pw-wrap">
      <input name="tts.elevenlabs.api_key" type="text" autocomplete="off" data-secret value="{escape(tts_cfg.get('api_key', ''))}" placeholder="Optional">
      <button type="button" class="pw-toggle" onclick="togglePw(this)" aria-label="Show password">&#128065;</button>
    </div>
    <div class="hint">Only needed if using ElevenLabs provider</div>
  </div>
</details>

<!-- Character & Appearance -->
<details>
  <summary>
    <span class="section-icon">&#127912;</span><span class="section-title">Character &amp; Appearance</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('character')">reset</span>
  </summary>
  <div class="card-body">
    <label>Character</label>
    <select name="character.default">{char_options}</select>
    <div class="hint">Which character face to display (cube, bmo, voxel)</div>

    <label class="mt-3">Accent Color</label>
    <select name="character.accent_color" onchange="document.getElementById('accent-preview').style.background=this.value">{accent_options}</select>
    <div style="display:flex;align-items:center;gap:8px;margin-top:4px">
      <div id="accent-preview" style="width:20px;height:20px;border-radius:50%;background:{accent_color}"></div>
      <span class="hint" style="margin:0">Eye glow, edge color, and UI accent</span>
    </div>

    <div style="border-top:1px solid var(--border);margin:16px 0"></div>

    <label class="check-row">
      <input type="checkbox" name="character.idle_personality" value="true" {idle_personality_checked}>
      <span class="check-label">Reactive idle moods</span>
    </label>
    <div class="hint">Mood changes from battery, connection, and idle time (not random)</div>

    <label class="check-row">
      <input type="checkbox" name="character.demo_mode" value="true" {demo_checked}>
      <span class="check-label">Demo mode</span>
    </label>
    <div class="hint">Auto-cycle through moods, characters, and styles (showcase)</div>

    <div style="border-top:1px solid var(--border);margin:16px 0"></div>

    <label>Gaze Range</label>
    <div class="range-row">
      <input name="character.gaze_range" type="range" min="0" max="100" value="{int(char_cfg.get('gaze_range', 0.5) * 100)}" oninput="document.getElementById('gr').textContent=this.value+'%'">
      <span class="range-val" id="gr">{int(char_cfg.get('gaze_range', 0.5) * 100)}%</span>
    </div>
    <div class="hint">How far eyes shift when looking around (0 = fixed, 100 = max wander)</div>

    <label class="mt-3">Gaze Speed</label>
    <div class="range-row">
      <input name="character.gaze_drift_speed" type="range" min="10" max="100" value="{int(char_cfg.get('gaze_drift_speed', 0.5) * 100)}" oninput="document.getElementById('gs').textContent=this.value+'%'">
      <span class="range-val" id="gs">{int(char_cfg.get('gaze_drift_speed', 0.5) * 100)}%</span>
    </div>
    <div class="hint">How quickly and often eyes shift to new positions</div>
  </div>
</details>

<!-- Personality -->
<details>
  <summary>
    <span class="section-icon">&#128172;</span><span class="section-title">Personality</span>
  </summary>
  <div class="card-body">
    <label class="check-row">
      <input type="checkbox" name="character.system_context_enabled" value="true" {sys_context_checked}> Enable device context
    </label>
    <div class="hint">Prepends a system message telling the agent about Voxel's constraints (short responses, tiny screen)</div>

    <label style="margin-top:12px">System Context</label>
    <textarea name="character.system_context" rows="4" style="width:100%;padding:10px;border:1px solid var(--border-input);border-radius:6px;background:var(--bg-input);color:var(--text);font-size:13px;font-family:inherit;resize:vertical">{escape(sys_context)}</textarea>
    <div class="hint">Injected as a system message before every conversation. Doesn't override the agent's personality.</div>
  </div>
</details>

<!-- Power Management -->
<details>
  <summary>
    <span class="section-icon">&#128267;</span><span class="section-title">Power</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('power')">reset</span>
  </summary>
  <div class="card-body">
    <label>Dim after idle (seconds)</label>
    <div class="range-row">
      <input name="power.dim_after_idle" type="range" min="10" max="300" value="{power.get('dim_after_idle', 60)}" oninput="document.getElementById('pdi').textContent=this.value+'s'">
      <span class="range-val" id="pdi">{power.get('dim_after_idle', 60)}s</span>
    </div>
    <label class="mt-3">Sleep after idle (seconds)</label>
    <div class="range-row">
      <input name="power.sleep_after_idle" type="range" min="30" max="900" value="{power.get('sleep_after_idle', 300)}" oninput="document.getElementById('psi').textContent=this.value+'s'">
      <span class="range-val" id="psi">{power.get('sleep_after_idle', 300)}s</span>
    </div>
    <label class="mt-3">Dim brightness</label>
    <div class="range-row">
      <input name="power.dim_brightness" type="range" min="0" max="100" value="{power.get('dim_brightness', 20)}" oninput="document.getElementById('pdb').textContent=this.value+'%'">
      <span class="range-val" id="pdb">{power.get('dim_brightness', 20)}%</span>
    </div>
  </div>
</details>

<!-- Display & LED -->
<details>
  <summary>
    <span class="section-icon">&#128161;</span><span class="section-title">Display &amp; LED</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('display')">reset</span>
  </summary>
  <div class="card-body">
    <label>Brightness</label>
    <div class="range-row">
      <input name="display.brightness" type="range" min="0" max="100" value="{display.get('brightness', 80)}" oninput="document.getElementById('bv').textContent=this.value+'%'">
      <span class="range-val" id="bv">{display.get('brightness', 80)}%</span>
    </div>
    <div class="hint">100% recommended (lower values may flicker on SPI)</div>

    <div style="border-top:1px solid var(--border);margin:16px 0"></div>

    <label class="check-row">
      <input type="checkbox" name="led.enabled" value="true" {led_checked}>
      <span class="check-label">Enable RGB LED</span>
    </label>
    <div class="hint">Status LED on the Whisplay HAT</div>

    <label class="mt-3">LED Brightness</label>
    <div class="range-row">
      <input name="led.brightness" type="range" min="0" max="100" value="{led_cfg.get('brightness', 80)}" oninput="document.getElementById('lv').textContent=this.value+'%'">
      <span class="range-val" id="lv">{led_cfg.get('brightness', 80)}%</span>
    </div>
  </div>
</details>

<!-- Development -->
<details>
  <summary>
    <span class="section-icon">&#128736;</span><span class="section-title">Development</span>
    <span class="section-reset" onclick="event.stopPropagation();resetSection('dev')">reset</span>
  </summary>
  <div class="card-body">
    <label class="check-row">
      <input type="checkbox" name="dev.enabled" value="true" {dev_checked}>
      <span class="check-label">Enable Dev Mode</span>
    </label>
    <div class="hint">Skips web auth, shows debug indicators, exposes /api/debug/state</div>

    <label class="check-row mt-3">
      <input type="checkbox" name="dev.advertise" value="true" {adv_checked}>
      <span class="check-label">Advertise on Network</span>
    </label>
    <div class="hint">Broadcasts device presence on LAN for auto-discovery</div>

    <div style="border-top:1px solid var(--border);margin:16px 0"></div>
    <div style="font-size:14px;font-weight:500;color:var(--text-label);margin-bottom:10px">Pair a dev machine</div>

    <div class="code-block" onclick="copyCode(this)">
      <div class="code-hint">Auto-discover on network</div>
      <code>uv run voxel dev-pair</code>
      <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
    </div>
    <div class="code-block" onclick="copyCode(this)">
      <div class="code-hint">Or specify this device</div>
      <code>uv run voxel dev-pair --host {escape(wifi.get("ip", ""))}</code>
      <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
    </div>

    <div style="font-size:13px;color:var(--text-label);margin-top:12px">
      PIN: <strong style="color:var(--pin-text);font-size:16px;letter-spacing:2px;font-family:monospace">{escape(get_access_pin())}</strong>
    </div>
    <div class="hint">Enter this PIN when prompted by the command</div>

    <button type="button" onclick="devPairBrowser()" class="btn-secondary mt-3">Enable Dev Mode Now</button>
    <div id="pair-status"></div>
  </div>
</details>

<!-- Integration -->
<details>
  <summary>
    <span class="section-icon">&#128268;</span>
    <span class="section-title">Integration</span>
  </summary>
  <div class="card-body">

    <!-- Agent Setup card (Moltbook-style) -->
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px">
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button type="button" class="btn-secondary agent-tab active" onclick="showAgentTab('human',this)" style="flex:1;font-size:13px;padding:8px">I'm a Human</button>
        <button type="button" class="btn-secondary agent-tab" onclick="showAgentTab('agent',this)" style="flex:1;font-size:13px;padding:8px">I'm an Agent</button>
      </div>
      <div id="tab-human">
        <div style="font-size:14px;font-weight:500;margin-bottom:8px">Connect an AI Agent to Voxel</div>
        <div class="code-block" onclick="copyCode(this)" style="margin-bottom:8px">
          <div class="code-hint">Send this URL to your agent</div>
          <code>{setup_url}</code>
          <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
        </div>
        <div style="font-size:12px;color:var(--text-dim);line-height:1.5">
          1. Send the setup URL to your AI agent<br>
          2. Agent reads instructions + installs skill<br>
          3. Agent connects via MCP (enable below)
        </div>
      </div>
      <div id="tab-agent" style="display:none">
        <div style="font-size:14px;font-weight:500;margin-bottom:8px">Agent Self-Setup</div>
        <div class="code-block" onclick="copyCode(this)" style="margin-bottom:8px">
          <div class="code-hint">Read setup instructions</div>
          <code>curl {setup_url}</code>
          <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
        </div>
        <div class="code-block" onclick="copyCode(this)" style="margin-bottom:8px">
          <div class="code-hint">Install skill definition</div>
          <code>curl {skill_url}</code>
          <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
        </div>
        <div class="code-block" onclick="copyCode(this)">
          <div class="code-hint">MCP discovery endpoint</div>
          <code>{discovery_url}</code>
          <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
        </div>
      </div>
    </div>

    <div style="border-top:1px solid var(--border);margin:14px 0"></div>

    <h2 style="font-size:15px;margin:0 0 8px">MCP Server</h2>
    <div class="status-row">
      <span>Status:</span>
      <span class="status-badge {mcp_status_class}">{mcp_status_text}</span>
    </div>

    <label class="check-row">
      <input type="checkbox" name="mcp.enabled" value="true" {mcp_checked} onchange="toggleMcp(this.checked)">
      <span class="check-label">Enable MCP Server (port {mcp_port})</span>
    </label>
    <div class="hint">Auto-starts with display service when enabled</div>

    <div class="connect-info" id="mcp-connect-info" {mcp_display}>
      <div style="font-size:13px;font-weight:500;color:var(--text-label);margin:10px 0 6px">OpenClaw (remote, SSE)</div>
      <div class="code-block" onclick="copyCode(this)">
        <code>mcporter config add voxel --url {mcp_sse_url}</code>
        <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
      </div>

      <div style="font-size:13px;font-weight:500;color:var(--text-label);margin:10px 0 6px">Claude Code / Codex (remote, SSE)</div>
      <div class="code-block" onclick="copyCode(this)">
        <code>{escape(claude_config)}</code>
        <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
      </div>

      <div style="font-size:13px;font-weight:500;color:var(--text-label);margin:10px 0 6px">Claude Code (local, stdio)</div>
      <div class="code-block" onclick="copyCode(this)">
        <code>{escape(claude_stdio)}</code>
        <button type="button" class="copy-btn" aria-label="Copy">&#128203;</button>
      </div>
    </div>

    <div style="border-top:1px solid var(--border);margin:14px 0"></div>

    <h2 style="font-size:15px;margin:0 0 8px">Webhooks</h2>
    <label>Webhook URL</label>
    <input type="url" name="webhook.url" value="{webhook_url}" placeholder="http://gateway:18789/hooks/agent" style="width:100%;padding:10px;border:1px solid var(--border-input);border-radius:6px;background:var(--bg-input);color:var(--text);font-size:13px">
    <label class="check-row" style="margin-top:8px">
      <input type="checkbox" name="webhook.enabled" value="true" {webhook_checked}>
      <span class="check-label">Enable outbound webhooks</span>
    </label>
  </div>
</details>

<!-- Web Server -->
<details>
  <summary>
    <span class="section-icon">&#9881;</span><span class="section-title">Web Server</span>
  </summary>
  <div class="card-body">
    <div style="font-size:14px;font-weight:500;color:var(--text-label);margin-bottom:10px">Theme</div>
    <div style="display:flex;gap:8px">
      <button type="button" id="theme-dark-btn" class="btn-secondary" style="flex:1" onclick="setTheme('dark')">Dark</button>
      <button type="button" id="theme-light-btn" class="btn-secondary" style="flex:1" onclick="setTheme('light')">Light</button>
    </div>
    <div class="hint">Choose dark or light appearance for this settings page</div>

    <div style="border-top:1px solid var(--border);margin:16px 0"></div>

    <label class="check-row">
      <input type="checkbox" id="auto-refresh-toggle" onchange="toggleAutoRefresh(this.checked)">
      <span class="check-label">Auto-refresh status</span>
    </label>
    <div class="hint">Periodically check device connectivity (every 30s)</div>
  </div>
</details>

<!-- Updates -->
<details>
  <summary>
    <span class="section-icon">&#128259;</span><span class="section-title">Updates</span>
  </summary>
  <div class="card-body">
    <button type="button" onclick="checkUpdate()" id="update-check-btn" class="btn-secondary">Check for Updates</button>
    <div id="update-result"></div>
  </div>
</details>

<!-- Reboot -->
<details>
  <summary>
    <span class="section-icon">&#x1f504;</span><span class="section-title" style="color:var(--warning)">Reboot</span>
  </summary>
  <div class="card-body">
    <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">Restart the device. The display will go dark for ~30 seconds.</p>
    <button type="button" onclick="rebootDevice()" class="btn-secondary" style="background:color-mix(in srgb, var(--warning) 12%, transparent);color:var(--warning);border-color:color-mix(in srgb, var(--warning) 25%, transparent)">Reboot Device</button>
    <div id="reboot-status"></div>
  </div>
</details>

<!-- Reset -->
<details>
  <summary>
    <span class="section-icon">&#9888;</span><span class="section-title" style="color:var(--danger)">Reset</span>
  </summary>
  <div class="card-body">
    <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">Remove all custom settings. Gateway tokens and API keys will be cleared.</p>
    <button type="button" onclick="resetSettings()" class="btn-destructive">Reset All to Defaults</button>
    <div id="reset-status"></div>
  </div>
</details>

</form>

<!-- Sticky save bar -->
<div class="save-bar">
  <div class="save-bar-inner">
    <button type="button" onclick="document.getElementById('f').requestSubmit()" class="btn-primary">Save Settings</button>
    <div id="status" class="status" style="display:none"></div>
  </div>
</div>

<script>
/* ── Theme toggle ──────────────────────────────────────────────── */
function applyTheme(t) {{
  document.documentElement.setAttribute('data-theme', t);
  var btn = document.getElementById('theme-btn');
  if (btn) btn.innerHTML = t === 'dark' ? '&#9728;&#65039;' : '&#127769;';
  var darkBtn = document.getElementById('theme-dark-btn');
  var lightBtn = document.getElementById('theme-light-btn');
  if (darkBtn && lightBtn) {{
    darkBtn.style.borderColor = t === 'dark' ? 'var(--accent)' : 'var(--btn-secondary-border)';
    darkBtn.style.color = t === 'dark' ? 'var(--accent)' : 'var(--text)';
    lightBtn.style.borderColor = t === 'light' ? 'var(--accent)' : 'var(--btn-secondary-border)';
    lightBtn.style.color = t === 'light' ? 'var(--accent)' : 'var(--text)';
  }}
}}
function toggleTheme() {{
  var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  setTheme(next);
}}
function setTheme(t) {{
  localStorage.setItem('voxel-theme', t);
  applyTheme(t);
}}
applyTheme(localStorage.getItem('voxel-theme') || 'dark');

/* ── Connection indicator ──────────────────────────────────────── */
var _autoRefreshTimer = null;
async function checkConnection() {{
  var dot = document.getElementById('conn-dot');
  var txt = document.getElementById('conn-text');
  try {{
    var r = await fetch('/api/health', {{method: 'GET'}});
    var d = await r.json();
    if (d.ok) {{
      dot.classList.add('ok');
      txt.textContent = 'Connected';
    }} else {{
      dot.classList.remove('ok');
      txt.textContent = 'Error';
    }}
  }} catch(e) {{
    dot.classList.remove('ok');
    txt.textContent = 'Offline';
  }}
}}
checkConnection();

function toggleAutoRefresh(on) {{
  if (_autoRefreshTimer) {{ clearInterval(_autoRefreshTimer); _autoRefreshTimer = null; }}
  if (on) {{
    _autoRefreshTimer = setInterval(checkConnection, 30000);
    localStorage.setItem('voxel-auto-refresh', '1');
  }} else {{
    localStorage.setItem('voxel-auto-refresh', '0');
  }}
}}
(function() {{
  var pref = localStorage.getItem('voxel-auto-refresh');
  var cb = document.getElementById('auto-refresh-toggle');
  if (pref === '1' && cb) {{
    cb.checked = true;
    toggleAutoRefresh(true);
  }}
}})();

/* ── Password show/hide toggle ──────────────────────────────────── */
function togglePw(btn) {{
  const input = btn.parentElement.querySelector('input');
  input.classList.toggle('revealed');
  btn.innerHTML = input.classList.contains('revealed') ? '&#128064;' : '&#128065;';
}}

/* ── Copy code block ────────────────────────────────────────────── */
function copyCode(block) {{
  const code = block.querySelector('code').textContent;
  const btn = block.querySelector('.copy-btn');
  // Use textarea fallback — navigator.clipboard requires HTTPS
  const ta = document.createElement('textarea');
  ta.value = code; ta.style.cssText = 'position:fixed;opacity:0;left:-9999px';
  document.body.appendChild(ta); ta.select();
  let ok = false;
  try {{ ok = document.execCommand('copy'); }} catch(e) {{}}
  document.body.removeChild(ta);
  if (ok) {{
    btn.classList.add('copied');
    btn.innerHTML = '&#10003;';
    showToast('Copied to clipboard');
    setTimeout(() => {{ btn.classList.remove('copied'); btn.innerHTML = '&#128203;'; }}, 1500);
  }} else {{
    showToast('Copy failed — select and copy manually', 'err');
  }}
}}

function showToast(msg, cls) {{
  let t = document.getElementById('toast');
  if (!t) {{
    t = document.createElement('div');
    t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);padding:10px 20px;border-radius:8px;font-size:13px;z-index:999;transition:opacity 0.3s ease;pointer-events:none';
    document.body.appendChild(t);
  }}
  var cs = getComputedStyle(document.documentElement);
  if (cls === 'err') {{
    t.style.background = cs.getPropertyValue('--danger-bg');
    t.style.color = cs.getPropertyValue('--danger');
    t.style.border = '1px solid ' + cs.getPropertyValue('--danger-border');
  }} else {{
    t.style.background = cs.getPropertyValue('--success-bg');
    t.style.color = cs.getPropertyValue('--success');
    t.style.border = '1px solid ' + cs.getPropertyValue('--success-border');
  }}
  t.textContent = msg;
  t.style.opacity = '1';
  setTimeout(() => {{ t.style.opacity = '0'; }}, 2500);
}}

/* ── Auto-dismiss status messages ───────────────────────────────── */
function showStatus(el, cls, msg, autoDismiss) {{
  el.className = 'status ' + cls;
  el.textContent = msg;
  el.style.display = 'block';
  el.style.opacity = '1';
  el.style.transition = 'opacity 0.3s ease';
  if (autoDismiss !== false) {{
    setTimeout(() => {{
      el.style.opacity = '0';
      setTimeout(() => {{ el.style.display = 'none'; }}, 300);
    }}, 4000);
  }}
}}

/* ── Reboot ─────────────────────────────────────────────────────── */
async function rebootDevice() {{
  if (!confirm('Reboot the device? The display will go dark for ~30 seconds.')) return;
  const rs = document.getElementById('reboot-status');
  showStatus(rs, 'ok', 'Rebooting...', false);
  try {{
    const r = await fetch('/api/reboot', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: '{{}}'
    }});
    const d = await r.json();
    if (d.ok) {{ showStatus(rs, 'ok', 'Reboot command sent. Device will restart shortly.', false); }}
    else {{ showStatus(rs, 'err', 'Error: ' + (d.error || 'unknown')); }}
  }} catch(e) {{ showStatus(rs, 'err', e.message); }}
}}

/* ── Reset ──────────────────────────────────────────────────────── */
async function resetSettings() {{
  if (!confirm('Reset all settings to defaults? This will clear API keys and tokens.')) return;
  const rs = document.getElementById('reset-status');
  showStatus(rs, 'ok', 'Resetting...', false);
  try {{
    const r = await fetch('/api/settings/reset', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{sections: ['all']}})
    }});
    const d = await r.json();
    if (d.ok) {{ showStatus(rs, 'ok', 'Reset complete. Reloading...', false); setTimeout(() => location.reload(), 1000); }}
    else {{ showStatus(rs, 'err', 'Error: ' + (d.error || 'unknown')); }}
  }} catch(e) {{ showStatus(rs, 'err', e.message); }}
}}

async function resetSection(section) {{
  if (!confirm('Reset ' + section + ' settings to defaults?')) return;
  try {{
    const r = await fetch('/api/settings/reset', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{sections: [section]}})
    }});
    const d = await r.json();
    if (d.ok) {{ location.reload(); }}
    else {{ alert('Error: ' + (d.error || 'unknown')); }}
  }} catch(e) {{ alert(e.message); }}
}}

/* ── Updates ────────────────────────────────────────────────────── */
async function checkUpdate() {{
  const btn = document.getElementById('update-check-btn');
  const div = document.getElementById('update-result');
  btn.textContent = 'Checking...'; btn.disabled = true;
  try {{
    const r = await fetch('/api/update/check');
    const d = await r.json();
    if (d.error) {{
      div.innerHTML = '<div class="status err" style="display:block">Error: ' + d.error + '</div>';
    }} else if (d.available) {{
      let html = '<div class="status ok" style="display:block">Current: ' + d.current + ' &rarr; Latest: ' + d.latest + '<br>' + d.behind + ' commit(s) behind</div>';
      if (d.changelog && d.changelog.length) {{
        html += '<div style="margin:8px 0;font-size:13px;color:var(--text-label)">';
        d.changelog.forEach(line => {{ html += '<div style="margin:2px 0;font-family:monospace;font-size:12px">' + line + '</div>'; }});
        html += '</div>';
      }}
      html += '<button type="button" onclick="installUpdate()" id="update-install-btn" class="btn-secondary mt-2" style="background:color-mix(in srgb, var(--warning) 12%, transparent);color:var(--warning);border-color:color-mix(in srgb, var(--warning) 25%, transparent)">Install Update</button>';
      div.innerHTML = html;
    }} else {{
      div.innerHTML = '<div class="status ok" style="display:block">Up to date (commit: ' + d.current + ')</div>';
    }}
  }} catch(e) {{ div.innerHTML = '<div class="status err" style="display:block">' + e.message + '</div>'; }}
  finally {{ btn.textContent = 'Check for Updates'; btn.disabled = false; }}
}}

async function installUpdate() {{
  if (!confirm('Install update? Services will need to be restarted after.')) return;
  const btn = document.getElementById('update-install-btn');
  const div = document.getElementById('update-result');
  btn.textContent = 'Installing...'; btn.disabled = true;
  try {{
    const r = await fetch('/api/update/install', {{ method: 'POST' }});
    const d = await r.json();
    if (d.ok) {{
      div.innerHTML = '<div class="status ok" style="display:block">Updated: ' + d.old_version + ' &rarr; ' + d.new_version + '<br>Restart services to apply.</div>';
    }} else {{
      div.innerHTML = '<div class="status err" style="display:block">Update failed: ' + (d.error || 'unknown') + '</div>';
    }}
  }} catch(e) {{ div.innerHTML = '<div class="status err" style="display:block">' + e.message + '</div>'; }}
}}

/* ── Dev pairing ────────────────────────────────────────────────── */
async function devPairBrowser() {{
  const ps = document.getElementById('pair-status');
  showStatus(ps, 'ok', 'Enabling dev mode...', false);
  try {{
    const r = await fetch('/api/dev/pair', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{pin: '{escape(get_access_pin())}', dev_host: 'browser'}})
    }});
    const d = await r.json();
    if (d.ok) {{
      showStatus(ps, 'ok', 'Dev mode enabled! SSH: ' + d.user + '@' + d.host);
      const cb = document.querySelector('input[name="dev.enabled"]');
      if (cb) cb.checked = true;
    }} else {{
      showStatus(ps, 'err', d.error || 'Failed');
    }}
  }} catch(e) {{ showStatus(ps, 'err', e.message); }}
}}

/* ── Save form ──────────────────────────────────────────────────── */
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {{}};
  for (const [k, v] of fd.entries()) body[k] = v;
  const s = document.getElementById('status');
  try {{
    const r = await fetch('/save', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(body) }});
    const d = await r.json();
    if (d.ok) {{
      showToast('Settings saved! Restart services to apply.');
      showStatus(s, 'ok', 'Settings saved! Restart services to apply.');
    }}
    else {{ showStatus(s, 'err', 'Error: ' + (d.error || 'unknown')); showToast('Error saving settings', 'err'); }}
  }} catch(e) {{ showStatus(s, 'err', e.message); showToast('Error: ' + e.message, 'err'); }}
}});

/* ── WiFi ───────────────────────────────────────────────────────── */
let selectedSSID = '';

function signalBars(signal, isActive) {{
  const levels = [signal > 10, signal > 30, signal > 55, signal > 75];
  const color = isActive ? 'active' : 'active';
  return '<span class="wifi-signal">' +
    levels.map((on, i) => '<span class="bar' + (on ? ' active' : '') + '"></span>').join('') +
    '</span>';
}}

async function wifiScan() {{
  const btn = document.getElementById('wifi-scan');
  const div = document.getElementById('wifi-networks');
  btn.textContent = 'Scanning...'; btn.disabled = true;
  try {{
    const r = await fetch('/wifi/scan');
    const nets = await r.json();
    if (!nets.length) {{ div.innerHTML = '<span style="color:var(--text-muted)">No networks found</span>'; return; }}
    div.innerHTML = nets.map(n => {{
      const sec = n.security !== '--' ? '<span style="font-size:11px;margin-left:4px">&#128274;</span>' : '';
      const act = n.connected ? ' active' : '';
      const safe = n.ssid.replace(/"/g,'&quot;');
      return '<div class="wifi-net' + act + '" onclick="selectNet(&quot;' + safe + '&quot;)">' +
        '<div><div class="ssid">' + n.ssid + '</div><div class="meta">' + n.security + '</div></div>' +
        '<div style="display:flex;align-items:center">' + signalBars(n.signal, n.connected) + '<span class="meta">' + n.signal + '%</span>' + sec + '</div></div>';
    }}).join('');
  }} catch(e) {{ div.innerHTML = '<span style="color:var(--danger)">Scan failed: '+e.message+'</span>'; }}
  finally {{ btn.textContent = 'Scan Networks'; btn.disabled = false; }}
}}

function selectNet(ssid) {{
  selectedSSID = ssid;
  document.getElementById('wifi-selected-ssid').textContent = ssid;
  document.getElementById('wifi-connect-form').style.display = 'block';
  document.getElementById('wifi-pass').value = '';
  document.getElementById('wifi-pass').focus();
}}

async function wifiConnect() {{
  if (!selectedSSID) return;
  const pass = document.getElementById('wifi-pass').value;
  const ws = document.getElementById('wifi-status');
  showStatus(ws, 'ok', 'Connecting to ' + selectedSSID + '...', false);
  try {{
    const r = await fetch('/wifi/connect', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ssid: selectedSSID, password: pass}})
    }});
    const d = await r.json();
    if (d.ok) {{
      showStatus(ws, 'ok', 'Connected! Page may reload on new IP.', false);
      setTimeout(() => location.reload(), 3000);
    }} else {{
      showStatus(ws, 'err', 'Failed: ' + (d.error || 'unknown'));
    }}
  }} catch(e) {{
    showStatus(ws, 'err', 'Connection lost — if WiFi changed, reconnect to new network and refresh.', false);
  }}
}}

/* ── Integration: MCP toggle ──────────────────────────────────── */
function toggleMcp(enabled) {{
  var info = document.getElementById('mcp-connect-info');
  if (info) info.style.display = enabled ? '' : 'none';
  fetch('/api/config', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{section: 'mcp', key: 'enabled', value: enabled}})
  }});
  if (enabled) {{
    fetch('/api/mcp/start', {{method: 'POST'}});
  }} else {{
    fetch('/api/mcp/stop', {{method: 'POST'}});
  }}
}}

/* ── Integration: Agent tab switch ────────────────────────────── */
function showAgentTab(tab, btn) {{
  document.getElementById('tab-human').style.display = tab === 'human' ? '' : 'none';
  document.getElementById('tab-agent').style.display = tab === 'agent' ? '' : 'none';
  document.querySelectorAll('.agent-tab').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
}}

/* ── Integration: click-to-copy code blocks ───────────────────── */
document.querySelectorAll('.code-block').forEach(function(el) {{
  el.addEventListener('click', function() {{
    var text = el.textContent.trim();
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try {{ ok = document.execCommand('copy'); }} catch(e) {{}}
    document.body.removeChild(ta);
    if (ok) {{
      el.style.borderColor = 'var(--accent)';
      showToast('Copied to clipboard');
      setTimeout(function() {{ el.style.borderColor = ''; }}, 1000);
    }}
  }});
}});
</script>
</body>
</html>"""


def _get_chat_client():
    """Get or create the lazy OpenClawClient for web chat."""
    global _chat_client
    if _chat_client is not None:
        return _chat_client
    try:
        settings = _load_settings()
        gw = settings.get("gateway", {})
        url = gw.get("url", "")
        token = gw.get("token", "")
        if not url or not token:
            return None
        from core.gateway import OpenClawClient
        agent = _display_state.agent if _display_state else gw.get("default_agent", "daemon")
        # Load system context if enabled
        char_cfg = settings.get("character", {})
        context = ""
        if char_cfg.get("system_context_enabled", True):
            context = char_cfg.get("system_context", "").strip()
        _chat_client = OpenClawClient(url, token, agent, system_context=context)
        return _chat_client
    except Exception as e:
        log.error(f"Failed to create chat client: {e}")
        return None


def _build_diagnostics_html() -> str:
    """Build the hardware diagnostics page HTML."""
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Voxel — Diagnostics</title>
{_FAVICON_LINK}
<style>
  :root, [data-theme="dark"] {{
    --bg: #0a0a0f; --bg-card: #12121a; --bg-input: #0e0e16;
    --bg-hover: #16161e;
    --border: #1e1e30; --border-input: #282840;
    --text: #e0e0e8; --text-dim: #666680; --text-muted: #555570;
    --text-label: #b0b0c4;
    --accent: #00d4d2; --accent-hover: #00e8e6; --accent-active: #00b0ae;
    --accent-text: #00d4d2;
    --danger: #ff5c5c; --danger-bg: #200a0a;
    --success: #34d381; --success-bg: #0a201a;
    --warning: #e8b840; --warning-bg: #201a0a;
    --scrollbar-thumb: #282840; --logo-body: #1a1a2e;
  }}
  [data-theme="light"] {{
    --bg: #f5f5f7; --bg-card: #ffffff; --bg-input: #f8f8fc;
    --bg-hover: #f0f0f5;
    --border: #e0e0e8; --border-input: #d0d0dc;
    --text: #1a1a2e; --text-dim: #666680; --text-muted: #888898;
    --text-label: #555570;
    --accent: #008886; --accent-hover: #00a5a3; --accent-active: #007070;
    --accent-text: #007070;
    --danger: #dc3545; --danger-bg: #fff0f0;
    --success: #28a745; --success-bg: #f0fff4;
    --warning: #c08800; --warning-bg: #fffbf0;
    --scrollbar-thumb: #c0c0cc; --logo-body: #1a1a2e;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 16px 16px 80px; max-width: 520px; margin: 0 auto;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
    transition: background 0.2s ease, color 0.2s ease;
  }}
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 3px; }}
  html {{ scrollbar-color: var(--scrollbar-thumb) var(--bg); }}

  .page-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
  .logo {{ width: 40px; height: 40px; flex-shrink: 0; }}
  .logo svg {{ width: 100%; height: 100%; }}
  .logo svg rect.logo-bg {{ fill: var(--logo-body); transition: fill 0.2s ease; }}
  h1 {{ color: var(--accent); font-size: 22px; }}
  .subtitle {{ font-size: 13px; color: var(--text-dim); margin-bottom: 16px; }}
  .header-actions {{ display: flex; align-items: center; gap: 6px; margin-left: auto; }}
  .nav-link {{
    color: var(--text-dim); font-size: 13px; text-decoration: none;
    padding: 6px 10px; border-radius: 6px;
    transition: color 0.15s ease, background 0.15s ease;
  }}
  .nav-link:hover {{ color: var(--text); background: var(--bg-card); }}
  .theme-toggle {{
    background: none; border: 1px solid var(--border);
    color: var(--text-dim); cursor: pointer; padding: 5px 8px;
    border-radius: 6px; font-size: 15px; min-height: auto;
    width: auto; margin: 0; line-height: 1;
    transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
  }}
  .theme-toggle:hover {{ color: var(--text); background: var(--bg-card); }}

  .card {{
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; margin-bottom: 12px;
    transition: background 0.2s ease, border-color 0.2s ease;
  }}
  .card h2 {{ color: var(--accent); font-size: 15px; margin-bottom: 12px; }}

  .check-row {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid var(--border);
    font-size: 14px;
  }}
  .check-row:last-child {{ border-bottom: none; }}
  .check-label {{ color: var(--text-label); }}
  .check-value {{ font-weight: 500; display: flex; align-items: center; gap: 6px; }}
  .check-ok {{ color: var(--success); }}
  .check-warn {{ color: var(--warning); }}
  .check-err {{ color: var(--danger); }}
  .check-na {{ color: var(--text-muted); }}
  .check-icon {{ font-size: 16px; }}
  .loading {{ color: var(--text-muted); font-style: italic; }}

  .test-btn {{
    background: var(--accent); color: var(--bg); border: none;
    padding: 12px 24px; border-radius: 8px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    min-height: 44px; transition: background 0.15s ease, opacity 0.15s ease;
  }}
  .test-btn:hover {{ background: var(--accent-hover); }}
  .test-btn:active {{ background: var(--accent-active); }}
  .test-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}

  .test-result {{
    margin-top: 10px; font-size: 13px; line-height: 1.5;
    padding: 10px 12px; border-radius: 8px; display: none;
  }}
  .test-result.ok {{ display: block; background: var(--success-bg); color: var(--success); border: 1px solid var(--success); }}
  .test-result.err {{ display: block; background: var(--danger-bg); color: var(--danger); border: 1px solid var(--danger); }}
  .test-result.running {{ display: block; background: var(--bg-input); color: var(--accent); border: 1px solid var(--border); }}

  .level-bar-wrap {{
    margin-top: 8px; height: 8px; background: var(--bg-input);
    border-radius: 4px; overflow: hidden; border: 1px solid var(--border);
  }}
  .level-bar {{
    height: 100%; background: var(--accent); border-radius: 4px;
    transition: width 0.3s ease; width: 0%;
  }}
</style>
</head>
<body>

<div class="page-header">
  <div class="logo">{_LOGO_SVG}</div>
  <h1>Diagnostics</h1>
  <div class="header-actions">
    <a href="/" class="nav-link">Settings</a>
    <a href="/chat" class="nav-link">Chat</a>
    <button type="button" class="theme-toggle" onclick="toggleTheme()" id="theme-btn" aria-label="Toggle theme"></button>
  </div>
</div>
<div class="subtitle">Hardware tests and system health</div>

<!-- System Health -->
<div class="card">
  <h2>System Health</h2>
  <div id="health-checks">
    <div class="loading">Loading system info...</div>
  </div>
</div>

<!-- Speaker Test -->
<div class="card">
  <h2>Speaker Test</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
    Plays a 440Hz test tone (0.5s) through the speaker.
  </p>
  <button class="test-btn" id="speaker-btn" onclick="testSpeaker()">Test Speaker</button>
  <div class="test-result" id="speaker-result"></div>
</div>

<!-- Microphone Test -->
<div class="card">
  <h2>Microphone Test</h2>
  <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
    Records 2 seconds from the microphone and analyzes levels.
  </p>
  <button class="test-btn" id="mic-btn" onclick="testMic()">Test Microphone</button>
  <div class="test-result" id="mic-result"></div>
  <div class="level-bar-wrap" id="mic-level-wrap" style="display:none">
    <div class="level-bar" id="mic-level"></div>
  </div>
</div>

<script>
/* Theme */
function applyTheme(t) {{
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-btn').textContent = t === 'dark' ? '\\u2600' : '\\u263D';
}}
function toggleTheme() {{
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  localStorage.setItem('voxel-theme', next);
  applyTheme(next);
}}
applyTheme(localStorage.getItem('voxel-theme') || 'dark');

/* System health */
async function loadHealth() {{
  const el = document.getElementById('health-checks');
  try {{
    const r = await fetch('/api/diagnostics/system');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    let html = '';

    function row(label, value, status) {{
      const cls = status === 'ok' ? 'check-ok' : status === 'warn' ? 'check-warn' : status === 'err' ? 'check-err' : 'check-na';
      const icon = status === 'ok' ? '\\u2713' : status === 'warn' ? '!' : status === 'err' ? '\\u2717' : '\\u2014';
      return '<div class="check-row"><span class="check-label">' + label + '</span>'
        + '<span class="check-value ' + cls + '"><span class="check-icon">' + icon + '</span> ' + value + '</span></div>';
    }}

    html += row('Platform', d.platform || 'Unknown', d.is_pi ? 'ok' : 'ok');
    html += row('Audio Backend', d.audio_backend || 'None', d.audio_backend !== 'none' ? 'ok' : 'err');
    html += row('WM8960 (Whisplay Audio)', d.wm8960_detected ? 'Detected' : 'Not detected', d.wm8960_detected ? 'ok' : (d.is_pi ? 'err' : 'na'));
    html += row('Display Backend', d.display_backend || 'Unknown', 'ok');
    html += row('Gateway URL', d.gateway_configured ? 'Configured' : 'Not set', d.gateway_configured ? 'ok' : 'warn');
    html += row('Gateway Token', d.gateway_token_set ? 'Set' : 'Not set', d.gateway_token_set ? 'ok' : 'warn');
    html += row('OpenAI API Key', d.openai_key_set ? 'Set' : 'Not set', d.openai_key_set ? 'ok' : 'warn');
    html += row('Battery', d.battery !== null ? d.battery + '%' : 'N/A', d.battery !== null ? (d.battery > 20 ? 'ok' : 'warn') : 'na');
    html += row('WiFi', d.wifi_connected ? ('Connected: ' + (d.wifi_ssid || '')) : 'Not connected', d.wifi_connected ? 'ok' : 'warn');

    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = '<div class="check-row"><span class="check-label">Error</span><span class="check-value check-err">' + e.message + '</span></div>';
  }}
}}

/* Speaker test */
async function testSpeaker() {{
  const btn = document.getElementById('speaker-btn');
  const res = document.getElementById('speaker-result');
  btn.disabled = true;
  btn.textContent = 'Playing...';
  res.className = 'test-result running';
  res.style.display = 'block';
  res.textContent = 'Playing 440Hz tone...';
  try {{
    const r = await fetch('/api/diagnostics/speaker-test', {{ method: 'POST' }});
    const d = await r.json();
    if (d.ok) {{
      res.className = 'test-result ok';
      res.textContent = 'Speaker OK — played ' + d.duration_ms + 'ms tone';
    }} else {{
      res.className = 'test-result err';
      res.textContent = 'Failed: ' + (d.error || 'unknown error');
    }}
  }} catch(e) {{
    res.className = 'test-result err';
    res.textContent = 'Error: ' + e.message;
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Test Speaker';
  }}
}}

/* Mic test */
async function testMic() {{
  const btn = document.getElementById('mic-btn');
  const res = document.getElementById('mic-result');
  const levelWrap = document.getElementById('mic-level-wrap');
  const levelBar = document.getElementById('mic-level');
  btn.disabled = true;
  btn.textContent = 'Recording...';
  res.className = 'test-result running';
  res.style.display = 'block';
  res.textContent = 'Recording 2 seconds...';
  levelWrap.style.display = 'none';
  try {{
    const r = await fetch('/api/diagnostics/mic-test', {{ method: 'POST' }});
    const d = await r.json();
    if (d.ok) {{
      res.className = 'test-result ok';
      res.innerHTML = 'Microphone OK<br>'
        + 'RMS: ' + d.rms.toFixed(4) + ' &middot; Peak: ' + d.peak.toFixed(4) + '<br>'
        + 'Noise floor: ' + d.noise_floor + ' &middot; ' + d.bytes + ' bytes recorded';
      levelWrap.style.display = 'block';
      const pct = Math.min(d.peak * 100 / 0.5, 100);
      levelBar.style.width = pct + '%';
      levelBar.style.background = pct > 80 ? 'var(--danger)' : pct > 40 ? 'var(--warning)' : 'var(--accent)';
    }} else {{
      res.className = 'test-result err';
      res.textContent = 'Failed: ' + (d.error || 'unknown error');
    }}
  }} catch(e) {{
    res.className = 'test-result err';
    res.textContent = 'Error: ' + e.message;
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Test Microphone';
  }}
}}

loadHealth();
</script>
</body>
</html>"""


def _build_chat_html() -> str:
    """Build the chat page HTML."""
    settings = _load_settings()
    agents = settings.get("agents", [])
    current_agent = _display_state.agent if _display_state else settings.get("gateway", {}).get("default_agent", "daemon")

    agent_options = ""
    for a in agents:
        sel = "selected" if a["id"] == current_agent else ""
        name = escape(a.get("name", a["id"]))
        agent_options += f'<option value="{a["id"]}" {sel}>{name}</option>\n'

    # Pre-load existing transcripts
    messages_json = "[]"
    if _display_state and _display_state.transcripts:
        msgs = [{"role": t.role, "text": t.text} for t in _display_state.transcripts]
        messages_json = json.dumps(msgs)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Voxel — Chat</title>
{_FAVICON_LINK}
<style>
  :root, [data-theme="dark"] {{
    --bg: #0a0a0f; --bg-card: #12121a; --bg-input: #0e0e16;
    --bg-hover: #16161e;
    --border: #1e1e30; --border-input: #282840;
    --text: #e0e0e8; --text-dim: #666680;
    --accent: #00d4d2; --accent-hover: #00e8e6; --accent-active: #00b0ae;
    --accent-text: #00d4d2;
    --danger: #ff5c5c; --success: #34d381;
    --scrollbar-thumb: #282840; --logo-body: #1a1a2e;
    --msg-user-bg: #00d4d2; --msg-user-text: #0a0a0f; --msg-user-name: #0a6060;
    --msg-agent-bg: #1e1e30; --msg-agent-text: #e0e0e8;
    --tool-bg: rgba(128, 90, 213, 0.12); --tool-border: rgba(128, 90, 213, 0.2);
    --tool-text: #a78bda;
    --empty-text: #444460;
    --error-bg: rgba(255,60,60,0.1); --error-border: rgba(255,60,60,0.2);
  }}
  [data-theme="light"] {{
    --bg: #f5f5f7; --bg-card: #ffffff; --bg-input: #f8f8fc;
    --bg-hover: #f0f0f5;
    --border: #e0e0e8; --border-input: #d0d0dc;
    --text: #1a1a2e; --text-dim: #666680;
    --accent: #008886; --accent-hover: #00a5a3; --accent-active: #007070;
    --accent-text: #007070;
    --danger: #dc3545; --success: #28a745;
    --scrollbar-thumb: #c0c0cc; --logo-body: #1a1a2e;
    --msg-user-bg: #008886; --msg-user-text: #ffffff; --msg-user-name: #c0f0f0;
    --msg-agent-bg: #e8e8f0; --msg-agent-text: #1a1a2e;
    --tool-bg: rgba(128, 90, 213, 0.08); --tool-border: rgba(128, 90, 213, 0.15);
    --tool-text: #7c5db8;
    --empty-text: #888898;
    --error-bg: rgba(220,53,69,0.08); --error-border: rgba(220,53,69,0.15);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; overflow: hidden; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; flex-direction: column;
    -webkit-font-smoothing: antialiased;
    transition: background 0.2s ease, color 0.2s ease;
  }}

  /* Scrollbar */
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 3px; }}
  html {{ scrollbar-color: var(--scrollbar-thumb) var(--bg); }}

  /* Header */
  .header {{
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; background: var(--bg-card);
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }}
  .header .logo {{
    width: 32px; height: 32px; flex-shrink: 0;
  }}
  .header .logo svg {{ width: 100%; height: 100%; }}
  .header .logo svg rect.logo-bg {{ fill: var(--logo-body); transition: fill 0.2s ease; }}
  .header-title {{
    display: flex; align-items: center; gap: 8px; flex: 1;
  }}
  .header-title h1 {{ color: var(--accent); font-size: 18px; }}
  .theme-toggle {{
    background: none; border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-dim); cursor: pointer; padding: 4px 8px; font-size: 14px;
  }}
  .theme-toggle:hover {{ color: var(--text); background: var(--bg-card); }}
  .conn-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--danger); flex-shrink: 0;
    transition: background 0.3s ease;
  }}
  .conn-dot.connected {{ background: var(--accent); }}
  .header-mood {{
    font-size: 11px; color: var(--text-dim); white-space: nowrap;
    max-width: 80px; overflow: hidden; text-overflow: ellipsis;
  }}
  .nav-link {{
    color: var(--text-dim); font-size: 13px; text-decoration: none;
    padding: 6px 10px; border-radius: 6px;
    transition: color 0.15s ease, background 0.15s ease;
  }}
  .nav-link:hover {{ color: var(--text); background: var(--bg-hover); }}

  /* Agent selector */
  .agent-bar {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 16px; background: var(--bg-input);
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }}
  .agent-bar label {{ font-size: 13px; color: var(--text-dim); white-space: nowrap; }}
  .agent-bar select {{
    flex: 1; padding: 8px 10px; min-height: 36px;
    border: 1px solid var(--border-input); border-radius: 6px;
    background: var(--bg-card); color: var(--text);
    font-size: 14px; font-family: inherit;
  }}
  .agent-bar select:focus {{ outline: none; border-color: var(--accent); }}

  /* Messages area */
  .messages {{
    flex: 1; overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column; gap: 8px;
    scroll-behavior: smooth; position: relative;
  }}
  .msg {{
    max-width: 85%; padding: 10px 14px; border-radius: 12px;
    font-size: 14px; line-height: 1.5; word-wrap: break-word;
    white-space: pre-wrap; position: relative;
  }}
  .msg.user {{
    align-self: flex-end; background: var(--msg-user-bg); color: var(--msg-user-text);
    border-bottom-right-radius: 4px;
  }}
  .msg.assistant {{
    align-self: flex-start; background: var(--msg-agent-bg); color: var(--msg-agent-text);
    border-bottom-left-radius: 4px; padding-left: 22px;
  }}
  .msg .agent-dot {{
    position: absolute; left: 8px; top: 14px;
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
  }}
  .msg .agent-name {{
    font-size: 11px; font-weight: 600;
    margin-bottom: 2px; display: block;
  }}
  .msg.user .agent-name {{ color: var(--msg-user-name); }}
  .msg.assistant .agent-name {{ color: var(--accent-text); }}
  .msg-text {{ display: inline; }}
  .msg-time {{
    font-size: 11px; opacity: 0.4; margin-top: 4px; display: block;
  }}

  /* Streaming cursor */
  .streaming-cursor {{
    display: inline-block; width: 2px; height: 14px;
    background: var(--accent); margin-left: 2px;
    vertical-align: text-bottom;
    animation: cursorBlink 0.8s step-end infinite;
  }}
  @keyframes cursorBlink {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0; }}
  }}

  /* Tool call indicators */
  .tool-call {{
    align-self: flex-start; max-width: 85%;
    padding: 6px 12px; border-radius: 8px;
    background: var(--tool-bg);
    border: 1px solid var(--tool-border);
    font-size: 12px; color: var(--tool-text);
    display: flex; align-items: center; gap: 6px;
  }}
  .tool-call.running {{
    animation: toolPulse 2s ease-in-out infinite;
  }}
  .tool-call.done {{ opacity: 0.6; }}
  .tool-call .tool-icon {{ flex-shrink: 0; }}
  .tool-call .tool-name {{ font-weight: 500; }}
  .tool-call .tool-check {{ color: var(--success); margin-left: 2px; }}
  @keyframes toolPulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
  }}

  /* Typing / thinking indicator */
  .typing {{
    align-self: flex-start; padding: 10px 14px;
    background: var(--msg-agent-bg); border-radius: 12px;
    border-bottom-left-radius: 4px; display: none;
    margin: 0 16px 8px;
  }}
  .typing.visible {{ display: block; }}
  .typing-dots {{ display: flex; gap: 4px; align-items: center; }}
  .typing-dots span {{
    width: 6px; height: 6px; background: var(--text-dim); border-radius: 50%;
    animation: typingBounce 1.4s infinite both;
  }}
  .typing-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
  .typing-dots span:nth-child(3) {{ animation-delay: 0.4s; }}
  @keyframes typingBounce {{
    0%, 60%, 100% {{ transform: translateY(0); opacity: 0.4; }}
    30% {{ transform: translateY(-4px); opacity: 1; }}
  }}

  /* Empty state */
  .empty-state {{
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: var(--text-dim); font-size: 14px; text-align: center; padding: 32px;
    line-height: 1.6;
  }}
  .empty-state .empty-icon {{
    width: 48px; height: 48px; margin-bottom: 12px; opacity: 0.3;
  }}
  .empty-state .empty-icon svg {{ width: 100%; height: 100%; }}

  /* Floating emoji reaction */
  .emoji-reaction {{
    position: fixed; font-size: 32px;
    pointer-events: none; z-index: 100;
    animation: emojiFloat 2s ease-out forwards;
  }}
  @keyframes emojiFloat {{
    0% {{ transform: translateY(0) scale(0.5); opacity: 0; }}
    15% {{ transform: translateY(-10px) scale(1.2); opacity: 1; }}
    30% {{ transform: translateY(-20px) scale(1); opacity: 1; }}
    100% {{ transform: translateY(-80px) scale(0.8); opacity: 0; }}
  }}

  /* Input area */
  .input-bar {{
    display: flex; gap: 8px; padding: 12px 16px;
    background: var(--bg-card); border-top: 1px solid var(--border); flex-shrink: 0;
  }}
  .input-bar input {{
    flex: 1; padding: 12px; min-height: 48px;
    border: 1px solid var(--border-input); border-radius: 8px;
    background: var(--bg-input); color: var(--text);
    font-size: 15px; font-family: inherit;
  }}
  .input-bar input:focus {{ outline: none; border-color: var(--accent); }}
  .input-bar input:disabled {{ opacity: 0.5; }}
  .send-btn {{
    padding: 0 18px; min-height: 48px; border: none; border-radius: 8px;
    background: var(--accent); color: var(--msg-user-text); font-size: 16px; font-weight: 600;
    cursor: pointer; transition: background 0.15s ease, opacity 0.15s ease;
    white-space: nowrap;
  }}
  .send-btn:hover {{ background: var(--accent-hover); }}
  .send-btn:active {{ background: var(--accent-active); }}
  .send-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}

  /* Error banner */
  .error-banner {{
    padding: 10px 16px; background: var(--error-bg);
    color: var(--danger); font-size: 13px; text-align: center;
    border-bottom: 1px solid var(--error-border); display: none;
  }}
  .error-banner.visible {{ display: block; }}

  /* ── Mic button ───────────────────────────────────────────── */
  .mic-btn {{
    padding: 0 14px; min-height: 48px; min-width: 48px; border: none;
    border-radius: 8px; background: var(--bg-input);
    border: 1px solid var(--border-input); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s ease, border-color 0.15s ease;
    flex-shrink: 0;
  }}
  .mic-btn:hover {{ background: var(--bg-hover); border-color: var(--accent); }}
  .mic-btn:disabled {{ opacity: 0.3; cursor: not-allowed; }}
  .mic-btn svg {{ width: 20px; height: 20px; }}
  .mic-btn .mic-icon {{ fill: var(--text-dim); transition: fill 0.15s ease; }}
  .mic-btn.recording {{ background: rgba(0,212,210,0.1); border-color: var(--accent); }}
  .mic-btn.recording .mic-icon {{ fill: var(--accent); }}
  @keyframes micPulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
  }}
  .mic-btn.recording {{
    animation: micPulse 1.2s ease-in-out infinite;
  }}

  /* ── Speaker toggle ──────────────────────────────────────── */
  .speaker-toggle {{
    background: none; border: 1px solid var(--border); border-radius: 6px;
    cursor: pointer; padding: 4px 8px; display: flex; align-items: center;
    justify-content: center; min-width: 36px; min-height: 36px;
    transition: border-color 0.15s ease, background 0.15s ease;
  }}
  .speaker-toggle:hover {{ background: var(--bg-hover); }}
  .speaker-toggle svg {{ width: 18px; height: 18px; }}
  .speaker-toggle .speaker-icon {{ fill: var(--text-dim); transition: fill 0.15s ease; }}
  .speaker-toggle.active {{ border-color: var(--accent); }}
  .speaker-toggle.active .speaker-icon {{ fill: var(--accent); }}

  /* ── Listening indicator ─────────────────────────────────── */
  .listening-indicator {{
    display: none; align-items: center; gap: 6px;
    padding: 6px 14px; background: rgba(0,212,210,0.08);
    border-bottom: 1px solid rgba(0,212,210,0.15);
    font-size: 13px; color: var(--accent); flex-shrink: 0;
  }}
  .listening-indicator.visible {{ display: flex; }}
  .listening-indicator .pulse-dot {{
    width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
    animation: micPulse 1.2s ease-in-out infinite;
  }}

  /* ── Speaking highlight on message ───────────────────────── */
  .msg.speaking-now {{
    outline: 1px solid rgba(0,212,210,0.25);
    outline-offset: 2px;
  }}

  /* Mobile: keep input above virtual keyboard */
  @supports (height: 100dvh) {{
    html, body {{ height: 100dvh; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="logo">{_LOGO_SVG}</div>
  <div class="header-title">
    <h1>Chat</h1>
    <span class="conn-dot" id="conn-dot" title="Disconnected"></span>
    <span class="header-mood" id="header-mood"></span>
  </div>
  <button type="button" class="speaker-toggle" id="speaker-toggle" onclick="toggleSpeaker()" aria-label="Toggle voice output" title="Read responses aloud">
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path class="speaker-icon" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
  </button>
  <button type="button" class="theme-toggle" onclick="toggleTheme()" id="theme-btn" aria-label="Toggle theme"></button>
  <a href="/" class="nav-link">Settings</a>
  <a href="/diagnostics" class="nav-link">Diagnostics</a>
</div>

<div class="agent-bar">
  <label for="agent-select">Agent:</label>
  <select id="agent-select" onchange="switchAgent(this.value)">
    {agent_options}
  </select>
</div>

<div class="error-banner" id="error-banner"></div>
<div class="listening-indicator" id="listening-indicator">
  <span class="pulse-dot"></span>
  <span id="listening-text">Listening...</span>
</div>

<div class="messages" id="messages">
  <div class="empty-state" id="empty-state">
    <div class="empty-icon">{_LOGO_SVG}</div>
    Start a conversation...
  </div>
</div>

<div class="typing" id="typing">
  <div class="typing-dots">
    <span></span><span></span><span></span>
  </div>
</div>

<div class="input-bar">
  <input type="text" id="msg-input" placeholder="Type a message..." autocomplete="off"
         enterkeyhint="send">
  <button class="mic-btn" id="mic-btn" onclick="toggleMic()" aria-label="Voice input" title="Speak a message" style="display:none">
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path class="mic-icon" d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
  </button>
  <button class="send-btn" id="send-btn" onclick="sendMessage()">Send</button>
</div>

<script>
(function() {{
  var messagesEl = document.getElementById('messages');
  var emptyState = document.getElementById('empty-state');
  var typingEl = document.getElementById('typing');
  var inputEl = document.getElementById('msg-input');
  var sendBtn = document.getElementById('send-btn');
  var errorBanner = document.getElementById('error-banner');
  var connDot = document.getElementById('conn-dot');
  var headerMood = document.getElementById('header-mood');
  var sending = false;
  var wsConnected = false;
  var ws = null;
  var userScrolledUp = false;

  // Streaming partial message tracking
  var partialMsgEl = null;
  var partialTextEl = null;

  // Tool call DOM elements by name
  var toolCallEls = {{}};

  // Timestamps for relative time updates
  var msgTimestamps = [];

  // ── Auto-scroll detection ──
  messagesEl.addEventListener('scroll', function() {{
    var threshold = 60;
    var atBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < threshold;
    userScrolledUp = !atBottom;
  }});

  function scrollToBottom() {{
    if (!userScrolledUp) {{
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }}
  }}

  // ── Relative time formatting ──
  function relativeTime(ts) {{
    var diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 10) return 'now';
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return new Date(ts).toLocaleDateString([], {{month:'short', day:'numeric'}});
  }}

  // Update visible timestamps every 30s
  setInterval(function() {{
    for (var i = 0; i < msgTimestamps.length; i++) {{
      msgTimestamps[i].el.textContent = relativeTime(msgTimestamps[i].ts);
    }}
  }}, 30000);

  // ── HTML escaping ──
  function escapeHtml(s) {{
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }}

  // ── Get agent display name ──
  function getAgentName() {{
    var sel = document.getElementById('agent-select');
    return sel.options[sel.selectedIndex].text;
  }}

  // ── Add a complete message bubble ──
  function addMessage(role, text, scroll) {{
    if (emptyState) emptyState.style.display = 'none';
    var div = document.createElement('div');
    div.className = 'msg ' + role;
    var agentName = role === 'assistant' ? getAgentName() : 'You';
    var ts = Date.now();
    var dotHtml = role === 'assistant' ? '<span class="agent-dot"></span>' : '';
    div.innerHTML = dotHtml +
      '<span class="agent-name">' + escapeHtml(agentName) + '</span>' +
      '<span class="msg-text">' + escapeHtml(text) + '</span>' +
      '<span class="msg-time">' + relativeTime(ts) + '</span>';
    messagesEl.appendChild(div);
    var timeEl = div.querySelector('.msg-time');
    msgTimestamps.push({{ el: timeEl, ts: ts }});
    if (scroll !== false) scrollToBottom();
    // TTS: speak assistant messages aloud when enabled
    if (role === 'assistant' && text && typeof window._voxelSpeakText === 'function') {{
      window._voxelSpeakText(text, div);
    }}
    return div;
  }}

  // ── Streaming: create or update a partial assistant message ──
  function startOrUpdatePartial(text) {{
    if (emptyState) emptyState.style.display = 'none';
    if (!partialMsgEl) {{
      partialMsgEl = document.createElement('div');
      partialMsgEl.className = 'msg assistant';
      partialMsgEl.innerHTML =
        '<span class="agent-dot"></span>' +
        '<span class="agent-name">' + escapeHtml(getAgentName()) + '</span>' +
        '<span class="msg-text"></span>' +
        '<span class="streaming-cursor"></span>' +
        '<span class="msg-time"></span>';
      partialTextEl = partialMsgEl.querySelector('.msg-text');
      messagesEl.appendChild(partialMsgEl);
    }}
    partialTextEl.textContent = text;
    scrollToBottom();
  }}

  function finalizePartial(text) {{
    if (partialMsgEl) {{
      var cursor = partialMsgEl.querySelector('.streaming-cursor');
      if (cursor) cursor.remove();
      if (partialTextEl) partialTextEl.textContent = text;
      var ts = Date.now();
      var timeEl = partialMsgEl.querySelector('.msg-time');
      if (timeEl) {{
        timeEl.textContent = relativeTime(ts);
        msgTimestamps.push({{ el: timeEl, ts: ts }});
      }}
      var msgEl = partialMsgEl;
      partialMsgEl = null;
      partialTextEl = null;
      scrollToBottom();
      // TTS: speak completed streamed response
      if (text && typeof window._voxelSpeakText === 'function') {{
        window._voxelSpeakText(text, msgEl);
      }}
    }} else {{
      addMessage('assistant', text);
    }}
  }}

  // ── Tool call display ──
  function showToolCall(name, status) {{
    if (status === 'running') {{
      var div = document.createElement('div');
      div.className = 'tool-call running';
      div.innerHTML = '<span class="tool-icon">&#9881;</span>' +
        '<span class="tool-name">Running ' + escapeHtml(name) + '...</span>';
      messagesEl.appendChild(div);
      toolCallEls[name] = div;
      scrollToBottom();
    }} else if (status === 'done') {{
      var el = toolCallEls[name];
      if (el) {{
        el.className = 'tool-call done';
        el.innerHTML = '<span class="tool-icon">&#9881;</span>' +
          '<span class="tool-name">' + escapeHtml(name) + '</span>' +
          '<span class="tool-check">&#10003;</span>';
        delete toolCallEls[name];
      }}
    }}
  }}

  // ── Emoji reaction animation ──
  function showReaction(emoji) {{
    var lastMsg = messagesEl.querySelector('.msg:last-child');
    var rect = lastMsg ? lastMsg.getBoundingClientRect() : {{ left: 100, top: 200 }};
    var el = document.createElement('div');
    el.className = 'emoji-reaction';
    el.textContent = emoji;
    el.style.left = (rect.left + 20) + 'px';
    el.style.top = (rect.top - 10) + 'px';
    document.body.appendChild(el);
    el.addEventListener('animationend', function() {{ el.remove(); }});
    setTimeout(function() {{ if (el.parentNode) el.remove(); }}, 2500);
  }}

  // ── Error display ──
  function showError(msg) {{
    errorBanner.textContent = msg;
    errorBanner.classList.add('visible');
    setTimeout(function() {{ errorBanner.classList.remove('visible'); }}, 6000);
  }}

  // ── Loading / thinking state ──
  function setLoading(on) {{
    sending = on;
    inputEl.disabled = on;
    sendBtn.disabled = on;
    typingEl.classList.toggle('visible', on);
    if (on) scrollToBottom();
  }}

  // ── Connection status ──
  function setConnected(on) {{
    wsConnected = on;
    connDot.classList.toggle('connected', on);
    connDot.title = on ? 'Connected' : 'Disconnected';
  }}

  // ── WebSocket connection to server.py on port 8080 ──
  function connectWs() {{
    try {{
      var host = location.hostname || 'localhost';
      ws = new WebSocket('ws://' + host + ':8080');
      ws.onopen = function() {{
        setConnected(true);
        ws.send(JSON.stringify({{ type: 'get_chat_history' }}));
      }};
      ws.onclose = function() {{
        setConnected(false);
        ws = null;
        setTimeout(connectWs, 3000);
      }};
      ws.onerror = function() {{
        setConnected(false);
      }};
      ws.onmessage = function(ev) {{
        try {{
          handleWsMessage(JSON.parse(ev.data));
        }} catch(e) {{}}
      }};
    }} catch(e) {{
      setTimeout(connectWs, 3000);
    }}
  }}

  function handleWsMessage(msg) {{
    switch (msg.type) {{
      case 'state':
        if (msg.mood) {{
          headerMood.textContent = msg.mood + (msg.state ? ' / ' + msg.state : '');
        }}
        if (msg.agent) {{
          var sel = document.getElementById('agent-select');
          if (sel.value !== msg.agent) sel.value = msg.agent;
        }}
        if (msg.state === 'THINKING' && !sending) {{
          typingEl.classList.add('visible');
          scrollToBottom();
        }} else if (msg.state !== 'THINKING' && !sending) {{
          typingEl.classList.remove('visible');
        }}
        break;

      case 'transcript':
        if (msg.role === 'assistant') {{
          if (msg.status === 'partial') {{
            typingEl.classList.remove('visible');
            startOrUpdatePartial(msg.text || '');
          }} else if (msg.status === 'done') {{
            typingEl.classList.remove('visible');
            finalizePartial(msg.text || '');
            if (sending) setLoading(false);
          }} else {{
            typingEl.classList.add('visible');
            scrollToBottom();
          }}
        }} else if (msg.role === 'user' && msg.status === 'done') {{
          addMessage('user', msg.text || '');
        }}
        break;

      case 'tool_call':
        showToolCall(msg.name || 'tool', msg.status || 'running');
        break;

      case 'reaction':
        if (msg.emoji) showReaction(msg.emoji);
        break;

      case 'chat_history':
        if (msg.messages && Array.isArray(msg.messages)) {{
          for (var i = 0; i < msg.messages.length; i++) {{
            addMessage(msg.messages[i].role, msg.messages[i].text, false);
          }}
          scrollToBottom();
        }}
        break;
    }}
  }}

  // ── Send message via HTTP API ──
  window.sendMessage = async function() {{
    var text = inputEl.value.trim();
    if (!text || sending) return;
    inputEl.value = '';
    addMessage('user', text);
    setLoading(true);
    try {{
      var agent = document.getElementById('agent-select').value;
      var r = await fetch('/api/chat', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{text: text, agent: agent}})
      }});
      var d = await r.json();
      if (d.ok) {{
        if (!partialMsgEl) {{
          addMessage('assistant', d.response);
        }} else {{
          finalizePartial(d.response);
        }}
      }} else {{
        showError(d.error || 'Failed to send message');
      }}
    }} catch(e) {{
      showError('Connection error: ' + e.message);
    }} finally {{
      setLoading(false);
      inputEl.focus();
    }}
  }};

  window.switchAgent = async function(agent) {{
    try {{
      var r = await fetch('/api/chat/agent', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{agent: agent}})
      }});
      var d = await r.json();
      if (!d.ok) showError(d.error || 'Failed to switch agent');
    }} catch(e) {{
      showError('Connection error: ' + e.message);
    }}
  }};

  // Enter key to send
  inputEl.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' && !e.shiftKey) {{
      e.preventDefault();
      sendMessage();
    }}
  }});

  // Load existing messages from server-side pre-render
  var existing = {messages_json};
  for (var i = 0; i < existing.length; i++) {{
    addMessage(existing[i].role, existing[i].text, false);
  }}

  // Focus input and scroll
  inputEl.focus();
  userScrolledUp = false;
  scrollToBottom();

  // Start WebSocket connection
  connectWs();
}})();

/* ── Theme toggle ──────────────────────────────────────────────── */
function applyTheme(t) {{
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('voxel-theme', t);
  var btn = document.getElementById('theme-btn');
  if (btn) btn.innerHTML = t === 'dark' ? '&#9728;&#65039;' : '&#127769;';
}}
function toggleTheme() {{
  var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}}
applyTheme(localStorage.getItem('voxel-theme') || 'dark');

/* ── Voice: TTS (browser speechSynthesis) ─────────────────────── */
(function() {{
  var speakerBtn = document.getElementById('speaker-toggle');
  var synth = window.speechSynthesis || null;
  var ttsEnabled = false;
  var currentUtterance = null;
  var speakingMsgEl = null;

  // Hide speaker toggle if speechSynthesis not available
  if (!synth) {{
    if (speakerBtn) speakerBtn.style.display = 'none';
  }} else {{
    // Restore preference from localStorage
    try {{
      ttsEnabled = localStorage.getItem('voxel-tts') === '1';
    }} catch(e) {{}}
    updateSpeakerIcon();
  }}

  function updateSpeakerIcon() {{
    if (!speakerBtn) return;
    speakerBtn.classList.toggle('active', ttsEnabled);
    speakerBtn.title = ttsEnabled ? 'Voice output ON (click to mute)' : 'Voice output OFF (click to enable)';
    // Update the SVG path for on/off state
    if (ttsEnabled) {{
      speakerBtn.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path class="speaker-icon" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>';
    }} else {{
      speakerBtn.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path class="speaker-icon" d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
    }}
  }}

  window.toggleSpeaker = function() {{
    if (!synth) return;
    ttsEnabled = !ttsEnabled;
    try {{ localStorage.setItem('voxel-tts', ttsEnabled ? '1' : '0'); }} catch(e) {{}}
    updateSpeakerIcon();
    // Cancel current speech if turning off
    if (!ttsEnabled && synth.speaking) {{
      synth.cancel();
      clearSpeakingHighlight();
    }}
  }};

  function clearSpeakingHighlight() {{
    if (speakingMsgEl) {{
      speakingMsgEl.classList.remove('speaking-now');
      speakingMsgEl = null;
    }}
  }}

  // Pick a natural-sounding voice
  var selectedVoice = null;
  function pickVoice() {{
    if (!synth) return;
    var voices = synth.getVoices();
    if (!voices.length) return;
    // Prefer English voices with "natural" or "enhanced" in name
    var preferred = ['Google', 'Samantha', 'Daniel', 'Karen', 'Moira', 'Alex'];
    for (var p = 0; p < preferred.length; p++) {{
      for (var v = 0; v < voices.length; v++) {{
        if (voices[v].name.indexOf(preferred[p]) !== -1 && voices[v].lang.startsWith('en')) {{
          selectedVoice = voices[v];
          return;
        }}
      }}
    }}
    // Fallback: first English voice
    for (var v = 0; v < voices.length; v++) {{
      if (voices[v].lang.startsWith('en')) {{
        selectedVoice = voices[v];
        return;
      }}
    }}
    // Last resort: first voice
    selectedVoice = voices[0];
  }}

  if (synth) {{
    pickVoice();
    if (synth.onvoiceschanged !== undefined) {{
      synth.onvoiceschanged = pickVoice;
    }}
  }}

  // Exposed for addMessage / finalizePartial to call
  window._voxelSpeakText = function(text, msgEl) {{
    if (!ttsEnabled || !synth) return;
    // Cancel previous utterance
    if (synth.speaking) {{
      synth.cancel();
      clearSpeakingHighlight();
    }}
    var utterance = new SpeechSynthesisUtterance(text);
    if (selectedVoice) utterance.voice = selectedVoice;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    currentUtterance = utterance;

    // Highlight the message being spoken
    if (msgEl) {{
      speakingMsgEl = msgEl;
      msgEl.classList.add('speaking-now');
    }}

    utterance.onend = function() {{
      clearSpeakingHighlight();
      currentUtterance = null;
    }};
    utterance.onerror = function() {{
      clearSpeakingHighlight();
      currentUtterance = null;
    }};

    synth.speak(utterance);
  }};
}})();

/* ── Voice: STT (browser SpeechRecognition) ───────────────────── */
(function() {{
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var micBtn = document.getElementById('mic-btn');
  var listeningIndicator = document.getElementById('listening-indicator');
  var listeningText = document.getElementById('listening-text');
  var inputEl = document.getElementById('msg-input');
  var recognition = null;
  var isRecording = false;

  // Show mic button only if SpeechRecognition is supported
  if (SpeechRecognition && micBtn) {{
    micBtn.style.display = 'flex';
  }}

  function showListening(visible, text) {{
    if (listeningIndicator) {{
      listeningIndicator.classList.toggle('visible', visible);
    }}
    if (listeningText && text) {{
      listeningText.textContent = text;
    }}
  }}

  function stopRecording() {{
    isRecording = false;
    if (micBtn) micBtn.classList.remove('recording');
    showListening(false);
    if (recognition) {{
      try {{ recognition.stop(); }} catch(e) {{}}
    }}
  }}

  window.toggleMic = function() {{
    if (!SpeechRecognition) return;

    if (isRecording) {{
      stopRecording();
      return;
    }}

    // Start recording
    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {{
      isRecording = true;
      if (micBtn) micBtn.classList.add('recording');
      showListening(true, 'Listening...');
    }};

    recognition.onresult = function(event) {{
      var transcript = '';
      var isFinal = false;
      for (var i = event.resultIndex; i < event.results.length; i++) {{
        transcript += event.results[i][0].transcript;
        if (event.results[i].isFinal) isFinal = true;
      }}
      // Show interim results in input
      if (inputEl) inputEl.value = transcript;
      if (isFinal) {{
        stopRecording();
        // Auto-send the final transcript
        if (transcript.trim() && typeof window.sendMessage === 'function') {{
          window.sendMessage();
        }}
      }}
    }};

    recognition.onerror = function(event) {{
      stopRecording();
      var msg = 'Speech recognition error';
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {{
        msg = 'Microphone access denied';
        if (micBtn) micBtn.disabled = true;
      }} else if (event.error === 'no-speech') {{
        msg = 'No speech detected';
      }} else if (event.error === 'network') {{
        msg = 'Network error — speech recognition unavailable';
      }} else if (event.error === 'aborted') {{
        return; // User cancelled, no error to show
      }}
      showListening(true, msg);
      setTimeout(function() {{ showListening(false); }}, 3000);
    }};

    recognition.onend = function() {{
      // Fires when recognition stops (final result already handled or timeout)
      if (isRecording) {{
        stopRecording();
      }}
    }};

    try {{
      recognition.start();
    }} catch(e) {{
      showListening(true, 'Speech recognition not available');
      setTimeout(function() {{ showListening(false); }}, 3000);
    }}
  }};
}})();
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.debug(format % args)

    def _get_query_token(self) -> str | None:
        """Extract token query parameter from the URL."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        tokens = params.get("token", [])
        return tokens[0] if tokens else None

    def _is_authed(self) -> bool:
        return _check_session(self.headers.get("Cookie"), self._get_query_token())

    def _send_html_gz(self, html: str, status: int = 200) -> None:
        """Send an HTML response, gzip-compressed if the client supports it."""
        body = html.encode("utf-8")
        accept_enc = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_enc:
            import gzip
            body = gzip.compress(body, compresslevel=6)
            self.send_response(status)
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self) -> None:
        """Server-Sent Events stream for live device status."""
        if not self._is_authed():
            self.send_error(401)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        import time
        try:
            while True:
                stats = {}
                if _display_state:
                    stats["battery"] = _display_state.battery
                    stats["wifi"] = _display_state.wifi_connected
                    stats["state"] = _display_state.state
                    stats["mood"] = _display_state.mood
                    stats["agent"] = _display_state.agent
                    stats["speaking"] = _display_state.speaking

                try:
                    from display.system_stats import get_system_stats
                    stats["system"] = get_system_stats()
                except ImportError:
                    pass

                data = json.dumps(stats)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                time.sleep(3)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client disconnected

    def do_GET(self):
        # Token-based auth from QR code — set cookie and redirect to clean URL
        query_token = self._get_query_token()
        if query_token:
            expiry = _sessions.get(query_token, 0)
            if expiry > _time.time():
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"voxel_session={query_token}; Path=/; Max-Age={SESSION_DURATION}; SameSite=Strict",
                )
                self.end_headers()
                return

        # Health check — no auth required (used by connection indicator)
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json_response(200, {"ok": True, "status": "running"})
            return

        # Agent setup guide — public, no auth
        if parsed.path in ("/setup", "/openclaw/setup"):
            root = Path(__file__).parent.parent
            # Prefer AGENTS_SETUP.md (comprehensive), fall back to openclaw/SETUP.md
            setup_path = root / "AGENTS_SETUP.md"
            if not setup_path.exists():
                setup_path = root / "openclaw" / "SETUP.md"
            if setup_path.exists():
                # Replace DEVICE_IP placeholder with actual IP
                text = setup_path.read_text(encoding="utf-8")
                try:
                    import socket as _s
                    ip = _s.gethostbyname(_s.gethostname())
                except Exception:
                    ip = "localhost"
                text = text.replace("DEVICE_IP", ip)
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404, "Setup guide not found")
            return

        # Skill file — public, no auth (agent auto-discovery)
        if parsed.path in ("/skill", "/openclaw/skill"):
            skill_path = Path(__file__).parent.parent / "openclaw" / "SKILL.md"
            if skill_path.exists():
                body = skill_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404, "Skill file not found")
            return

        # MCP discovery — public, no auth (standard discovery endpoint)
        if parsed.path == "/.well-known/mcp":
            from config.settings import load_settings
            cfg = load_settings()
            mcp_cfg = cfg.get("mcp", {})
            mcp_port = mcp_cfg.get("port", 8082)
            mcp_enabled = mcp_cfg.get("enabled", False)

            # Try to detect if MCP server is actually running
            mcp_running = False
            try:
                _s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                _s.settimeout(0.5)
                _s.connect(("127.0.0.1", mcp_port))
                _s.close()
                mcp_running = True
            except Exception:
                pass

            hostname = socket.gethostname()
            try:
                ip = socket.gethostbyname(hostname)
            except Exception:
                ip = "127.0.0.1"

            discovery = {
                "name": "voxel",
                "description": "Voxel AI companion device — animated face, speaker, LED, mood control",
                "version": "0.1.0",
                "mcp": {
                    "enabled": mcp_enabled,
                    "running": mcp_running,
                    "transport": "sse",
                    "url": f"http://{ip}:{mcp_port}/sse",
                    "tools": 20,
                    "resources": 3,
                },
                "interfaces": {
                    "mcp": {"url": f"http://{ip}:{mcp_port}/sse", "status": "running" if mcp_running else "stopped"},
                    "rest": {"url": f"http://{ip}:{_server_port}", "note": "Config server REST API. Public: /api/health, /api/stats, /setup, /skill. Auth required for control endpoints."},
                    "websocket": {"url": f"ws://{ip}:8080", "note": "Backend WebSocket. Full bidirectional JSON control. No auth."},
                },
                "setup_url": f"http://{ip}:{_server_port}/setup",
                "skill_url": f"http://{ip}:{_server_port}/skill",
                "config_url": f"http://{ip}:{_server_port}/",
            }
            self._send_json(discovery)
            return

        # Auth check — show login page if not authenticated
        if not self._is_authed():
            html = _build_login_html()
            self._send_html_gz(html)
            return

        if self.path == "/wifi/scan":
            self._wifi_scan()
            return

        if self.path == "/api/update/check":
            self._update_check()
            return

        if self.path == "/api/settings/diff":
            self._settings_diff()
            return

        if self.path == "/api/backup/export":
            self._backup_export()
            return

        if self.path == "/api/debug/state" and _dev_mode:
            self._debug_state()
            return

        if self.path == "/api/chat/history":
            self._chat_history()
            return

        if self.path == "/api/stats":
            self._system_stats()
            return

        if self.path == "/api/events":
            self._handle_sse()
            return

        if self.path == "/api/diagnostics/system":
            self._diagnostics_system()
            return

        parsed_path = urlparse(self.path).path

        if parsed_path == "/chat":
            html = _build_chat_html()
            self._send_html_gz(html)
            return

        if parsed_path == "/diagnostics":
            html = _build_diagnostics_html()
            self._send_html_gz(html)
            return

        settings = _load_settings()
        html = _build_html(settings)
        self._send_html_gz(html)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Auth endpoint — no session required
        if self.path == "/auth":
            self._handle_auth(body)
            return

        # Dev-pair endpoint — uses PIN auth, no session required
        if self.path == "/api/dev/pair":
            self._handle_dev_pair(body)
            return

        if self.path == "/api/dev/pair/request":
            # Ask device user to approve before showing PIN
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}

            if _display_state:
                requester = data.get("dev_host", self.client_address[0])
                _display_state.pairing_request = True
                _display_state.pairing_request_from = requester
                _display_state.pairing_approved = False
                _display_state.pairing_denied = False
                log.info(f"Pairing request from {requester}")

                # Wait up to 30s for user to approve/deny on device
                import time as _tw
                deadline = _tw.time() + 30.0
                while _tw.time() < deadline:
                    if _display_state.pairing_approved:
                        _display_state.pairing_approved = False
                        # Device approval = authenticated. Create session so browser skips PIN.
                        token = _create_session()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Set-Cookie",
                            f"voxel_session={token}; Path=/; Max-Age={SESSION_DURATION}; SameSite=Strict")
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "ok": True, "approved": True, "authenticated": True
                        }).encode("utf-8"))
                        return
                    if _display_state.pairing_denied:
                        _display_state.pairing_denied = False
                        self._json_response(200, {"ok": True, "approved": False})
                        return
                    _tw.sleep(0.2)

                _display_state.pairing_request = False
                self._json_response(200, {"ok": True, "approved": False, "timeout": True})
            else:
                self._json_response(200, {"ok": True, "approved": True, "pin_required": _auth_enabled})
            return

        # All other POST endpoints require auth
        if not self._is_authed():
            self._json_response(401, {"ok": False, "error": "Not authenticated"})
            return

        if self.path == "/api/diagnostics/speaker-test":
            self._diagnostics_speaker_test()
            return

        if self.path == "/api/diagnostics/mic-test":
            self._diagnostics_mic_test()
            return

        if self.path == "/wifi/connect":
            self._wifi_connect(body)
            return

        if self.path == "/api/mcp/start":
            import sys
            mcp_cfg = _load_settings().get("mcp", {})
            port = mcp_cfg.get("port", 8082)
            try:
                subprocess.Popen(
                    [sys.executable, "-m", "mcp", "--transport", "sse", "--port", str(port)],
                    cwd=str(Path(__file__).parent.parent),
                )
                self._send_json({"ok": True, "message": f"MCP server starting on :{port}"})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        if self.path == "/api/mcp/stop":
            # Kill MCP server by finding its PID via the port it listens on
            mcp_cfg = _load_settings().get("mcp", {})
            port = mcp_cfg.get("port", 8082)
            killed = False
            try:
                import sys as _sys
                if _sys.platform == "win32":
                    # Find PID listening on the MCP port
                    result = subprocess.run(
                        ["netstat", "-ano", "-p", "TCP"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in result.stdout.splitlines():
                        if f":{port}" in line and "LISTENING" in line:
                            pid = line.strip().split()[-1]
                            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                            killed = True
                            break
                else:
                    result = subprocess.run(
                        ["fuser", f"{port}/tcp"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout.strip():
                        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
                        killed = True
            except Exception:
                pass
            self._send_json({"ok": True, "killed": killed})
            return

        if self.path == "/api/mcp/status":
            mcp_cfg = _load_settings().get("mcp", {})
            port = mcp_cfg.get("port", 8082)
            running = False
            try:
                _s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                _s.settimeout(0.5)
                _s.connect(("127.0.0.1", port))
                _s.close()
                running = True
            except Exception:
                pass
            self._send_json({"running": running, "port": port, "enabled": mcp_cfg.get("enabled", False)})
            return

        if self.path == "/api/update/install":
            self._update_install()
            return

        if self.path == "/api/settings/reset":
            self._settings_reset(body)
            return

        if self.path == "/api/backup/import":
            self._backup_import(body)
            return

        if self.path == "/api/reboot":
            self._reboot(body)
            return

        if self.path == "/api/factory-reset":
            self._factory_reset(body)
            return

        if self.path == "/api/chat":
            self._chat_send(body)
            return

        if self.path == "/api/chat/agent":
            self._chat_switch_agent(body)
            return

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_response(400, {"ok": False, "error": "Invalid JSON"})
            return

        # Handle checkbox fields (unchecked checkboxes aren't sent in form data)
        _checkbox_fields = ["dev.enabled", "dev.advertise", "led.enabled",
                            "character.system_context_enabled", "character.idle_personality",
                            "character.demo_mode", "mcp.enabled", "webhook.enabled"]
        for cb_key in _checkbox_fields:
            if cb_key not in data:
                data[cb_key] = False

        # Convert flat dotted keys to nested dict
        updates: dict[str, Any] = {}
        for key, value in data.items():
            # Convert boolean-like strings
            if value == "true":
                value = True
            elif value == "false":
                value = False
            # Convert numeric strings for known numeric fields
            elif isinstance(value, str) and value.isdigit():
                value = int(value)
            # Float fields stored as 0-1 but sent as 0-100 from range sliders
            _float_fields = {"character.gaze_range", "character.gaze_drift_speed",
                             "character.mouth_sensitivity", "character.breathing_speed"}
            if key in _float_fields and isinstance(value, int):
                value = value / 100.0
            parts = key.split(".")
            d = updates
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = value

        try:
            _save_settings(updates)
            log.info(f"Settings saved via web UI: {list(data.keys())}")

            # Update setup state if gateway token was configured
            if "gateway" in updates and updates["gateway"].get("token"):
                try:
                    from display.components.onboarding import save_setup_flag
                    save_setup_flag("gateway_configured")
                    log.info("Setup state: gateway_configured")
                except Exception:
                    pass

            self._json_response(200, {"ok": True})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _handle_auth(self, body: bytes):
        try:
            data = json.loads(body)
            pin = data.get("pin", "")
            if pin == _access_pin:
                token = _create_session()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"voxel_session={token}; Path=/; Max-Age={SESSION_DURATION}; SameSite=Strict")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                log.info("Web auth: PIN accepted from %s", self.client_address[0])
            else:
                self._json_response(401, {"ok": False, "error": "Invalid PIN"})
                log.warning("Web auth: invalid PIN from %s", self.client_address[0])
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _handle_dev_pair(self, body: bytes):
        """Handle dev-pair request: verify PIN, enable dev mode, return SSH creds."""
        try:
            data = json.loads(body)
            pin = data.get("pin", "")
            dev_host = data.get("dev_host", "")  # dev machine's IP for reference

            if pin != _access_pin:
                self._json_response(401, {"ok": False, "error": "Invalid PIN"})
                return

            # Enable dev mode
            _save_settings({"dev": {"enabled": True}})

            # Return SSH credentials + device info
            settings = _load_settings()
            ssh = settings.get("dev", {}).get("ssh", {})

            try:
                from display.updater import get_current_version
                version = get_current_version()
            except Exception:
                version = "unknown"

            self._json_response(200, {
                "ok": True,
                "host": get_local_ip(),
                "user": ssh.get("user", "pi"),
                "password": ssh.get("password", "voxel"),
                "config_port": _server_port,
                "version": version,
            })
            log.info(f"Dev-pair successful from {dev_host or 'unknown'}")
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _wifi_scan(self):
        try:
            from display.wifi import scan_networks
            nets = scan_networks()
            data = [{"ssid": n.ssid, "signal": n.signal, "security": n.security, "connected": n.connected} for n in nets]
            self._json_response(200, data)
        except Exception as e:
            self._json_response(500, [])

    def _wifi_connect(self, body: bytes):
        try:
            data = json.loads(body)
            ssid = data.get("ssid", "")
            password = data.get("password", "")
            if not ssid:
                self._json_response(400, {"ok": False, "error": "No SSID provided"})
                return
            from display.wifi import connect_to_network
            ok, error = connect_to_network(ssid, password)
            self._json_response(200, {"ok": ok, "error": error})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _update_check(self):
        """Check for available updates via git."""
        try:
            from display.updater import check_for_update
            result = check_for_update()
            # Update display state if available
            if _display_state is not None:
                _display_state.update_available = result.get("available", False)
                _display_state.update_behind = result.get("behind", 0)
                _display_state.update_checking = False
            self._json_response(200, result)
        except Exception as e:
            self._json_response(500, {"available": False, "error": str(e)})

    def _update_install(self):
        """Install available update (pull + sync deps)."""
        try:
            from display.updater import install_update
            result = install_update()
            # Clear update indicator on success
            if result.get("ok") and _display_state is not None:
                _display_state.update_available = False
                _display_state.update_behind = 0
            self._json_response(200, result)
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _debug_state(self):
        """Return the current DisplayState as JSON (dev mode only)."""
        from dataclasses import asdict
        if _display_state is not None:
            # Filter out private fields
            raw = asdict(_display_state)
            state_data = {k: v for k, v in raw.items() if not k.startswith("_")}
        else:
            state_data = {"error": "DisplayState not available"}
        self._json_response(200, state_data)

    def _settings_diff(self):
        """Return settings that differ from defaults."""
        try:
            diff = _get_settings_diff()
            self._json_response(200, {"ok": True, "diff": diff})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _settings_reset(self, body: bytes):
        """Reset settings to defaults (all or specific sections)."""
        try:
            data = json.loads(body)
            sections = data.get("sections", ["all"])
            if not isinstance(sections, list):
                self._json_response(400, {"ok": False, "error": "sections must be a list"})
                return
            settings = _reset_settings(sections)
            label = "all" if "all" in sections else ", ".join(sections)
            log.info(f"Settings reset via web UI: {label}")
            self._json_response(200, {"ok": True, "settings": settings})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _backup_export(self):
        """Export device backup as JSON download."""
        try:
            from config.settings import export_backup
            backup = export_backup()

            # Set headers for file download
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition",
                           'attachment; filename="voxel-backup.json"')
            self.end_headers()
            self.wfile.write(json.dumps(backup, indent=2).encode("utf-8"))
            log.info("Backup exported via web UI")
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _backup_import(self, body: bytes):
        """Import a backup from uploaded JSON."""
        try:
            backup = json.loads(body)
            from config.settings import import_backup
            settings = import_backup(backup)
            log.info("Backup imported via web UI")
            self._json_response(200, {"ok": True, "message": "Backup restored. Restart recommended."})
        except ValueError as e:
            self._json_response(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _factory_reset(self, body: bytes):
        """Factory reset — delete all user config."""
        try:
            # Require explicit confirmation
            data = json.loads(body) if body else {}
            if not data.get("confirm"):
                self._json_response(400, {
                    "ok": False,
                    "error": "Factory reset requires confirm: true"
                })
                return

            from config.settings import factory_reset
            settings = factory_reset()
            log.warning("Factory reset executed via web UI from %s",
                       self.client_address[0])
            self._json_response(200, {
                "ok": True,
                "message": "Factory reset complete. Device will need reconfiguration."
            })
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _reboot(self, body: bytes):
        """Reboot the device (Pi only — no-op on desktop)."""
        try:
            from hw.detect import IS_PI
        except ImportError:
            IS_PI = False

        if not IS_PI:
            log.info("Reboot requested on desktop — ignoring")
            self._json_response(200, {"ok": True, "message": "Reboot skipped (not on Pi)"})
            return

        log.warning("Reboot requested via web UI from %s", self.client_address[0])
        self._json_response(200, {"ok": True, "message": "Rebooting..."})

        # Schedule reboot after the HTTP response is sent
        import threading

        def _do_reboot():
            _time.sleep(1)
            try:
                subprocess.run(["sudo", "reboot"], timeout=5)
            except Exception:
                pass

        threading.Thread(target=_do_reboot, daemon=True).start()

    def _chat_send(self, body: bytes):
        """Handle POST /api/chat — send a message to the AI agent.

        The gateway call runs in a background thread so the HTTP server
        isn't blocked. The client receives an immediate acknowledgement
        and can poll for the response via the existing transcript/SSE
        mechanism.
        """
        try:
            data = json.loads(body)
            text = data.get("text", "").strip()
            agent = data.get("agent", "")
            if not text:
                self._json_response(400, {"ok": False, "error": "No message text"})
                return

            client = _get_chat_client()
            if client is None:
                if _display_state:
                    _display_state.state = "ERROR"
                    _display_state.mood = "error"
                    _display_state.push_transcript("assistant", "Gateway not configured")
                    _start_error_recovery(_display_state)
                self._json_response(503, {
                    "ok": False,
                    "error": "Gateway not configured — set gateway URL and token in Settings",
                })
                return

            # Switch agent if different
            if agent and agent != client.agent_id:
                client.set_agent(agent)
                if _display_state:
                    _display_state.agent = agent

            # Push user message to LCD and set THINKING state
            if _display_state:
                _display_state.push_transcript("user", text)
                _display_state.state = "THINKING"
                _display_state.mood = "thinking"

            log.info(f"Chat: sending to {client.agent_id}: {text[:80]}")

            # Run the gateway call in a background thread so the HTTP
            # response returns immediately and the server stays responsive.
            def _gateway_call():
                try:
                    response = client.send_message(text)

                    if response:
                        from core.mood_parser import extract_mood
                        mood, clean_response = extract_mood(response)

                        from display.emoji_reactions import parse_reaction, apply_reaction
                        emoji, clean_response = parse_reaction(clean_response)

                        if _display_state:
                            _display_state.mood = mood
                            _display_state.push_transcript("assistant", clean_response)
                            if emoji:
                                apply_reaction(_display_state, emoji, _time.time(),
                                               duration=3.0, set_mood=True)
                            _start_speaking_simulation(clean_response, _display_state)
                    else:
                        if _display_state:
                            _display_state.state = "ERROR"
                            _display_state.mood = "error"
                            _display_state.push_transcript("assistant", "(no response)")
                            _start_error_recovery(_display_state)
                except Exception as e:
                    log.error(f"Chat gateway error: {e}")
                    if _display_state:
                        _display_state.state = "ERROR"
                        _display_state.mood = "error"
                        _display_state.push_transcript("assistant", f"Error: {str(e)[:40]}")
                        _start_error_recovery(_display_state)

            Thread(target=_gateway_call, daemon=True).start()

            # Return immediately — the client sees the response via
            # transcript updates on the LCD / polling endpoint.
            self._json_response(200, {"ok": True, "status": "sending", "agent": client.agent_id})

        except json.JSONDecodeError:
            self._json_response(400, {"ok": False, "error": "Invalid JSON"})
        except Exception as e:
            log.error(f"Chat send error: {e}")
            if _display_state:
                _display_state.state = "ERROR"
                _display_state.mood = "error"
                _display_state.push_transcript("assistant", f"Error: {str(e)[:40]}")
                _start_error_recovery(_display_state)
            self._json_response(500, {"ok": False, "error": str(e)})

    def _chat_switch_agent(self, body: bytes):
        """Handle POST /api/chat/agent — switch the active agent."""
        try:
            data = json.loads(body)
            agent = data.get("agent", "").strip()
            if not agent:
                self._json_response(400, {"ok": False, "error": "No agent specified"})
                return

            # Update display state
            if _display_state:
                _display_state.agent = agent

            # Update chat client if it exists
            if _chat_client is not None:
                _chat_client.set_agent(agent)

            log.info(f"Chat: switched agent to {agent}")
            self._json_response(200, {"ok": True, "agent": agent})
        except json.JSONDecodeError:
            self._json_response(400, {"ok": False, "error": "Invalid JSON"})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _chat_history(self):
        """Handle GET /api/chat/history — return recent transcripts."""
        messages = []
        if _display_state and _display_state.transcripts:
            messages = [{"role": t.role, "text": t.text} for t in _display_state.transcripts]
        self._json_response(200, {"messages": messages})

    def _system_stats(self):
        """Handle GET /api/stats — return real-time system health info."""
        try:
            from display.system_stats import get_system_stats
            self._json_response(200, get_system_stats())
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    def _diagnostics_system(self):
        """Handle GET /api/diagnostics/system — return system health info."""
        try:
            from hw.detect import IS_PI, probe_hardware
            from core.audio import _pyaudio_available, _sounddevice_available, _pa

            settings = _load_settings()
            hw = probe_hardware()

            # Audio backend
            if _pyaudio_available:
                audio_backend = "pyaudio"
            elif _sounddevice_available:
                audio_backend = "sounddevice"
            else:
                audio_backend = "none"

            # WM8960 detection
            wm8960 = hw.has_wm8960_audio

            # Audio device info
            audio_devices = []
            if _pyaudio_available and _pa is not None:
                try:
                    for i in range(_pa.get_device_count()):
                        info = _pa.get_device_info_by_index(i)
                        audio_devices.append({
                            "index": i,
                            "name": info.get("name", ""),
                            "inputs": info.get("maxInputChannels", 0),
                            "outputs": info.get("maxOutputChannels", 0),
                        })
                except Exception:
                    pass

            # Display backend
            if _display_state and hasattr(_display_state, "backend_name"):
                display_backend = _display_state.backend_name
            elif IS_PI:
                display_backend = "spi"
            else:
                display_backend = "tkinter"

            # Gateway config
            gw = settings.get("gateway", {})
            gateway_configured = bool(gw.get("url", ""))
            gateway_token_set = bool(gw.get("token", ""))

            # API key
            stt = settings.get("stt", {}).get("whisper", {})
            openai_key_set = bool(stt.get("api_key", ""))

            # Battery
            battery = None
            if _display_state and _display_state.battery is not None:
                battery = _display_state.battery

            # WiFi
            wifi = get_wifi_status()

            self._json_response(200, {
                "is_pi": IS_PI,
                "platform": "Pi" if IS_PI else "Desktop",
                "audio_backend": audio_backend,
                "audio_devices": audio_devices,
                "wm8960_detected": wm8960,
                "display_backend": display_backend,
                "gateway_configured": gateway_configured,
                "gateway_token_set": gateway_token_set,
                "openai_key_set": openai_key_set,
                "battery": battery,
                "wifi_connected": wifi.get("connected", False),
                "wifi_ssid": wifi.get("ssid", ""),
                "wifi_ip": wifi.get("ip", ""),
            })
        except Exception as e:
            log.error("Diagnostics system check failed: %s", e)
            self._json_response(500, {"ok": False, "error": str(e)})

    def _diagnostics_speaker_test(self):
        """Handle POST /api/diagnostics/speaker-test — play a 440Hz test tone."""
        try:
            import io
            import math
            import struct
            import wave
            from core.audio import init as audio_init, play_audio, is_playing
            from core.audio import _pyaudio_available, _sounddevice_available

            # Ensure audio is initialized
            if not _pyaudio_available and not _sounddevice_available:
                audio_init()

            from core.audio import _pyaudio_available as pa_avail, _sounddevice_available as sd_avail
            if not pa_avail and not sd_avail:
                self._json_response(200, {"ok": False, "error": "No audio backend available"})
                return

            # Generate 440Hz sine wave, 0.5s, 16-bit mono
            sample_rate = 16000
            duration = 0.5
            frequency = 440.0
            n_samples = int(sample_rate * duration)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                for i in range(n_samples):
                    # Fade in/out to avoid clicks (20ms ramps)
                    t = i / sample_rate
                    ramp_samples = int(0.02 * sample_rate)
                    if i < ramp_samples:
                        envelope = i / ramp_samples
                    elif i > n_samples - ramp_samples:
                        envelope = (n_samples - i) / ramp_samples
                    else:
                        envelope = 1.0
                    sample = int(24000 * envelope * math.sin(2 * math.pi * frequency * t))
                    wf.writeframes(struct.pack("<h", max(-32768, min(32767, sample))))

            wav_bytes = buf.getvalue()
            play_audio(wav_bytes)

            # Wait for playback to finish (up to 3s)
            deadline = _time.time() + 3.0
            while is_playing() and _time.time() < deadline:
                _time.sleep(0.05)

            self._json_response(200, {"ok": True, "duration_ms": int(duration * 1000)})
        except Exception as e:
            log.error("Speaker test failed: %s", e)
            self._json_response(200, {"ok": False, "error": str(e)})

    def _diagnostics_mic_test(self):
        """Handle POST /api/diagnostics/mic-test — record 2s and analyze."""
        ambient_paused = False
        try:
            import io
            import wave
            from core.audio import init as audio_init, start_recording, stop_recording
            from core.audio import _pyaudio_available, _sounddevice_available

            # Pause ambient monitor to release the mic (ALSA only allows one consumer)
            from display.ambient import _active_monitor
            _saved_ambient = _active_monitor
            if _saved_ambient:
                _saved_ambient.pause()
                ambient_paused = True
                _time.sleep(0.3)  # let ALSA release

            # Ensure audio is initialized
            if not _pyaudio_available and not _sounddevice_available:
                audio_init()

            from core.audio import _pyaudio_available as pa_avail, _sounddevice_available as sd_avail
            if not pa_avail and not sd_avail:
                self._json_response(200, {"ok": False, "error": "No audio backend available"})
                return

            start_recording()
            _time.sleep(2.0)
            wav_bytes = stop_recording()

            if not wav_bytes or len(wav_bytes) < 100:
                self._json_response(200, {"ok": False, "error": "No audio data recorded"})
                return

            # Analyze the WAV data
            buf = io.BytesIO(wav_bytes)
            with wave.open(buf, "rb") as wf:
                raw = wf.readframes(wf.getnframes())

            import numpy as np
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            rms = float(np.sqrt(np.mean(samples ** 2)))
            peak = float(np.max(np.abs(samples)))

            # Noise floor estimate
            if rms < 0.005:
                noise_floor = "silent"
            elif rms < 0.02:
                noise_floor = "low"
            elif rms < 0.08:
                noise_floor = "medium"
            else:
                noise_floor = "high"

            self._json_response(200, {
                "ok": True,
                "duration_s": 2.0,
                "rms": round(rms, 6),
                "peak": round(peak, 6),
                "noise_floor": noise_floor,
                "bytes": len(wav_bytes),
            })
        except Exception as e:
            log.error("Mic test failed: %s", e)
            self._json_response(200, {"ok": False, "error": str(e)})
        finally:
            if ambient_paused and _saved_ambient:
                try:
                    _saved_ambient.resume()
                except Exception as e:
                    log.warning("Failed to resume ambient monitor: %s", e)

    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def _find_open_port(start: int = PREFERRED_PORT, attempts: int = 10) -> int:
    """Find an available port starting from the preferred one."""
    for offset in range(attempts):
        port = start + offset
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No open port found in range {start}-{start + attempts - 1}")


def start_config_server(state=None) -> str:
    """Start the config web server in a background thread. Returns the URL."""
    global _access_pin, _auth_enabled, _dev_mode, _display_state, _server_port

    # Store state reference for debug endpoint
    _display_state = state

    # Check if auth is disabled in config
    try:
        settings = _load_settings()
        web_cfg = settings.get("web", {})
        _auth_enabled = web_cfg.get("auth_enabled", True)
        _dev_mode = settings.get("dev", {}).get("enabled", False)
    except Exception:
        _auth_enabled = True
        _dev_mode = False

    # Generate access PIN
    _access_pin = _generate_pin()
    if _dev_mode:
        log.info("Web config auth SKIPPED (dev mode enabled)")
    elif _auth_enabled:
        log.info(f"Web config PIN: {_access_pin}")
    else:
        log.info("Web config auth DISABLED (web.auth_enabled: false)")

    ip = get_local_ip()
    port = _find_open_port()
    _server_port = port
    url = f"http://{ip}:{port}"

    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    log.info(f"Config server running at {url}")
    return url
