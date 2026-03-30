"""Text-to-Speech — edge-tts (free), OpenAI (quality), and ElevenLabs (premium)."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger("voxel.core.tts")

# Default voices
_EDGE_DEFAULT = "en-US-ChristopherNeural"

# OpenAI TTS voices (available for all models)
OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
OPENAI_MODELS = ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]
_OPENAI_DEFAULT_VOICE = "nova"
_OPENAI_DEFAULT_MODEL = "tts-1"


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
        provider: "edge" (free), "openai" (quality), or "elevenlabs" (premium).
        settings: Full settings dict for API keys and config.

    Returns WAV bytes suitable for audio.play_audio(), or None on failure.
    """
    if not text:
        log.debug("TTS: empty text, skipping synthesis")
        return None

    settings = settings or {}
    log.info("TTS: synthesizing %d chars with provider=%s, requested_voice=%s",
             len(text), provider, voice or "(default)")

    if provider == "openai":
        return await _openai_tts(text, voice, settings)
    elif provider == "elevenlabs":
        return await _elevenlabs(text, voice, settings)
    else:
        return await _edge_tts(text, voice, settings)


async def _openai_tts(text: str, voice: str, settings: dict) -> Optional[bytes]:
    """Synthesize using OpenAI TTS API (returns WAV directly, no conversion needed)."""
    tts_cfg = settings.get("tts", {}).get("openai", {})
    # Share API key with STT (same OpenAI account)
    api_key = tts_cfg.get("api_key", "") or settings.get("stt", {}).get("whisper", {}).get("api_key", "")
    model = tts_cfg.get("model", _OPENAI_DEFAULT_MODEL)

    log.debug("TTS (openai): api_key=%s, model=%s", "present" if api_key else "MISSING", model)

    if not api_key:
        log.warning("OpenAI API key not configured, falling back to edge-tts")
        return await _edge_tts(text, voice, settings)

    # Resolve voice: use agent voice if it's a valid OpenAI voice, else config default
    original_voice = voice
    if voice not in OPENAI_VOICES:
        voice = tts_cfg.get("voice", _OPENAI_DEFAULT_VOICE)
    if voice not in OPENAI_VOICES:
        voice = _OPENAI_DEFAULT_VOICE
    if original_voice and original_voice != voice:
        log.debug("TTS (openai): voice resolved %s -> %s (not a valid OpenAI voice)", original_voice, voice)

    def _call() -> Optional[bytes]:
        try:
            from core.stt import _get_client

            log.debug("TTS (openai): calling API with voice=%s, model=%s, text=%d chars", voice, model, len(text))
            t0 = time.perf_counter()
            client = _get_client(api_key)
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format="wav",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            wav_bytes = response.content
            if wav_bytes:
                duration_info = _wav_duration_info(wav_bytes)
                log.info("TTS (openai): %d bytes, voice=%s, model=%s, %s, API call took %.0fms",
                         len(wav_bytes), voice, model, duration_info, elapsed_ms)
            else:
                log.warning("TTS (openai): API returned empty content after %.0fms", elapsed_ms)
            return wav_bytes
        except Exception as e:
            err_type = type(e).__name__
            if "Authentication" in err_type or "auth" in str(e).lower():
                log.error("OpenAI TTS failed: invalid API key — check config")
            else:
                log.error("OpenAI TTS failed: %s (%s)", e, err_type)
            return None

    result = await asyncio.to_thread(_call)
    if not result:
        log.warning("OpenAI TTS produced no audio, falling back to edge-tts")
        return await _edge_tts(text, voice, settings)
    return result


