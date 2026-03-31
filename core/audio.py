"""Audio — laptop mic/speakers (desktop) or Whisplay HAT (Pi)."""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Optional

import numpy as np
from hw.detect import IS_PI

log = logging.getLogger(f"voxel.{__name__}")

# Audio config
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT_WIDTH = 2  # 16-bit

# Pi ALSA device for Whisplay HAT (WM8960)
# Use named device (reliable across reboots), fallback to card 0
_PI_DEVICE = "hw:wm8960soundcard"
_PI_DEVICE_FALLBACK = "hw:0,0"

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

    log.info("Audio: initializing (platform=%s)", "Pi" if IS_PI else "desktop")

    # Try PyAudio first
    try:
        import pyaudio  # type: ignore
        _pa = pyaudio.PyAudio()
        _pyaudio_available = True
        device_count = _pa.get_device_count()
        log.info("Audio: PyAudio initialized (%s, %d devices found)",
                 "Pi HAT" if IS_PI else "desktop", device_count)
        if IS_PI:
            in_dev = _get_pi_input_device()
            out_dev = _get_pi_output_device()
            log.info("Audio: Pi input device=%s, output device=%s",
                     _device_name(in_dev) if in_dev is not None else "default",
                     _device_name(out_dev) if out_dev is not None else "default")
        return
    except ImportError:
        log.debug("PyAudio not available (not installed), trying sounddevice...")
    except Exception as e:
        log.warning("PyAudio init failed: %s, trying sounddevice...", e)

    # Fallback: sounddevice
    try:
        import sounddevice  # type: ignore  # noqa: F401
        _sounddevice_available = True
        log.info("Audio: sounddevice initialized (%s)", "Pi HAT" if IS_PI else "desktop")
        return
    except ImportError:
        log.debug("sounddevice not available (not installed)")

    log.warning("No audio backend available (install PyAudio or sounddevice). Audio disabled.")


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
        input_dev = _get_pi_input_device() if IS_PI else None
        kwargs: dict = dict(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=_pyaudio_record_callback,
        )
        if input_dev is not None:
            kwargs["input_device_index"] = input_dev

        _stream_in = _pa.open(**kwargs)
        _stream_in.start_stream()
        log.info("Recording started (PyAudio, device=%s, rate=%dHz, ch=%d)",
                 _device_name(input_dev) if input_dev is not None else "default",
                 SAMPLE_RATE, CHANNELS)

    elif _sounddevice_available:
        import sounddevice as sd  # type: ignore
        device = _get_sd_device("input")
        _stream_in = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK,
            device=device,
            callback=_sounddevice_record_callback,
        )
        _stream_in.start()
        log.info("Recording started (sounddevice, device=%s, rate=%dHz, ch=%d)",
                 device or "default", SAMPLE_RATE, CHANNELS)
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
    num_frames = len(_recording_frames)
    raw_size = sum(len(f) for f in _recording_frames)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(FORMAT_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(_recording_frames))

    data = buf.getvalue()
    duration = raw_size / (SAMPLE_RATE * CHANNELS * FORMAT_WIDTH) if SAMPLE_RATE > 0 else 0
    log.info("Recording stopped — %d bytes, %d chunks, ~%.1fs duration",
             len(data), num_frames, duration)
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
                n_frames = wf.getnframes()
                # Some APIs (OpenAI) set nframes to INT32_MAX; calculate from data size
                if n_frames > 1_000_000_000 and rate > 0:
                    sw = wf.getsampwidth()
                    n_frames = max(0, len(data) - 44) // (ch * sw) if sw > 0 else 0
                duration = n_frames / rate if rate > 0 else 0
                backend = "PyAudio" if _pyaudio_available else "sounddevice" if _sounddevice_available else "none"
                log.info("Playback starting (%s): rate=%dHz, ch=%d, duration=%.1fs, %d bytes",
                         backend, rate, ch, duration, len(data))

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
                    device = _get_sd_device("output")
                    sd.play(arr, samplerate=rate, device=device)
                    # Track amplitude per-chunk during playback
                    total_samples = len(arr)
                    samples_per_chunk = CHUNK
                    chunk_idx = 0
                    while sd.get_stream().active and not _stop_playback.is_set():
                        # Estimate current playback position
                        pos = min(chunk_idx * samples_per_chunk, total_samples - 1)
                        end = min(pos + samples_per_chunk, total_samples)
                        if pos < total_samples:
                            chunk_data = arr[pos:end].tobytes()
                            _update_amplitude(chunk_data)
                        chunk_idx += 1
                        threading.Event().wait(0.05)
                    if _stop_playback.is_set():
                        sd.stop()

        except Exception as e:
            log.error("Audio playback error: %s (type: %s)", e, type(e).__name__)
        finally:
            with _amp_lock:
                _amplitude = 0.0
            _playback_done.set()
            log.debug("Playback finished")

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
        return float(_amplitude)


