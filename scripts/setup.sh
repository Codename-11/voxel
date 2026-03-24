#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Voxel Relay — Pi Zero 2W setup & management               ║
# ║                                                              ║
# ║  First-time install (curl):                                  ║
# ║    curl -sSL https://voxel.sh/setup | bash                  ║
# ║    — or —                                                    ║
# ║    curl -sSL https://raw.githubusercontent.com/              ║
# ║      Codename-11/voxel/main/scripts/setup.sh | bash         ║
# ║                                                              ║
# ║  From repo:                                                  ║
# ║    ./scripts/setup.sh [command]                              ║
# ║                                                              ║
# ║  Commands:                                                   ║
# ║    install   Full first-time setup (default)                 ║
# ║    update    Pull latest, rebuild, restart services          ║
# ║    hw        Install Whisplay HAT drivers + tune config.txt  ║
# ║    start     Start Voxel services                            ║
# ║    stop      Stop Voxel services                             ║
# ║    restart   Restart Voxel services                          ║
# ║    logs      Tail backend + UI logs                          ║
# ║    status    Show service status, battery, memory            ║
# ╚══════════════════════════════════════════════════════════════╝
set -e

REPO_URL="https://github.com/Codename-11/voxel.git"
VOXEL_DIR="${VOXEL_DIR:-/home/pi/voxel}"
SERVICES="voxel voxel-ui"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo "  ▸ $*"; }
header() {
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║  $1"
    printf "╚══════════════════════════════════════╝\n"
    echo ""
}

ensure_repo() {
    if [ ! -d "$VOXEL_DIR/.git" ]; then
        info "Cloning voxel repo..."
        git clone "$REPO_URL" "$VOXEL_DIR"
    fi
    cd "$VOXEL_DIR"
}

ensure_node() {
    if ! command -v node &> /dev/null; then
        info "Installing Node.js via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
        sudo apt install -y nodejs
    else
        info "Node.js $(node --version)"
    fi
}

ensure_uv() {
    if ! command -v uv &> /dev/null; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    else
        info "uv $(uv --version)"
    fi
}

build_app() {
    info "Python dependencies..."
    uv sync --extra pi

    info "Building React app..."
    cd "$VOXEL_DIR/app"
    npm install
    npm run build
    cd "$VOXEL_DIR"
    info "Built → app/dist/"
}

