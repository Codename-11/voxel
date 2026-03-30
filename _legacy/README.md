# Legacy Code — Archived

This directory contains **archived code that is no longer active**. Nothing in the active codebase imports from `_legacy/`.

Do not import, modify, or reference these files in new code. They exist only as historical reference.

| Directory/File | What it was |
|---------------|-------------|
| `main.py` | Old pygame entry point |
| `face/` | Pygame-based face renderer + sprites |
| `ui/` | Old UI screens |
| `services/` | Archived systemd units (voxel-ui, voxel-web) |
| `hardware_display.py` | Old direct hardware display code |
| `hardware_led.py` | Old LED control code |

The production display is now `display/` (PIL-SPI renderer). See the root `CLAUDE.md` for current architecture.
