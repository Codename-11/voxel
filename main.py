#!/usr/bin/env python3
"""Voxel — Pocket AI companion device."""

import sys
import signal
import logging

import pygame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("voxel")

# ── Colors ────────────────────────────────────────────────────────────────────
BG_COLOR        = (10, 10, 15)       # #0a0a0f
CYAN            = (0, 220, 210)
EYE_HIGHLIGHT   = (180, 255, 252)
MOUTH_COLOR     = (0, 200, 190)
STATUS_BG       = (20, 20, 28)
STATUS_FG       = (160, 160, 180)
STATE_IDLE_FG   = (80, 200, 160)
STATE_LISTEN_FG = (80, 160, 255)

WIDTH, HEIGHT = 240, 280
FPS = 30
STATUS_H = 24


def draw_face(surface: pygame.Surface, state_text: str) -> None:
    """Draw a simple placeholder face: two oval eyes and a small arc mouth."""
    cx = WIDTH // 2

    # ── Eyes ──────────────────────────────────────────────────────────────────
    eye_y = 120
    eye_w, eye_h = 44, 32
    left_eye_rect  = pygame.Rect(cx - 60 - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)
    right_eye_rect = pygame.Rect(cx + 60 - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)

    pygame.draw.ellipse(surface, CYAN, left_eye_rect)
    pygame.draw.ellipse(surface, CYAN, right_eye_rect)

    # Highlight dot on each eye
    hl_size = 8
    pygame.draw.ellipse(surface, EYE_HIGHLIGHT,
                        (left_eye_rect.x + 8, left_eye_rect.y + 6, hl_size, hl_size))
    pygame.draw.ellipse(surface, EYE_HIGHLIGHT,
                        (right_eye_rect.x + 8, right_eye_rect.y + 6, hl_size, hl_size))

    # ── Mouth ─────────────────────────────────────────────────────────────────
    mouth_rect = pygame.Rect(cx - 28, 168, 56, 30)
    # Draw arc as a series of points (pygame.draw.arc draws outline only)
    pygame.draw.arc(surface, MOUTH_COLOR, mouth_rect,
                    -2.4, -0.74, 3)  # roughly bottom half of ellipse = smile


def draw_status_bar(surface: pygame.Surface, state_text: str, platform_name: str,
                    battery_level: int, led_color: tuple) -> None:
    """Draw status bar at bottom of screen."""
    bar_rect = pygame.Rect(0, HEIGHT - STATUS_H, WIDTH, STATUS_H)
    pygame.draw.rect(surface, STATUS_BG, bar_rect)
    # Divider line
    pygame.draw.line(surface, (40, 40, 55), (0, HEIGHT - STATUS_H), (WIDTH, HEIGHT - STATUS_H))

    font = pygame.font.SysFont("monospace", 11)

    label = f"Voxel v0.1 | {platform_name}"
    label_surf = font.render(label, True, STATUS_FG)
    surface.blit(label_surf, (6, HEIGHT - STATUS_H + 6))

    # State text (right-aligned)
    state_color = STATE_LISTEN_FG if state_text == "Listening" else STATE_IDLE_FG
    state_surf = font.render(state_text, True, state_color)
    surface.blit(state_surf, (WIDTH - state_surf.get_width() - 6, HEIGHT - STATUS_H + 6))


def main() -> None:
    from hardware import display, buttons, led, battery
    from hardware.platform import PLATFORM_NAME

    log.info(f"Voxel starting — platform: {PLATFORM_NAME}")

    # ── Hardware init ─────────────────────────────────────────────────────────
    display.init()
    buttons.init()
    led.init()
    battery.init()

    # Set idle LED: soft cyan pulse
    led.pulse((0, 180, 160), speed=0.6)

    surface = display.get_surface()
    clock   = display.get_clock()

    # ── Audio init (optional — don't crash if not available) ─────────────────
    try:
        from core import audio as audio_mod
        audio_mod.init()
        _audio_ok = True
    except Exception as e:
        log.warning(f"Audio init failed: {e}")
        _audio_ok = False

    state_text = "Idle"
    running    = True

    log.info("Voxel ready. Space=toggle state, Escape=quit")

    try:
        while running:
            # ── Events ────────────────────────────────────────────────────────
            # Consume all pygame events (buttons.poll reads KEYDOWN internally)
            quit_events = pygame.event.get(pygame.QUIT)
            if quit_events:
                running = False
                break

            btn_events = buttons.poll()
            for evt in btn_events:
                from hardware.buttons import ButtonEvent
                if evt == ButtonEvent.BUTTON_MENU:
                    log.info("Quit via Escape")
                    running = False
                elif evt == ButtonEvent.BUTTON_PRESS:
                    # Toggle state
                    state_text = "Listening" if state_text == "Idle" else "Idle"
                    log.info(f"State toggled: {state_text}")
                    if state_text == "Listening":
                        led.set_color(0, 100, 255)
                    else:
                        led.pulse((0, 180, 160), speed=0.6)

            # ── Render ────────────────────────────────────────────────────────
            surface.fill(BG_COLOR)
            draw_face(surface, state_text)

            # LED indicator (desktop only — overlays top-right corner)
            led.draw_indicator(surface)

            batt = battery.get_level()
            draw_status_bar(surface, state_text, PLATFORM_NAME, batt, led.get_color())

            display.update()
            clock.tick(FPS)

    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    finally:
        log.info("Shutting down...")
        led.cleanup()
        buttons.cleanup()
        if _audio_ok:
            try:
                audio_mod.cleanup()
            except Exception:
                pass
        battery.cleanup()
        display.cleanup()
        pygame.quit()
        log.info("Voxel stopped.")


def shutdown(signum, frame) -> None:
    log.info(f"Signal {signum} received, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
