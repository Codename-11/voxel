#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Voxel Relay — Bootstrap                                    ║
# ║                                                              ║
# ║  This script bootstraps the Voxel CLI on a fresh Pi.        ║
# ║  After bootstrap, use the `voxel` command for everything:   ║
# ║                                                              ║
# ║    voxel setup     — first-time install                     ║
# ║    voxel doctor    — diagnose system health                 ║
# ║    voxel update    — pull latest, rebuild, restart          ║
# ║    voxel hw        — Whisplay HAT drivers + Pi tuning       ║
# ║    voxel start     — start services                         ║
# ║    voxel stop      — stop services                          ║
# ║    voxel restart   — restart services                       ║
# ║    voxel logs      — tail service logs                      ║
# ║    voxel status    — show status                            ║
# ║    voxel config    — show / edit configuration              ║
# ║    voxel doctor    — full system health check               ║
# ║    voxel uninstall — remove everything                      ║
# ║                                                              ║
# ║  Curl install:                                               ║
# ║    curl -sSL https://raw.githubusercontent.com/              ║
# ║      Codename-11/voxel/main/scripts/setup.sh | bash         ║
# ╚══════════════════════════════════════════════════════════════╝
set -e

REPO_URL="https://github.com/Codename-11/voxel.git"
VOXEL_DIR="${VOXEL_DIR:-/home/pi/voxel}"

info()  { echo "  ▸ $*"; }

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     Voxel Relay — Bootstrap          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Git ───────────────────────────────────────────────────────────────────

if ! command -v git &> /dev/null; then
    info "Installing git..."
    sudo apt update
    sudo apt install -y git
fi

# ── 2. Clone repo ───────────────────────────────────────────────────────────

if [ ! -d "$VOXEL_DIR/.git" ]; then
    info "Cloning voxel repo..."
    git clone "$REPO_URL" "$VOXEL_DIR"
else
    info "Repo already at $VOXEL_DIR"
fi

cd "$VOXEL_DIR"

# ── 3. uv ───────────────────────────────────────────────────────────────────

if ! command -v uv &> /dev/null; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    info "uv $(uv --version)"
fi

# ── 4. Python deps (needed for the CLI) ─────────────────────────────────────

info "Installing Python dependencies..."
sudo apt install -y python3-dev 2>/dev/null || true

# Detect Pi and include extras
if uname -m | grep -qE '^(aarch64|arm)'; then
    uv sync --extra pi
else
    uv sync
fi

# ── 5. Global `voxel` command ──────────────────────────────────────────────

info "Installing voxel command..."
sudo tee /usr/local/bin/voxel > /dev/null <<WRAPPER
#!/bin/bash
# Voxel CLI wrapper — delegates to uv-managed Python entry point
exec $HOME/.local/bin/uv run --project $VOXEL_DIR voxel "\$@"
WRAPPER
sudo chmod +x /usr/local/bin/voxel

# ── 6. Hand off to the Voxel CLI ────────────────────────────────────────────

echo ""
info "Bootstrap complete! Running voxel setup..."
echo ""

exec voxel setup