install_services() {
    info "Installing systemd services..."
    sudo cp "$VOXEL_DIR/voxel.service" /etc/systemd/system/
    sudo cp "$VOXEL_DIR/voxel-ui.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICES
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_install() {
    header "Voxel Relay — Install"

    # System packages
    info "System dependencies..."
    sudo apt update
    sudo apt install -y git portaudio19-dev libasound2-dev cog

    ensure_node
    ensure_uv
    ensure_repo
    build_app

    # Config
    if [ ! -f config/local.yaml ]; then
        cp config/default.yaml config/local.yaml
        info "Created config/local.yaml"
    else
        info "config/local.yaml already exists"
    fi

    install_services

    header "Install complete            "
    echo "  Next steps:"
    echo ""
    echo "  1. If you haven't installed hardware drivers yet:"
    echo "     ./scripts/setup.sh hw"
    echo ""
    echo "  2. Edit your config:"
    echo "     nano config/local.yaml"
    echo ""
    echo "  3. Start Voxel:"
    echo "     ./scripts/setup.sh start"
    echo ""
}

cmd_update() {
    header "Voxel Relay — Update        "
    ensure_repo

    info "Pulling latest..."
    git pull origin main

    ensure_node
    ensure_uv
    build_app
    install_services

    info "Restarting services..."
    sudo systemctl restart $SERVICES

    header "Update complete             "
    cmd_status
}

cmd_hw() {
    header "Hardware Setup               "

    # Whisplay HAT drivers
    info "Installing Whisplay HAT drivers (display + audio)..."
    curl -sSL https://docs.pisugar.com/whisplay/install.sh | sudo bash

    # GPU memory + HDMI power saving
    CONFIG="/boot/firmware/config.txt"
    [ -f "$CONFIG" ] || CONFIG="/boot/config.txt"

    if ! grep -q "gpu_mem=128" "$CONFIG" 2>/dev/null; then
        info "Tuning $CONFIG..."
        sudo tee -a "$CONFIG" > /dev/null <<'BOOT'

# ── Voxel display settings ──
gpu_mem=128
hdmi_blanking=2
BOOT
        info "Added gpu_mem=128, hdmi_blanking=2"
    else
        info "$CONFIG already configured"
    fi

    # Swap
    if [ -f /etc/dphys-swapfile ]; then
        CURRENT_SWAP=$(grep "^CONF_SWAPSIZE" /etc/dphys-swapfile | cut -d= -f2)
        if [ "${CURRENT_SWAP:-100}" -lt 256 ]; then
            info "Increasing swap to 256MB..."
            sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=256/' /etc/dphys-swapfile
            sudo systemctl restart dphys-swapfile
        else
            info "Swap already ${CURRENT_SWAP}MB"
        fi
    fi

    header "Hardware setup complete      "
    echo "  Verify after reboot:"
    echo "    ls /dev/fb*       # should show /dev/fb1"
    echo "    arecord -l        # should show WM8960"
    echo ""
    echo "  Reboot now?"
    echo "    sudo reboot"
    echo ""
}

cmd_start() {
    info "Starting Voxel..."
    sudo systemctl start $SERVICES
    sleep 2
    cmd_status
}

cmd_stop() {
    info "Stopping Voxel..."
    sudo systemctl stop $SERVICES
    cmd_status
}

cmd_restart() {
    info "Restarting Voxel..."
    sudo systemctl restart $SERVICES
    sleep 2
    cmd_status
}

cmd_logs() {
    journalctl -u voxel -u voxel-ui -f --no-hostname -o short-iso
}

cmd_status() {
    header "Voxel Status                "

    # Services
    for svc in $SERVICES; do
        STATE=$(systemctl is-active "$svc" 2>/dev/null || true)
        case "$STATE" in
            active)   icon="●" ;;
            inactive) icon="○" ;;
            *)        icon="✕" ;;
        esac
        printf "  %s %-14s %s\n" "$icon" "$svc" "$STATE"
    done
    echo ""

    # Memory
    MEM_USED=$(free -m | awk '/^Mem:/ {print $3}')
    MEM_TOTAL=$(free -m | awk '/^Mem:/ {print $2}')
    info "Memory: ${MEM_USED}MB / ${MEM_TOTAL}MB"

    # Battery (if PiSugar API is available)
    BATT=$(curl -sf http://localhost:8421/api/battery 2>/dev/null || true)
    if [ -n "$BATT" ]; then
        info "Battery: $BATT"
    fi

    # Display
    if [ -e /dev/fb1 ]; then
        info "Display: /dev/fb1 present"
    else
        info "Display: /dev/fb1 not found (run: ./scripts/setup.sh hw)"
    fi

    echo ""
}

cmd_help() {
    echo "Usage: ./scripts/setup.sh [command]"
    echo ""
    echo "Commands:"
    echo "  install   Full first-time setup (default)"
    echo "  update    Pull latest, rebuild, restart"
    echo "  hw        Whisplay drivers + config.txt tuning"
    echo "  start     Start services"
    echo "  stop      Stop services"
    echo "  restart   Restart services"
    echo "  logs      Tail service logs"
    echo "  status    Show service/system status"
    echo "  help      Show this message"
    echo ""
    echo "First-time curl install:"
    echo "  curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash"
    echo ""
}

# ── Entrypoint ───────────────────────────────────────────────────────────────

CMD="${1:-install}"

case "$CMD" in
    install) cmd_install ;;
    update)  cmd_update ;;
    hw)      cmd_hw ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    logs)    cmd_logs ;;
    status)  cmd_status ;;
    help|-h|--help) cmd_help ;;
    *)
        echo "Unknown command: $CMD"
        cmd_help
        exit 1
        ;;
esac
