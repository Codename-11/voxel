"""Tkinter window backend — stdlib-only desktop preview of the 240x280 display.

Uses tkinter (built into Python) so it works even when pygame isn't available.
Supports docking the dev panel side-by-side in the same window.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageTk

from display.backends.base import OutputBackend

WIDTH = 240
HEIGHT = 280

_BG = "#1e1e30"


class TkinterBackend(OutputBackend):
    """Renders PIL frames into a tkinter window for local development.

    Supports a dockable dev panel: the right side of the window can host
    the DevPanel content frame. Toggle with backtick (`) or the dock button.
    """

    def __init__(self, scale: int = 2):
        self._scale = scale
        self._root: tk.Tk | None = None
        self._label: tk.Label | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._quit = False
        self._key_callback: callable | None = None

        # LED simulation
        self._led_canvas: tk.Canvas | None = None
        self._led_color: str = "#000000"

        # Docking support
        self._dock_container: tk.Frame | None = None
        self._docked = False
        self._display_w = 0
        self._display_h = 0

    def init(self) -> None:
        self._root = tk.Tk()
        self._root.title("Voxel Preview")
        self._root.configure(bg=_BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.bind("<Escape>", lambda _: self._on_close())
        self._root.bind("<Key>", self._on_key)
        self._root.bind("<KeyPress-space>", self._on_space_press)
        self._root.bind("<KeyRelease-space>", self._on_space_release)
        self._space_hold_callback: callable | None = None
        self._space_release_callback: callable | None = None

        self._display_w = WIDTH * self._scale
        self._display_h = HEIGHT * self._scale

        # Left column: LED + display stacked vertically
        self._left_col = tk.Frame(self._root, bg=_BG)
        self._left_col.pack(side="left", anchor="n", padx=8, pady=8)

        # LED simulation — small pill above the display, mimics the
        # WhisPlay HAT RGB LED so developers can see LED state.
        led_h = 8
        led_w = self._display_w // 3
        self._led_canvas = tk.Canvas(
            self._left_col, width=self._display_w + 4, height=led_h + 8,
            bg=_BG, highlightthickness=0,
        )
        self._led_canvas.pack(pady=(0, 2))
        # Centered pill shape
        lx = (self._display_w + 4 - led_w) // 2
        self._led_pill = self._led_canvas.create_rectangle(
            lx, 4, lx + led_w, 4 + led_h,
            fill="#0a0a0f", outline="#1a1a2a", width=1,
        )
        # Glow oval behind the pill (larger, faint)
        self._led_glow = self._led_canvas.create_oval(
            lx - 8, 0, lx + led_w + 8, led_h + 8,
            fill="", outline="",
        )
        self._led_canvas.tag_lower(self._led_glow, self._led_pill)

        # Display area — preview image in a subtle recessed well
        self._display_well = tk.Frame(
            self._left_col, bg="#2a2a44", padx=2, pady=2,
        )
        self._display_well.pack()

        self._label = tk.Label(
            self._display_well, bg="black",
            borderwidth=0, highlightthickness=0,
        )
        self._label.pack()

        # Dock container — right side, starts hidden
        self._dock_container = tk.Frame(self._root, bg=_BG)

        # Initial size — display + well padding
        pad = 20  # 8px outer pad + 2px well border, each side
        self._root.geometry(
            f"{self._display_w + pad}x{self._display_h + pad}")
        self._root.resizable(False, False)

    # ── Docking API ───────────────────────────────────────────────────────

    @property
    def dock_container(self) -> tk.Frame | None:
        """Frame where the dev panel can pack its content when docked."""
        return self._dock_container

    @property
    def is_docked(self) -> bool:
        return self._docked

    def dock(self, panel_width: int = 400) -> None:
        """Expand the window to show the dock container on the right."""
        if self._docked or not self._root or not self._dock_container:
            return
        self._docked = True
        self._root.resizable(True, True)
        total_w = self._display_w + 20 + panel_width
        total_h = max(self._display_h + 20, 900)
        self._root.geometry(f"{total_w}x{total_h}")
        self._root.minsize(self._display_w + 200, 500)
        self._dock_container.pack(side="right", fill="both", expand=True)
        self._root.title("Voxel Preview + Dev Panel")

    def undock(self) -> None:
        """Collapse back to display-only window."""
        if not self._docked or not self._root or not self._dock_container:
            return
        self._docked = False
        self._dock_container.pack_forget()
        pad = 20
        self._root.geometry(
            f"{self._display_w + pad}x{self._display_h + pad}")
        self._root.resizable(False, False)
        self._root.title("Voxel Preview")

    # ── Frame rendering ───────────────────────────────────────────────────

    def push_frame(self, image: Image.Image) -> None:
        if self._root is None or self._quit:
            return

        if self._scale != 1:
            display_img = image.resize(
                (self._display_w, self._display_h), Image.NEAREST)
        else:
            display_img = image

        self._photo = ImageTk.PhotoImage(display_img)
        if self._label:
            self._label.configure(image=self._photo)

        try:
            self._root.update_idletasks()
            self._root.update()
        except tk.TclError:
            self._quit = True

    def should_quit(self) -> bool:
        return self._quit

    def cleanup(self) -> None:
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass

    # ── Input callbacks ───────────────────────────────────────────────────

    def set_key_callback(self, callback: callable) -> None:
        self._key_callback = callback

    def set_button_callbacks(self, on_press: callable, on_release: callable) -> None:
        self._space_hold_callback = on_press
        self._space_release_callback = on_release

    def _on_key(self, event: tk.Event) -> None:
        if event.keysym == "space":
            return
        if self._key_callback and event.char:
            self._key_callback(event.char)

    def _on_space_press(self, event: tk.Event) -> None:
        if self._space_hold_callback:
            self._space_hold_callback()

    def _on_space_release(self, event: tk.Event) -> None:
        if self._space_release_callback:
            self._space_release_callback()

    def set_led(self, r: int, g: int, b: int) -> None:
        """Update the simulated LED color. Called from the render loop."""
        if not self._led_canvas:
            return
        if r == 0 and g == 0 and b == 0:
            color = "#0a0a0f"
            glow = ""
        else:
            color = f"#{r:02x}{g:02x}{b:02x}"
            # Dim glow version for the oval behind
            gr = max(0, r // 5)
            gg = max(0, g // 5)
            gb = max(0, b // 5)
            glow = f"#{gr:02x}{gg:02x}{gb:02x}"
        if color != self._led_color:
            self._led_color = color
            self._led_canvas.itemconfig(self._led_pill, fill=color)
            self._led_canvas.itemconfig(self._led_glow, fill=glow)

    def _on_close(self) -> None:
        self._quit = True
