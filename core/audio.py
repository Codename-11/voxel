"""Audio — laptop mic/speakers (desktop) or Whisplay HAT (Pi)."""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Optional

import numpy as np
from hardware.platform import IS_PI

log = logging.getLogger(f"voxel.{__name__}")

# Audio config
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT_WIDTH = 2  # 16-bit

# Pi ALSA device for Whisplay HAT (WM8960)
_PI_DEVICE = "hw:0,0"

_pa = None           # PyAudio instance
_stream_in = None    # Recording stream
_stream_out = None   # Playback stream
_recording_frames: list[bytes] = []
_is_recording = False
_amplitude: float = 0.0
_amp_lock = threading.Lock()

# Playback control
_playback_done = threading.Event()
_stop_playback = threading.Event()
_playback_done.set()  # Not playing initially

_sounddevice_available = False
_pyaudio_available = False


def init() -> None:
    """Initialize audio subsystem."""
    global _pa, _pyaudio_available, _sounddevice_available

    # Try PyAudio first
    try:
        import pyaudio  # type: ignore
        _pa = pyaudio.PyAudio()
        _pyaudio_available = True
        log.info(f"Audio: PyAudio initialized ({'Pi HAT' if IS_PI else 'desktop'})")
        return
    except ImportError:
        log.debug("PyAudio not available, trying sounddevice...")

    # Fallback: sounddevice
    try:
        import sounddevice  # type: ignore  # noqa: F401
        _sounddevice_available = True
        log.info(f"Audio: sounddevice initialized ({'Pi HAT' if IS_PI else 'desktop'})")
        return
    except ImportError:
        log.warning("No audio backend available (PyAudio or sounddevice). Audio disabled.")


def start_recording() -> None:
    """Start recording audio from mic."""
    global _stream_in, _recording_frames, _is_recording

    if _is_recording:
        log.warning("Already recording.")
        return

    _recording_frames = []
    _is_recording = True

    if _pyaudio_available:
        import pyaudio  # type: ignore
        kwargs: dict = dict(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=_pyaudio_record_callback,
        )
        if IS_PI:
            kwargs["input_device_index"] = _get_pi_input_device()

        _stream_in = _pa.open(**kwargs)
        _stream_in.start_stream()
        log.info("Recording started (PyAudio)")

    elif _sounddevice_available:
        import sounddevice as sd  # type: ignore
        device = _PI_DEVICE if IS_PI else None
        _stream_in = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK,
            device=device,
            callback=_sounddevice_record_callback,
        )
        _stream_in.start()
        log.info("Recording started (sounddevice)")
    else:
        log.warning("Audio not initialized — cannot record")
        _is_recording = False


def stop_recording() -> bytes:
    """Stop recording and return WAV bytes."""
    global _stream_in, _is_recording

    if not _is_recording:
        log.warning("Not recording.")
        return b""

    _is_recording = False

    if _stream_in is not None:
        try:
            _stream_in.stop()
            _stream_in.close()
        except Exception:
            pass
        _stream_in = None

    # Pack frames into WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(FORMAT_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(_recording_frames))

    data = buf.getvalue()
    log.info(f"Recording stopped — {len(data)} bytes captured")
    return data


def play_audio(data: bytes) -> None:
    """Play WAV audio bytes through speaker. Non-blocking (runs in a thread)."""
    if not data:
        return

    _playback_done.clear()
    _stop_playback.clear()

    def _play():
        global _amplitude
        try:
            buf = io.BytesIO(data)
            with wave.open(buf, "rb") as wf:
                rate = wf.getframerate()
                ch = wf.getnchannels()

                if _pyaudio_available:
                    import pyaudio  # type: ignore
                    kwargs: dict = dict(
                        format=_pa.get_format_from_width(wf.getsampwidth()),
                        channels=ch,
                        rate=rate,
                        output=True,
                    )
                    if IS_PI:
                        kwargs["output_device_index"] = _get_pi_output_device()
                    stream = _pa.open(**kwargs)
                    chunk = CHUNK
                    frame = wf.readframes(chunk)
                    while frame and not _stop_playback.is_set():
                        _update_amplitude(frame)
                        stream.write(frame)
                        frame = wf.readframes(chunk)
                    stream.stop_stream()
                    stream.close()

                elif _sounddevice_available:
                    import sounddevice as sd  # type: ignore
                    import numpy as np
                    frames = wf.readframes(wf.getnframes())
                    arr = np.frombuffer(frames, dtype=np.int16).reshape(-1, ch)
                    _update_amplitude(frames)
                    device = _PI_DEVICE if IS_PI else None
                    sd.play(arr, samplerate=rate, device=device)
                    # Poll for completion with stop check
                    while sd.get_stream().active and not _stop_playback.is_set():
                        threading.Event().wait(0.05)
                    if _stop_playback.is_set():
                        sd.stop()

        except Exception as e:
            log.error(f"Audio playback error: {e}")
        finally:
            with _amp_lock:
                _amplitude = 0.0
            _playback_done.set()

    t = threading.Thread(target=_play, daemon=True)
    t.start()


def is_playing() -> bool:
    """Return True if audio is currently being played back."""
    return not _playback_done.is_set()


def stop_playback() -> None:
    """Signal the playback thread to stop. Non-blocking."""
    _stop_playback.set()


def get_amplitude() -> float:
    """Return current playback amplitude (0.0–1.0) for mouth sync."""
    with _amp_lock:
        return _amplitude


def _update_amplitude(frame_bytes: bytes) -> None:
    global _amplitude
    try:
        arr = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(arr ** 2))
        # Normalize: int16 max = 32768
        val = min(rms / 32768.0 * 4.0, 1.0)  # *4 for perceptual boost
        with _amp_lock:
            _amplitude = val
    except Exception:
        pass


def _pyaudio_record_callback(in_data, frame_count, time_info, status):
    if _is_recording:
        _recording_frames.append(in_data)
    import pyaudio  # type: ignore
    return (None, pyaudio.paContinue)


def _sounddevice_record_callback(indata, frames, time, status):
    if _is_recording:
        _recording_frames.append(bytes(indata))


def _get_pi_input_device() -> Optional[int]:
    """Find PyAudio device index for Whisplay HAT input."""
    try:
        import pyaudio  # type: ignore
        for i in range(_pa.get_device_count()):
            info = _pa.get_device_info_by_index(i)
            if "wm8960" in info["name"].lower() and info["maxInputChannels"] > 0:
                return i
    except Exception:
        pass
    return None


def _get_pi_output_device() -> Optional[int]:
    """Find PyAudio device index for Whisplay HAT output."""
    try:
        import pyaudio  # type: ignore
        for i in range(_pa.get_device_count()):
            info = _pa.get_device_info_by_index(i)
            if "wm8960" in info["name"].lower() and info["maxOutputChannels"] > 0:
                return i
    except Exception:
        pass
    return None


def cleanup() -> None:
    """Release audio resources."""
    global _pa

    if _is_recording:
        stop_recording()

    if _pa is not None:
        try:
            _pa.terminate()
        except Exception:
            pass
        _pa = None

    log.info("Audio cleaned up.")
