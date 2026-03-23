#!/usr/bin/env python3
"""Voxel — Pocket AI companion device."""

import sys
import signal
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("axiom")


def main():
    log.info("Voxel starting...")

    # TODO: Initialize hardware (display, buttons, LED, audio)
    # TODO: Load configuration
    # TODO: Initialize state machine
    # TODO: Initialize face renderer
    # TODO: Initialize OpenClaw gateway client
    # TODO: Start main loop

    log.info("Voxel ready.")

    # Placeholder main loop
    try:
        while True:
            # TODO: State machine tick
            # TODO: Render face
            # TODO: Process button input
            # TODO: Handle audio I/O
            pass
    except KeyboardInterrupt:
        log.info("Shutting down...")
        sys.exit(0)


def shutdown(signum, frame):
    log.info(f"Signal {signum} received, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
