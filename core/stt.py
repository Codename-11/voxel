"""Speech-to-Text — Whisper API via OpenAI SDK."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from typing import Optional

log = logging.getLogger("voxel.core.stt")

# Cached OpenAI client — creating it is expensive (~2s first call)
_client = None
_client_key = ""


def _wav_info(wav_bytes: bytes) -> str:
    """Extract WAV details for logging."""
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.getnframes()
            duration = frames / rate if rate > 0 else 0
            return f"rate={rate}Hz ch={channels} duration={duration:.1f}s"
    except Exception:
        return "WAV details unavailable"


def _get_client(api_key: str):
    """Get or create a cached OpenAI client."""
    global _client, _client_key
    if _client is not None and _client_key == api_key:
        return _client
    from openai import OpenAI
    _client = OpenAI(api_key=api_key)
    _client_key = api_key
    return _client


async def transcribe(
    wav_bytes: bytes,
    api_key: str,
    model: str = "whisper-1",
    language: str = "en",
) -> Optional[str]:
    """Transcribe WAV audio bytes to text using the Whisper API.

    Runs the blocking OpenAI call in a thread so the event loop stays free.
    Returns the transcribed text, or None on failure.
    """
    if not wav_bytes or len(wav_bytes) < 1000:
        log.warning("Audio too short to transcribe (%d bytes)", len(wav_bytes) if wav_bytes else 0)
        return None

    log.info("STT: input %d bytes, %s", len(wav_bytes), _wav_info(wav_bytes))

    if not api_key:
        log.error("No OpenAI API key configured for STT")
        return None

    def _call() -> Optional[str]:
        try:
            client = _get_client(api_key)

            audio_file = io.BytesIO(wav_bytes)
            audio_file.name = "recording.wav"

            t0 = time.perf_counter()
            result = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language=language,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            text = result.text.strip() if result.text else ""
            if text:
                log.info("STT: transcribed %d chars in %.0fms: '%s'",
                         len(text), elapsed_ms, text[:80])
            else:
                log.warning("STT: returned empty text after %.0fms", elapsed_ms)
            return text or None
        except Exception as e:
            # Surface auth errors clearly so user knows the key is wrong
            err_type = type(e).__name__
            if "Authentication" in err_type or "auth" in str(e).lower():
                log.error("STT failed: invalid OpenAI API key — check stt.whisper.api_key")
            else:
                log.error("STT failed: %s (%s)", e, err_type)
            return None

    return await asyncio.to_thread(_call)
