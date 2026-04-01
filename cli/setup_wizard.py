"""Interactive TUI setup wizard for Voxel configuration."""

from __future__ import annotations

import getpass
import platform
import socket
from typing import Any

from cli.display import (
    console,
    cyan,
    dim,
    header,
    info,
    kv,
    ok,
    section,
    warn,
)
from config.settings import load_settings, save_local_settings


# ── Input helpers ───────────────────────────────────────────────────────────


def prompt_text(label: str, default: str | None = None) -> str:
    """Prompt for text input with an optional default value."""
    if default:
        suffix = f" {dim(f'[{default}]')}"
    else:
        suffix = ""
    console.print(f"\n  {label}{suffix}")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return default or ""
    return raw if raw else (default or "")


def prompt_choice(label: str, options: list[str], default: int = 0) -> int:
    """Show numbered options and return the selected index."""
    console.print(f"\n  {label}")
    for i, opt in enumerate(options):
        marker = f"[bold cyan]*[/]" if i == default else " "
        console.print(f"    {marker} {dim(f'{i + 1}.')} {opt}")
    hint = f" {dim(f'[{default + 1}]')}" if default is not None else ""
    console.print(f"  Choose{hint}")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return default
    if not raw:
        return default
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return idx
    except ValueError:
        pass
    warn(f"Invalid choice, using default ({options[default]})")
    return default


def prompt_yesno(label: str, default: bool = True) -> bool:
    """Prompt for a yes/no answer."""
    hint = "Y/n" if default else "y/N"
    console.print(f"\n  {label} {dim(f'[{hint}]')}")
    try:
        raw = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return default
    if not raw:
        return default
    return raw in ("y", "yes")


def prompt_secret(label: str) -> str:
    """Prompt for a secret (hidden input)."""
    console.print(f"\n  {label}")
    try:
        value = getpass.getpass("  > ")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return ""
    return value.strip()


def prompt_int(label: str, default: int, lo: int = 0, hi: int = 100) -> int:
    """Prompt for an integer within a range."""
    console.print(f"\n  {label} {dim(f'[{default}]')} {dim(f'({lo}-{hi})')}")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return default
    if not raw:
        return default
    try:
        val = int(raw)
        if lo <= val <= hi:
            return val
        warn(f"Out of range, using default ({default})")
    except ValueError:
        warn(f"Invalid number, using default ({default})")
    return default


# ── Device info ─────────────────────────────────────────────────────────────


def _get_device_info() -> dict[str, str]:
    """Gather basic device/host information."""
    info_dict: dict[str, str] = {}
    info_dict["hostname"] = socket.gethostname()
    info_dict["platform"] = platform.machine()
    info_dict["os"] = platform.system()

    # IP address (best effort)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info_dict["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        info_dict["ip"] = "unknown"

    # Pi model
    from hw.detect import IS_PI
    if IS_PI:
        try:
            with open("/proc/device-tree/model", "r") as f:
                info_dict["model"] = f.read().strip().rstrip("\x00")
        except Exception:
            info_dict["model"] = "Raspberry Pi"
    else:
        info_dict["model"] = f"{platform.system()} ({platform.machine()})"

    return info_dict


# ── Gateway connection test ─────────────────────────────────────────────────


