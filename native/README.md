# Native LVGL PoC — Experimental

This directory contains an **experimental** LVGL native renderer proof-of-concept. It pre-renders RGB565 frames on a workstation for playback on the Pi.

This is **not the production renderer**. The production display uses `display/` (PIL-SPI). CLI commands (`voxel lvgl-*`) exist for testing but this path is isolated and exploratory.
