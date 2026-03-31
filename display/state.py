"""Display state — updated by the WebSocket client, read by the renderer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TranscriptEntry:
    role: str = ""        # "user", "assistant", or "tool"
    text: str = ""
    status: str = "done"  # "partial", "done", "thinking", "tool_running", "tool_done"
    tool_name: str = ""   # for role="tool": name of the tool being called


@dataclass
class DisplayState:
    """All state the renderer needs to draw a frame."""

    # From server "state" messages
    mood: str = "neutral"
    style: str = "kawaii"
    state: str = "IDLE"
    speaking: bool = False
    amplitude: float = 0.0
    battery: int = 100
    agent: str = "daemon"
    brightness: int = 80
    volume: int = 80
    connected: bool = False      # WebSocket to server.py
    wifi_connected: bool = True  # WiFi network status
    wifi_ap_mode: bool = False   # True when in AP onboarding mode
    wifi_ap_ssid: str = ""
    wifi_ap_password: str = ""

    # Status decoration events — set by idle personality, read by renderer
    connection_event: str | None = None        # "connected" or "disconnected"
    connection_event_time: float = 0.0         # when the event fired (time.time())
    battery_warning: str | None = None         # "low_battery" or "critical_battery"

    # Ambient audio activity — set by render loop from AmbientMonitor
    ambient_active: bool = False               # mic hearing sound above threshold
    ambient_amplitude: float = 0.0             # smoothed ambient RMS level (0-1)

    # Emoji reactions — set by agent response parser or dev panel
    reaction_emoji: str = ""                   # emoji character to display (e.g. "😊")
    reaction_time: float = 0.0                 # when reaction was triggered
    reaction_duration: float = 3.0             # how long to show (seconds)

    # Transcript buffer (most recent entries)
    transcripts: list[TranscriptEntry] = field(default_factory=list)
    max_transcripts: int = 20

    # View mode: "face" (default) or "chat" (full-screen chat history)
    view: str = "face"

    # Transcript overlay — shows temporarily during conversation, then auto-hides
    transcript_visible: bool = False
    transcript_user: str = ""
    transcript_voxel: str = ""
    _transcript_hide_at: float = 0.0  # auto-hide timestamp

    # Button hold progress (0.0 = not pressed, 0.0-1.0 = filling over 10s full scale)
    # Zone 1: 0.0-0.1 = menu (1s), Zone 2: 0.1-0.5 = sleep (5s), Zone 3: 0.5-1.0 = shutdown (10s)
    button_hold: float = 0.0
    button_pressed: bool = False
    # Brief flash after release/action: "short_press", "start_recording", "long_press", "sleep", "shutdown" for ~0.5s, then ""
    button_flash: str = ""
    _button_flash_until: float = 0.0

    # Shutdown confirmation overlay
    shutdown_confirm: bool = False
    _shutdown_at: float = 0.0  # timestamp when shutdown executes (0 = not pending)
    _watchdog_error_until: float = 0.0  # watchdog error recovery timestamp

    # Character selection (e.g. "cube", "bmo", "voxel")
    character: str = "voxel"
    accent_color: str = "#00d4d2"  # primary accent (eyes, glow, edges)

    # Pairing mode — shows PIN/QR overlay, dismissed by button press
    pairing_mode: bool = False
    # Pairing request — device asks user to approve/deny before showing PIN
    pairing_request: bool = False       # True when a pair request is pending
    pairing_request_from: str = ""      # IP/name of requester
    pairing_approved: bool = False      # Set by button press (short=approve, long=deny)
    pairing_denied: bool = False

    # Update status
    update_available: bool = False
    update_behind: int = 0
    update_checking: bool = False

    # Dev mode (set from config dev.enabled)
    dev_mode: bool = False

    # Demo mode (auto-cycle showcase)
    demo_mode: bool = False
    demo_mood_index: int = 0
    demo_char_index: int = 0
    demo_style_index: int = 0
    _demo_next_cycle: float = 0.0

    # Idle prompt indicator ("?" hint after prolonged idle)
    idle_prompt_visible: bool = False
    _idle_prompt_alpha: float = 0.0  # 0.0-1.0 for fade animation

    # Chat peek bubble overlay on face view
    _peek_until: float = 0.0      # timestamp when peek bubble should dismiss
    _peek_triggered: bool = False  # prevent re-triggering for same message

    # Gateway greeting overlay (fade-in, hold, fade-out text below eyes)
    greeting_text: str = ""
    greeting_time: float = 0.0  # timestamp when greeting was set

    # Frame timing (set each frame by the render loop)
    time: float = 0.0
    dt: float = 0.0

    def trigger_chat_peek(self, now: float, duration: float = 4.0) -> None:
        """Trigger a peek bubble overlay on the face view."""
        if self.view == "face":  # only peek on face view
            self._peek_until = now + duration

    def push_transcript(self, role: str, text: str, status: str = "done",
                        tool_name: str = "") -> None:
        """Add or update a transcript entry."""
        # Strip mood tags like [neutral], [happy] etc. from display text
        if role == "assistant" and text:
            import re
            text = re.sub(r'^\s*\[\w+\]\s*', '', text)

        # Update last entry if same role and partial
        if self.transcripts and self.transcripts[-1].role == role and self.transcripts[-1].status == "partial":
            self.transcripts[-1].text = text
            self.transcripts[-1].status = status
            if tool_name:
                self.transcripts[-1].tool_name = tool_name
        else:
            self.transcripts.append(TranscriptEntry(role=role, text=text, status=status,
                                                    tool_name=tool_name))
        # Cap size
        if len(self.transcripts) > self.max_transcripts:
            self.transcripts = self.transcripts[-self.max_transcripts:]

        # Update transcript overlay (temporary display during conversation)
        if role == "user":
            self.transcript_user = text
            self.transcript_voxel = ""
        else:
            self.transcript_voxel = text
        # Don't auto-show the transcript overlay on face view —
        # the chat peek handles new message notifications.
        # transcript_visible is toggled manually ('t' key / dev panel).
        self._transcript_hide_at = 0.0

        # Trigger chat peek only for completed messages (not partials/placeholders)
        if status == "done" and role in ("user", "assistant") and text and text != "…":
            self.trigger_chat_peek(time.time())

    def update_transcript_visibility(self, now: float) -> None:
        """Auto-hide transcript overlay after returning to IDLE."""
        if not self.transcript_visible:
            return
        if self.state == "IDLE":
            if self._transcript_hide_at == 0.0:
                self._transcript_hide_at = now + 3.0  # hide 3s after idle
            elif now >= self._transcript_hide_at:
                self.transcript_visible = False
                self._transcript_hide_at = 0.0
        else:
            # Still in conversation — reset hide timer
            self._transcript_hide_at = 0.0
