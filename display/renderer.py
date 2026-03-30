"""PILRenderer — composes face + dashboard components into a 240x280 PIL Image."""

from __future__ import annotations

import logging
import time

from PIL import Image, ImageDraw

from shared import load_expressions, load_styles, Expression, BodyConfig
from config.settings import load_settings
from display.state import DisplayState
from display.fonts import get_font, text_width
from display.layout import SCREEN_W, SCREEN_H, CORNER_RADIUS, STATUS_H
from display.animation import BlinkState, GazeDrift, MoodTransition, BreathingState
from display.transitions import ViewTransition, OverlayFade, DrawerSlide
from display.characters import get_character
from display.components.face import BG
from display.decorations import draw_mood_decorations
from display.status_decorations import draw_status_decorations
from display.demo import DemoController
from display.components.status_bar import draw_status_bar
from display.components.transcript import (
    draw_transcript_overlay,
    draw_chat_drawer,
    draw_chat_full,
    draw_chat_peek,
    draw_view_dots,
)
from display.components.menu import draw_menu, MenuState
from display.components.button_indicator import draw_button_indicator
from display.components.speaking_pill import (
    draw_speaking_pill, draw_listening_indicator, draw_ambient_indicator,
)
from display.components.shutdown_overlay import draw_shutdown_overlay
from display.components.qr_overlay import draw_setup_screen
from display.components.wifi_setup import draw_wifi_setup
from display.components.onboarding import needs_onboarding, draw_configure_screen
from display.config_server import PREFERRED_PORT
from display.idle import IdlePersonality, IdlePrompt
from display.emoji_reactions import draw_emoji_reaction

log = logging.getLogger("voxel.display.renderer")


def _build_corner_mask() -> Image.Image:
    """Build a mask image with black rounded corners matching the LCD bevel.

    The Whisplay 1.69" LCD has ~40px radius rounded corners. We draw
    black corner wedges so the local preview matches what's visible
    on the physical screen.
    """
    mask = Image.new("L", (SCREEN_W, SCREEN_H), 0)
    draw = ImageDraw.Draw(mask)
    # White = visible, black = masked (corners)
    draw.rounded_rectangle(
        [0, 0, SCREEN_W - 1, SCREEN_H - 1],
        radius=CORNER_RADIUS,
        fill=255,
    )
    return mask


