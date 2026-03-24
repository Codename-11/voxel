#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Voxel Relay — Pi Zero 2W setup & management               ║
# ║                                                              ║
# ║  First-time install (curl):                                  ║
# ║    curl -sSL https://raw.githubusercontent.com/              ║
# ║      Codename-11/voxel/main/scripts/setup.sh | bash         ║
# ║                                                              ║
# ║  Interactive mode:                                           ║
# ║    ./scripts/setup.sh                                        ║
# ║                                                              ║
# ║  Direct commands:                                            ║
# ║    ./scripts/setup.sh [install|update|hw|start|stop|...]     ║
# ╚══════════════════════════════════════════════════════════════╝
set -e

REPO_URL="https://github.com/Codename-11/voxel.git"
VOXEL_DIR="${VOXEL_DIR:-/home/pi/voxel}"
SERVICES="voxel voxel-ui"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo "  ▸ $*"; }
warn()  { echo "  ⚠ $*"; }

header() {
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║  $1"
    printf "╚══════════════════════════════════════╝\n"
    echo ""
}

has_tty() {
    # Detect if we're in a terminal (not piped via curl)
    [ -t 0 ] && [ -t 1 ] && command -v whiptail &> /dev/null
}

needs_hw() {
    [ ! -e /dev/fb1 ] && return 0
    ! arecord -l 2>/dev/null | grep -q "WM8960" && return 0
    return 1
}

needs_reboot() {
    CONFIG="/boot/firmware/config.txt"
    [ -f "$CONFIG" ] || CONFIG="/boot/config.txt"
    UPTIME_SECS=$(awk '{print int($1)}' /proc/uptime)
    CONFIG_MOD=$(stat -c %Y "$CONFIG" 2>/dev/null || echo 0)
    BOOT_TIME=$(( $(date +%s) - UPTIME_SECS ))
    [ "$CONFIG_MOD" -gt "$BOOT_TIME" ] && return 0
    return 1
}

svc_state() {
    systemctl is-active "$1" 2>/dev/null || echo "unknown"
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

# ── TUI (whiptail) ──────────────────────────────────────────────────────────

tui_main() {
    while true; do
        # Build status line
        local be_state ui_state
        be_state=$(svc_state voxel)
        ui_state=$(svc_state voxel-ui)

        local choice
        choice=$(whiptail --title "Voxel Relay" \
            --menu "  Backend: $be_state  |  UI: $ui_state" 18 56 9 \
            "install"   "Full setup (deps + build + services)" \
            "update"    "Pull latest, rebuild, restart" \
            "hw"        "Hardware drivers + config.txt" \
            "start"     "Start services" \
            "stop"      "Stop services" \
            "restart"   "Restart services" \
            "status"    "System status" \
            "logs"      "Tail service logs (Ctrl+C to exit)" \
            "uninstall" "Remove Voxel completely" \
            3>&1 1>&2 2>&3) || break

        case "$choice" in
            install)   tui_install ;;
            update)    cmd_update; tui_pause ;;
            hw)        cmd_hw; tui_pause ;;
            start)     cmd_start; tui_pause ;;
            stop)      cmd_stop; tui_pause ;;
            restart)   cmd_restart; tui_pause ;;
            status)    tui_status ;;
            logs)      cmd_logs ;;
            uninstall) tui_uninstall ;;
        esac
    done
}

tui_pause() {
    echo ""
    read -rp "  Press Enter to continue..." _
}

tui_install() {
    # Confirm what will be installed
    local selections
    selections=$(whiptail --title "Install Components" \
        --checklist "Select what to install (SPACE to toggle):" 16 60 6 \
        "deps"     "System packages (apt)"        ON \
        "node"     "Node.js"                      ON \
        "uv"       "uv (Python package manager)"  ON \
        "app"      "Build React app"              ON \
        "services" "Configure systemd services"   ON \
        "hw"       "Hardware drivers + config.txt" "$(needs_hw && echo ON || echo OFF)" \
        3>&1 1>&2 2>&3) || return

    echo ""
    # Parse selections — whiptail returns "key1" "key2" ...
    if echo "$selections" | grep -q '"deps"'; then
        info "System dependencies..."
        sudo apt update
        sudo apt install -y git portaudio19-dev libasound2-dev python3-dev cog
    fi

    if echo "$selections" | grep -q '"node"'; then
        ensure_node
    fi

    if echo "$selections" | grep -q '"uv"'; then
        ensure_uv
    fi

    ensure_repo

    if echo "$selections" | grep -q '"app"'; then
        build_app
    fi

    # Config
    if [ ! -f "$VOXEL_DIR/config/local.yaml" ]; then
        cp "$VOXEL_DIR/config/default.yaml" "$VOXEL_DIR/config/local.yaml"
        info "Created config/local.yaml"
    fi

    if echo "$selections" | grep -q '"services"'; then
        install_services
    fi

    if echo "$selections" | grep -q '"hw"'; then
        cmd_hw
    fi

    # Reboot check
    if needs_reboot; then
        if whiptail --title "Reboot Required" \
            --yesno "Hardware drivers were installed.\nReboot now to activate them?" 10 50; then
            sudo reboot
        fi
    else
        whiptail --title "Install Complete" \
            --msgbox "Voxel is installed!\n\nNext: edit config/local.yaml, then start services." 10 50
    fi
}

