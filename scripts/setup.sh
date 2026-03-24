#!/bin/bash
# Voxel Relay — Pi Zero 2W setup script
# Installs all dependencies, builds the React app, configures systemd services.
# Run from the voxel repo root: ./scripts/setup.sh
set -e

VOXEL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VOXEL_DIR"

echo "╔══════════════════════════════════════╗"
echo "║         Voxel Relay Setup            ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Directory: $VOXEL_DIR"
echo ""

# ── 1. System packages ──────────────────────────────────────────────────────

echo "▸ Installing system dependencies..."
sudo apt update
sudo apt install -y \
    git \
    portaudio19-dev \
    libasound2-dev \
    cog

# ── 2. Node.js (for building the React app) ─────────────────────────────────

if ! command -v node &> /dev/null; then
    echo "▸ Installing Node.js via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
else
    echo "▸ Node.js already installed: $(node --version)"
fi

# ── 3. uv (Python package manager) ──────────────────────────────────────────

if ! command -v uv &> /dev/null; then
    echo "▸ Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "▸ uv already installed: $(uv --version)"
fi

# ── 4. Python dependencies ──────────────────────────────────────────────────

echo "▸ Installing Python dependencies (with Pi extras)..."
uv sync --extra pi

# ── 5. React app build ──────────────────────────────────────────────────────

echo "▸ Building React app..."
cd "$VOXEL_DIR/app"
npm install
npm run build
cd "$VOXEL_DIR"

echo "  Built to app/dist/"

# ── 6. Configuration ────────────────────────────────────────────────────────

if [ ! -f config/local.yaml ]; then
    cp config/default.yaml config/local.yaml
    echo "▸ Created config/local.yaml — edit with your gateway URL and API keys:"
    echo "    nano config/local.yaml"
else
    echo "▸ config/local.yaml already exists (skipping)"
fi

# ── 7. Systemd services ─────────────────────────────────────────────────────

echo "▸ Installing systemd services..."
sudo cp "$VOXEL_DIR/voxel.service" /etc/systemd/system/
sudo cp "$VOXEL_DIR/voxel-ui.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable voxel voxel-ui

echo ""
echo "╔══════════════════════════════════════╗"
echo "║           Setup Complete             ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Install Whisplay HAT drivers (if not done):"
echo "     curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash"
echo ""
echo "  2. Edit your configuration:"
echo "     nano config/local.yaml"
echo ""
echo "  3. Test manually:"
echo "     uv run server.py                                        # Terminal 1: backend"
echo "     COG_PLATFORM=drm cog file:///home/pi/voxel/app/dist/index.html  # Terminal 2: browser"
echo ""
echo "  4. Or start via systemd:"
echo "     sudo systemctl start voxel voxel-ui"
echo ""
echo "  5. Check logs:"
echo "     journalctl -u voxel -f        # backend logs"
echo "     journalctl -u voxel-ui -f     # browser logs"
echo ""
