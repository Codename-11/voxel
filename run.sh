#!/bin/bash
set -e
cd "$(dirname "$0")"
# Use python3.12 if available (needed for pygame wheel compatibility on some systems)
PYTHON=$(command -v python3.12 2>/dev/null || command -v python3 || echo python3)
"$PYTHON" -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q pygame numpy Pillow pyyaml
python main.py
