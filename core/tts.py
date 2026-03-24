"""Text-to-Speech — edge-tts (free) and ElevenLabs (premium)."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("voxel.core.tts")

# Default voices
_EDGE_DEFAULT = "en-US-ChristopherNeural"


async def synthesize(
    text: str,
    voice: str = "",
    provider: str = "edge",
    settings: Optional[dict] = None,
) -> Optional[bytes]:
    """Synthesize text to WAV audio bytes.

    Args:
        text: The text to speak.
        voice: Voice name/ID (provider-specific).
        provider: "edge" (free, default) or "elevenlabs" (premium).
        settings: Full settings dict for API keys and config.

    Returns WAV bytes suitable for audio.play_audio(), or None on failure.
    """
    if not text:
        return None

    settings = settings or {}

    if provider == "elevenlabs":
        return await _elevenlabs(text, voice, settings)
    else:
        return await _edge_tts(text, voice, settings)


async def _edge_tts(text: str, voice: str, settings: dict) -> Optional[bytes]:
    """Synthesize using edge-tts (free, async-native)."""
    try:
        import edge_tts

        voice = voice or settings.get("tts", {}).get("edge", {}).get("voice", _EDGE_DEFAULT)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)

            wav_bytes = await _mp3_to_wav(tmp_path)
            if wav_bytes:
                log.info("TTS (edge): %d bytes, voice=%s", len(wav_bytes), voice)
            return wav_bytes
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        log.error("edge-tts failed: %s", e)
        return None


async def _elevenlabs(text: str, voice: str, settings: dict) -> Optional[bytes]:
    """Synthesize using ElevenLabs API (premium, blocking HTTP)."""
    el_settings = settings.get("tts", {}).get("elevenlabs", {})
    api_key = el_settings.get("api_key", "")
    model = el_settings.get("model", "eleven_turbo_v2_5")

    if not api_key:
        log.warning("ElevenLabs API key not configured, falling back to edge-tts")
        return await _edge_tts(text, voice, settings)

    if not voice:
        voice = "charlie"  # Default ElevenLabs voice

    def _call() -> Optional[bytes]:
        try:
            import requests

            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": model,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content  # MP3 bytes
        except Exception as e:
            log.error("ElevenLabs API failed: %s", e)
            return None

    mp3_bytes = await asyncio.to_thread(_call)
    if not mp3_bytes:
        return None

    # Convert MP3 to WAV
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = tmp.name

    try:
        wav_bytes = await _mp3_to_wav(tmp_path)
        if wav_bytes:
            log.info("TTS (elevenlabs): %d bytes, voice=%s", len(wav_bytes), voice)
        return wav_bytes
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def _mp3_to_wav(mp3_path: str) -> Optional[bytes]:
    """Convert MP3 file to 16kHz mono WAV bytes using ffmpeg."""
    def _convert() -> Optional[bytes]:
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", mp3_path,
                    "-f", "wav", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                log.error("ffmpeg failed: %s", result.stderr.decode()[:200])
                return None
            return result.stdout
        except FileNotFoundError:
            log.error("ffmpeg not found — install it: sudo apt install ffmpeg")
            return None
        except Exception as e:
            log.error("MP3→WAV conversion failed: %s", e)
            return None

    return await asyncio.to_thread(_convert)
