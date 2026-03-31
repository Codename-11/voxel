#!/bin/bash -e
# Install Python deps, systemd services, voxel CLI wrapper, and setup state
# Runs inside the ARM chroot (qemu emulation)

VOXEL_DIR="/home/pi/voxel"

# ── Python dependencies ─────────────────────────────────────────────────────

su - pi -c "cd ${VOXEL_DIR} && /home/pi/.local/bin/uv sync --extra pi"

# ── Local config from defaults ───────────────────────────────────────────────

if [ ! -f "${VOXEL_DIR}/config/local.yaml" ]; then
    cp "${VOXEL_DIR}/config/default.yaml" "${VOXEL_DIR}/config/local.yaml"
    chown 1000:1000 "${VOXEL_DIR}/config/local.yaml"
fi

# ── Systemd services ────────────────────────────────────────────────────────
# Install all 4 core services + first-boot driver installer

cp "${VOXEL_DIR}/services/voxel-splash.service"     /etc/systemd/system/voxel-splash.service
cp "${VOXEL_DIR}/services/voxel-guardian.service"    /etc/systemd/system/voxel-guardian.service
cp "${VOXEL_DIR}/services/voxel.service"             /etc/systemd/system/voxel.service
cp "${VOXEL_DIR}/services/voxel-display.service"     /etc/systemd/system/voxel-display.service
cp "${VOXEL_DIR}/services/voxel-first-boot.service"  /etc/systemd/system/voxel-first-boot.service

# Enable services (they start on boot)
systemctl enable voxel-splash.service
systemctl enable voxel-guardian.service
systemctl enable voxel.service
systemctl enable voxel-display.service
systemctl enable voxel-first-boot.service

# ── Global voxel CLI wrapper ────────────────────────────────────────────────

cat > /usr/local/bin/voxel << 'WRAPPER'
#!/bin/bash
exec /home/pi/.local/bin/uv run --project /home/pi/voxel voxel "$@"
WRAPPER
chmod +x /usr/local/bin/voxel

# ── Boot splash frame ──────────────────────────────────────────────────────
# Pre-copy the RGB565 splash frame so it's ready on first boot.
# The splash C binary can't be compiled in chroot (ARM) — first-boot handles that.

SPLASH_FRAME="${VOXEL_DIR}/native/boot_splash/splash.rgb565"
if [ -f "${SPLASH_FRAME}" ]; then
    cp "${SPLASH_FRAME}" /boot/voxel-splash.rgb565
    echo "Splash frame installed to /boot/voxel-splash.rgb565"
else
    echo "WARNING: splash.rgb565 not found — splash will show blank on first boot"
fi

# ── Setup state ─────────────────────────────────────────────────────────────
# Tracks which setup steps are already done in the pre-built image.
# The `voxel setup` command reads this to skip completed steps.
# drivers_installed is false because kernel modules need real Pi hardware.

cat > "${VOXEL_DIR}/config/.setup-state" << 'STATE'
system_deps: true
uv_installed: true
python_deps: true
build_complete: true
config_created: true
services_installed: true
drivers_installed: false
STATE
chown 1000:1000 "${VOXEL_DIR}/config/.setup-state"

# ── Fix ownership ───────────────────────────────────────────────────────────

chown -R 1000:1000 /home/pi/voxel /home/pi/.local
