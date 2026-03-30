"""Dev Panel — secondary control window for desktop preview.

Opens alongside the main 240x280 preview window when running `uv run dev`.
Supports two modes:

  **Docked** (default): Panel content sits inside the preview window's right
  side. Single combined window. Toggle with backtick (`) key.

  **Undocked**: Panel floats as a separate window. Same backtick toggle.

Disable entirely with: uv run dev --no-panel
"""

from __future__ import annotations

import logging
import math
import threading
import time
import tkinter as tk
from typing import Callable

from display.state import DisplayState

log = logging.getLogger("voxel.display.dev_panel")

# ── Data ─────────────────────────────────────────────────────────────────────

ALL_MOODS = [
    "neutral", "happy", "curious", "thinking", "listening",
    "excited", "sleepy", "confused", "surprised", "focused",
    "frustrated", "sad", "working", "error",
    "low_battery", "critical_battery",
]

ALL_STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR", "SLEEPING"]

ALL_CHARACTERS = ["voxel", "cube", "bmo", "bmo-full"]

ALL_STYLES = ["kawaii", "retro", "minimal"]

ALL_AGENTS = [
    ("daemon", "Daemon"), ("soren", "Soren"), ("ash", "Ash"),
    ("mira", "Mira"), ("jace", "Jace"), ("pip", "Pip"),
]

ACCENT_PRESETS = [
    ("#00d4d2", "Cyan"),   ("#ff6b8a", "Pink"),  ("#40ff80", "Green"),
    ("#ffa040", "Orange"), ("#a080ff", "Purple"), ("#ff4040", "Red"),
    ("#ffdd40", "Yellow"), ("#4090ff", "Blue"),
]

# ── Theme ────────────────────────────────────────────────────────────────────

BG        = "#1e1e30"
BG_CARD   = "#262640"
BG_BTN    = "#30304e"
BG_ACTIVE = "#00d4d2"
FG        = "#d0d0e0"
FG_DIM    = "#8888a0"
FG_ACCENT = "#00d4d2"
FG_HEAD   = "#f0f0ff"
BORDER    = "#38385a"

FONT      = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_HEAD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 8)
FONT_BTN  = ("Segoe UI", 8)

PANEL_W = 520


# ── Mic capture (background thread) ─────────────────────────────────────────

