"""Platform and Whisplay hardware detection helpers."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


IS_PI = platform.machine().startswith(("aarch64", "arm"))
PLATFORM_NAME = "Pi" if IS_PI else "Desktop"


@dataclass(frozen=True)
class HardwareProbe:
    """Best-effort snapshot of the Pi display and audio stack."""

    is_pi: bool
    has_wm8960_audio: bool
    has_spi_device: bool
    spi_enabled: bool
    has_fb1: bool
    has_drm: bool
    has_cog: bool

    @property
    def whisplay_detected(self) -> bool:
        """Whisplay HAT appears to be attached/configured."""
        # Generic SPI peripherals also expose /dev/spidev* and dtparam=spi=on,
        # so treat SPI as a hint only and require a Whisplay-specific signal.
        return self.is_pi and (self.has_wm8960_audio or self.has_fb1)

    @property
    def cog_ready(self) -> bool:
        """Local Cog rendering has a plausible display backend available."""
        return self.has_cog and (self.has_fb1 or (self.whisplay_detected and self.has_drm))

    @property
    def recommended_display_mode(self) -> str:
        """Suggested auto mode based on the current machine state."""
        return "whisplay" if self.whisplay_detected else "desktop"


def _run_capture(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (result.stdout or "") + (result.stderr or "")
    except Exception:
        return ""


def _spi_setting_from_config(config_text: str) -> bool | None:
    """Parse the effective SPI dtparam from a config.txt-style file.

    Raspberry Pi config allows repeated dtparam assignments where later lines
    override earlier ones, so this returns the last explicit SPI setting.
    """

    spi_enabled: bool | None = None
    for raw_line in config_text.splitlines():
        line = raw_line.split("#", 1)[0].strip().lower()
        if not line:
            continue

        compact = line.replace(" ", "")
        if not compact.startswith("dtparam="):
            continue

        params = compact.split("=", 1)[1].split(",")
        for param in params:
            if param == "spi":
                spi_enabled = True
                continue
            if not param.startswith("spi="):
                continue
            value = param.split("=", 1)[1]
            if value in {"on", "1", "true", "yes"}:
                spi_enabled = True
            elif value in {"off", "0", "false", "no"}:
                spi_enabled = False
    return spi_enabled


def _spi_enabled() -> bool:
    for path in (Path("/boot/firmware/config.txt"), Path("/boot/config.txt")):
        if not path.exists():
            continue
        try:
            spi_enabled = _spi_setting_from_config(path.read_text(encoding="utf-8", errors="replace"))
            if spi_enabled is not None:
                return spi_enabled
        except Exception:
            continue
    return False


def probe_hardware() -> HardwareProbe:
    """Detect the current Pi/Whisplay environment.

    Notes:
    - Whisplay presence is inferred from WM8960 audio and/or framebuffer devices.
    - SPI configuration is tracked separately as a setup diagnostic hint.
    - Cog readiness is a separate question from hardware presence.
    """

    audio_listing = _run_capture(["arecord", "-l"]) + "\n" + _run_capture(["aplay", "-l"])
    audio_lower = audio_listing.lower()

    return HardwareProbe(
        is_pi=IS_PI,
        has_wm8960_audio="wm8960" in audio_lower or "wm8960soundcard" in audio_lower,
        has_spi_device=any(Path("/dev").glob("spidev*")),
        spi_enabled=_spi_enabled(),
        has_fb1=Path("/dev/fb1").exists(),
        has_drm=any(Path("/dev/dri").glob("card*")) if Path("/dev/dri").exists() else False,
        has_cog=shutil.which("cog") is not None,
    )
