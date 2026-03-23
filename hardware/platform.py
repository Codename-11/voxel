"""Platform detection — Pi vs desktop."""

import platform

IS_PI = platform.machine().startswith(('aarch64', 'arm'))
PLATFORM_NAME = "Pi" if IS_PI else "Desktop"