tui_status() {
    local be_state ui_state
    be_state=$(svc_state voxel)
    ui_state=$(svc_state voxel-ui)

    local mem_used mem_total
    mem_used=$(free -m | awk '/^Mem:/ {print $3}')
    mem_total=$(free -m | awk '/^Mem:/ {print $2}')

    local batt_line=""
    local batt
    batt=$(curl -sf http://localhost:8421/api/battery 2>/dev/null || true)
    [ -n "$batt" ] && batt_line="\n  Battery:     $batt"

    local fb_line audio_line
    [ -e /dev/fb1 ] && fb_line="present" || fb_line="NOT FOUND"
    arecord -l 2>/dev/null | grep -q "WM8960" && audio_line="WM8960" || audio_line="NOT FOUND"

    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    whiptail --title "Voxel Status" \
        --msgbox "\
  Services
  ──────────────────────────
  Backend (voxel):     $be_state
  UI (voxel-ui):       $ui_state

  Hardware
  ──────────────────────────
  Display (/dev/fb1):  $fb_line
  Audio (WM8960):      $audio_line

  System
  ──────────────────────────
  IP Address:    $ip
  Memory:        ${mem_used}MB / ${mem_total}MB$batt_line
" 22 50
}

tui_uninstall() {
    if whiptail --title "Uninstall Voxel" \
        --yesno --defaultno \
        "This will:\n- Stop and remove systemd services\n- Delete $VOXEL_DIR\n- Clean uv cache\n\nAre you sure?" \
        12 50; then
        cmd_uninstall
        whiptail --title "Uninstalled" \
            --msgbox "Voxel has been removed.\n\nSystem packages (Node.js, cog, etc.) were kept." 10 50
        exit 0
    fi
}

# ── CLI Commands ─────────────────────────────────────────────────────────────

cmd_install() {
    header "Voxel Relay — Install"

    info "System dependencies..."
    sudo apt update
    sudo apt install -y git portaudio19-dev libasound2-dev python3-dev cog

    ensure_node
    ensure_uv
    ensure_repo
    build_app

    if [ ! -f config/local.yaml ]; then
        cp config/default.yaml config/local.yaml
        info "Created config/local.yaml"
    else
        info "config/local.yaml already exists"
    fi

    install_services

    # Auto-detect hardware needs
    if needs_hw; then
        echo ""
        info "Hardware drivers not detected — running hw setup..."
        echo ""
        cmd_hw
    fi

    if needs_reboot; then
        header "Install complete — reboot needed"
        echo "  Hardware drivers were installed. Reboot to activate:"
        echo "    sudo reboot"
        echo ""
        echo "  After reboot:"
        echo "    cd ~/voxel"
        echo "    nano config/local.yaml"
        echo "    ./scripts/setup.sh start"
        echo ""
    else
        header "Install complete            "
        echo "  Next: nano config/local.yaml && ./scripts/setup.sh start"
        echo ""
    fi
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

    if needs_hw; then
        info "Installing Whisplay HAT drivers (display + audio)..."
        local whisplay_tmp
        whisplay_tmp=$(mktemp -d)

        cleanup_whisplay_tmp() {
            rm -rf "$whisplay_tmp"
        }

        trap cleanup_whisplay_tmp RETURN

        if ! command -v git &> /dev/null; then
            info "Installing git (required to fetch PiSugar drivers)..."
            sudo apt update
            sudo apt install -y git
        fi

        info "Fetching PiSugar Whisplay driver repo..."
        git clone --depth 1 https://github.com/PiSugar/Whisplay.git "$whisplay_tmp/Whisplay"

        if [ ! -f "$whisplay_tmp/Whisplay/Driver/install_wm8960_drive.sh" ]; then
            warn "PiSugar driver installer not found in cloned repo"
            return 1
        fi

        (
            cd "$whisplay_tmp/Whisplay/Driver"
            sudo bash ./install_wm8960_drive.sh
        )
    else
        info "Whisplay drivers already installed"
    fi

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
    echo "  Reboot to activate: sudo reboot"
    echo ""
}

cmd_start() {
    if needs_hw; then
        warn "Hardware drivers not detected. Run: ./scripts/setup.sh hw"
        echo ""
    fi
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

    for svc in $SERVICES; do
        STATE=$(svc_state "$svc")
        case "$STATE" in
            active)   icon="●" ;;
            inactive) icon="○" ;;
            *)        icon="✕" ;;
        esac
        printf "  %s %-14s %s\n" "$icon" "$svc" "$STATE"
    done
    echo ""

    MEM_USED=$(free -m | awk '/^Mem:/ {print $3}')
    MEM_TOTAL=$(free -m | awk '/^Mem:/ {print $2}')
    info "Memory: ${MEM_USED}MB / ${MEM_TOTAL}MB"

    BATT=$(curl -sf http://localhost:8421/api/battery 2>/dev/null || true)
    [ -n "$BATT" ] && info "Battery: $BATT"

    if [ -e /dev/fb1 ]; then
        info "Display: /dev/fb1 ✓"
    else
        warn "Display: /dev/fb1 not found"
    fi

    if arecord -l 2>/dev/null | grep -q "WM8960"; then
        info "Audio: WM8960 ✓"
    else
        warn "Audio: WM8960 not found"
    fi

    echo ""
}

