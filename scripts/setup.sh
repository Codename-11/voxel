#!/bin/bash
# Axiom Companion — First-time setup
set -e

echo "=== Axiom Companion Setup ==="

# System deps
sudo apt update
sudo apt install -y python3-pip python3-venv python3-pygame libsdl2-dev \
    libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    portaudio19-dev python3-pyaudio

# Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Whisplay HAT drivers (audio + display)
echo "Install Whisplay HAT drivers from: https://docs.pisugar.com/docs/product-wiki/whisplay/driver"
echo "Run: curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash"

# Config
if [ ! -f config/local.yaml ]; then
    cp config/default.yaml config/local.yaml
    echo "Created config/local.yaml — edit with your gateway URL and API keys"
fi

echo "=== Setup complete ==="
echo "Run: python main.py"
