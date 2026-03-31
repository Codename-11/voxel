# Voxel Boot Splash — build and install
#
# Build:   make
# Install: sudo make install
# Clean:   make clean
#
# Cross-compile for Pi from x86:
#   make CC=aarch64-linux-gnu-gcc

CC      ?= gcc
CFLAGS   = -O2 -Wall -Wextra -Wno-unused-parameter
LDFLAGS  =

PREFIX   = /usr/local/bin
SPLASH_DEST = /boot/voxel-splash.rgb565

.PHONY: all install install-frame generate clean

all: splash

splash: splash.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

# Generate the RGB565 splash frame (requires Python + Pillow)
generate:
	python3 generate_splash.py

# Install binary + frame file
install: splash
	sudo cp splash $(PREFIX)/voxel-splash
	sudo chmod 755 $(PREFIX)/voxel-splash
	@if [ -f splash.rgb565 ]; then \
		sudo cp splash.rgb565 $(SPLASH_DEST); \
		echo "Installed splash frame to $(SPLASH_DEST)"; \
	else \
		echo "WARNING: splash.rgb565 not found — run 'make generate' first"; \
	fi

# Install just the frame file (no compilation needed)
install-frame:
	@if [ -f splash.rgb565 ]; then \
		sudo cp splash.rgb565 $(SPLASH_DEST); \
		echo "Installed splash frame to $(SPLASH_DEST)"; \
	else \
		echo "ERROR: splash.rgb565 not found — run 'make generate' first"; \
		exit 1; \
	fi

clean:
	rm -f splash