class PILRenderer:
    """Renders the full 240x280 display frame using PIL.

    View modes:
      - "face": Main view — cube face + status bar + temporary transcript overlay
      - "chat_drawer": Face dimmed, chat drawer peeks up from bottom
      - "chat_full": Full-screen chat history (replaces face)
      - Menu overlay drawn on top of any view when menu.open is True
    """

    def __init__(self) -> None:
        self._expressions = load_expressions()
        self._styles = load_styles()
        self._config = load_settings()
        log.info("Loaded %d expressions, %d styles",
                 len(self._expressions), len(self._styles))

        # Animation state (tunable via config/default.yaml character section)
        char_cfg = self._config.get("character", {})
        default_expr = self._expressions.get("neutral", Expression(name="neutral"))
        self._transition = MoodTransition(default_expr)
        self._blink = BlinkState(
            next_blink=time.time() + 2.0,
            interval_scale=char_cfg.get("idle_blink_interval", 3.5) / 3.5,
        )
        self._gaze = GazeDrift(
            next_change=time.time() + 1.0,
            speed=char_cfg.get("gaze_drift_speed", 0.5),
        )
        self._breathing = BreathingState(
            speed=char_cfg.get("breathing_speed", 0.3),
        )
        self._gaze_range: float = char_cfg.get("gaze_range", 0.5)
        self._mouth_sensitivity: float = char_cfg.get("mouth_sensitivity", 0.6)
        self._current_mood = "neutral"
        self._current_character = ""  # track for change logging
        self._mood_override_until: float = 0.0  # external mood lock (dev panel, ws)

        # View transition and overlay fade state
        display_cfg = self._config.get("display", {})
        self._status_animations = display_cfg.get("status_animations", True)
        self._ambient_indicator = display_cfg.get("ambient_indicator", True)
        transitions_enabled = display_cfg.get("transitions", True)
        transition_speed = display_cfg.get("transition_speed", 0.3)
        self._view_transition = ViewTransition(
            duration=transition_speed, enabled=transitions_enabled,
        )
        self._menu_fade = OverlayFade(
            duration=0.15, enabled=transitions_enabled,
        )
        self._pairing_fade = OverlayFade(
            duration=0.15, enabled=transitions_enabled,
        )
        self._shutdown_fade = OverlayFade(
            duration=0.15, enabled=transitions_enabled,
        )
        self._sleep_dim: float = 0.0  # 0=fully bright, 1=fully dimmed
        self._drawer_slide = DrawerSlide(
            rest_y=140, hidden_y=280, duration=0.25,
        )

        # Menu state
        self.menu = MenuState()

        # Config server URL (set by display.service after starting the server)
        self.config_url: str = ""

        # Idle personality system
        self._idle = IdlePersonality(enabled=char_cfg.get("idle_personality", True))
        self._idle_prompt = IdlePrompt(
            enabled=char_cfg.get("idle_prompt", True),
            interval=char_cfg.get("idle_prompt_interval", 90),
        )

        # Demo mode controller
        self._demo = DemoController(
            cycle_speed=char_cfg.get("demo_cycle_speed", 5),
            include_characters=char_cfg.get("demo_include_characters", True),
            include_styles=char_cfg.get("demo_include_styles", True),
        )

        # Wake-up micro-expression tracking
        self._was_sleeping = False
        self._wake_time = 0.0
        self._wake_phase = 0  # 0=not waking, 1=sleepy, 2=surprised, 3=done

        # Idle attention response tracking
        self._attention_time = 0.0
        self._attention_active = False
        self._was_button_pressed = False

        # Corner mask — black corners matching the LCD bevel
        self._corner_mask = _build_corner_mask()

    def render(self, state: DisplayState) -> Image.Image:
        """Render a complete frame and return a 240x280 RGB PIL Image."""
        now = state.time
        dt = state.dt

        # Update transcript auto-hide
        state.update_transcript_visibility(now)

        # Demo mode — auto-cycle moods/characters/styles
        self._demo.update(state, now)

        # ── Mood resolution ───────────────────────────────────────
        # External sources (dev panel, WebSocket) write state.mood.
        # Internal sources (idle personality, wake-up) also propose moods.
        # We resolve priority here and track _current_mood for transitions.

        # Detect external mood change — lock out idle's non-urgent
        # returns for 5s so the manual mood is visible.
        if state.mood != self._current_mood:
            self._mood_override_until = now + 5.0

        # Wake-up micro-expression: sleepy → surprised → neutral
        if state.state != "SLEEPING" and self._was_sleeping:
            self._wake_time = now
            self._wake_phase = 1
            self._was_sleeping = False
        elif state.state == "SLEEPING":
            self._was_sleeping = True

        if self._wake_phase > 0:
            elapsed = now - self._wake_time
            if elapsed < 0.4:
                state.mood = "sleepy"
            elif elapsed < 0.8:
                state.mood = "surprised"
            else:
                self._wake_phase = 0

        # Attention response: brief "curious" on button press from idle
        if state.button_pressed and not self._was_button_pressed and state.state == "IDLE":
            self._attention_time = now
            self._attention_active = True
        self._was_button_pressed = state.button_pressed

        if self._attention_active:
            elapsed = now - self._attention_time
            if elapsed < 0.3:
                state.mood = "curious"
            else:
                self._attention_active = False

        # Idle personality — always runs so battery/connection are tracked,
        # but only overrides mood if:
        #   a) it's an urgent reaction (battery, connection change), OR
        #   b) the manual lockout has expired (5s after last external change)
        # Skip during demo mode — demo controller owns mood cycling.
        if (state.state == "IDLE" and not self._attention_active
                and not state.demo_mode):
            idle_mood, urgent = self._idle.update_ex(state, now)
            if idle_mood:
                if urgent:
                    # Device state change — always apply
                    state.mood = idle_mood
                elif now >= self._mood_override_until and idle_mood != state.mood:
                    # Non-urgent (neutral return, sleepy) — respect lockout
                    state.mood = idle_mood

        # Idle prompt indicator ("?" hint)
        self._idle_prompt.update(state, now)

        # Update mood transition if mood changed
        if state.mood != self._current_mood:
            target = self._expressions.get(state.mood)
            if target:
                log.info("Mood: %s → %s", self._current_mood, state.mood)
                self._transition.set_target(target)
                self._current_mood = state.mood
            else:
                log.warning("Unknown mood '%s', staying on '%s'",
                            state.mood, self._current_mood)

        # Update animation state
        expr = self._transition.update()
        # Suppress blinks when eyes are already nearly closed (sleepy, sleeping)
        if expr.eyes.openness > 0.35:
            self._blink.update(now, expr.eyes.blink_rate)
        else:
            self._blink.blink_phase = -1.0  # force open (no blink animation)
        self._gaze.update(now, dt)

        # Apply breathing scale to expression body
        breath_scale = self._breathing.update(now, dt)
        if abs(breath_scale - 1.0) > 0.001:
            expr = Expression(
                name=expr.name,
                eyes=expr.eyes,
                mouth=expr.mouth,
                body=BodyConfig(
                    bounce_speed=expr.body.bounce_speed,
                    bounce_amount=expr.body.bounce_amount,
                    tilt=expr.body.tilt,
                    scale=expr.body.scale * breath_scale,
                ),
                left_eye=expr.left_eye,
                right_eye=expr.right_eye,
                eye_color_override=expr.eye_color_override,
            )

        # Get style
        style = self._styles.get(state.style)
        if not style:
            style = self._styles.get("kawaii") or next(iter(self._styles.values()))

        # Create image
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
        draw = ImageDraw.Draw(img)

        # WiFi AP onboarding mode — full-screen takeover
        if state.wifi_ap_mode:
            portal = self.config_url or f"http://10.42.0.1:{PREFERRED_PORT}"
            draw_wifi_setup(draw, img, state.wifi_ap_ssid, state.wifi_ap_password, portal)
            draw_button_indicator(draw, state)
            img = Image.composite(img, Image.new("RGB", img.size, (0, 0, 0)), self._corner_mask)
            return img

        # Onboarding: show config screen if gateway not yet configured
        if needs_onboarding() and self.config_url and not state.connected:
            try:
                from display.config_server import get_access_pin
                pin = get_access_pin()
            except Exception:
                pin = ""
            draw_configure_screen(draw, img, self.config_url, access_pin=pin)
            draw_button_indicator(draw, state)
            img = Image.composite(img, Image.new("RGB", img.size, (0, 0, 0)), self._corner_mask)
            return img

        # Status bar is always drawn first
        draw_status_bar(draw, state, config=self._config)

        # ── Render the current view content (without overlays) ──
        self._draw_view_content(draw, img, expr, style, state, now)

        # Note: we intentionally do NOT restore state.mood here.
        # The renderer resolves the effective mood (idle personality,
        # battery, etc.) and that result should persist in state.mood
        # so the status bar and other components reflect reality.
        # The server will overwrite via WebSocket on the next push.

        # View dots removed — transitions are obvious on a 240px single-button device

        # Speaking waveform pill / listening pulse ring (face views only)
        if not self.menu.open and state.view not in ("chat_full",):
            if state.state == "SPEAKING" or state.speaking:
                draw_speaking_pill(draw, state, now)
            elif state.state == "LISTENING":
                draw_listening_indicator(draw, state, now)

        # Ambient mic activity indicator (subtle dot, always visible if active)
        if not self.menu.open and self._ambient_indicator:
            draw_ambient_indicator(draw, state, now)

        # ── View transition (cross-fade between views) ──
        self._view_transition.set_view(state.view, now)
        if self._view_transition.is_transitioning():
            progress = self._view_transition.update(now)
            img = self._view_transition.blend(img, progress)
            # Re-bind draw to the blended image
            draw = ImageDraw.Draw(img)
        # Capture this frame for future transitions
        self._view_transition.capture(img)

        # ── Menu overlay with fade-in ──
        menu_alpha = self._menu_fade.update(self.menu.open, now)
        if self.menu.open and menu_alpha > 0:
            # Render menu onto a separate image
            menu_img = img.copy()
            menu_draw = ImageDraw.Draw(menu_img)
            if self.menu.sub_screen == "setup" and self.config_url:
                try:
                    from display.config_server import get_access_pin
                    pin = get_access_pin()
                except Exception:
                    pin = ""
                draw_setup_screen(menu_draw, menu_img, self.config_url, access_pin=pin)
            else:
                draw_menu(menu_draw, state, self.menu)
            # Blend menu over the base frame
            if menu_alpha < 1.0:
                img = Image.blend(img, menu_img, alpha=menu_alpha)
            else:
                img = menu_img
            draw = ImageDraw.Draw(img)

        # ── Pairing overlays with fade-in ──
        has_pairing = state.pairing_request or (state.pairing_mode and self.config_url)
        pairing_alpha = self._pairing_fade.update(has_pairing, now)
        if has_pairing and pairing_alpha > 0:
            pairing_img = img.copy()
            pairing_draw = ImageDraw.Draw(pairing_img)
            if state.pairing_request:
                self._draw_pairing_request(pairing_draw, state)
            elif state.pairing_mode and self.config_url:
                self._draw_pairing_overlay(pairing_draw, pairing_img, state)
            if pairing_alpha < 1.0:
                img = Image.blend(img, pairing_img, alpha=pairing_alpha)
            else:
                img = pairing_img
            draw = ImageDraw.Draw(img)

        # Button hold indicator (overlays on any view)
        draw_button_indicator(draw, state)

        # ── Shutdown confirmation overlay with fade-in ──
        shutdown_alpha = self._shutdown_fade.update(state.shutdown_confirm, now)
        if state.shutdown_confirm and shutdown_alpha > 0:
            shutdown_img = img.copy()
            shutdown_draw = ImageDraw.Draw(shutdown_img)
            draw_shutdown_overlay(shutdown_draw, state)
            if shutdown_alpha < 1.0:
                img = Image.blend(img, shutdown_img, alpha=shutdown_alpha)
            else:
                img = shutdown_img

        # ── Sleep fade — smoothly dims screen on sleep, brightens on wake ──
        is_sleeping = state.state == "SLEEPING"
        target_dim = 0.85 if is_sleeping else 0.0
        # Smooth lerp: ~0.8s to dim, ~0.4s to wake (faster wake feels snappier)
        speed = 1.8 if is_sleeping else 3.5
        self._sleep_dim += (target_dim - self._sleep_dim) * min(speed * dt, 1.0)
        if self._sleep_dim > 0.01:
            black = Image.new("RGB", img.size, (0, 0, 0))
            img = Image.blend(img, black, alpha=self._sleep_dim)

        # Apply corner mask — black out the rounded corners
        img = Image.composite(img, Image.new("RGB", img.size, (0, 0, 0)), self._corner_mask)

        return img

    def _draw_view_content(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                           expr, style, state: DisplayState, now: float) -> None:
        """Draw the active view content (face, chat_drawer, or chat_full).

        This is separated from render() so the view transition system can
        capture the output for cross-fade blending.
        """
        view = state.view

        # Update drawer slide animation
        drawer_open = view == "chat_drawer"
        self._drawer_slide.set_open(drawer_open, now)
        drawer_y = self._drawer_slide.update(now)

        # Parse accent color and apply to character
        _accent = self._parse_accent(state.accent_color)

        # Log character switches
        if state.character != self._current_character:
            log.info("Character: %s → %s", self._current_character or "(init)",
                     state.character)
            self._current_character = state.character

        if view == "chat_full":
            draw_chat_full(draw, state)
        elif view == "chat_drawer" or self._drawer_slide.is_animating:
            character = get_character(state.character)
            character._accent = _accent
            character.draw(
                draw, img, expr, style,
                blink_factor=self._blink.get_openness_factor(),
                gaze_x=self._gaze.current_x * self._gaze_range,
                gaze_y=self._gaze.current_y * self._gaze_range,
                amplitude=state.amplitude * self._mouth_sensitivity,
                now=now,
                compact=drawer_open,
            )
            draw_chat_drawer(draw, state, slide_y=drawer_y)
        else:
            character = get_character(state.character)
            character._accent = _accent
            character.draw(
                draw, img, expr, style,
                blink_factor=self._blink.get_openness_factor(),
                gaze_x=self._gaze.current_x * self._gaze_range,
                gaze_y=self._gaze.current_y * self._gaze_range,
                amplitude=state.amplitude * self._mouth_sensitivity,
                now=now,
            )
            draw_transcript_overlay(draw, state)
            draw_chat_peek(draw, state, now)

            # Overlay decorations — single RGBA pass for both mood + status
            from display.decorations import _MOOD_RENDERERS
            has_mood_deco = state.mood in _MOOD_RENDERERS
            has_status_deco = self._status_animations and (
                state.connection_event or state.battery_warning
            )

            if has_mood_deco or has_status_deco:
                face_cx = character._last_face_cx
                face_cy = character._last_face_cy
                left_eye = character._last_left_eye
                right_eye = character._last_right_eye
                img_rgba = img.convert("RGBA")

                if has_mood_deco:
                    draw_mood_decorations(
                        draw, img_rgba, state.mood, now,
                        face_cx, face_cy, left_eye, right_eye,
                    )
                if has_status_deco:
                    draw_status_decorations(
                        draw, img_rgba, now,
                        state.connection_event, state.connection_event_time,
                        state.battery_warning,
                    )

                img.paste(img_rgba.convert("RGB"))
                draw = ImageDraw.Draw(img)

            # Emoji reactions (agent-driven, auto-dismissing)
            if state.reaction_emoji:
                draw_emoji_reaction(draw, img, state, now)

            # Idle quirks and prompt (face view only, during IDLE)
            if state.state == "IDLE":
                character.idle_quirk(draw, img, now)
                # Only show idle prompt "?" during neutral — avoids
                # confusing overlay when a specific mood is active.
                if state.idle_prompt_visible and state.mood == "neutral":
                    self._draw_idle_prompt(draw, state)

    @staticmethod
    def _parse_accent(hex_str: str) -> tuple[int, int, int]:
        """Parse a hex color string into an RGB tuple."""
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        return (0, 212, 210)  # fallback cyan

    def _draw_idle_prompt(self, draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
        """Draw the '?' idle hint indicator in the top-right of the face area.

        Uses the alpha value from IdlePrompt for smooth fade in/out.
        Positioned to avoid overlap with the status bar and transcript overlay.
        """
        alpha = state._idle_prompt_alpha
        if alpha <= 0.01:
            return

        font = get_font(18)
        text = "?"

        # Position: top-right of face, similar zone to ZZZs
        x = SCREEN_W // 2 + 40
        y = STATUS_H + 10

        # Fade the color from transparent to a soft cyan
        r = int(0 * alpha + BG[0] * (1 - alpha))
        g = int(180 * alpha + BG[1] * (1 - alpha))
        b = int(178 * alpha + BG[2] * (1 - alpha))
        color = (r, g, b)

        draw.text((x, y), text, fill=color, font=font)

    def _draw_pairing_request(self, draw: ImageDraw.ImageDraw, state: DisplayState) -> None:
        """Draw pairing approval notification — short press = approve, long = deny."""
        font_lg = get_font(16)
        font_md = get_font(14)
        font_sm = get_font(11)

        draw.rectangle([0, STATUS_H, SCREEN_W - 1, SCREEN_H - 1], fill=(14, 14, 22))

        y = STATUS_H + 16
        title = "Pair Request"
        tw = text_width(font_lg, title)
        draw.text(((SCREEN_W - tw) // 2, y), title, fill=(0, 212, 210), font=font_lg)

        y += 30
        requester = state.pairing_request_from or "Unknown device"
        draw.text((20, y), "From:", fill=(100, 100, 120), font=font_sm)
        y += 16
        tw = text_width(font_md, requester)
        draw.text((max(20, (SCREEN_W - tw) // 2), y), requester, fill=(200, 200, 220), font=font_md)

        y += 40
        # Approve
        draw.rounded_rectangle([20, y, 220, y + 34], radius=8, fill=(0, 40, 38))
        draw.rounded_rectangle([20, y, 220, y + 34], radius=8, outline=(0, 212, 210))
        approve_text = "Tap = Approve"
        tw = text_width(font_md, approve_text)
        draw.text(((SCREEN_W - tw) // 2, y + 8), approve_text, fill=(0, 212, 210), font=font_md)

        y += 46
        # Deny
        draw.rounded_rectangle([20, y, 220, y + 34], radius=8, fill=(40, 14, 14))
        draw.rounded_rectangle([20, y, 220, y + 34], radius=8, outline=(255, 60, 60))
        deny_text = "Hold = Deny"
        tw = text_width(font_md, deny_text)
        draw.text(((SCREEN_W - tw) // 2, y + 8), deny_text, fill=(255, 60, 60), font=font_md)

    def _draw_pairing_overlay(self, draw: ImageDraw.ImageDraw, img: Image.Image,
                              state: DisplayState) -> None:
        """Draw a pairing mode overlay — shows PIN, URL, QR, auto-dismisses."""
        try:
            from display.config_server import get_access_pin
            pin = get_access_pin()
        except Exception:
            return

        font_lg = get_font(20)
        font_md = get_font(14)
        font_sm = get_font(11)

        # Semi-dark overlay
        draw.rectangle([0, STATUS_H, SCREEN_W - 1, SCREEN_H - 1], fill=(10, 10, 18))

        y = STATUS_H + 10
        # Title
        title = "Pairing Mode"
        tw = text_width(font_md, title)
        draw.text(((SCREEN_W - tw) // 2, y), title, fill=(0, 212, 210), font=font_md)

        # QR code
        y += 24
        try:
            from display.config_server import get_direct_url
            from display.components.qr_overlay import _generate_qr
            qr_url = get_direct_url(self.config_url)
            qr_img = _generate_qr(qr_url)
            qr_size = 90
            qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
            img.paste(qr_img, ((SCREEN_W - qr_size) // 2, y))
            y += qr_size + 6
        except Exception:
            y += 10

        # URL
        url_short = self.config_url.replace("http://", "")
        tw = text_width(font_md, url_short)
        draw.text((max(4, (SCREEN_W - tw) // 2), y), url_short, fill=(0, 212, 210), font=font_md)

        # PIN — large
        y += 24
        pin_text = f"PIN: {pin}"
        tw = text_width(font_lg, pin_text)
        draw.text(((SCREEN_W - tw) // 2, y), pin_text, fill=(64, 255, 248), font=font_lg)

        # Hint
        y += 30
        hint = "Press button to dismiss"
        tw = text_width(font_sm, hint)
        draw.text(((SCREEN_W - tw) // 2, y), hint, fill=(80, 80, 100), font=font_sm)
