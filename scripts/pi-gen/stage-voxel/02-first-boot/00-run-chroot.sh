#!/bin/bash -e
# Verify first-boot service was installed by the previous stage.
# The actual service unit is installed and enabled in 01-install-voxel.
# This stage is kept as a safety check.

if systemctl is-enabled voxel-first-boot.service >/dev/null 2>&1; then
    echo "voxel-first-boot.service is enabled — OK"
else
    echo "ERROR: voxel-first-boot.service not enabled — check 01-install-voxel"
    exit 1
fi
