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
        return self.is_pi and (
            self.has_wm8960_audio or self.has_fb1 or (self.spi_enabled and self.has_spi_device)
        )

    @property
    def cog_ready(self) -> bool:
        """Local Cog rendering has a plausible display backend available."""
        return self.has_cog and (self.has_fb1 or (self.whisplay_detected and self.has_drm))

    @property
    def recommended_display_mode(self) -> str:
        """Suggested auto mode based on the current machine state."""
        return "cog" if self.cog_ready else "remote"


def _run_capture(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (result.stdout or "") + (result.stderr or "")
    except Exception:
        return ""


def _spi_enabled() -> bool:
    for path in (Path("/boot/firmware/config.txt"), Path("/boot/config.txt")):
        if not path.exists():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip().lower()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("dtparam=spi="):
                    return line.endswith("=on")
        except Exception:
            continue
    return False


def probe_hardware() -> HardwareProbe:
    """Detect the current Pi/Whisplay environment.

    Notes:
    - Whisplay presence is inferred from the WM8960 sound card and SPI/display hints.
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
