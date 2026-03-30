# Display Architecture

Voxel's display system renders an animated face on a 240x280 IPS LCD. The production renderer uses Python PIL to composite frames and push them to the SPI display.

## Display Paths

Multiple rendering paths have been explored. Only the PIL renderer is used in production.

| Path | Method | Status |
|------|--------|--------|
| PIL to SPI | Python PIL renders frames, pushes RGB565 via WhisPlay driver | **Production** |
| LVGL native | C binary pre-renders RGB565 frames, played back on Pi | Shelved PoC |
| WPE/Cog | React app via WebKit to framebuffer | Never tested |
| React browser | Vite dev server in a desktop browser | Dev tool only |

## System Overview

```
                    ┌─────────────────────────────────────────────┐
                    │            display/service.py               │
                    │  (entry point: render loop + event loop)    │
                    ├─────────────────────────────────────────────┤
                    │                                             │
  WebSocket ◄──────┤  DisplayState    PILRenderer                │
  server.py :8080  │  (shared state)  (frame compositor)         │
                    │       │                │                    │
  Button poll ─────┤       ▼                ▼                    │
  (GPIO / kbd)     │  ┌──────────────────────────────┐           │
                    │  │     Frame Compositing        │           │
  Config server ───┤  │  1. Background fill           │           │
  :8081            │  │  2. Character.draw()          │           │
                    │  │  3. Mood decorations          │           │
                    │  │  4. Status bar                │           │
                    │  │  5. Overlays (menu, chat...)  │           │
                    │  │  6. Button indicator          │           │
                    │  │  7. Corner mask               │           │
                    │  └──────────┬───────────────────┘           │
                    │             │ PIL Image (240x280 RGB)       │
                    │             ▼                               │
                    │  ┌──────────────────────┐                   │
                    │  │   Output Backend     │                   │
                    │  │  Pi:  SPI → LCD      │                   │
                    │  │  Dev: tkinter window  │                   │
                    │  └──────────────────────┘                   │
                    └─────────────────────────────────────────────┘
```

## Render Pipeline

Every frame follows this exact sequence inside `PILRenderer.render()`:

```
┌─ Per-frame pipeline ──────────────────────────────────────────┐
│                                                               │
│  1. Update state                                              │
│     ├── Poll button / WebSocket messages                      │
│     ├── Update transcript auto-hide timers                    │
│     └── Demo mode: auto-cycle moods/characters/styles         │
│                                                               │
│  2. Resolve mood                                              │
│     ├── External sources (dev panel, WebSocket)               │
│     ├── Wake-up micro-expression (sleepy→surprised→neutral)   │
│     ├── Idle attention ("curious" on button press)            │
│     └── Idle personality (battery, connection, ambient)       │
│                                                               │
│  3. Advance animations                                        │
│     ├── MoodTransition.update() → lerped Expression           │
│     ├── BlinkState.update()     → blink_factor (0..1)         │
│     ├── GazeDrift.update()      → gaze_x, gaze_y (-1..1)     │
│     └── BreathingState.update() → body scale (0.98..1.02)     │
│                                                               │
│  4. Compose frame (PIL Image 240x280)                         │
│     ├── Background fill (dark)                                │
│     ├── Status bar (top 48px)                                 │
│     ├── View content:                                         │
│     │   ├── "face": Character.draw() + decorations + peek     │
│     │   ├── "chat_drawer": Character + drawer overlay         │
│     │   └── "chat_full": Full-screen chat history             │
│     ├── View transition cross-fade (if switching)             │
│     ├── Menu overlay (with fade-in)                           │
│     ├── Button indicator (progress ring + flash pills)        │
│     ├── Shutdown overlay (if confirming)                      │
│     └── Corner mask (black out rounded LCD corners)           │
│                                                               │
│  5. Push to backend                                           │
│     ├── Pi:  PIL → RGB565 numpy → SPI write                  │
│     └── Dev: PIL → tkinter PhotoImage                         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Frame Timing

- **Target:** 30 FPS (configurable via `display.fps`)
- **Actual on Pi:** ~20 FPS due to CPU and SPI bandwidth limits
- **Render loop:** `display/service.py` runs a synchronous loop with `time.sleep()` to maintain target framerate

## Animation System

Four independent animation state machines run every frame, all time-based (driven by `now` float seconds):

### MoodTransition

Smoothly interpolates between Expression states over 300ms using ease-in-out easing. When the mood changes, the current expression becomes `_previous` and the target is set. Each frame computes `lerp_expression(previous, target, t)` which interpolates all sub-objects (eyes, mouth, body, per-eye overrides).

```
neutral ──(mood change)──→ happy
  │                          │
  └── lerp_expression(neutral, happy, ease_in_out(t)) ──→ smooth blend
