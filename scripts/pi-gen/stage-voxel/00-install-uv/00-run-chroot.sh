#!/bin/bash -e
# Install uv (Python package manager) for the pi user

# Install uv to /home/pi/.local/bin
su - pi -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Verify installation
su - pi -c '/home/pi/.local/bin/uv --version'
