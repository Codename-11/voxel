#!/bin/bash
# Voxel — First-time Pi setup
set -e

echo "=== Voxel Setup ==="

# System deps
sudo apt update
sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    portaudio19-dev

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install project with Pi extras
uv sync --extra pi

# Whisplay HAT drivers (audio + display)
echo ""
echo "Install Whisplay HAT drivers from: https://docs.pisugar.com/docs/product-wiki/whisplay/driver"
echo "Run: curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash"

# Config
if [ ! -f config/local.yaml ]; then
    cp config/default.yaml config/local.yaml
    echo "Created config/local.yaml — edit with your gateway URL and API keys"
fi

echo ""
echo "=== Setup complete ==="
echo "Run: uv run main.py"
