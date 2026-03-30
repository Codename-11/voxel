#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Voxel Relay — Bootstrap                                    ║
# ║                                                              ║
# ║  Safe to re-run. Idempotent. One command to set up a Pi:    ║
# ║                                                              ║
# ║    curl -sSL https://raw.githubusercontent.com/              ║
# ║      Codename-11/voxel/main/scripts/setup.sh | bash         ║
# ║                                                              ║
# ║  After setup completes: sudo reboot                         ║
# ║  After reboot, the device auto-starts and guides you        ║
# ║  through WiFi + configuration on the LCD screen.            ║
# ╚══════════════════════════════════════════════════════════════╝
set -e

REPO_URL="https://github.com/Codename-11/voxel.git"
VOXEL_DIR="${VOXEL_DIR:-/home/pi/voxel}"

info()  { echo "  [*] $*"; }
ok()    { echo "  [+] $*"; }
err()   { echo "  [!] $*" >&2; }

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     Voxel Relay — Bootstrap          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Git ───────────────────────────────────────────────────────────────────

if ! command -v git &> /dev/null; then
    info "Installing git..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq git
fi
ok "git available"

# ── 2. Clone or update repo ─────────────────────────────────────────────────

if [ -d "$VOXEL_DIR/.git" ]; then
    info "Updating existing repo at $VOXEL_DIR..."
    cd "$VOXEL_DIR"
    git pull --ff-only || true
else
    info "Cloning voxel repo..."
    git clone "$REPO_URL" "$VOXEL_DIR"
    cd "$VOXEL_DIR"
fi
ok "Repo ready at $VOXEL_DIR"

# ── 3. uv (Python package manager) ──────────────────────────────────────────

if ! command -v uv &> /dev/null; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    ok "uv $(uv --version 2>/dev/null || echo 'installed')"
fi

# ── 4. Python deps (needed for the voxel CLI) ───────────────────────────────

info "Syncing Python dependencies..."
sudo apt-get install -y -qq python3-dev 2>/dev/null || true

if uname -m | grep -qE '^(aarch64|arm)'; then
    uv sync --extra pi
else
    uv sync
fi
ok "Python environment ready"

# ── 5. Global `voxel` command ────────────────────────────────────────────────

if [ ! -x /usr/local/bin/voxel ]; then
    info "Installing voxel command..."
    sudo tee /usr/local/bin/voxel > /dev/null <<WRAPPER
#!/bin/bash
# Voxel CLI wrapper — delegates to uv-managed Python entry point
exec $HOME/.local/bin/uv run --project $VOXEL_DIR voxel "\$@"
WRAPPER
    sudo chmod +x /usr/local/bin/voxel
fi
ok "voxel command available"

# ── 6. Run full setup (includes hw drivers on Pi) ───────────────────────────

echo ""
info "Running voxel setup..."
echo ""

voxel setup
