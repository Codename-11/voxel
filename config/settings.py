"""Runtime settings loader/saver for Voxel."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

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
    settings = _deep_merge(_read_yaml(DEFAULT_PATH), _read_yaml(LOCAL_PATH))

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
        yaml.safe_dump(merged_local, f, sort_keys=False, allow_unicode=False)

    return load_settings()
