"""Ambient audio monitor — deterministic face reactivity from mic input.

Reads RMS amplitude from short mic samples in a background thread.
No audio is recorded or stored — just amplitude levels for face reactions.

Reactions are deterministic (no LLM call):
  - Loud noise (clap/bang): surprised mood for 1.5s
  - Sustained sound: curious mood while audio continues
  - Long silence: sleepy mood until sound returns
  - Rhythmic pattern: sync body bounce to detected beat
"""

from __future__ import annotations

import logging
import math
import threading
import time
from enum import Enum, auto

log = logging.getLogger("voxel.display.ambient")

# Audio sampling constants
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 512  # 512 samples @ 16kHz = 32ms per read


class _AudioState(Enum):
    """Internal state machine for ambient audio classification."""
    QUIET = auto()         # No significant sound
    LOUD_SPIKE = auto()    # Sudden loud noise (clap, bang)
    SUSTAINED = auto()     # Ongoing sound (music, talking)
    SILENCE = auto()       # Extended silence (sleepy trigger)


class AmbientMonitor:
    """Monitors ambient audio level from the mic, updates display state.

    Runs in a background thread. Does NOT record full audio — just
    reads RMS amplitude from short mic samples for reactivity.
    """

    # Amplitude thresholds (after sensitivity scaling)
    SPIKE_THRESHOLD = 0.7     # sudden loud noise
    SUSTAINED_LOW = 0.15      # minimum for "sustained sound"
    SUSTAINED_HIGH = 0.7      # upper bound for sustained (above = spike)
    SILENCE_THRESHOLD = 0.05  # below this = silence

    # Timing
    SUSTAINED_MIN_DURATION = 2.0   # seconds of sound to trigger "sustained"
    SILENCE_TIMEOUT = 180.0        # seconds of silence before "sleepy" (default)
    SPIKE_REACTION_DURATION = 1.5  # seconds to hold "surprised" mood
    SPIKE_COOLDOWN = 3.0           # minimum seconds between spike reactions

    # Smoothing
    EMA_ALPHA = 0.3  # exponential moving average factor (higher = less smoothing)

    def __init__(self, enabled: bool = True, sensitivity: float = 0.6,
                 silence_timeout: float = 180.0):
        self._enabled = enabled
        self._sensitivity = max(0.0, min(1.0, sensitivity))
        self._amplitude: float = 0.0
        self._raw_amplitude: float = 0.0
        self._thread: threading.Thread | None = None
        self._running = False

        # Reaction state machine
        self._audio_state = _AudioState.QUIET
        self._sound_start: float = 0.0      # when sustained sound began
        self._silence_start: float = 0.0    # when silence began
        self._last_spike: float = 0.0       # last spike reaction time
        self._spike_until: float = 0.0      # hold surprised until this time

        # Beat detection (simple peak interval tracking)
        self._peak_times: list[float] = []
        self._beat_interval: float = 0.0    # estimated beat interval (seconds)
        self._last_peak: float = 0.0
        self._peak_threshold: float = 0.0   # dynamic threshold for peak detection

        # Config
        self.SILENCE_TIMEOUT = silence_timeout

    def start(self) -> None:
        """Start monitoring in a background thread."""
        if not self._enabled:
            log.debug("Ambient monitor disabled")
            return
        if self._running:
            return

        self._running = True
        self._silence_start = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True,
                                        name="ambient-audio")
        self._thread.start()
        log.info("Ambient audio monitor started")

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Ambient audio monitor stopped")

    @property
    def amplitude(self) -> float:
        """Current smoothed amplitude (0-1)."""
        return self._amplitude

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_reaction(self) -> str | None:
        """Return a mood reaction based on recent audio, or None.

        Called from the render loop. Returns a mood name to apply,
        or None if no ambient reaction is warranted.
        """
        if not self._enabled or not self._running:
            return None

        now = time.time()

        # Spike reaction (surprised) — highest priority
        if now < self._spike_until:
            return "surprised"

        # Check for new spike
        if (self._raw_amplitude > self.SPIKE_THRESHOLD
                and (now - self._last_spike) > self.SPIKE_COOLDOWN):
            self._last_spike = now
            self._spike_until = now + self.SPIKE_REACTION_DURATION
            self._audio_state = _AudioState.LOUD_SPIKE
            log.info("Ambient: loud spike → surprised")
            return "surprised"

        # Sustained sound detection
        if self._amplitude >= self.SUSTAINED_LOW:
            if self._audio_state != _AudioState.SUSTAINED:
                if self._sound_start == 0.0:
                    self._sound_start = now
                elif (now - self._sound_start) >= self.SUSTAINED_MIN_DURATION:
                    self._audio_state = _AudioState.SUSTAINED
                    self._silence_start = 0.0
                    log.info("Ambient: sustained sound → curious")
            # Reset silence timer while sound is present
            self._silence_start = 0.0

            if self._audio_state == _AudioState.SUSTAINED:
                return "curious"
        else:
            # Sound stopped
            self._sound_start = 0.0
            if self._audio_state == _AudioState.SUSTAINED:
                self._audio_state = _AudioState.QUIET
                log.info("Ambient: sustained sound ended")

            # Silence tracking
            if self._amplitude < self.SILENCE_THRESHOLD:
                if self._silence_start == 0.0:
                    self._silence_start = now
                elif (now - self._silence_start) >= self.SILENCE_TIMEOUT:
                    self._audio_state = _AudioState.SILENCE
                    return "sleepy"
            else:
                self._silence_start = 0.0

        return None

    def get_beat_interval(self) -> float:
        """Return estimated beat interval in seconds, or 0 if no rhythm detected."""
        return self._beat_interval

    def simulate_spike(self) -> None:
        """Simulate a loud noise spike (for desktop testing)."""
        now = time.time()
        self._raw_amplitude = 0.9
        self._amplitude = 0.9
        self._last_spike = now
        self._spike_until = now + self.SPIKE_REACTION_DURATION
        self._audio_state = _AudioState.LOUD_SPIKE
        log.info("Ambient: simulated noise spike")

    def _monitor_loop(self) -> None:
        """Background thread: read mic input and compute amplitude."""
        stream = None
        backend = None  # "pyaudio" or "sounddevice"

        try:
            stream, backend = self._open_stream()
            if stream is None:
                log.warning("Ambient: no mic available, disabling monitor")
                self._enabled = False
                self._running = False
                return

            log.debug(f"Ambient: using {backend} backend")

            while self._running:
                try:
                    raw_rms = self._read_rms(stream, backend)
                    # Apply sensitivity scaling (higher sensitivity = amplify more)
                    scaled = raw_rms * (0.5 + self._sensitivity * 2.0)
                    scaled = min(scaled, 1.0)

                    # Store raw (pre-smoothing) for spike detection
                    self._raw_amplitude = scaled

                    # Exponential moving average for smooth display
                    self._amplitude = (self.EMA_ALPHA * scaled +
                                       (1.0 - self.EMA_ALPHA) * self._amplitude)

                    # Beat detection
                    self._update_beat_detection(scaled)

                except Exception as e:
                    log.debug(f"Ambient read error: {e}")
                    time.sleep(0.1)

        except Exception as e:
            log.warning(f"Ambient monitor thread error: {e}")
            self._enabled = False
        finally:
            self._close_stream(stream, backend)
            self._running = False

    def _open_stream(self):
        """Try to open an audio input stream. Returns (stream, backend_name) or (None, None)."""
        # Try PyAudio first
        try:
            import pyaudio  # type: ignore
            pa = pyaudio.PyAudio()

            # Find input device
            device_idx = None
            try:
                from hw.detect import IS_PI
                if IS_PI:
                    for i in range(pa.get_device_count()):
                        info = pa.get_device_info_by_index(i)
                        if "wm8960" in info["name"].lower() and info["maxInputChannels"] > 0:
                            device_idx = i
                            break
            except ImportError:
                pass

            kwargs: dict = dict(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            if device_idx is not None:
                kwargs["input_device_index"] = device_idx

            stream = pa.open(**kwargs)
            stream.start_stream()
            # Store pa reference on the stream so we can terminate later
            stream._pa_instance = pa  # type: ignore[attr-defined]
            return stream, "pyaudio"

        except Exception as e:
            log.debug(f"PyAudio not available for ambient: {e}")

        # Try sounddevice
        try:
            import sounddevice as sd  # type: ignore
            import numpy as np  # noqa: F401

            device = None
            try:
                from hw.detect import IS_PI
                if IS_PI:
                    device = "hw:0,0"
            except ImportError:
                pass

            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK,
                device=device,
            )
            stream.start()
            return stream, "sounddevice"

        except Exception as e:
            log.debug(f"sounddevice not available for ambient: {e}")

        return None, None

    def _read_rms(self, stream, backend: str) -> float:
        """Read one chunk from the stream and return RMS amplitude (0-1)."""
        if backend == "pyaudio":
            data = stream.read(CHUNK, exception_on_overflow=False)
            import numpy as np
            arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        elif backend == "sounddevice":
            data, _overflowed = stream.read(CHUNK)
            import numpy as np
            arr = data.flatten().astype(np.float32)
        else:
            return 0.0

        if len(arr) == 0:
            return 0.0

        rms = math.sqrt(float(np.mean(arr ** 2)))
        # Normalize: int16 max = 32768, with perceptual boost (*4)
        return min(rms / 32768.0 * 4.0, 1.0)

    def _close_stream(self, stream, backend: str | None) -> None:
        """Close the audio stream."""
        if stream is None:
            return
        try:
            if backend == "pyaudio":
                stream.stop_stream()
                stream.close()
                if hasattr(stream, "_pa_instance"):
                    stream._pa_instance.terminate()
            elif backend == "sounddevice":
                stream.stop()
                stream.close()
        except Exception:
            pass

    def _update_beat_detection(self, amplitude: float) -> None:
        """Simple beat detection via peak interval tracking."""
        now = time.time()

        # Dynamic peak threshold: 1.5x recent average
        if self._peak_threshold == 0.0:
            self._peak_threshold = 0.3
        self._peak_threshold = 0.95 * self._peak_threshold + 0.05 * amplitude

        # Detect peak: amplitude above threshold and above recent average
        is_peak = (amplitude > self._peak_threshold * 1.5
                   and amplitude > 0.2
                   and (now - self._last_peak) > 0.15)  # min 150ms between peaks

        if is_peak:
            self._last_peak = now
            self._peak_times.append(now)

            # Keep only last 8 peaks
            if len(self._peak_times) > 8:
                self._peak_times = self._peak_times[-8:]

            # Compute average interval between recent peaks
            if len(self._peak_times) >= 3:
                intervals = [
                    self._peak_times[i] - self._peak_times[i - 1]
                    for i in range(1, len(self._peak_times))
                ]
                # Filter outliers (keep intervals within 2x of median)
                intervals.sort()
                median = intervals[len(intervals) // 2]
                filtered = [iv for iv in intervals if 0.5 * median <= iv <= 2.0 * median]
                if filtered:
                    avg = sum(filtered) / len(filtered)
                    # Only report as rhythm if interval is consistent (0.2s-2s = 30-300 BPM)
                    if 0.2 <= avg <= 2.0:
                        self._beat_interval = avg
                    else:
                        self._beat_interval = 0.0
                else:
                    self._beat_interval = 0.0

        # Decay beat detection if no peaks for a while
        if (now - self._last_peak) > 3.0:
            self._beat_interval = 0.0
            self._peak_times.clear()