_amp_log_counter = 0


def _update_amplitude(frame_bytes: bytes) -> None:
    global _amplitude, _amp_log_counter
    try:
        arr = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(arr ** 2))
        # Normalize: int16 max = 32768
        val = min(rms / 32768.0 * 4.0, 1.0)  # *4 for perceptual boost
        with _amp_lock:
            _amplitude = val
        # Log amplitude at debug level every ~20 frames (~1s at 20Hz)
        _amp_log_counter += 1
        if _amp_log_counter % 20 == 0:
            log.debug("Amplitude: %.3f (rms=%.0f)", val, rms)
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
                log.debug("Pi input device found: index=%d, name=%s", i, info["name"])
                return i
        log.warning("No WM8960 input device found among %d devices", _pa.get_device_count())
    except Exception as e:
        log.debug("Error scanning Pi input devices: %s", e)
    return None


def _get_pi_output_device() -> Optional[int]:
    """Find PyAudio device index for Whisplay HAT output."""
    try:
        import pyaudio  # type: ignore
        for i in range(_pa.get_device_count()):
            info = _pa.get_device_info_by_index(i)
            if "wm8960" in info["name"].lower() and info["maxOutputChannels"] > 0:
                log.debug("Pi output device found: index=%d, name=%s", i, info["name"])
                return i
        log.warning("No WM8960 output device found among %d devices", _pa.get_device_count())
    except Exception as e:
        log.debug("Error scanning Pi output devices: %s", e)
    return None


def _device_name(index: Optional[int]) -> str:
    """Get a human-readable device name for a PyAudio device index."""
    if index is None or _pa is None:
        return "unknown"
    try:
        info = _pa.get_device_info_by_index(index)
        return f"#{index} '{info['name']}'"
    except Exception:
        return f"#{index}"


def _get_sd_device(direction: str = "input") -> Optional[str]:
    """Find the sounddevice device string for the WM8960 on Pi.

    Tries the named ALSA device first, then scans available devices
    for 'wm8960', and falls back to the generic hw:0,0.
    """
    if not IS_PI:
        return None
    try:
        import sounddevice as sd  # type: ignore
        # Try named device first
        try:
            sd.check_input_parameters(device=_PI_DEVICE) if direction == "input" else \
                sd.check_output_parameters(device=_PI_DEVICE)
            log.debug("sounddevice: using named device %s", _PI_DEVICE)
            return _PI_DEVICE
        except Exception:
            pass
        # Scan for wm8960 in device list
        for dev in sd.query_devices():
            max_ch = dev.get(f"max_{direction}_channels", 0)
            if max_ch > 0 and "wm8960" in dev["name"].lower():
                log.debug("sounddevice: found WM8960 device: %s", dev["name"])
                return dev["name"]
        # Fallback
        log.debug("sounddevice: WM8960 not found by name, using fallback %s", _PI_DEVICE_FALLBACK)
        return _PI_DEVICE_FALLBACK
    except Exception as e:
        log.debug("sounddevice device scan failed: %s", e)
        return _PI_DEVICE_FALLBACK


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
