#!/bin/bash
# Voxel — Desktop development launcher (uses uv)
set -e
cd "$(dirname "$0")"

echo "Starting Voxel (desktop mode)..."
uv run main.py
