"""Audio — laptop mic/speakers (desktop) or Whisplay HAT (Pi)."""

from __future__ import annotations

import io
import logging
import threading
import wave
from pathlib import Path
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
# Use named device (reliable across reboots), fallback to card 0.
# plughw: adds ALSA format/rate conversion and often works when hw: doesn't,
# especially when asound.conf is misconfigured for capture.
_PI_DEVICE = "hw:wm8960soundcard"
_PI_DEVICE_FALLBACK = "hw:0,0"
_PI_DEVICE_PLUG = "plughw:0,0"
_PI_DEVICE_PLUG_NAMED = "plughw:wm8960soundcard"
# ALSA PCM names from asound.conf (Whisplay driver)
# These use dsnoop for shared capture access
_PI_CAPTURE_PCM = "capture"       # plug → dsnoop (from asound.conf)
_PI_PLAYBACK_PCM = "playback"     # plug → dmix (from asound.conf)

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

    # On Pi, ensure ALSA config has capture device definitions.
    # The Whisplay HAT driver's asound.conf may only define playback,
    # which causes PortAudio/sounddevice to see 0 input channels.
    if IS_PI:
        _ensure_alsa_capture_config()

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
        if IS_PI:
            in_dev = _get_sd_device("input")
            out_dev = _get_sd_device("output")
            log.info("Audio: sounddevice input=%s, output=%s", in_dev, out_dev)
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
        # On Pi, use the ALSA default device for recording. The asound.conf
        # (installed by Whisplay driver) routes the default capture through
        # dsnoop for shared mic access. We use "default" because sounddevice/
        # PortAudio doesn't resolve custom ALSA PCM names like "capture" —
        # it only sees devices from its internal enumeration.
        # The ambient monitor is paused before we get here (via WebSocket
        # ambient_control message), so the device should be available.
        if IS_PI:
            device = "default"
            log.info("Recording: using ALSA default device (Pi, routed via asound.conf)")
        else:
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
    """Find PyAudio device index for Whisplay HAT input.

    First scans for a WM8960 device with input channels > 0.
    If none found (common when asound.conf lacks capture definitions),
    falls back to any device with 'wm8960' in the name and attempts
    to use it anyway — PyAudio may succeed where the channel query
    returned 0 if the ALSA config was repaired after the initial scan.
    Also tries device index 0 as last resort.
    """
    try:
        import pyaudio  # type: ignore
        wm8960_index = None
        for i in range(_pa.get_device_count()):
            info = _pa.get_device_info_by_index(i)
            name_lower = info["name"].lower()
            if "wm8960" in name_lower and info["maxInputChannels"] > 0:
                log.debug("Pi input device found: index=%d, name=%s", i, info["name"])
                return i
            # Remember WM8960 even with 0 input channels (broken asound.conf)
            if "wm8960" in name_lower and wm8960_index is None:
                wm8960_index = i

        # If we found WM8960 but it reported 0 input channels, try it anyway.
        # After _ensure_alsa_capture_config() runs, the device may work even
        # though the channel count was cached as 0 during the initial scan.
        if wm8960_index is not None:
            log.info("Pi input: WM8960 found at index %d with 0 reported input channels "
                     "(asound.conf may have been repaired) — using it anyway", wm8960_index)
            return wm8960_index

        # Try device 0 as absolute fallback
        if _pa.get_device_count() > 0:
            info0 = _pa.get_device_info_by_index(0)
            if info0["maxInputChannels"] > 0:
                log.info("Pi input: using device 0 (%s) as fallback", info0["name"])
                return 0

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

    PortAudio relies on ALSA config to discover device capabilities.
    The Whisplay HAT driver installs an asound.conf that may not define
    capture devices, causing PortAudio to report max_input_channels=0
    even though the hardware supports recording (arecord -l shows it).

    Strategy for input devices:
    1. Try named ALSA device (hw:wm8960soundcard)
    2. Scan query_devices() for WM8960 with matching channels
    3. Try plughw: variants (adds ALSA format conversion, bypasses
       broken asound.conf default device definitions)
    4. Fall back to hw:0,0

    For output, the standard flow usually works since asound.conf
    typically defines playback correctly.
    """
    if not IS_PI:
        return None
    try:
        import sounddevice as sd  # type: ignore
        check_fn = sd.check_input_parameters if direction == "input" else sd.check_output_parameters

        # 1. Try named device
        try:
            check_fn(device=_PI_DEVICE, channels=CHANNELS, samplerate=SAMPLE_RATE)
            log.debug("sounddevice: using named device %s for %s", _PI_DEVICE, direction)
            return _PI_DEVICE
        except Exception:
            pass

        # 2. Scan for wm8960 in device list with matching channels
        for dev in sd.query_devices():
            max_ch = dev.get(f"max_{direction}_channels", 0)
            if max_ch > 0 and "wm8960" in dev["name"].lower():
                log.debug("sounddevice: found WM8960 device: %s (%s ch=%d)",
                          dev["name"], direction, max_ch)
                return dev["name"]

        # 3. Try plughw: variants — these bypass asound.conf device
        #    definitions and talk to the hardware through ALSA's plug
        #    layer, which adds automatic format/rate/channel conversion.
        #    This is the key fix for the Whisplay HAT where asound.conf
        #    defines playback devices (dmix/softvol) but not capture
        #    devices (dsnoop), causing PortAudio to see 0 input channels.
        for plug_dev in (_PI_DEVICE_PLUG_NAMED, _PI_DEVICE_PLUG):
            try:
                check_fn(device=plug_dev, channels=CHANNELS, samplerate=SAMPLE_RATE)
                log.info("sounddevice: using plughw device %s for %s "
                         "(asound.conf may be missing capture definition)",
                         plug_dev, direction)
                return plug_dev
            except Exception:
                pass

        # 4. Try device index 0 directly (bypasses ALSA name resolution)
        try:
            check_fn(device=0, channels=CHANNELS, samplerate=SAMPLE_RATE)
            log.info("sounddevice: using device index 0 for %s", direction)
            return 0
        except Exception:
            pass

        # 5. Last resort
        log.warning("sounddevice: no working %s device found, using fallback %s",
                     direction, _PI_DEVICE_FALLBACK)
        return _PI_DEVICE_FALLBACK
    except Exception as e:
        log.debug("sounddevice device scan failed: %s", e)
        return _PI_DEVICE_FALLBACK


def _ensure_alsa_capture_config() -> None:
    """Ensure ALSA config includes capture device definitions for WM8960.

    The Whisplay HAT driver installer drops an /etc/asound.conf that
    typically defines playback devices (dmix, softvol) but may omit
    capture devices (dsnoop). When capture is missing, PortAudio
    (used by both PyAudio and sounddevice) reports max_input_channels=0
    for the WM8960 — even though `arecord -l` shows the hardware.

    This function checks whether the existing asound.conf has a
    capture/dsnoop definition for the WM8960. If not, it appends one.
    This only runs on Pi at audio init time.
    """
    asound_conf = Path("/etc/asound.conf")

    try:
        content = asound_conf.read_text() if asound_conf.exists() else ""
    except PermissionError:
        log.debug("Cannot read /etc/asound.conf — skipping capture config check")
        return

    # Check if capture is already defined — look for dsnoop, dmic, or
    # a pcm.capture definition that references the WM8960
    content_lower = content.lower()
    has_capture = any(marker in content_lower for marker in [
        "pcm.dsnoop",
        "pcm.dmic",
        "pcm.capture",
        "type dsnoop",
        "# voxel capture",
    ])

    if has_capture:
        log.debug("ALSA config already has capture definition")
        return

    # No capture definition found — check if the WM8960 card exists
    # before writing config for it
    try:
        proc_cards = Path("/proc/asound/cards").read_text().lower()
        if "wm8960" not in proc_cards:
            log.debug("WM8960 not in /proc/asound/cards — skipping ALSA capture config")
            return
    except Exception:
        return

    # Append a dsnoop capture definition that exposes the WM8960 mics
    # to PortAudio. dsnoop allows multiple readers on the same hw device.
    capture_config = """
# voxel capture — WM8960 microphone access for PortAudio/sounddevice
# Added by Voxel because the Whisplay driver's asound.conf may omit capture.
pcm.dsnoop {
    type dsnoop
    ipc_key 2048
    slave {
        pcm "hw:0,0"
        channels 2
        rate 16000
    }
}

# Default capture device — ensures PortAudio sees an input device
pcm.dsnooppl {
    type plug
    slave.pcm "dsnoop"
}

# Make default capture point to the WM8960 dsnoop
pcm.!default {
    type asym
    playback.pcm {
        type plug
        slave.pcm "dmix"
    }
    capture.pcm {
        type plug
        slave.pcm "dsnoop"
    }
}
"""

    try:
        import subprocess
        # Use tee with sudo to write — the service may not run as root
        result = subprocess.run(
            ["sudo", "tee", "-a", "/etc/asound.conf"],
            input=capture_config,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            log.info("ALSA: appended capture (dsnoop) config to /etc/asound.conf")
        else:
            log.warning("ALSA: failed to append capture config: %s", result.stderr.strip())
    except Exception as e:
        log.warning("ALSA: could not update asound.conf: %s", e)


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