```

### BlinkState

Periodic eye blinks with realistic clustering. Controls a `blink_factor` (0.0 = closed, 1.0 = open) that characters use to modulate eye height.

- **Blink duration:** 150ms
- **Interval:** `10 / blink_rate` seconds (blink_rate from expression YAML)
- **Clustering:** 30% chance of a double/triple blink (0.2-0.4s gap)
- **Suppressed** when eyes are already nearly closed (sleepy moods)

### GazeDrift

Saccadic eye movement — fast snaps between fixation points with slow micro-drift during fixation.

- **Saccade speed:** 12x delta-time (fast snap to new target)
- **Fixation duration:** 2-6s (scaled by `gaze_drift_speed` config)
- **Micro-drift:** Sinusoidal 0.012px during fixation (subtle organic movement)
- **Range:** ±0.2 to ±0.4 (scales with speed setting)

### BreathingState

Continuous sinusoidal body scale oscillation for organic feel.

- **Range:** 0.98x to 1.02x scale
- **Cycle:** ~4s at default speed (0.3), ~1.2s at speed 1.0
- **Variation:** Speed randomly drifts ±15% every ~4s

## Character System

Characters are pluggable renderers in `display/characters/`. Each character implements the abstract interface from `display/characters/base.py` and interprets the same `Expression` data differently.

### Interface Contract

```python
class Character(ABC):
    name: str  # e.g. "voxel", "cube", "bmo"

    # Position feedback — set during draw(), read by decorations
    _last_face_cx: int    # face center X
    _last_face_cy: int    # face center Y
    _last_left_eye: tuple[int, int]   # left eye center
    _last_right_eye: tuple[int, int]  # right eye center

    # Accent color — set by renderer from config before draw()
    _accent: tuple[int, int, int]  # RGB, default (0, 212, 210)

    @abstractmethod
    def draw(self, draw, img, expr, style,
             blink_factor, gaze_x, gaze_y,
             amplitude, now) -> None:
        """Draw the character onto the image."""

    def idle_quirk(self, draw, img, now) -> None:
        """Optional idle-only decoration (default: no-op)."""
```

### draw() Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `draw` | `ImageDraw` | — | PIL drawing context |
| `img` | `Image` | — | PIL image (for alpha compositing) |
| `expr` | `Expression` | — | Current interpolated expression |
| `style` | `FaceStyle` | — | Active face style (kawaii/retro/minimal) |
| `blink_factor` | `float` | 0.0–1.0 | Eye openness (0=closed, 1=open) |
| `gaze_x` | `float` | -1..1 | Horizontal gaze offset |
| `gaze_y` | `float` | -1..1 | Vertical gaze offset |
| `amplitude` | `float` | 0..1 | Audio level for mouth sync |
| `now` | `float` | — | Current time (for continuous animations) |

### Position Feedback

Characters **must** update these instance variables during `draw()`:

- `_last_face_cx`, `_last_face_cy` — center of the face/body
- `_last_left_eye`, `_last_right_eye` — center of each eye

These positions are read by the decoration system to place mood-specific overlays (tears, sparkles, blush, etc.) relative to the actual rendered face, not hardcoded screen positions.

### Built-in Characters

| Character | File | Description |
|-----------|------|-------------|
| **Voxel** | `voxel.py` | Glowing cyan pill eyes — minimal, expressive. Uses emotion-specific cuts (happy squint, angry slant, sad droop). Default character. |
| **Cube** | `cube.py` | Isometric 3D charcoal cube with neon edge glow, detailed pupils, mouth shapes, multi-layer shading. |
| **BMO** | `bmo.py` | Adventure Time console. Pixel-art style with screen-face, antenna, buttons. |

## Creating a New Character

### Step 1: Create the file

Create `display/characters/mychar.py`:

```python
from __future__ import annotations
from PIL import Image, ImageDraw
from shared import Expression, FaceStyle
from display.characters.base import Character
from display.layout import SCREEN_W, SCREEN_H, STATUS_H

