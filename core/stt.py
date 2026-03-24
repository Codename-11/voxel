"""Speech-to-Text — Whisper API via OpenAI SDK."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

log = logging.getLogger("voxel.core.stt")


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
        log.warning("Audio too short to transcribe (%d bytes)", len(wav_bytes))
        return None

    if not api_key:
        log.error("No OpenAI API key configured for STT")
        return None

    def _call() -> Optional[str]:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)

            # Wrap bytes in a file-like object with a .name attribute
            audio_file = io.BytesIO(wav_bytes)
            audio_file.name = "recording.wav"

            result = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language=language,
            )
            text = result.text.strip() if result.text else ""
            if text:
                log.info("STT: '%s'", text[:80])
            else:
                log.warning("STT returned empty text")
            return text or None
        except Exception as e:
            log.error("STT failed: %s", e)
            return None

    return await asyncio.to_thread(_call)
