@echo off
REM Voxel — Windows desktop development launcher (uses uv)
setlocal
cd /d "%~dp0"

echo Starting Voxel (desktop mode)...
uv run main.py