class MyChar(Character):
    name = "mychar"

    def draw(self, draw: ImageDraw.ImageDraw, img: Image.Image,
             expr: Expression, style: FaceStyle,
             blink_factor: float, gaze_x: float, gaze_y: float,
             amplitude: float, now: float) -> None:

        # Face area: below status bar
        cx = SCREEN_W // 2          # 120
        cy = STATUS_H + (SCREEN_H - STATUS_H) // 2  # ~164

        # ── Body ──
        # Draw your character body here
        # Use expr.body.scale, expr.body.bounce_amount, expr.body.tilt

        # ── Eyes ──
        # Use expr.eyes.openness * blink_factor for eye height
        # Use gaze_x, gaze_y for pupil/eye offset
        # Use expr.eyes.pupil_size for pupil scale
        eye_h = int(24 * expr.eyes.openness * blink_factor)
        left_x = cx - 20
        right_x = cx + 20
        eye_y = cy - 10

        # Draw left eye
        draw.rounded_rectangle(
            [left_x - 6, eye_y - eye_h//2, left_x + 6, eye_y + eye_h//2],
            radius=6, fill=self._accent,
        )
        # Draw right eye (same)
        draw.rounded_rectangle(
            [right_x - 6, eye_y - eye_h//2, right_x + 6, eye_y + eye_h//2],
            radius=6, fill=self._accent,
        )

        # ── Mouth ──
        # Use expr.mouth.smile (-1..1), expr.mouth.openness (0..1)
        # Use amplitude for speaking animation

        # ── IMPORTANT: Update position feedback ──
        self._last_face_cx = cx
        self._last_face_cy = cy
        self._last_left_eye = (left_x, eye_y)
        self._last_right_eye = (right_x, eye_y)
```

### Step 2: Register the character

Add your character to `display/characters/__init__.py`:

```python
from display.characters.mychar import MyChar

_CHARACTERS["mychar"] = MyChar()
```

### Step 3: Set as active

In `config/local.yaml`:

```yaml
character:
  default: mychar
```

Or switch at runtime via the settings menu or WebSocket command:
```json
{ "type": "set_setting", "section": "character", "key": "default", "value": "mychar" }
```

### Step 4: Test

```bash
uv run dev          # Preview in tkinter window
```

Use keyboard shortcuts to cycle moods (`[`/`]`), test all 16 expressions, verify decorations appear at the right positions.

### Tips for Character Development

- **Start with eyes.** Eyes carry 80% of the expression. Get those right first, then add body/mouth.
- **Respect blink_factor.** Multiply eye height/openness by `blink_factor` — this is how the blink system controls your character's eyes without knowing your geometry.
- **Use `_accent` color.** The renderer sets this from config before calling `draw()`. Use it for your primary glow/edge/eye color so users can customize the accent.
- **Keep it simple.** PIL rendering is CPU-bound on a 1GHz ARM. Avoid heavy alpha compositing or complex fills per frame. Flat shapes with accent edges work well.
- **Test at 1:1 scale.** The LCD is 240x280px. Run `uv run dev` (scale 1) to see exactly what the hardware shows. Details below 2-3px are invisible.
- **Update eye positions.** If you skip updating `_last_left_eye` / `_last_right_eye`, mood decorations (tears, blush, sparkles) will appear at wrong positions.
- **Use `idle_quirk()` for flavor.** Subtle idle-only effects (glow pulse, antenna wiggle, screen flicker) make characters feel alive without cluttering active states.

## Expression System

### YAML Schema

Expressions are defined in `shared/expressions.yaml`. Each of the 16 moods follows this schema:

```yaml
mood_name:
  eyes:
    width: 1.0        # Eye width multiplier (0.5–1.5)
    height: 1.0       # Eye height multiplier (0.5–1.5)
    openness: 0.9      # How open the eyes are (0.0–1.0)
    pupil_size: 0.4    # Pupil radius multiplier (0.1–0.8)
    gaze_x: 0          # Default horizontal gaze (-1..1)
    gaze_y: 0          # Default vertical gaze (-1..1)
    blink_rate: 3.0    # Blinks per ~10s (0.5–5.0)
    squint: 0          # Squint amount (0.0–1.0)
  mouth:
    openness: 0        # Mouth open amount (0.0–1.0)
    smile: 0.3         # Smile curve (-1.0=frown, 0=neutral, 1.0=big smile)
    width: 1.0         # Mouth width multiplier (0.5–2.0)
  body:
    bounce_speed: 0.3  # Bounce animation speed (0.1–2.0)
    bounce_amount: 2   # Bounce height in pixels (0–8)
    tilt: 0            # Body tilt in degrees (-15..15)
    scale: 1.0         # Body scale multiplier (0.8–1.2)

  # Optional: per-eye overrides for asymmetric expressions
  left_eye:
    openness: 0.5      # Override left eye openness
    height: 0.8        # Override left eye height
    squint: 0.3        # Override left eye squint
    tilt: -5           # Override left eye tilt (degrees)
  right_eye:
    openness: 1.0      # Different from left = winking

  # Optional: eye color override (hex string)
  eye_color_override: "#ff4444"  # Used by low_battery, critical_battery
```

### Built-in Moods

| Mood | Key Expression Traits |
|------|----------------------|
| neutral | Relaxed eyes, slight smile, gentle bounce |
| happy | Squinted eyes, big smile, faster bounce |
| curious | Wide eyes, large pupils, slight tilt |
| thinking | Upward gaze, slow blink, tilt oscillation |
| listening | Wide open, large pupils, still body |
| excited | Very wide eyes, big bounce, high energy |
| sleepy | Nearly closed eyes, slow everything |
| confused | Asymmetric eyes, tilted, furrowed |
| surprised | Maximum openness, tiny pupils, jump |
| focused | Narrow eyes, squint, reduced blink |
| frustrated | Squint, frown, tight body |
| sad | Drooped eyes, downward gaze, frown |
| error | Wide + small pupils, red eye override |
| low_battery | Drowsy, orange eye override |
| critical_battery | Nearly closed, red eye override |
| connected | Brief wide eyes, quick smile |

## Mood Decorations

After the character draws, the renderer checks if the current mood has decorations (`display/decorations.py`). These are drawn on an RGBA overlay and alpha-composited onto the frame.

| Mood | Decoration | Positioning |
|------|-----------|-------------|
| happy | Sparkles, blush circles | Around face center, on cheeks |
| excited | Sparkles (more, faster) | Around face center |
| frustrated | Sweat drops | Above-right of face |
| sleepy | ZZZ symbols (floating) | Above-right of face |
| sad | Tear drops | Below each eye center |
| surprised | "!" exclamation | Above face center |
| thinking | Animated dots | Above-right of face |

Decorations read the character's `_last_face_cx`, `_last_left_eye`, `_last_right_eye` to position themselves relative to the actual rendered face.

## Backend Abstraction

Output backends are pluggable via `display/backends/`. Each backend receives a PIL `Image` and displays it.

### WhisPlay Backend (Pi)

`display/backends/spi.py`

Converts the PIL frame to RGB565 and writes it to the ST7789 LCD controller over SPI at 100MHz. This is the production path on the Pi.

### tkinter Backend (Desktop)

`display/backends/tkinter.py`

Opens a tkinter window sized to 240x280 and displays each frame as a `PhotoImage`. Used by `uv run dev` for local preview. Simulates the hardware button with the spacebar.

### pygame Backend (Desktop)

`display/backends/pygame.py`

Alternative desktop preview using pygame. Same functionality as tkinter but uses a different windowing library.

## Component System

UI components live in `display/components/`. Each renders a specific overlay or element:

| Component | File | Purpose |
|-----------|------|---------|
| Face | `face.py` | Composites eyes and mouth via the active character |
| Menu | `menu.py` | Settings and navigation overlay |
| Status Bar | `status_bar.py` | Battery level, WiFi status, active agent |
| Transcript | `transcript.py` | Chat message overlay and drawer |
| Button Indicator | `button_indicator.py` | Three-zone progress ring and flash pills |
| Speaking Pill | `speaking_pill.py` | Waveform pill during speech, mic indicator |
| Shutdown Overlay | `shutdown_overlay.py` | Countdown (3... 2... 1...) before shutdown |
| QR Overlay | `qr_overlay.py` | QR code for config URL |
| WiFi Setup | `wifi_setup.py` | AP mode WiFi onboarding UI |
| Onboarding | `onboarding.py` | First-run configuration screen |
| Emoji Reactions | `emoji_reactions.py` (in `display/`) | Floating emoji decoration from agent responses |

## Display State

`display/state.py` (`DisplayState`) holds the shared state that all components read from:

- Current mood, face style, character
- Speaking state and audio amplitude
- Battery level, charging, WiFi status
- Active agent name
- Menu state and view mode
- Button hold progress and flash type
- Transcript history (TranscriptEntry supports `role="tool"` and streaming statuses: `partial`, `done`, `thinking`, `tool_running`, `tool_done`)
- Connection and pairing state
- Emoji reaction state: `reaction_emoji` (current emoji string or `None`), `reaction_time` (when it was triggered), `reaction_duration` (display length in seconds, default 3.0)

State is updated from the WebSocket connection to the Python backend (`server.py`), which manages the state machine and hardware I/O.

## Screen Layout

`display/layout.py` defines the screen geometry:

```
┌──────────────────────────────┐ 0
│  Status Bar (48px)           │
│  Agent  State·icon  Bat% wifi│
├──────────────────────────────┤ 48
│                              │
│    ┌────────────────────┐    │
│    │                    │    │
│    │   Character Face   │    │
│    │   (eyes, mouth,    │    │
│    │    body, accents)  │    │
│    │                    │    │
│    └────────────────────┘    │
│                              │
│  ···  (view dots)            │
├──────────────────────────────┤ ~250
│  Button indicator / peek     │
└──────────────────────────────┘ 280
```

- **Resolution:** 240x280 pixels
- **Corner radius:** ~40px (physical bezel clips corners)
- **Safe area:** Inset content 20px+ from edges at top and bottom rows
- **Status bar:** Top 48px
- **Face:** Center area, fills most of the screen
- **Button indicator:** Bottom of screen

## Emoji Reaction System

Agents can prefix their text responses with an emoji (e.g. "😊 That's great!"). The backend parses the leading emoji, strips it from the text, and sends a `reaction` message over WebSocket.

**Emoji-to-mood mapping:** 31 emoji are mapped to 11 moods. For example, 😊/😄 map to `happy`, 🤔 maps to `thinking`, 😮 maps to `surprised`, and so on. When a mapped emoji is received, the display service changes the current mood accordingly. Unmapped emoji still display as a visual decoration but do not trigger a mood change.

**Animation:** The emoji decoration renders as a floating overlay near the top of the face area. The animation sequence is:

1. **Pop-in** — emoji scales up quickly from 0 to full size
2. **Hold** — emoji stays visible at full size
3. **Fade-out** — emoji fades to transparent and disappears

The full cycle defaults to 3 seconds (configurable via `reaction_duration` on DisplayState). The decoration is drawn by `display/emoji_reactions.py` and composited during the render pipeline after mood decorations.

## Streaming & Tool Calls

The OpenClaw gateway supports Server-Sent Events (SSE) streaming, with automatic fallback to non-streaming requests if the gateway returns empty or errors.

**Streaming transcript flow:**

1. User sends a message (via voice or text input)
2. The backend opens an SSE connection to the gateway
3. As chunks arrive, `transcript` messages are emitted with `status: "partial"` containing the accumulated text so far
4. When the stream completes, a final `transcript` message is sent with `status: "done"`
5. If streaming fails, the backend falls back to a single non-streaming request

**Tool call display:**

When the gateway invokes tools during a response, the backend emits `tool_call` messages:

- `status: "running"` — tool execution has started (display shows a gear icon prefix in the chat transcript)
- `status: "done"` — tool execution completed, result available

Tool calls appear in the transcript with `role: "tool"` entries. In the chat view, they are displayed with a gear icon prefix and the tool name.

**Transcript statuses:**

| Status | Meaning |
|--------|---------|
| `partial` | Streaming response in progress (text is accumulating) |
| `done` | Response complete |
| `thinking` | Agent is processing (before first token) |
| `tool_running` | A tool call is currently executing |
| `tool_done` | A tool call has finished |

## MCP Integration

Voxel's MCP server is an **optional enhancement** — the display service works independently without it. When enabled, external AI agents can control the device via standard MCP protocol.

**Discovery:** The config web server (port 8081) provides two public endpoints for agent auto-discovery:
- `GET /.well-known/mcp` — JSON with MCP server status, URL, tool count
- `GET /skill` — raw OpenClaw skill definition (markdown)

These endpoints require no authentication, allowing agents to discover Voxel automatically.

**Architecture:** The MCP server connects to server.py via WebSocket on port 8080 (same protocol as the display service). It translates MCP tool calls into WS commands. 20 tools are exposed across three categories: control (mood, speech, LED), query (stats, logs, diagnostics), and manage (config, services, updates, WiFi). MCP tools have exactly the same capabilities as the web chat — no privileged access, no separate API.

See `openclaw/README.md` for setup instructions.

## Constraints

- **SPI bandwidth:** Full-frame writes at 100MHz SPI. No VSYNC pin available — cannot sync writes to panel refresh.
- **CPU bound:** PIL rendering is single-threaded Python on a quad-core 1GHz ARM. Keep rendering logic simple.
- **Backlight:** Must run at 100% to avoid flicker. The software PWM implementation causes visible brightness pulsing at lower levels. Future improvement: use ST7789 panel-level brightness commands (registers 0x51/0x53) or hardware PWM.
- **Memory:** Target under 40MB for the display service process. The Pi has only 512MB total.
