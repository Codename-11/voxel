# Native — C Programs for Voxel

## boot_splash/ — Early Boot LCD Splash

Minimal C program that drives the ST7789 LCD via SPI and shows Voxel's closed-eye bars ~3 seconds after power-on, before Python starts. Zero external dependencies beyond libc and kernel headers.

- `splash.c` — C program: SPI init, ST7789 init, frame push, backlight on
- `generate_splash.py` — Python script to generate the RGB565 splash frame
- `Makefile` — Build, generate, and install targets
- `splash.rgb565` — Pre-rendered frame (generated, 134,400 bytes)
- `splash.png` — PNG preview (generated)

**Boot sequence:** `config.txt` GPIO (LED cyan, BL off) -> `voxel-splash.service` (C splash, ~3s) -> `voxel-guardian.service` (Python boot animation)

Build and install (on Pi):
```bash
cd native/boot_splash
make generate   # Generate splash frame (needs Python + Pillow)
make            # Compile C program
sudo make install  # Install binary + frame
```

Or via CLI: `voxel hw` compiles and installs automatically.

## lvgl_poc/ — Experimental LVGL Renderer

Experimental LVGL native renderer proof-of-concept. Pre-renders RGB565 frames on a workstation for playback on the Pi.

This is **not the production renderer**. The production display uses `display/` (PIL-SPI). CLI commands (`voxel lvgl-*`) exist for testing but this path is isolated and exploratory.
