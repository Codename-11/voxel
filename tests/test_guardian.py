"""Tests for the Voxel Display Guardian.

Covers boot screen rendering, error screen rendering, WiFi setup screen,
display lock file management, WiFi setup flag, and menu integration.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from display.guardian import (
    render_boot_screen,
    render_error_screen,
    render_recovery_screen,
    render_wifi_setup_screen,
    acquire_display_lock,
    release_display_lock,
    display_is_locked,
    wifi_setup_requested,
    clear_wifi_setup_flag,
    LOCK_FILE,
    WIFI_SETUP_FLAG,
    SCREEN_W,
    SCREEN_H,
    Guardian,
    GuardianDisplay,
)


# ── Screen rendering tests ────────────────────────────────────────────────


class TestBootScreen:
    """Boot splash screen renders at correct dimensions with content."""

    def test_basic_boot_screen(self):
        img = render_boot_screen("Starting...")
        assert isinstance(img, Image.Image)
        assert img.size == (SCREEN_W, SCREEN_H)
        assert img.mode == "RGB"

    def test_boot_screen_with_status_lines(self):
        lines = [("WiFi", "OK"), ("IP", "192.168.1.100"), ("Services", "WAIT")]
        img = render_boot_screen("Booting...", extra_lines=lines)
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_boot_screen_with_fail_status(self):
        lines = [("WiFi", "FAIL")]
        img = render_boot_screen("No WiFi", extra_lines=lines)
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_boot_screen_empty_lines(self):
        img = render_boot_screen("Starting...", extra_lines=[])
        assert img.size == (SCREEN_W, SCREEN_H)


class TestErrorScreen:
    """Error screen renders with title, message, and detail."""

    def test_basic_error_screen(self):
        img = render_error_screen()
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_error_screen_with_message(self):
        img = render_error_screen(
            title="Display Crashed",
            message="voxel-display stopped unexpectedly",
            detail="Mar 30 12:00:01 voxel python[123]: Error: segfault",
        )
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_error_screen_long_message_wraps(self):
        """Long messages should word-wrap without crashing."""
        long_msg = "This is a very long error message that should be " \
                   "wrapped across multiple lines on the small 240px display"
        img = render_error_screen(message=long_msg)
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_error_screen_multiline_detail(self):
        detail = "\n".join([f"line {i}: some log output" for i in range(10)])
        img = render_error_screen(detail=detail)
        assert img.size == (SCREEN_W, SCREEN_H)


class TestRecoveryScreen:
    """Recovery screen renders with service name and attempt count."""

    def test_basic_recovery(self):
        img = render_recovery_screen("voxel-display", attempt=1)
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_recovery_attempt_count(self):
        for attempt in [1, 2, 5, 10]:
            img = render_recovery_screen("voxel-display", attempt=attempt)
            assert img.size == (SCREEN_W, SCREEN_H)


class TestWifiSetupScreen:
    """WiFi setup screen renders with AP info."""

    def test_basic_wifi_screen(self):
        img = render_wifi_setup_screen(
            ap_ssid="Voxel-Setup",
            ap_password="voxel1234",
            ap_ip="10.42.0.1",
        )
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_wifi_screen_with_pin(self):
        img = render_wifi_setup_screen(
            ap_ssid="Voxel-Setup",
            ap_password="voxel1234",
            ap_ip="10.42.0.1",
            pin="123456",
        )
        assert img.size == (SCREEN_W, SCREEN_H)

    def test_wifi_screen_with_qr(self):
        """QR generation is optional — should not crash if qrcode missing."""
        img = render_wifi_setup_screen(
            ap_ssid="Voxel-Setup",
            ap_password="voxel1234",
            ap_ip="10.42.0.1",
            pin="654321",
            qr_url="http://10.42.0.1:8083/",
        )
        assert img.size == (SCREEN_W, SCREEN_H)


# ── Lock file management ─────────────────────────────────────────────────


class TestDisplayLock:
    """File-based display lock for guardian <-> voxel-display handoff."""

    def setup_method(self):
        """Clean up lock file before each test."""
        LOCK_FILE.unlink(missing_ok=True)

    def teardown_method(self):
        """Clean up after each test."""
        LOCK_FILE.unlink(missing_ok=True)

    def test_acquire_creates_lock(self, tmp_path, monkeypatch):
        lock = tmp_path / "test-display.lock"
        monkeypatch.setattr("display.guardian.LOCK_FILE", lock)
        acquire_display_lock()
        assert lock.exists()

    def test_release_removes_lock(self, tmp_path, monkeypatch):
        lock = tmp_path / "test-display.lock"
        monkeypatch.setattr("display.guardian.LOCK_FILE", lock)
        acquire_display_lock()
        assert lock.exists()
        release_display_lock()
        assert not lock.exists()

    def test_display_is_locked(self, tmp_path, monkeypatch):
        lock = tmp_path / "test-display.lock"
        monkeypatch.setattr("display.guardian.LOCK_FILE", lock)
        assert not display_is_locked()
        acquire_display_lock()
        assert display_is_locked()
        release_display_lock()
        assert not display_is_locked()

    def test_release_without_acquire(self, tmp_path, monkeypatch):
        """Releasing without acquiring should not raise."""
        lock = tmp_path / "test-display.lock"
        monkeypatch.setattr("display.guardian.LOCK_FILE", lock)
        release_display_lock()  # should not raise


# ── WiFi setup flag ───────────────────────────────────────────────────────


class TestWifiSetupFlag:
    """File-based signal for menu -> guardian WiFi setup trigger."""

    def setup_method(self):
        WIFI_SETUP_FLAG.unlink(missing_ok=True)

    def teardown_method(self):
        WIFI_SETUP_FLAG.unlink(missing_ok=True)

    def test_flag_not_set_initially(self, tmp_path, monkeypatch):
        flag = tmp_path / "test-wifi-setup"
        monkeypatch.setattr("display.guardian.WIFI_SETUP_FLAG", flag)
        assert not wifi_setup_requested()

    def test_flag_set_and_clear(self, tmp_path, monkeypatch):
        flag = tmp_path / "test-wifi-setup"
        monkeypatch.setattr("display.guardian.WIFI_SETUP_FLAG", flag)
        flag.touch()
        assert wifi_setup_requested()
        clear_wifi_setup_flag()
        assert not wifi_setup_requested()


# ── Menu integration ──────────────────────────────────────────────────────


class TestMenuWifiSetup:
    """WiFi Setup menu item triggers the guardian flag."""

    def test_wifi_setup_in_menu_items(self):
        from display.components.menu import MENU_ITEMS
        ids = [item[0] for item in MENU_ITEMS]
        assert "wifi_setup" in ids

    def test_menu_has_wifi_setup_triggered_attr(self):
        from display.components.menu import MenuState
        menu = MenuState()
        assert hasattr(menu, "_wifi_setup_triggered")
        assert menu._wifi_setup_triggered is False

    def test_wifi_setup_select_triggers_flag(self):
        from display.components.menu import MenuState
        from display.state import DisplayState
        menu = MenuState()
        state = DisplayState()
        menu.open = True
        menu.sub_screen = "wifi_setup"
        menu.select(state)
        assert menu._wifi_setup_triggered is True
        assert menu.open is False


# ── Guardian class (unit tests with mocked hardware) ──────────────────────


class TestGuardianInit:
    """Guardian class initialization and signal handling."""

    def test_guardian_creates_display(self):
        guardian = Guardian()
        assert guardian.display is not None
        assert isinstance(guardian.display, GuardianDisplay)
        assert guardian.running is True
        assert guardian.ap_mode is False

    def test_signal_handler_sets_running_false(self):
        guardian = Guardian()
        guardian._handle_signal(15, None)  # SIGTERM
        assert guardian.running is False


class TestGuardianDisplay:
    """GuardianDisplay without real hardware."""

    def test_display_init_fails_gracefully(self):
        """On desktop, WhisPlay won't be found — init returns False."""
        display = GuardianDisplay()
        # Should not raise, returns False
        result = display.init()
        assert result is False

    def test_push_frame_noop_without_init(self):
        """Pushing frames without init should not raise."""
        display = GuardianDisplay()
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        display.push_frame(img)  # should be a no-op

    def test_set_led_noop_without_init(self):
        display = GuardianDisplay()
        display.set_led(255, 0, 0)  # should not raise

    def test_cleanup_noop_without_init(self):
        display = GuardianDisplay()
        display.cleanup()  # should not raise
