"""Runtime settings loader/saver for Voxel."""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("voxel.config")

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_PATH = CONFIG_DIR / "default.yaml"
LOCAL_PATH = CONFIG_DIR / "local.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a top-level mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_settings() -> dict[str, Any]:
    """Load default settings merged with local overrides and env secrets."""
    local = _read_yaml(LOCAL_PATH)
    if local:
        log.debug("Local overrides loaded from %s (%d keys)", LOCAL_PATH, len(local))
    settings = _deep_merge(_read_yaml(DEFAULT_PATH), local)

    gateway = settings.setdefault("gateway", {})
    tts = settings.setdefault("tts", {})
    elevenlabs = tts.setdefault("elevenlabs", {})

    gateway_token = os.getenv("OPENCLAW_TOKEN")
    if gateway_token:
        gateway["token"] = gateway_token

    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    if elevenlabs_key:
        elevenlabs["api_key"] = elevenlabs_key

    # OpenAI API key for Whisper STT
    stt = settings.setdefault("stt", {})
    whisper = stt.setdefault("whisper", {})
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        whisper["api_key"] = openai_key

    return settings


def save_local_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into config/local.yaml and return the full settings."""
    local = _read_yaml(LOCAL_PATH)
    merged_local = _deep_merge(local, updates)

    with LOCAL_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged_local, f, sort_keys=False, allow_unicode=True)

    log.info("Settings saved: %s", list(updates.keys()))
    return load_settings()


def reset_to_defaults(sections: list[str] | None = None) -> dict[str, Any]:
    """Reset settings to defaults by removing keys from local.yaml.

    If sections is None or contains "all", deletes entire local.yaml (full reset).
    If sections is a list like ["gateway", "audio"], only removes those sections.
    Returns the new merged settings.
    """
    if not LOCAL_PATH.exists():
        return load_settings()

    if sections is None or "all" in sections:
        LOCAL_PATH.unlink()
        return load_settings()

    local = _read_yaml(LOCAL_PATH)
    for section in sections:
        local.pop(section, None)

    if local:
        with LOCAL_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(local, f, sort_keys=False, allow_unicode=True)
    else:
        # No keys left — remove the file entirely
        LOCAL_PATH.unlink()

    return load_settings()


def get_diff_from_defaults() -> dict[str, Any]:
    """Return a dict of only the settings that differ from defaults.

    Useful for showing what the user has customized.
    """
    defaults = _read_yaml(DEFAULT_PATH)
    local = _read_yaml(LOCAL_PATH)
    return _diff_dicts(defaults, local)


def _diff_dicts(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return keys from overrides that differ from defaults (recursively)."""
    diff: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in defaults:
            diff[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(defaults.get(key), dict):
            nested = _diff_dicts(defaults[key], value)
            if nested:
                diff[key] = nested
        elif value != defaults[key]:
            diff[key] = copy.deepcopy(value)
    return diff


def export_backup() -> dict[str, Any]:
    """Export a complete backup of user configuration.

    Returns a dict containing:
      - local_settings: contents of local.yaml (user overrides)
      - setup_state: contents of .setup-state (onboarding flags)
      - version: backup format version
      - timestamp: ISO format creation time

    Secrets (tokens, API keys, passwords) are included so the backup
    is fully restorable. The web UI should warn the user about this.
    """
    import datetime

    backup = {
        "version": 1,
        "timestamp": datetime.datetime.now().isoformat(),
        "local_settings": _read_yaml(LOCAL_PATH),
    }

    # Setup state
    setup_path = CONFIG_DIR / ".setup-state"
    if setup_path.exists():
        backup["setup_state"] = _read_yaml(setup_path)
    else:
        backup["setup_state"] = {}

    return backup


def import_backup(backup: dict[str, Any]) -> dict[str, Any]:
    """Import a backup, replacing current local settings and setup state.

    Args:
        backup: Dict from export_backup() with version, local_settings, setup_state.

    Returns the new merged settings.

    Raises ValueError if the backup format is invalid.
    """
    if not isinstance(backup, dict) or "version" not in backup:
        raise ValueError("Invalid backup format — missing version field")

    if backup["version"] != 1:
        raise ValueError(f"Unsupported backup version: {backup['version']}")

    # Restore local settings
    local = backup.get("local_settings", {})
    if isinstance(local, dict) and local:
        with LOCAL_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(local, f, sort_keys=False, allow_unicode=True)
        log.info("Backup restored: local settings (%d keys)", len(local))

    # Restore setup state
    setup_state = backup.get("setup_state", {})
    setup_path = CONFIG_DIR / ".setup-state"
    if isinstance(setup_state, dict) and setup_state:
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        with setup_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(setup_state, f, default_flow_style=False)
        log.info("Backup restored: setup state")

    return load_settings()


def factory_reset() -> dict[str, Any]:
    """Full factory reset — deletes all user configuration.

    Removes:
      - config/local.yaml (user settings)
      - config/.setup-state (onboarding flags)

    Returns the default settings (no overrides).
    Does NOT restart services — caller should handle that.
    """
    # Remove local settings
    if LOCAL_PATH.exists():
        LOCAL_PATH.unlink()
        log.warning("Factory reset: deleted local.yaml")

    # Remove setup state
    setup_path = CONFIG_DIR / ".setup-state"
    if setup_path.exists():
        setup_path.unlink()
        log.warning("Factory reset: deleted .setup-state")

    log.warning("Factory reset complete — device will need reconfiguration")
    return load_settings()


def validate_settings(settings: dict[str, Any]) -> list[str]:
    """Return a list of warnings about the current settings.

    Checks for missing tokens/keys and potentially misconfigured values.
    """
    warnings: list[str] = []

    gw = settings.get("gateway", {})
    if not gw.get("token"):
        warnings.append("Gateway token not set — AI chat will not work")

    stt = settings.get("stt", {}).get("whisper", {})
    if not stt.get("api_key"):
        warnings.append("OpenAI API key not set — voice input will not work")

    audio = settings.get("audio", {})
    tts_provider = audio.get("tts_provider", "edge")
    if tts_provider == "openai":
        openai_tts_key = settings.get("tts", {}).get("openai", {}).get("api_key", "")
        openai_stt_key = stt.get("api_key", "")
        if not openai_tts_key and not openai_stt_key:
            warnings.append("OpenAI API key not set — TTS won't work (shares key with STT)")
    elif tts_provider == "elevenlabs":
        el = settings.get("tts", {}).get("elevenlabs", {})
        if not el.get("api_key"):
            warnings.append("ElevenLabs API key not set — switch to Edge TTS or add key")

    gw_url = gw.get("url", "")
    if not gw_url:
        warnings.append("Gateway URL not set")

    return warnings
