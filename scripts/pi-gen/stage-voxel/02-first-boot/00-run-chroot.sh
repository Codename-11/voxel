#!/bin/bash -e
# Install a one-shot systemd service that runs on first boot to install
# Whisplay HAT drivers (WM8960 kernel module). These cannot be compiled
# in a chroot — they need real Pi hardware or matching kernel headers.

VOXEL_DIR="/home/pi/voxel"

# Copy the first-boot service unit
cp "${VOXEL_DIR}/services/voxel-first-boot.service" /etc/systemd/system/voxel-first-boot.service

# Enable it (runs once on first boot, then disables itself)
systemctl enable voxel-first-boot.service
