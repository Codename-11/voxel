#!/usr/bin/env python3
"""Voxel — Pocket AI companion device."""

import sys
import os
import signal
import logging

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from core.log import setup as setup_logging, boot_message, ready_message, shutdown_message

setup_logging(level=logging.INFO)
log = logging.getLogger("voxel")

# ── Constants ────────────────────────────────────────────────────────────────

BG_COLOR   = (10, 10, 15)
STATUS_BG  = (20, 20, 28)
STATUS_FG  = (160, 160, 180)

# State → status bar color
_STATE_COLORS = {
    "IDLE":      (80, 200, 160),
    "LISTENING": (80, 160, 255),
    "THINKING":  (220, 180, 60),
    "SPEAKING":  (80, 220, 120),
    "ERROR":     (255, 80, 80),
    "SLEEPING":  (100, 100, 140),
    "MENU":      (160, 160, 180),
}

# State → LED behavior
_STATE_LED = {
    "IDLE":      ("pulse", (0, 180, 160), 0.6),
    "LISTENING": ("solid", (0, 100, 255), 0),
    "THINKING":  ("pulse", (220, 180, 40), 1.5),
    "SPEAKING":  ("solid", (0, 200, 100), 0),
    "ERROR":     ("pulse", (255, 40, 40), 3.0),
    "SLEEPING":  ("pulse", (60, 60, 100), 0.2),
    "MENU":      ("solid", (160, 160, 180), 0),
}

WIDTH, HEIGHT = 240, 280
FPS = 30
STATUS_H = 24


def draw_status_bar(surface: pygame.Surface, state_name: str, mood_name: str,
                    platform_name: str, battery_level: int) -> None:
    """Draw status bar at bottom of screen."""
    bar_rect = pygame.Rect(0, HEIGHT - STATUS_H, WIDTH, STATUS_H)
    pygame.draw.rect(surface, STATUS_BG, bar_rect)
    pygame.draw.line(surface, (40, 40, 55), (0, HEIGHT - STATUS_H), (WIDTH, HEIGHT - STATUS_H))

    font = pygame.font.SysFont("monospace", 11)

    # Left: version + mood
    label = f"Voxel v0.1 | {mood_name}"
    label_surf = font.render(label, True, STATUS_FG)
    surface.blit(label_surf, (6, HEIGHT - STATUS_H + 6))

    # Right: state name
    state_color = _STATE_COLORS.get(state_name, STATUS_FG)
    state_surf = font.render(state_name, True, state_color)
    surface.blit(state_surf, (WIDTH - state_surf.get_width() - 6, HEIGHT - STATUS_H + 6))


def main() -> None:
    from hardware import display, buttons, led, battery
    from hardware.platform import PLATFORM_NAME
    from hardware.buttons import ButtonEvent
    from states.machine import StateMachine, State
    from face.renderer import FaceRenderer
    from face.expressions import Mood

    boot_message()
    log.info(f"Platform: {PLATFORM_NAME}")

    # ── Hardware init ────────────────────────────────────────────────────────
    display.init()
    buttons.init()
    led.init()
    battery.init()

    surface = display.get_surface()
    clock = display.get_clock()

    # ── State machine ────────────────────────────────────────────────────────
    sm = StateMachine()
    face = FaceRenderer()

    # Wire state changes to face renderer + LED
    def _on_state_change(old: State, new: State) -> None:
        face.on_state_change(old, new)
        mode, color, speed = _STATE_LED.get(new.name, ("pulse", (0, 180, 160), 0.6))
        if mode == "pulse":
            led.pulse(color, speed=speed)
        else:
            led.set_color(*color)

    sm.on_change(_on_state_change)

    # Trigger initial state
    _on_state_change(State.IDLE, State.IDLE)

    # ── Mood cycling for dev/testing ─────────────────────────────────────────
    moods = list(Mood)
    mood_idx = 0

    # ── Audio init (optional) ────────────────────────────────────────────────
    _audio_ok = False
    try:
        from core import audio as audio_mod
        audio_mod.init()
        _audio_ok = True
    except Exception as e:
        log.warning(f"Audio init skipped: {e}")

    running = True
    ready_message()
    log.info("Controls: Space=cycle state, Z/X=cycle mood, Escape=quit")

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0

            # ── Events ───────────────────────────────────────────────────────
            quit_events = pygame.event.get(pygame.QUIT)
            if quit_events:
                running = False
                break

            btn_events = buttons.poll()
            for evt in btn_events:
                if evt == ButtonEvent.BUTTON_MENU:
                    log.info("Quit via Escape")
                    running = False

                elif evt == ButtonEvent.BUTTON_PRESS:
                    # Cycle through states: IDLE → LISTENING → THINKING → SPEAKING → IDLE
                    cycle = [State.IDLE, State.LISTENING, State.THINKING, State.SPEAKING]
                    cur_idx = next((i for i, s in enumerate(cycle) if s == sm.state), 0)
                    nxt = cycle[(cur_idx + 1) % len(cycle)]
                    sm.transition(nxt)

                elif evt == ButtonEvent.BUTTON_LEFT:
                    # Previous mood
                    mood_idx = (mood_idx - 1) % len(moods)
                    face.set_mood(moods[mood_idx])
                    log.info(f"Mood override: {moods[mood_idx].name}")

                elif evt == ButtonEvent.BUTTON_RIGHT:
                    # Next mood
                    mood_idx = (mood_idx + 1) % len(moods)
                    face.set_mood(moods[mood_idx])
                    log.info(f"Mood override: {moods[mood_idx].name}")

            # ── Update ───────────────────────────────────────────────────────
            face.update(dt)

            # ── Render ───────────────────────────────────────────────────────
            surface.fill(BG_COLOR)
            face.draw(surface)

            # LED indicator (desktop overlay)
            led.draw_indicator(surface)

            batt = battery.get_level()
            draw_status_bar(surface, sm.state.name, face.character.get_mood().name,
                            PLATFORM_NAME, batt)

            display.update()

    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    finally:
        shutdown_message()
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


def shutdown(signum, frame) -> None:
    log.info(f"Signal {signum} received, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