async def _edge_tts(text: str, voice: str, settings: dict) -> Optional[bytes]:
    """Synthesize using edge-tts (free, async-native)."""
    try:
        import edge_tts

        voice = voice or settings.get("tts", {}).get("edge", {}).get("voice", _EDGE_DEFAULT)
        log.debug("TTS (edge): synthesizing %d chars with voice=%s", len(text), voice)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            t0 = time.perf_counter()
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.debug("TTS (edge): edge-tts synthesis took %.0fms", elapsed_ms)

            wav_bytes = await _mp3_to_wav(tmp_path)
            if wav_bytes:
                duration_info = _wav_duration_info(wav_bytes)
                log.info("TTS (edge): %d bytes, voice=%s, %s, total %.0fms",
                         len(wav_bytes), voice, duration_info, (time.perf_counter() - t0) * 1000)
            else:
                log.warning("TTS (edge): MP3-to-WAV conversion produced no output")
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

    log.debug("TTS (elevenlabs): api_key=%s, model=%s", "present" if api_key else "MISSING", model)

    if not api_key:
        log.warning("ElevenLabs API key not configured, falling back to edge-tts")
        return await _edge_tts(text, voice, settings)

    if not voice:
        voice = "charlie"  # Default ElevenLabs voice
    log.debug("TTS (elevenlabs): synthesizing %d chars with voice=%s, model=%s", len(text), voice, model)

    def _call() -> Optional[bytes]:
        try:
            import requests

            t0 = time.perf_counter()
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
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.debug("TTS (elevenlabs): API returned %d bytes in %.0fms", len(resp.content), elapsed_ms)
            return resp.content  # MP3 bytes
        except Exception as e:
            log.error("ElevenLabs API failed: %s", e)
            return None

    mp3_bytes = await asyncio.to_thread(_call)
    if not mp3_bytes:
        log.warning("ElevenLabs TTS produced no audio, falling back to edge-tts")
        return await _edge_tts(text, voice, settings)

    # Convert MP3 to WAV
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = tmp.name

    try:
        wav_bytes = await _mp3_to_wav(tmp_path)
        if wav_bytes:
            duration_info = _wav_duration_info(wav_bytes)
            log.info("TTS (elevenlabs): %d bytes, voice=%s, %s", len(wav_bytes), voice, duration_info)
        else:
            log.warning("TTS (elevenlabs): MP3-to-WAV conversion produced no output")
        return wav_bytes
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _wav_duration_info(wav_bytes: bytes) -> str:
    """Extract WAV details (sample rate, channels, duration) for logging."""
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            frames = wf.getnframes()
            # Some APIs (OpenAI) set nframes to INT32_MAX; calculate from data size
            if frames > 1_000_000_000 and rate > 0 and width > 0 and channels > 0:
                data_bytes = len(wav_bytes) - 44  # WAV header is typically 44 bytes
                frames = max(0, data_bytes) // (channels * width)
            duration = frames / rate if rate > 0 else 0
            return f"rate={rate}Hz ch={channels} duration={duration:.1f}s"
    except Exception:
        return "WAV details unavailable"


async def _mp3_to_wav(mp3_path: str) -> Optional[bytes]:
    """Convert MP3 file to 16kHz mono WAV bytes.

    Tries miniaudio (pure Python, no external deps) first,
    then falls back to ffmpeg subprocess.
    """
    def _convert() -> Optional[bytes]:
        mp3_bytes = Path(mp3_path).read_bytes()

        # Try miniaudio first (no ffmpeg needed)
        try:
            return _mp3_bytes_to_wav(mp3_bytes)
        except Exception as e:
            log.debug("miniaudio decode failed, trying ffmpeg: %s", e)

        # Fallback: ffmpeg subprocess
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
            log.error("No audio decoder available — install miniaudio or ffmpeg")
            return None
        except Exception as e:
            log.error("MP3→WAV conversion failed: %s", e)
            return None

    return await asyncio.to_thread(_convert)


def _mp3_bytes_to_wav(mp3_bytes: bytes) -> bytes:
    """Decode MP3 bytes to 16kHz mono WAV using miniaudio."""
    import miniaudio
    import wave

    decoded = miniaudio.decode(
        mp3_bytes,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=16000,
    )

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(decoded.samples.tobytes())

    return buf.getvalue()