class _MicCapture:
    """Captures RMS amplitude from the default mic in a background thread.

    Similar to display/ambient.py but designed for dev panel use:
    returns a smoothed 0-1 amplitude that can drive the face mouth.
    """

    CHUNK = 512
    RATE = 16000

    def __init__(self, sensitivity: float = 0.5):
        self.sensitivity = sensitivity
        self.amplitude: float = 0.0
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Start mic capture. Returns True if mic was opened."""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                         name="dev-mic")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.amplitude = 0.0

    def _loop(self) -> None:
        stream = None
        backend_name = None
        try:
            stream, backend_name = self._open()
            if stream is None:
                log.warning("Dev mic: no audio input available")
                self._running = False
                return
            log.info("Dev mic: started (%s)", backend_name)

            smooth = 0.0
            while self._running:
                try:
                    rms = self._read_rms(stream, backend_name)
                    scale = 1.5 + self.sensitivity * 6.5
                    boosted = min(1.0, (min(1.0, rms * scale)) ** 0.7)
                    smooth += (boosted - smooth) * 0.14
                    if smooth < 0.005:
                        smooth = 0.0
                    self.amplitude = smooth
                except Exception:
                    time.sleep(0.05)
        except Exception as e:
            log.warning("Dev mic error: %s", e)
        finally:
            self._close(stream, backend_name)
            self._running = False
            self.amplitude = 0.0
            log.info("Dev mic: stopped")

    def _open(self):
        # Try PyAudio
        try:
            import pyaudio  # type: ignore
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.RATE,
                input=True, frames_per_buffer=self.CHUNK,
            )
            stream.start_stream()
            stream._pa_instance = pa  # type: ignore[attr-defined]
            return stream, "pyaudio"
        except Exception:
            pass
        # Try sounddevice
        try:
            import sounddevice as sd  # type: ignore
            stream = sd.InputStream(
                samplerate=self.RATE, channels=1, dtype="int16",
                blocksize=self.CHUNK,
            )
            stream.start()
            return stream, "sounddevice"
        except Exception:
            pass
        return None, None

    def _read_rms(self, stream, backend: str) -> float:
        import numpy as np
        if backend == "pyaudio":
            data = stream.read(self.CHUNK, exception_on_overflow=False)
            arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        elif backend == "sounddevice":
            data, _ = stream.read(self.CHUNK)
            arr = data.flatten().astype(np.float32)
        else:
            return 0.0
        if len(arr) == 0:
            return 0.0
        rms = math.sqrt(float(np.mean(arr ** 2)))
        return min(rms / 32768.0 * 4.0, 1.0)

    def _close(self, stream, backend):
        if stream is None:
            return
        try:
            if backend == "pyaudio":
                stream.stop_stream()
                stream.close()
                if hasattr(stream, "_pa_instance"):
                    stream._pa_instance.terminate()
            elif backend == "sounddevice":
                stream.stop()
                stream.close()
        except Exception:
            pass


# ── Chat client (runs gateway call in background thread) ─────────────────────

class _ChatClient:
    """Lightweight gateway client for standalone dev testing.

    Sends text to OpenClaw and returns the response. Runs the blocking
    HTTP request in a background thread so tkinter doesn't freeze.
    """

    def __init__(self):
        self._client = None
        self._busy = False

    def _ensure_client(self):
        if self._client is not None:
            return True
        try:
            from config.settings import load_settings
            from core.gateway import OpenClawClient
            cfg = load_settings()
            gw = cfg.get("gateway", {})
            url = gw.get("url", "")
            token = gw.get("token", "")
            if not url or not token:
                return False
            agent = gw.get("default_agent", "daemon")
            char_cfg = cfg.get("character", {})
            ctx = char_cfg.get("system_context", "") if char_cfg.get("system_context_enabled", True) else ""
            self._client = OpenClawClient(url, token, agent, ctx)
            return True
        except Exception as e:
            log.warning("Chat client init failed: %s", e)
            return False

    @property
    def available(self) -> bool:
        return self._ensure_client()

    @property
    def busy(self) -> bool:
        return self._busy

    def send(self, text: str, state: DisplayState,
             on_done: Callable[[str | None], None]) -> None:
        """Send text to gateway in a background thread."""
        if self._busy or not self._ensure_client():
            on_done(None)
            return
        self._busy = True
        state.state = "THINKING"
        state.mood = "thinking"

        def _work():
            try:
                # Sync agent
                self._client.set_agent(state.agent)
                return self._client.send_message(text)
            except Exception as e:
                log.error("Chat error: %s", e)
                return None

        def _thread():
            result = _work()
            self._busy = False
            on_done(result)

        threading.Thread(target=_thread, daemon=True, name="dev-chat").start()


class DevPanel:
    """Dev control panel — dockable into the preview window or floating."""

    def __init__(self, root: tk.Tk, state: DisplayState, backend=None,
                 on_mood: Callable[[str], None] | None = None,
                 on_state: Callable[[str], None] | None = None):
        self._root = root
        self._state = state
        self._backend = backend
        self._on_mood = on_mood
        self._on_state = on_state
        self._closed = False

        # Persistent tk variables (survive widget rebuilds)
        self._char_var = tk.StringVar(value=state.character)
        self._style_var = tk.StringVar(value=state.style)
        self._agent_var = tk.StringVar(value=state.agent)
        self._demo_var = tk.BooleanVar(value=state.demo_mode)
        self._connected_var = tk.BooleanVar(value=state.connected)
        self._amp_var = tk.DoubleVar(value=0.0)
        self._bat_var = tk.IntVar(value=state.battery)
        self._bright_var = tk.IntVar(value=state.brightness)
        self._vol_var = tk.IntVar(value=state.volume)
        self._status_var = tk.StringVar(value="")

        # Mic capture
        self._mic = _MicCapture(sensitivity=0.5)
        self._mic_var = tk.BooleanVar(value=False)
        self._mic_sens_var = tk.DoubleVar(value=50.0)
        self._mic_level_var = tk.StringVar(value="--")

        # Chat client (standalone gateway access)
        self._chat = _ChatClient()

        # Text input for chat
        self._text_var = tk.StringVar(value="")

        # Widget refs (rebuilt on dock/undock)
        self._mood_buttons: dict[str, tk.Button] = {}
        self._state_buttons: dict[str, tk.Button] = {}
        self._mic_bar: tk.Canvas | None = None
        self._content_frame: tk.Frame | None = None
        self._toplevel: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None

        # Backtick toggle
        root.bind("`", lambda _: self.toggle_dock())

        # Start docked if backend supports it
        if backend and hasattr(backend, "dock_container") and backend.dock_container:
            self._build_docked()
        else:
            self._build_floating()

        log.info("Dev panel opened (%s)", "docked" if self.is_docked else "floating")

    # ── Dock / Undock ─────────────────────────────────────────────────────

    @property
    def is_docked(self) -> bool:
        return self._toplevel is None and self._content_frame is not None

    def toggle_dock(self) -> None:
        if self._closed:
            return
        if self.is_docked:
            self._undock()
        else:
            self._dock()

    def _build_docked(self) -> None:
        container = self._backend.dock_container
        self._backend.dock(panel_width=PANEL_W)
        self._canvas, self._content_frame = self._make_scrollable(container)
        self._populate(self._content_frame)

    def _build_floating(self) -> None:
        self._toplevel = tk.Toplevel(self._root)
        self._toplevel.title("Voxel Dev Panel")
        self._toplevel.configure(bg=BG)
        self._toplevel.resizable(True, True)
        self._toplevel.minsize(PANEL_W, 400)
        self._toplevel.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.update_idletasks()
        rx = self._root.winfo_x() + self._root.winfo_width()
        ry = self._root.winfo_y()
        self._toplevel.geometry(f"{PANEL_W}x900+{rx + 8}+{ry}")
        self._canvas, self._content_frame = self._make_scrollable(self._toplevel)
        self._populate(self._content_frame)

    def _dock(self) -> None:
        if not self._backend or not hasattr(self._backend, "dock_container"):
            return
        self._destroy_content()
        if self._toplevel:
            self._toplevel.destroy()
            self._toplevel = None
        self._build_docked()
        log.info("Dev panel: docked")

    def _undock(self) -> None:
        self._destroy_content()
        if self._backend:
            self._backend.undock()
        self._build_floating()
        log.info("Dev panel: undocked")

    def _destroy_content(self) -> None:
        self._mood_buttons.clear()
        self._state_buttons.clear()
        self._mic_bar = None
        self._mic_btn = None
        if self._canvas:
            self._canvas.destroy()
            self._canvas = None
        self._content_frame = None

    # ── Scrollable container ──────────────────────────────────────────────

    def _make_scrollable(self, parent: tk.Widget) -> tuple[tk.Canvas, tk.Frame]:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                                 bg=BG, troughcolor=BG_CARD,
                                 highlightthickness=0, bd=0, width=8)
        frame = tk.Frame(canvas, bg=BG)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_canvas_cfg(e):
            canvas.itemconfigure(frame_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_cfg)
        frame.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))

        def _bind_wheel(_):
            canvas.bind_all("<MouseWheel>",
                            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        def _unbind_wheel(_):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return canvas, frame

    # ── Build UI ──────────────────────────────────────────────────────────

    def _populate(self, f: tk.Frame) -> None:
        PX = 8  # global horizontal padding

        # ── Header ────────────────────────────────────────────────────
        hdr = tk.Frame(f, bg=BG)
        hdr.pack(fill="x", padx=PX, pady=(6, 0))
        tk.Label(hdr, text="Dev Panel", bg=BG, fg=FG_HEAD,
                 font=FONT_HEAD, anchor="w").pack(side="left")
        dock_text = "Undock `" if self.is_docked else "Dock `"
        tk.Button(hdr, text=dock_text, bg=BG_BTN, fg=FG_DIM,
                  font=FONT_MONO, relief="flat", cursor="hand2", bd=0,
                  activebackground=BG_ACTIVE, activeforeground=BG,
                  command=self.toggle_dock, padx=6, pady=1).pack(side="right")

        # ── Status ────────────────────────────────────────────────────
        tk.Label(f, textvariable=self._status_var, bg=BG_CARD, fg=FG_DIM,
                 font=FONT_MONO, anchor="w", justify="left",
                 padx=6, pady=3).pack(fill="x", padx=PX, pady=(4, 4))

        # ── Mood ──────────────────────────────────────────────────────
        self._section(f, "Mood", PX)
        mf = tk.Frame(f, bg=BG)
        mf.pack(fill="x", padx=PX)
        mf.columnconfigure((0, 1, 2, 3), weight=1, uniform="m")
        for i, mood in enumerate(ALL_MOODS):
            btn = tk.Button(
                mf, text=mood, bg=BG_BTN, fg=FG, font=FONT_BTN,
                activebackground=BG_ACTIVE, activeforeground=BG,
                relief="flat", cursor="hand2", bd=0, pady=2,
                command=lambda m=mood: self._set_mood(m),
            )
            btn.grid(row=i // 4, column=i % 4, padx=1, pady=1, sticky="ew")
            self._mood_buttons[mood] = btn

        # ── Emoji Reactions ────────────────────────────────────────────
        self._section(f, "Emoji Reactions", PX)
        ef = tk.Frame(f, bg=BG)
        ef.pack(fill="x", padx=PX)
        ef.columnconfigure((0, 1, 2, 3, 4, 5), weight=1, uniform="e")
        _TEST_EMOJI = [
            ("\U0001f60a", "happy"), ("\U0001f622", "sad"),
            ("\U0001f914", "thinking"), ("\U0001f62e", "surprised"),
            ("\U0001f389", "excited"), ("\U0001f615", "confused"),
            ("\U0001f634", "sleepy"), ("\U0001f620", "angry"),
            ("\U0001f4a1", "idea"), ("\u2764", "love"),
            ("\u2728", "sparkle"), ("\U0001f44d", "ok"),
        ]
        for i, (emoji, label) in enumerate(_TEST_EMOJI):
            btn = tk.Button(
                ef, text=emoji, bg=BG_BTN, fg=FG, font=("Segoe UI Emoji", 12),
                activebackground=BG_ACTIVE, relief="flat", cursor="hand2",
                bd=0, pady=1,
                command=lambda e=emoji: self._trigger_emoji(e),
            )
            btn.grid(row=i // 6, column=i % 6, padx=1, pady=1, sticky="ew")

        self._sep(f, PX)

        # ── State ─────────────────────────────────────────────────────
        self._section(f, "State", PX)
        sf = tk.Frame(f, bg=BG)
        sf.pack(fill="x", padx=PX)
        sf.columnconfigure((0, 1, 2), weight=1, uniform="s")
        for i, st in enumerate(ALL_STATES):
            btn = tk.Button(
                sf, text=st, bg=BG_BTN, fg=FG, font=FONT_BTN,
                activebackground=BG_ACTIVE, activeforeground=BG,
                relief="flat", cursor="hand2", bd=0, pady=2,
                command=lambda s=st: self._set_state(s),
            )
            btn.grid(row=i // 3, column=i % 3, padx=1, pady=1, sticky="ew")
            self._state_buttons[st] = btn

        self._sep(f, PX)

        # ── Character + Style side by side ────────────────────────────
        cards = tk.Frame(f, bg=BG)
        cards.pack(fill="x", padx=PX)
        cards.columnconfigure((0, 1), weight=1)

        cc = tk.LabelFrame(cards, text="Character", bg=BG_CARD, fg=FG_ACCENT,
                           font=FONT_BOLD, labelanchor="nw", bd=0,
                           padx=6, pady=3,
                           highlightbackground=BORDER, highlightthickness=1)
        cc.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=1)
        for ch in ALL_CHARACTERS:
            tk.Radiobutton(
                cc, text=ch, value=ch, variable=self._char_var,
                command=self._on_character_change, bg=BG_CARD, fg=FG,
                selectcolor=BG, activebackground=BG_CARD,
                activeforeground=FG_ACCENT, font=FONT, anchor="w",
                highlightthickness=0, bd=0,
            ).pack(fill="x", anchor="w")

        sc = tk.LabelFrame(cards, text="Style", bg=BG_CARD, fg=FG_ACCENT,
                           font=FONT_BOLD, labelanchor="nw", bd=0,
                           padx=6, pady=3,
                           highlightbackground=BORDER, highlightthickness=1)
        sc.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=1)
        for st in ALL_STYLES:
            tk.Radiobutton(
                sc, text=st, value=st, variable=self._style_var,
                command=self._on_style_change, bg=BG_CARD, fg=FG,
                selectcolor=BG, activebackground=BG_CARD,
                activeforeground=FG_ACCENT, font=FONT, anchor="w",
                highlightthickness=0, bd=0,
            ).pack(fill="x", anchor="w")

        self._sep(f, PX)

        # ── Accent Color ──────────────────────────────────────────────
        self._section(f, "Accent", PX)
        af = tk.Frame(f, bg=BG)
        af.pack(fill="x", padx=PX)
        af.columnconfigure(tuple(range(len(ACCENT_PRESETS))), weight=1, uniform="a")
        for i, (hx, _) in enumerate(ACCENT_PRESETS):
            tk.Button(
                af, bg=hx, activebackground=hx, relief="flat",
                cursor="hand2", bd=0,
                command=lambda c=hx: self._set_accent(c),
            ).grid(row=0, column=i, padx=1, pady=1, sticky="ew", ipady=4)

        self._sep(f, PX)

        # ── Agent ─────────────────────────────────────────────────────
        self._section(f, "Agent", PX)
        agf = tk.Frame(f, bg=BG)
        agf.pack(fill="x", padx=PX)
        agf.columnconfigure(tuple(range(len(ALL_AGENTS))), weight=1, uniform="ag")
        for i, (aid, aname) in enumerate(ALL_AGENTS):
            tk.Radiobutton(
                agf, text=aname, value=aid, variable=self._agent_var,
                command=self._on_agent_change, bg=BG_BTN, fg=FG,
                selectcolor=BG_ACTIVE, activebackground=BG_BTN,
                activeforeground=FG_ACCENT, font=FONT_BTN,
                indicatoron=0, padx=2, pady=2, relief="flat",
                cursor="hand2", highlightthickness=0, bd=0,
            ).grid(row=0, column=i, padx=1, pady=1, sticky="ew")

        self._sep(f, PX)

        # ── Audio / Mouth ─────────────────────────────────────────────
        self._section(f, "Audio", PX)

        # Amplitude row with MIC toggle
        amp_row = tk.Frame(f, bg=BG)
        amp_row.pack(fill="x", padx=PX, pady=1)
        amp_row.columnconfigure(1, weight=1)
        tk.Label(amp_row, text="Mouth", bg=BG, fg=FG, font=FONT,
                 width=9, anchor="w").grid(row=0, column=0, sticky="w")

        # Amplitude bar (canvas — shows live level when mic is on)
        self._mic_bar = tk.Canvas(amp_row, bg=BG_CARD, height=16,
                                   highlightthickness=0, bd=0)
        self._mic_bar.grid(row=0, column=1, sticky="ew", padx=2)

        tk.Label(amp_row, textvariable=self._mic_level_var, bg=BG,
                 fg=FG_DIM, font=FONT_MONO, width=5,
                 anchor="e").grid(row=0, column=2, sticky="e")

        mic_btn = tk.Button(
            amp_row, text="MIC", bg=BG_BTN, fg=FG, font=FONT_BTN,
            activebackground=BG_ACTIVE, activeforeground=BG,
            relief="flat", cursor="hand2", bd=0, padx=6, pady=1,
            command=self._toggle_mic,
        )
        mic_btn.grid(row=0, column=3, padx=(4, 0))
        self._mic_btn = mic_btn

        # Manual amplitude slider (hidden when mic is active)
        self._slider(f, "Amplitude", self._amp_var, 0, 100,
                     self._on_amplitude_change, PX)

        # Mic sensitivity (only relevant when mic is on)
        self._slider(f, "Mic Sens", self._mic_sens_var, 0, 100,
                     self._on_mic_sens_change, PX)

        self._sep(f, PX)

        # ── Sliders ───────────────────────────────────────────────────
        self._section(f, "Controls", PX)
        self._slider(f, "Battery", self._bat_var, 0, 100,
                     self._on_battery_change, PX)
        self._slider(f, "Brightness", self._bright_var, 0, 100,
                     self._on_brightness_change, PX)
        self._slider(f, "Volume", self._vol_var, 0, 100,
                     self._on_volume_change, PX)

        self._sep(f, PX)

        # ── Toggles ──────────────────────────────────────────────────
        tf = tk.Frame(f, bg=BG)
        tf.pack(fill="x", padx=PX, pady=2)
        tk.Checkbutton(
            tf, text="Demo Mode", variable=self._demo_var,
            command=self._on_demo_toggle, bg=BG, fg=FG,
            selectcolor=BG_CARD, activebackground=BG,
            activeforeground=FG_ACCENT, font=FONT, highlightthickness=0,
        ).pack(side="left", padx=(0, 10))
        tk.Checkbutton(
            tf, text="Connected", variable=self._connected_var,
            command=self._on_connected_toggle, bg=BG, fg=FG,
            selectcolor=BG_CARD, activebackground=BG,
            activeforeground=FG_ACCENT, font=FONT, highlightthickness=0,
        ).pack(side="left")

        self._sep(f, PX)

        # ── Text Input (chat) ────────────────────────────────────────
        self._section(f, "Text Input", PX)
        txt_row = tk.Frame(f, bg=BG)
        txt_row.pack(fill="x", padx=PX, pady=(0, 4))
        txt_row.columnconfigure(0, weight=1)
        entry = tk.Entry(txt_row, textvariable=self._text_var, bg=BG_CARD,
                         fg=FG, font=FONT, insertbackground=FG_ACCENT,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=BORDER,
                         highlightcolor=FG_ACCENT)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=3)
        entry.bind("<Return>", lambda _: self._send_text())
        tk.Button(txt_row, text="Send", bg=BG_BTN, fg=FG, font=FONT_BTN,
                  activebackground=BG_ACTIVE, activeforeground=BG,
                  relief="flat", cursor="hand2", bd=0, padx=8, pady=2,
                  command=self._send_text).grid(row=0, column=1)

        self._sep(f, PX)

        # ── Config ───────────────────────────────────────────────────
        self._section(f, "Config", PX)
        cfg_f = tk.Frame(f, bg=BG_CARD, padx=6, pady=4,
                         highlightbackground=BORDER, highlightthickness=1)
        cfg_f.pack(fill="x", padx=PX, pady=(0, 4))

        # Load current config for display
        try:
            from config.settings import load_settings, validate_settings
            cfg = load_settings()
            warnings = validate_settings(cfg)

            # Gateway status
            gw = cfg.get("gateway", {})
            gw_url = gw.get("url", "")
            gw_token = "set" if gw.get("token") else "missing"
            gw_agent = gw.get("default_agent", "daemon")
            tk.Label(cfg_f, text=f"Gateway: {gw_url}", bg=BG_CARD,
                     fg=FG_ACCENT if gw_token == "set" else "#ff6b4a",
                     font=FONT_MONO, anchor="w").pack(fill="x")
            tk.Label(cfg_f, text=f"Token: {gw_token}  Agent: {gw_agent}",
                     bg=BG_CARD, fg=FG_DIM, font=FONT_MONO,
                     anchor="w").pack(fill="x")

            # Audio config
            audio = cfg.get("audio", {})
            tk.Label(cfg_f, text=f"TTS: {audio.get('tts_provider', '?')}  "
                     f"STT: {audio.get('stt_provider', '?')}  "
                     f"Vol: {audio.get('volume', '?')}",
                     bg=BG_CARD, fg=FG_DIM, font=FONT_MONO,
                     anchor="w").pack(fill="x")

            # Display config
            disp = cfg.get("display", {})
            tk.Label(cfg_f, text=f"FPS: {disp.get('fps', '?')}  "
                     f"Transitions: {disp.get('transitions', '?')}  "
                     f"Clock: {disp.get('clock', '?')}",
                     bg=BG_CARD, fg=FG_DIM, font=FONT_MONO,
                     anchor="w").pack(fill="x")

            # Warnings
            for w in warnings[:3]:
                tk.Label(cfg_f, text=f"! {w}", bg=BG_CARD, fg="#ff6b4a",
                         font=FONT_MONO, anchor="w", wraplength=350).pack(fill="x")

            # Web config URL
            if hasattr(self, '_backend') and self._backend:
                try:
                    from display.config_server import get_access_pin, _server_port
                    pin = get_access_pin()
                    if pin:
                        tk.Label(cfg_f, text=f"Web config PIN: {pin}",
                                 bg=BG_CARD, fg=FG_ACCENT, font=FONT_MONO,
                                 anchor="w").pack(fill="x")
                except Exception:
                    pass

        except Exception as e:
            tk.Label(cfg_f, text=f"Config load error: {e}", bg=BG_CARD,
                     fg="#ff6b4a", font=FONT_MONO, anchor="w").pack(fill="x")

        # Open config file button
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(fill="x", padx=PX, pady=(2, 2))
        tk.Button(btn_row, text="Open local.yaml", bg=BG_BTN, fg=FG,
                  font=FONT_BTN, relief="flat", cursor="hand2", bd=0,
                  padx=8, pady=2,
                  command=self._open_config_file).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="Open Web Config", bg=BG_BTN, fg=FG,
                  font=FONT_BTN, relief="flat", cursor="hand2", bd=0,
                  padx=8, pady=2,
                  command=self._open_web_config).pack(side="left")

        self._sep(f, PX)

        # ── Keyboard Shortcuts ────────────────────────────────────────
        self._section(f, "Keys", PX)
        kf = tk.Frame(f, bg=BG_CARD, padx=6, pady=4,
                      highlightbackground=BORDER, highlightthickness=1)
        kf.pack(fill="x", padx=PX, pady=(0, 8))
        kf.columnconfigure(0, weight=0, minsize=60)
        kf.columnconfigure(1, weight=1)

        for i, (key, desc) in enumerate([
            ("1-9, 0", "Set mood (first 10)"),
            ("[ / ]", "Cycle all moods"),
            ("Space", "Button sim"),
            ("`", "Dock / undock"),
            ("m", "Menu"),
            ("c", "Cycle views"),
            ("t", "Transcript"),
            ("p", "Demo mode"),
            ("n", "Noise spike"),
        ]):
            tk.Label(kf, text=key, bg=BG_CARD, fg=FG_ACCENT,
                     font=FONT_MONO, anchor="w").grid(
                row=i, column=0, sticky="w", pady=0)
            tk.Label(kf, text=desc, bg=BG_CARD, fg=FG_DIM,
                     font=FONT_MONO, anchor="w").grid(
                row=i, column=1, sticky="w", padx=(4, 0), pady=0)

    # ── Widget helpers ────────────────────────────────────────────────────

    def _section(self, parent: tk.Frame, text: str, px: int = 8) -> None:
        tk.Label(parent, text=text, bg=BG, fg=FG_ACCENT, font=FONT_BOLD,
                 anchor="w").pack(fill="x", padx=px, pady=(6, 1))

    def _sep(self, parent: tk.Frame, px: int = 8) -> None:
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=px, pady=4)

    def _slider(self, parent: tk.Frame, label: str, var: tk.Variable,
                from_: int, to: int, command: Callable, px: int = 8) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=px, pady=1)
        row.columnconfigure(1, weight=1)
        tk.Label(row, text=label, bg=BG, fg=FG, font=FONT,
                 width=9, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Scale(
            row, from_=from_, to=to, variable=var, orient="horizontal",
            command=lambda _: command(), bg=BG, fg=FG, troughcolor=BG_CARD,
            activebackground=FG_ACCENT, highlightthickness=0,
            sliderrelief="flat", showvalue=False, bd=0, length=100,
        ).grid(row=0, column=1, sticky="ew", padx=2)
        tk.Label(row, textvariable=var, bg=BG, fg=FG_DIM, font=FONT_MONO,
                 width=4, anchor="e").grid(row=0, column=2, sticky="e")

    # ── State callbacks ───────────────────────────────────────────────────

    def _set_mood(self, mood: str) -> None:
        self._state.mood = mood
        # Always return to IDLE and clear transient state so the mood
        # is visible — matches what happens on the real device
        self._state.state = "IDLE"
        self._state.speaking = False
        self._state.amplitude = 0.0
        if self._on_mood:
            self._on_mood(mood)
        log.info("Dev panel: mood → %s", mood)

    def _set_state(self, state_name: str) -> None:
        prev = self._state.state
        self._state.state = state_name

        # Sync dependent state so the full pipeline reacts
        if state_name == "SPEAKING":
            self._state.speaking = True
            self._state.mood = "neutral"
            if self._state.amplitude < 0.1:
                self._state.amplitude = 0.3
        elif state_name == "LISTENING":
            self._state.mood = "listening"
            self._state.speaking = False
        elif state_name == "THINKING":
            self._state.mood = "thinking"
            self._state.speaking = False
        elif state_name == "ERROR":
            self._state.mood = "error"
            self._state.speaking = False
            self._state.amplitude = 0.0
        elif state_name == "SLEEPING":
            self._state.mood = "sleepy"
            self._state.speaking = False
            self._state.amplitude = 0.0
        elif state_name == "IDLE":
            # Clean return to idle — clear all transient state
            self._state.speaking = False
            self._state.amplitude = 0.0
            self._state.mood = "neutral"

        if self._on_state:
            self._on_state(state_name)
        log.info("Dev panel: state → %s", state_name)

    def _on_character_change(self) -> None:
        self._state.character = self._char_var.get()
        log.info("Dev panel: character → %s", self._state.character)

    def _on_style_change(self) -> None:
        self._state.style = self._style_var.get()
        log.info("Dev panel: style → %s", self._state.style)

    def _set_accent(self, color: str) -> None:
        self._state.accent_color = color
        log.info("Dev panel: accent → %s", color)

    def _on_agent_change(self) -> None:
        self._state.agent = self._agent_var.get()
        log.info("Dev panel: agent → %s", self._state.agent)

    def _trigger_emoji(self, emoji: str) -> None:
        from display.emoji_reactions import apply_reaction
        apply_reaction(self._state, emoji, time.time())
        log.info("Dev panel: emoji reaction → %s", emoji)

    def _toggle_mic(self) -> None:
        if self._mic.active:
            self._mic.stop()
            self._state.amplitude = 0.0
            self._state.speaking = False
            log.info("Dev panel: mic OFF")
        else:
            self._mic.start()
            log.info("Dev panel: mic ON")

    def _on_amplitude_change(self) -> None:
        if not self._mic.active:
            self._state.amplitude = self._amp_var.get() / 100.0
            self._state.speaking = self._state.amplitude > 0.01

    def _on_mic_sens_change(self) -> None:
        self._mic.sensitivity = self._mic_sens_var.get() / 100.0

    def _send_text(self) -> None:
        text = self._text_var.get().strip()
        if not text:
            return
        self._text_var.set("")
        log.info("Dev panel: text → %s", text[:60])

        # Show user message
        self._state.push_transcript("user", text)
        self._state.transcript_visible = True
        self._state.view = "face"

        # If gateway is configured, send through the full pipeline
        if self._chat.available and not self._chat.busy:
            self._state.push_transcript("assistant", "...", status="partial")

            def _on_response(response: str | None):
                if response:
                    # Extract mood tag if present
                    try:
                        from core.mood_parser import extract_mood
                        mood, clean = extract_mood(response)
                        if mood:
                            self._state.mood = mood
                        response = clean
                    except ImportError:
                        pass
                    self._state.push_transcript("assistant", response)
                    self._state.state = "SPEAKING"
                    self._state.speaking = True
                    self._state.amplitude = 0.3
                    log.info("Dev panel: response (%d chars)", len(response))
                else:
                    # Show error state briefly, then recover to IDLE
                    self._state.push_transcript("assistant", "(no response)")
                    self._state.state = "ERROR"
                    self._state.mood = "error"
                    self._state.speaking = False
                    self._state.amplitude = 0.0
                    log.warning("Dev panel: empty response → ERROR state")

                    # Auto-recover to IDLE after 3s
                    def _recover():
                        time.sleep(3.0)
                        if self._state.state == "ERROR":
                            self._state.state = "IDLE"
                            self._state.mood = "neutral"
                    threading.Thread(target=_recover, daemon=True).start()

            self._chat.send(text, self._state, _on_response)
        else:
            if not self._chat.available:
                log.debug("Dev panel: gateway not configured, transcript only")

    def _on_battery_change(self) -> None:
        level = max(0, min(100, int(self._bat_var.get())))
        self._state.battery = level
        # Sync battery_warning so status decorations fire immediately
        if level < 10:
            self._state.battery_warning = "critical_battery"
        elif level < 20:
            self._state.battery_warning = "low_battery"
        else:
            self._state.battery_warning = None

    def _on_brightness_change(self) -> None:
        self._state.brightness = self._bright_var.get()

    def _on_volume_change(self) -> None:
        self._state.volume = self._vol_var.get()

    def _on_demo_toggle(self) -> None:
        self._state.demo_mode = self._demo_var.get()
        log.info("Dev panel: demo → %s", self._state.demo_mode)

    def _on_connected_toggle(self) -> None:
        was = self._state.connected
        now_val = self._connected_var.get()
        self._state.connected = now_val
        # Trigger connection event so status decorations fire
        if was != now_val:
            self._state.connection_event = "connected" if now_val else "disconnected"
            self._state.connection_event_time = time.time()
        log.info("Dev panel: connected → %s", self._state.connected)

    def _open_config_file(self) -> None:
        """Open config/local.yaml in the system editor."""
        import os, subprocess
        path = os.path.join(os.path.dirname(__file__), "..", "config", "local.yaml")
        path = os.path.abspath(path)
        # Create if missing
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("# Voxel local config overrides\n")
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", path])  # Linux
        log.info("Dev panel: opened %s", path)

    def _open_web_config(self) -> None:
        """Open the web config UI in the default browser."""
        import webbrowser
        try:
            from display.config_server import _server_port
            url = f"http://localhost:{_server_port}"
            webbrowser.open(url)
            log.info("Dev panel: opened %s", url)
        except Exception:
            log.warning("Dev panel: web config not available")

    def _on_close(self) -> None:
        self._closed = True
        if self._mic.active:
            self._mic.stop()
        self._destroy_content()
        if self._toplevel:
            self._toplevel.destroy()
            self._toplevel = None
        if self._backend and self._backend.is_docked:
            self._backend.undock()
        log.info("Dev panel closed")

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def closed(self) -> bool:
        return self._closed

    def update(self) -> None:
        """Sync panel UI with current DisplayState."""
        if self._closed:
            return

        s = self._state

        # ── Mic → amplitude ───────────────────────────────────────
        if self._mic.active:
            s.amplitude = self._mic.amplitude
            s.speaking = self._mic.amplitude > 0.02
            self._mic_level_var.set(f"{self._mic.amplitude:.2f}")
        else:
            self._mic_level_var.set(f"{s.amplitude:.2f}")

        # Draw mic level bar
        if self._mic_bar:
            bar = self._mic_bar
            bar.delete("all")
            w = bar.winfo_width()
            h = bar.winfo_height()
            if w > 1:
                level = s.amplitude
                fill_w = int(w * min(level, 1.0))
                if fill_w > 0:
                    color = BG_ACTIVE if level < 0.7 else "#ff6b4a"
                    bar.create_rectangle(0, 0, fill_w, h, fill=color,
                                         outline="")

        # Style the MIC button
        if hasattr(self, "_mic_btn"):
            if self._mic.active:
                self._mic_btn.configure(bg=BG_ACTIVE, fg=BG)
            else:
                self._mic_btn.configure(bg=BG_BTN, fg=FG)

        # ── Status readout ────────────────────────────────────────
        self._status_var.set(
            f"{s.state}  {s.mood}  {s.character}  {s.style}  "
            f"{s.agent}  amp={s.amplitude:.2f}  bat={s.battery}%  "
            f"vol={s.volume}{'  DEMO' if s.demo_mode else ''}"
        )

        # Highlight active mood
        for mood, btn in self._mood_buttons.items():
            if mood == s.mood:
                btn.configure(bg=BG_ACTIVE, fg=BG)
            else:
                btn.configure(bg=BG_BTN, fg=FG)

        # Highlight active state
        for st, btn in self._state_buttons.items():
            if st == s.state:
                btn.configure(bg=BG_ACTIVE, fg=BG)
            else:
                btn.configure(bg=BG_BTN, fg=FG)

        # Sync vars if changed externally
        if self._char_var.get() != s.character:
            self._char_var.set(s.character)
        if self._style_var.get() != s.style:
            self._style_var.set(s.style)
        if self._agent_var.get() != s.agent:
            self._agent_var.set(s.agent)
        if self._demo_var.get() != s.demo_mode:
            self._demo_var.set(s.demo_mode)
        if self._connected_var.get() != s.connected:
            self._connected_var.set(s.connected)