def _test_gateway(url: str, token: str) -> bool:
    """Try to reach the gateway. Returns True on success."""
    import urllib.request
    import urllib.error

    test_url = url.rstrip("/") + "/v1/models"
    req = urllib.request.Request(test_url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("x-openclaw-scopes", "operator.read,operator.write")
    try:
        resp = urllib.request.urlopen(req, timeout=8)
        if resp.status == 200:
            return True
    except urllib.error.HTTPError as e:
        # 401/403 means it's reachable but auth failed
        if e.code in (401, 403):
            warn("Gateway reachable but auth failed -- check your token")
        else:
            warn(f"Gateway returned HTTP {e.code}")
        return False
    except Exception as e:
        warn(f"Could not reach gateway: {e}")
        return False
    return False


# ── Wizard sections ─────────────────────────────────────────────────────────


def _section_welcome() -> None:
    """Section 1: Welcome screen with device info."""
    device = _get_device_info()

    header("Voxel Configuration Wizard")
    console.print("  Welcome! This wizard will walk you through configuring your")
    console.print("  Voxel device. Each section is optional -- press Enter to")
    console.print("  accept defaults, or type [cyan]skip[/] to skip a section.\n")

    section("Device Info")
    kv("Hostname", device["hostname"])
    kv("IP Address", device["ip"])
    kv("Platform", device["model"])
    console.print()


def _section_gateway(updates: dict[str, Any]) -> None:
    """Section 2: OpenClaw gateway connection."""
    section("Gateway Connection")
    console.print("  Connect to an OpenClaw gateway for AI chat capabilities.")
    console.print(f"  {dim('Skip this section for standalone mode (face + menu only).')}")

    url = prompt_text("Gateway URL (e.g. http://gateway:18789)", default="")
    if not url:
        info("Skipping gateway -- standalone mode")
        return

    token = prompt_secret("Auth token (or set OPENCLAW_TOKEN env var later)")

    # Test connection
    if url:
        if prompt_yesno("Test gateway connection?", default=True):
            info(f"Testing {url}...")
            if _test_gateway(url, token):
                ok("Gateway connection successful!")
            else:
                if not prompt_yesno("Continue with this gateway URL anyway?", default=True):
                    return

    updates.setdefault("gateway", {})
    updates["gateway"]["url"] = url
    if token:
        updates["gateway"]["token"] = token

    # Default agent selection
    agents = [
        ("daemon", "Daemon -- Lead agent, coordinator"),
        ("soren", "Soren -- Senior architect"),
        ("ash", "Ash -- Builder/executor"),
        ("mira", "Mira -- Business operator"),
        ("jace", "Jace -- Flex agent"),
        ("pip", "Pip -- Intern"),
    ]
    agent_idx = prompt_choice(
        "Default agent:",
        [desc for _, desc in agents],
        default=0,
    )
    updates["gateway"]["default_agent"] = agents[agent_idx][0]
    ok(f"Gateway configured: {cyan(url)}")


def _section_voice(updates: dict[str, Any]) -> None:
    """Section 3: Voice / audio settings."""
    section("Voice Settings")
    console.print("  Configure text-to-speech and speech-to-text providers.")

    # TTS provider
    tts_options = [
        "edge -- Free Microsoft Edge TTS (no API key needed)",
        "openai -- OpenAI TTS (needs API key, higher quality)",
        "elevenlabs -- ElevenLabs TTS (needs API key, highest quality)",
    ]
    tts_idx = prompt_choice("TTS provider:", tts_options, default=0)
    tts_provider = ["edge", "openai", "elevenlabs"][tts_idx]
    updates.setdefault("audio", {})
    updates["audio"]["tts_provider"] = tts_provider

    openai_key = ""

    if tts_provider == "openai":
        openai_key = prompt_secret(
            "OpenAI API key (or set OPENAI_API_KEY env var later)"
        )
        if openai_key:
            updates.setdefault("tts", {}).setdefault("openai", {})
            updates["tts"]["openai"]["api_key"] = openai_key

            # OpenAI TTS voice selection
            voices = [
                "nova -- Warm female (default)",
                "alloy -- Neutral",
                "ash -- Conversational male",
                "coral -- Warm female",
                "echo -- Deep male",
                "fable -- British male",
                "onyx -- Deep male",
                "sage -- Calm female",
                "shimmer -- Cheerful female",
            ]
            voice_idx = prompt_choice("OpenAI TTS voice:", voices, default=0)
            voice_ids = ["nova", "alloy", "ash", "coral", "echo",
                         "fable", "onyx", "sage", "shimmer"]
            updates["tts"]["openai"]["voice"] = voice_ids[voice_idx]

    elif tts_provider == "elevenlabs":
        el_key = prompt_secret(
            "ElevenLabs API key (or set ELEVENLABS_API_KEY env var later)"
        )
        if el_key:
            updates.setdefault("tts", {}).setdefault("elevenlabs", {})
            updates["tts"]["elevenlabs"]["api_key"] = el_key

    # STT (Whisper)
    console.print(f"\n  {dim('Speech-to-text uses the OpenAI Whisper API.')}")
    if openai_key:
        if prompt_yesno("Use the same OpenAI key for STT (Whisper)?", default=True):
            updates.setdefault("stt", {}).setdefault("whisper", {})
            updates["stt"]["whisper"]["api_key"] = openai_key
            ok("STT will share the OpenAI API key")
        else:
            stt_key = prompt_secret("Separate OpenAI API key for Whisper STT")
            if stt_key:
                updates.setdefault("stt", {}).setdefault("whisper", {})
                updates["stt"]["whisper"]["api_key"] = stt_key
    else:
        stt_key = prompt_secret(
            "OpenAI API key for Whisper STT (or set OPENAI_API_KEY env var later)"
        )
        if stt_key:
            updates.setdefault("stt", {}).setdefault("whisper", {})
            updates["stt"]["whisper"]["api_key"] = stt_key

    # Volume
    vol = prompt_int("Audio volume:", default=80, lo=0, hi=100)
    updates["audio"]["volume"] = vol

    ok(f"Voice configured: {cyan(tts_provider)} TTS")


def _section_display(updates: dict[str, Any]) -> None:
    """Section 4: Display and character settings."""
    section("Display & Character")

    # Character
    char_options = [
        "voxel -- Glowing pill eyes (default)",
        "cube -- Isometric charcoal cube with edge glow",
        "bmo -- BMO character (Adventure Time)",
    ]
    char_idx = prompt_choice("Character:", char_options, default=0)
    char_id = ["voxel", "cube", "bmo"][char_idx]
    updates.setdefault("character", {})
    updates["character"]["default"] = char_id

    # Style
    style_options = [
        "kawaii -- Soft, round, cute (default)",
        "retro -- Pixel art, blocky",
        "minimal -- Clean, simple lines",
    ]
    style_idx = prompt_choice("Face style:", style_options, default=0)
    style_id = ["kawaii", "retro", "minimal"][style_idx]
    # Style is set in the display state, not in config YAML.
    # Store as character.default_style for the display service to pick up.
    updates["character"]["default_style"] = style_id

    # Brightness
    brightness = prompt_int("Display brightness:", default=80, lo=0, hi=100)
    updates.setdefault("display", {})
    updates["display"]["brightness"] = brightness

    ok(f"Display configured: {cyan(char_id)} / {cyan(style_id)} / brightness {brightness}")


def _section_mcp(updates: dict[str, Any]) -> None:
    """Section 5: MCP server settings."""
    section("MCP Server (AI Agent Integration)")
    console.print("  The MCP server lets AI agents (Claude, OpenClaw) control Voxel.")
    console.print(f"  {dim('Disabled by default. Enable if you use AI agents.')}")

    if not prompt_yesno("Enable MCP server?", default=False):
        info("MCP server will remain disabled")
        return

    updates.setdefault("mcp", {})
    updates["mcp"]["enabled"] = True

    transport_options = [
        "sse -- Network (for OpenClaw, remote agents)",
        "stdio -- Local (for Claude Code, Codex CLI)",
    ]
    transport_idx = prompt_choice("Transport:", transport_options, default=0)
    updates["mcp"]["transport"] = ["sse", "stdio"][transport_idx]

    if updates["mcp"]["transport"] == "sse":
        port = prompt_int("MCP server port:", default=8082, lo=1024, hi=65535)
        updates["mcp"]["port"] = port

    ok(f"MCP server enabled ({cyan(updates['mcp']['transport'])})")


def _section_webhooks(updates: dict[str, Any]) -> None:
    """Section 6: Webhook settings."""
    section("Webhooks")
    console.print("  Send outbound event notifications to an external endpoint.")
    console.print(f"  {dim('Disabled by default.')}")

    if not prompt_yesno("Enable webhooks?", default=False):
        info("Webhooks will remain disabled")
        return

    updates.setdefault("webhook", {})
    updates["webhook"]["enabled"] = True

    url = prompt_text("Webhook URL (e.g. http://gateway:18789/hooks/agent)")
    if url:
        updates["webhook"]["url"] = url

    token = prompt_secret("Bearer token for webhook auth (optional)")
    if token:
        updates["webhook"]["token"] = token

    # Event selection
    all_events = ["state_change", "battery_alert", "conversation_complete"]
    console.print(f"\n  Events to send: {dim(', '.join(all_events))}")
    if prompt_yesno("Send all event types?", default=True):
        updates["webhook"]["events"] = all_events
    else:
        selected: list[str] = []
        for ev in all_events:
            if prompt_yesno(f"  Send {cyan(ev)} events?", default=True):
                selected.append(ev)
        updates["webhook"]["events"] = selected

    ok("Webhooks enabled")


def _section_power(updates: dict[str, Any]) -> None:
    """Section 7: Power management settings."""
    section("Power Management")
    console.print("  Configure idle timeouts and dimming behavior.")

    sleep_idle = prompt_int(
        "Sleep after idle (seconds):", default=300, lo=30, hi=3600
    )
    dim_idle = prompt_int(
        "Dim display after idle (seconds):", default=60, lo=10, hi=600
    )
    dim_brightness = prompt_int(
        "Dimmed brightness:", default=20, lo=0, hi=100
    )

    updates.setdefault("power", {})
    updates["power"]["sleep_after_idle"] = sleep_idle
    updates["power"]["dim_after_idle"] = dim_idle
    updates["power"]["dim_brightness"] = dim_brightness

    ok("Power management configured")


# ── Summary ─────────────────────────────────────────────────────────────────


def _print_summary(updates: dict[str, Any]) -> None:
    """Print a summary of all configured settings."""
    section("Configuration Summary")

    if not updates:
        info("No changes -- all defaults kept")
        return

    # Gateway
    gw = updates.get("gateway", {})
    if gw:
        kv("Gateway URL", gw.get("url", dim("(not set)")))
        kv("Gateway token", "****" if gw.get("token") else dim("(not set)"))
        kv("Default agent", gw.get("default_agent", "daemon"))

    # Voice
    audio = updates.get("audio", {})
    if audio:
        kv("TTS provider", audio.get("tts_provider", "edge"))
        kv("Volume", str(audio.get("volume", 80)))

    stt = updates.get("stt", {}).get("whisper", {})
    if stt.get("api_key"):
        kv("STT API key", "****")

    tts = updates.get("tts", {})
    if tts.get("openai", {}).get("api_key"):
        kv("OpenAI TTS key", "****")
        kv("OpenAI TTS voice", tts["openai"].get("voice", "nova"))
    if tts.get("elevenlabs", {}).get("api_key"):
        kv("ElevenLabs key", "****")

    # Display
    char = updates.get("character", {})
    if char:
        kv("Character", char.get("default", "voxel"))
        if char.get("default_style"):
            kv("Style", char["default_style"])

    display = updates.get("display", {})
    if display:
        kv("Brightness", str(display.get("brightness", 80)))

    # MCP
    mcp = updates.get("mcp", {})
    if mcp:
        kv("MCP server", "enabled" if mcp.get("enabled") else "disabled")
        if mcp.get("enabled"):
            kv("MCP transport", mcp.get("transport", "sse"))
            if mcp.get("port"):
                kv("MCP port", str(mcp["port"]))

    # Webhooks
    wh = updates.get("webhook", {})
    if wh:
        kv("Webhooks", "enabled" if wh.get("enabled") else "disabled")
        if wh.get("url"):
            kv("Webhook URL", wh["url"])

    # Power
    pwr = updates.get("power", {})
    if pwr:
        kv("Sleep after", f"{pwr.get('sleep_after_idle', 300)}s")
        kv("Dim after", f"{pwr.get('dim_after_idle', 60)}s")
        kv("Dim brightness", str(pwr.get("dim_brightness", 20)))


# ── Main wizard runner ──────────────────────────────────────────────────────


def run_wizard() -> int:
    """Run the interactive setup wizard. Returns 0 on success."""
    from hw.detect import IS_PI

    updates: dict[str, Any] = {}

    try:
        # 1. Welcome
        _section_welcome()

        # Define the sections and their runners
        sections = [
            ("Gateway Connection", _section_gateway),
            ("Voice Settings", _section_voice),
            ("Display & Character", _section_display),
            ("MCP Server", _section_mcp),
            ("Webhooks", _section_webhooks),
            ("Power Management", _section_power),
        ]

        for name, runner in sections:
            runner(updates)

        # Summary
        console.print()
        _print_summary(updates)

        # Save
        if updates:
            console.print()
            if prompt_yesno("Save these settings to config/local.yaml?", default=True):
                save_local_settings(updates)
                ok("Settings saved to config/local.yaml")
            else:
                warn("Settings discarded")
                console.print()
                return 0

        # Next steps
        console.print()
        section("Next Steps")
        if IS_PI:
            info("Reboot to apply all changes:")
            console.print(f"    {cyan('sudo reboot')}")
            console.print()
            info("After reboot, Voxel will auto-start with your new settings.")
        else:
            info("Start the display preview:")
            console.print(f"    {cyan('uv run dev')}")
            console.print()
            info("Or with the full voice pipeline:")
            console.print(f"    {cyan('uv run dev --server')}")
            console.print()
            info("Run diagnostics anytime:")
            console.print(f"    {cyan('voxel doctor')}")

        console.print()
        return 0

    except KeyboardInterrupt:
        console.print("\n")
        warn("Wizard cancelled -- no changes saved")
        console.print()
        return 1
