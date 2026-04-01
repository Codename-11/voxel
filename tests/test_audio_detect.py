"""Tests for audio device detection and ALSA capture config.

Covers the _get_sd_device() 5-strategy fallback, _get_pi_input_device()
PyAudio scanning, and _ensure_alsa_capture_config() file detection logic.
All hardware and sounddevice/pyaudio APIs are mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# Import the module upfront so it's registered in sys.modules and patchable.
import core.audio as audio_mod


# ── Helpers ─────────────────────────────────────────────────────────────────


def _mock_sd_module(
    *,
    named_works: bool = False,
    scan_devices: list | None = None,
    plughw_works: list | None = None,
    index0_works: bool = False,
):
    """Create a mock sounddevice module with configurable behavior.

    Args:
        named_works: Whether check_input_parameters(device="hw:wm8960soundcard") succeeds
        scan_devices: List of device dicts from query_devices()
        plughw_works: List of plughw device strings that succeed
        index0_works: Whether device index 0 works
    """
    sd = MagicMock()

    if scan_devices is None:
        scan_devices = []
    if plughw_works is None:
        plughw_works = []

    sd.query_devices.return_value = scan_devices

    def check_input(device=None, channels=None, samplerate=None):
        if device == "hw:wm8960soundcard":
            if named_works:
                return
            raise Exception("Device not available")
        if isinstance(device, str) and device.startswith("plughw"):
            if device in plughw_works:
                return
            raise Exception("Device not available")
        if isinstance(device, int) and device == 0:
            if index0_works:
                return
            raise Exception("Device not available")
        raise Exception("Unknown device")

    def check_output(device=None, channels=None, samplerate=None):
        if device == "hw:wm8960soundcard":
            if named_works:
                return
            raise Exception("Device not available")
        raise Exception("Unknown device")

    sd.check_input_parameters = MagicMock(side_effect=check_input)
    sd.check_output_parameters = MagicMock(side_effect=check_output)

    return sd


def _mock_pyaudio_module():
    """Create a mock pyaudio module with a paInt16 constant."""
    pa = MagicMock()
    pa.paInt16 = 8
    pa.paContinue = 0
    return pa


def _setup_mock_pa(devices: list[dict]):
    """Create and install a mock PyAudio instance with given devices."""
    mock_pa = MagicMock()
    mock_pa.get_device_count.return_value = len(devices)
    mock_pa.get_device_info_by_index.side_effect = lambda i: devices[i]
    return mock_pa


# ── 1. _get_sd_device — Strategy 1: Named device works ─────────────────────


def test_sd_device_named_device_works():
    """When the named ALSA device works, return it directly."""
    sd = _mock_sd_module(named_works=True)

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert result == "hw:wm8960soundcard"


# ── 2. _get_sd_device — Strategy 2: Scan finds WM8960 ──────────────────────


def test_sd_device_scan_finds_wm8960():
    """When named device fails but scan finds WM8960, return its name."""
    devices = [
        {"name": "default", "max_input_channels": 2},
        {"name": "snd_rpi_wm8960: WM8960 HiFi", "max_input_channels": 2},
    ]
    sd = _mock_sd_module(named_works=False, scan_devices=devices)

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert "wm8960" in result.lower()


def test_sd_device_scan_ignores_zero_channels():
    """Scan should skip WM8960 devices with 0 input channels."""
    devices = [
        {"name": "snd_rpi_wm8960: WM8960 HiFi", "max_input_channels": 0},
    ]
    sd = _mock_sd_module(named_works=False, scan_devices=devices, plughw_works=["plughw:wm8960soundcard"])

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    # Should fall through to plughw
    assert result == "plughw:wm8960soundcard"


# ── 3. _get_sd_device — Strategy 3: plughw works ───────────────────────────


def test_sd_device_plughw_named_works():
    """When named and scan fail, plughw:wm8960soundcard should be tried."""
    sd = _mock_sd_module(
        named_works=False,
        scan_devices=[],
        plughw_works=["plughw:wm8960soundcard"],
    )

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert result == "plughw:wm8960soundcard"


def test_sd_device_plughw_fallback_works():
    """When plughw:wm8960soundcard fails, plughw:0,0 should be tried."""
    sd = _mock_sd_module(
        named_works=False,
        scan_devices=[],
        plughw_works=["plughw:0,0"],
    )

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert result == "plughw:0,0"


# ── 4. _get_sd_device — Strategy 4: Index 0 works ──────────────────────────


def test_sd_device_index_zero_works():
    """When all string devices fail, device index 0 should be tried."""
    sd = _mock_sd_module(
        named_works=False,
        scan_devices=[],
        plughw_works=[],
        index0_works=True,
    )

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert result == 0


# ── 5. _get_sd_device — Strategy 5: All fail → fallback ────────────────────


def test_sd_device_all_fail_returns_fallback():
    """When everything fails, return the hw:0,0 fallback."""
    sd = _mock_sd_module(
        named_works=False,
        scan_devices=[],
        plughw_works=[],
        index0_works=False,
    )

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("input")

    assert result == "hw:0,0"


# ── 6. _get_sd_device — Desktop returns None ───────────────────────────────


def test_sd_device_desktop_returns_none():
    """On desktop (IS_PI=False), should return None immediately."""
    with patch.object(audio_mod, "IS_PI", False):
        result = audio_mod._get_sd_device("input")

    assert result is None


# ── 7. _get_sd_device — Output direction ───────────────────────────────────


def test_sd_device_output_named_works():
    """Output direction should also try the named device first."""
    sd = _mock_sd_module(named_works=True)

    with patch.dict("sys.modules", {"sounddevice": sd}), \
         patch.object(audio_mod, "IS_PI", True):
        result = audio_mod._get_sd_device("output")

    assert result == "hw:wm8960soundcard"


# ── 8. _get_pi_input_device — PyAudio scanning ─────────────────────────────


def test_pi_input_device_finds_wm8960():
    """_get_pi_input_device finds WM8960 with input channels > 0."""
    mock_pa = _setup_mock_pa([
        {"name": "default", "maxInputChannels": 0},
        {"name": "snd_rpi_wm8960", "maxInputChannels": 2},
        {"name": "HDMI", "maxInputChannels": 0},
    ])
    mock_pyaudio = _mock_pyaudio_module()

    original_pa = audio_mod._pa
    audio_mod._pa = mock_pa

    try:
        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            result = audio_mod._get_pi_input_device()
        assert result == 1
    finally:
        audio_mod._pa = original_pa


def test_pi_input_device_wm8960_zero_channels_still_used():
    """WM8960 with 0 input channels is returned as fallback (broken asound.conf)."""
    mock_pa = _setup_mock_pa([
        {"name": "default", "maxInputChannels": 0},
        {"name": "snd_rpi_wm8960", "maxInputChannels": 0},
    ])
    mock_pyaudio = _mock_pyaudio_module()

    original_pa = audio_mod._pa
    audio_mod._pa = mock_pa

    try:
        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            result = audio_mod._get_pi_input_device()
        assert result == 1, "Should return WM8960 index even with 0 channels"
    finally:
        audio_mod._pa = original_pa


def test_pi_input_device_no_wm8960_uses_device_zero():
    """If no WM8960 found, fall back to device 0 if it has input channels."""
    mock_pa = _setup_mock_pa([
        {"name": "default", "maxInputChannels": 2},
    ])
    mock_pyaudio = _mock_pyaudio_module()

    original_pa = audio_mod._pa
    audio_mod._pa = mock_pa

    try:
        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            result = audio_mod._get_pi_input_device()
        assert result == 0
    finally:
        audio_mod._pa = original_pa


def test_pi_input_device_no_devices_returns_none():
    """If no devices at all, return None."""
    mock_pa = MagicMock()
    mock_pa.get_device_count.return_value = 0
    mock_pyaudio = _mock_pyaudio_module()

    original_pa = audio_mod._pa
    audio_mod._pa = mock_pa

    try:
        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            result = audio_mod._get_pi_input_device()
        assert result is None
    finally:
        audio_mod._pa = original_pa


# ── 9. _ensure_alsa_capture_config — detection logic ───────────────────────


def _make_path_mock(exists: bool, content: str):
    """Create a Path-like mock with exists() and read_text()."""
    m = MagicMock(spec=Path)
    m.exists.return_value = exists
    m.read_text.return_value = content
    return m


def test_alsa_config_already_has_dsnoop():
    """If asound.conf already has dsnoop, do not modify it."""
    mock_asound = _make_path_mock(True, 'pcm.dsnoop { type dsnoop }')
    mock_cards = _make_path_mock(True, "wm8960")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: {
            "/etc/asound.conf": mock_asound,
            "/proc/asound/cards": mock_cards,
        }.get(arg, MagicMock(spec=Path))

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_detects_voxel_capture_marker():
    """'# voxel capture' marker should count as capture being present."""
    mock_asound = _make_path_mock(True, "# voxel capture config\nsome settings")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: mock_asound if arg == "/etc/asound.conf" else MagicMock(spec=Path)

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_detects_type_dsnoop():
    """'type dsnoop' in config should be detected as capture present."""
    mock_asound = _make_path_mock(True, "pcm.mic { type dsnoop }")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: mock_asound if arg == "/etc/asound.conf" else MagicMock(spec=Path)

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_detects_pcm_capture():
    """'pcm.capture' in config should be detected."""
    mock_asound = _make_path_mock(True, "pcm.capture { type plug }")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: mock_asound if arg == "/etc/asound.conf" else MagicMock(spec=Path)

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_detects_pcm_dmic():
    """'pcm.dmic' in config should be detected."""
    mock_asound = _make_path_mock(True, "pcm.dmic { type plug }")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: mock_asound if arg == "/etc/asound.conf" else MagicMock(spec=Path)

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_no_file_skips():
    """If /etc/asound.conf does not exist, check proc and skip if no WM8960."""
    mock_asound = _make_path_mock(False, "")
    # Content intentionally does NOT contain "wm8960"
    mock_cards = _make_path_mock(True, " 0 [bcm2835]: bcm2835 - bcm2835 ALSA")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: {
            "/etc/asound.conf": mock_asound,
            "/proc/asound/cards": mock_cards,
        }.get(arg, MagicMock(spec=Path))

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            # No WM8960 in /proc/asound/cards → skip
            mock_run.assert_not_called()


def test_alsa_config_missing_capture_with_wm8960_appends():
    """If asound.conf lacks capture but WM8960 exists, append capture config."""
    # Only playback config — no dsnoop, dmic, or capture definitions
    mock_asound = _make_path_mock(True, "pcm.dmix { type dmix }\npcm.softvol { type softvol }")
    mock_cards = _make_path_mock(True, " 0 [wm8960soundcar]: wm8960 - WM8960")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: {
            "/etc/asound.conf": mock_asound,
            "/proc/asound/cards": mock_cards,
        }.get(arg, MagicMock(spec=Path))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            audio_mod._ensure_alsa_capture_config()
            # Should have called subprocess.run to append capture config
            mock_run.assert_called_once()
            # Verify it's calling tee -a
            call_args = mock_run.call_args
            assert call_args[0][0] == ["sudo", "tee", "-a", "/etc/asound.conf"]
            assert "dsnoop" in call_args[1].get("input", "")


def test_alsa_config_no_wm8960_in_proc_skips():
    """If WM8960 is not in /proc/asound/cards, skip config modification."""
    mock_asound = _make_path_mock(True, "# some playback config only")
    mock_cards = _make_path_mock(True, " 0 [bcm2835]: bcm2835 - bcm2835 ALSA")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: {
            "/etc/asound.conf": mock_asound,
            "/proc/asound/cards": mock_cards,
        }.get(arg, MagicMock(spec=Path))

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_permission_error_skips():
    """PermissionError reading asound.conf should skip gracefully."""
    mock_asound = MagicMock(spec=Path)
    mock_asound.exists.return_value = True
    mock_asound.read_text.side_effect = PermissionError("denied")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: mock_asound if arg == "/etc/asound.conf" else MagicMock(spec=Path)

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            mock_run.assert_not_called()


def test_alsa_config_proc_read_error_returns():
    """If /proc/asound/cards read fails, return gracefully."""
    mock_asound = _make_path_mock(True, "# playback only, no capture")
    mock_cards = MagicMock(spec=Path)
    mock_cards.read_text.side_effect = FileNotFoundError("no such file")

    with patch.object(audio_mod, "Path") as MockPath:
        MockPath.side_effect = lambda arg: {
            "/etc/asound.conf": mock_asound,
            "/proc/asound/cards": mock_cards,
        }.get(arg, MagicMock(spec=Path))

        with patch("subprocess.run") as mock_run:
            audio_mod._ensure_alsa_capture_config()
            # Exception reading cards → early return, no modification
            mock_run.assert_not_called()


# ── 10. _get_sd_device — sounddevice completely unavailable ─────────────────


def test_sd_device_no_sounddevice_returns_fallback():
    """If sounddevice import raises inside the function, return fallback."""
    with patch.object(audio_mod, "IS_PI", True):
        # Set sounddevice to None so import raises TypeError (caught by except)
        original = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = None

        try:
            result = audio_mod._get_sd_device("input")
            assert result == "hw:0,0"
        finally:
            if original is not None:
                sys.modules["sounddevice"] = original
            else:
                sys.modules.pop("sounddevice", None)


# ── 11. _get_pi_input_device — exception handling ──────────────────────────


def test_pi_input_device_exception_returns_none():
    """If device scanning throws an exception, return None."""
    mock_pa = MagicMock()
    mock_pa.get_device_count.side_effect = Exception("PortAudio not initialized")
    mock_pyaudio = _mock_pyaudio_module()

    original_pa = audio_mod._pa
    audio_mod._pa = mock_pa

    try:
        with patch.dict("sys.modules", {"pyaudio": mock_pyaudio}):
            result = audio_mod._get_pi_input_device()
        assert result is None
    finally:
        audio_mod._pa = original_pa