cmd_uninstall() {
    header "Voxel Relay — Uninstall     "

    info "Stopping services..."
    sudo systemctl stop $SERVICES 2>/dev/null || true
    sudo systemctl disable $SERVICES 2>/dev/null || true

    info "Removing systemd units..."
    sudo rm -f /etc/systemd/system/voxel.service
    sudo rm -f /etc/systemd/system/voxel-ui.service
    sudo systemctl daemon-reload

    if [ -d "$VOXEL_DIR" ]; then
        info "Removing $VOXEL_DIR..."
        rm -rf "$VOXEL_DIR"
    fi

    if [ -d "$HOME/.cache/uv" ]; then
        info "Cleaning uv cache..."
        rm -rf "$HOME/.cache/uv"
    fi

    header "Uninstall complete          "
    echo "  Kept (shared system packages):"
    echo "    Node.js, uv, cog, python3-dev, Whisplay drivers"
    echo ""
    echo "  To remove those too:"
    echo "    sudo apt remove -y cog nodejs"
    echo "    rm -rf ~/.local/bin/uv ~/.local/share/uv"
    echo ""
}

cmd_help() {
    echo "Usage: ./scripts/setup.sh [command]"
    echo ""
    echo "  No argument = interactive TUI (if terminal available)"
    echo ""
    echo "Commands:"
    echo "  install     Full first-time setup"
    echo "  update      Pull latest, rebuild, restart"
    echo "  hw          Whisplay drivers + config.txt tuning"
    echo "  start       Start services"
    echo "  stop        Stop services"
    echo "  restart     Restart services"
    echo "  logs        Tail service logs"
    echo "  status      Show service/system status"
    echo "  uninstall   Remove services, repo, and caches"
    echo "  help        Show this message"
    echo ""
    echo "Curl install (non-interactive):"
    echo "  curl -sSL https://raw.githubusercontent.com/Codename-11/voxel/main/scripts/setup.sh | bash"
    echo ""
}

# ── Entrypoint ───────────────────────────────────────────────────────────────

# No args + TTY = interactive TUI
# No args + piped = headless install
# With args = direct command
if [ $# -eq 0 ]; then
    if has_tty; then
        tui_main
    else
        cmd_install
    fi
else
    case "$1" in
        install)   cmd_install ;;
        update)    cmd_update ;;
        hw)        cmd_hw ;;
        start)     cmd_start ;;
        stop)      cmd_stop ;;
        restart)   cmd_restart ;;
        logs)      cmd_logs ;;
        status)    cmd_status ;;
        uninstall) cmd_uninstall ;;
        help|-h|--help) cmd_help ;;
        *)
            echo "Unknown command: $1"
            cmd_help
            exit 1
            ;;
    esac
fi
