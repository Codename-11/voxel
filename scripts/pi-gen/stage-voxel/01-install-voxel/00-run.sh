#!/bin/bash -e
# Copy the voxel repo into the image filesystem (runs on build host)
# ${ROOTFS_DIR} is the mounted image root provided by pi-gen
# Source tree is prepared at /tmp/voxel-src by the workflow

VOXEL_SRC="/tmp/voxel-src"

if [ ! -d "${VOXEL_SRC}" ]; then
    echo "ERROR: Source tree not found at ${VOXEL_SRC}"
    echo "The workflow should prepare it before pi-gen runs."
    exit 1
fi

install -v -d "${ROOTFS_DIR}/home/pi/voxel"

rsync -a \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.cache' \
    --exclude='.claude' \
    --exclude='.code' \
    --exclude='out' \
    --exclude='wsl-setup-check.txt' \
    "${VOXEL_SRC}/" \
    "${ROOTFS_DIR}/home/pi/voxel/"

# Ensure the pre-built React app is included
if [ -d "${ROOTFS_DIR}/home/pi/voxel/app/dist" ]; then
    echo "React app dist/ found in image"
else
    echo "WARNING: app/dist/ not found — React app was not pre-built"
fi

# Set ownership (numeric IDs — pi is 1000:1000 on Raspberry Pi OS)
chown -R 1000:1000 "${ROOTFS_DIR}/home/pi/voxel"
