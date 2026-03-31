# Character Design — Voxel

> For the React face renderer, face styles, shared YAML data layer, and instructions on adding moods/styles, see [Design System](design-system.md).

## Identity

**Voxel** is the name of both the project and the character. The character is the soul of the device — it's what makes this a companion, not just a voice assistant.

## Characters

The project includes multiple character renderers, all pluggable via `display/characters/`. The **default character is "voxel"** (configured via `character.default` in `config/default.yaml`).

### Voxel (default) — `display/characters/voxel.py`

The signature Voxel face. **Eyes only** — no pupils, no highlights, no mouth. All expression is conveyed through eye shape and cuts. Inspired by Deskimon/EMO desktop companions.

**Design:**
- **Eyes:** Solid glowing vertical pill shapes on the dark background
- **No mouth** — expression is purely through eye geometry
- **Accent color theming** — eye color comes from a configurable accent color (cyan/teal by default), with per-mood color overrides (e.g., amber for low battery)
- **Background:** Deep dark (#0a0a0f)

**Expression through tilt cuts:**
Emotions are expressed by masking portions of the pill-shaped eyes with the background color:

| Expression | Technique |
|-----------|-----------|
| Neutral | Full pill shapes |
| Happy | Bottom half cut (upward crescents ^_^) |
| Angry | Diagonal top cut, inner edge lower (V-brow) |
| Sad | Diagonal top cut, outer edge lower (droopy) |
| Surprised | Taller, rounder pills |
| Sleepy | Thin horizontal slits |
| Thinking | Asymmetric (one open, one narrowed) |
| Error | Red X marks |

**Mood-specific eye shapes:**
- **Happy:** Curved bottom cutout on eyes (smile-shaped, inspired by FluxGarage RoboEyes) -- creates upward crescent "squint-smile" eyes
- **Sleepy / low-battery:** Bar-shaped eyes with filleted ends (not elliptical) -- narrow horizontal slits that read as drowsy
- **Closed eyes (blink):** Flat horizontal bars with small fillet radius (not capsules) -- crisp, deliberate closure
- **Sad:** Curved arc eyelid overlay (softer than triangular mask), increased tilt (+/-15 degrees), reduced openness (0.6)
- **Frustrated/angry:** Increased tilt (+/-16 degrees) for more aggressive V-brow

**Gaze:** Eyes shift position toward gaze direction. Gaze-proportional eye sizing creates perspective depth -- the eye on the gaze side shrinks (~12% width reduction) while the opposite eye grows, creating a dramatic look effect.

**Glow:** A subtle breathing pulse modulates eye brightness. Speaking amplitude boosts the glow intensity.

### Cube — `display/characters/cube.py`

The original isometric cube mascot. A dark charcoal rounded cube with glowing cyan/teal accent lines on edges, semi-transparent glass quality, isometric 2.5D flat style.

**Face:**
- **Eyes:** Large expressive ovals, ~40% of face width, with glossy highlights and pupil tracking
- **Mouth:** Simple arc/line below eyes, scales from closed to open oval
- **Body:** Isometric cube with edge shimmer idle animation

### BMO — `display/characters/bmo.py`

Adventure Time BMO character with pixel game idle quirks, CRT glitch effects, and speaker vibration.

### Scale
The character should fill most of the 240x280 screen, with ~20px padding on sides and 60px reserved for the status bar at the top. Effective character area: ~200x200px.

## Expression System

Each expression is defined by three config objects in `shared/expressions.yaml`. Per-eye overrides (`leftEye`/`rightEye`) and `eyeColorOverride` are also supported for asymmetric or tinted expressions. See [Design System](design-system.md) for full details on config properties, styles, and how to add new moods.

### EyeConfig
- `openness` (0.0 closed -> 1.0 fully open)
- `width` / `height` (scale factors)
- `pupil_size` (relative to eye)
- `gaze_x` / `gaze_y` (-1.0 to 1.0)
- `blink_rate` (blinks per ~10 seconds)
- `squint` (0.0 none -> 1.0 full)

### MouthConfig
- `openness` (0.0 closed -> 1.0 wide open)
- `smile` (-1.0 frown -> 0.0 neutral -> 1.0 smile)
- `width` (scale factor)

### BodyConfig
- `bounce_speed` / `bounce_amount` (idle animation)
- `tilt` (degrees, -15 to 15)
- `scale` (1.0 normal, 1.03 "leaning in")

## Mood States (16 moods)

| Mood | Personality | Icon | When |
|------|-------------|------|------|
| **Neutral** | Calm, present, gentle smile | -- | Default idle |
| **Happy** | Squint-smile, bouncy | heart | Positive response, greeting |
| **Curious** | Wide eyes, head tilt, leaning in | ? | Processing interesting input |
| **Thinking** | Asymmetric brow raise, gaze up-left | brain + cog | Waiting for AI response |
| **Confused** | Asymmetric eyes, rapid blinks, tilted | ??? | Error recovery, unclear input |
| **Excited** | Wide everything, very bouncy | !! | Great news, achievement |
| **Sleepy** | Half-closed eyes, slow breathing | z z Z | Idle timeout approaching |
| **Error** | X_X eyes, flat mouth | ?! | Connection failure, API error |
| **Listening** | Wide, focused, slightly forward | ))) | Recording audio input |
| **Sad** | Droopy tilted brows, downward gaze, frown | tear | Negative sentiment, apology |
| **Surprised** | Very wide tall eyes, O-mouth | ! | Unexpected input |
| **Focused** | Narrowed squinting eyes, still body | dots | Deep processing, long task |
| **Frustrated** | Angry V-brows, squint, frown | # | Repeated errors, user frustration |
| **Working** | Slightly narrowed eyes, calm, downward gaze | cog | Background task in progress |
| **Low Battery** | Droopy amber eyes, slight frown, leaning | battery | Battery below warning threshold |
| **Critical Battery** | Very droopy dim-amber eyes, deep frown | battery | Battery critically low |

## Animation Principles

1. **Always moving** — even in "idle," Voxel breathes (subtle vertical bounce), occasionally blinks, and slowly drifts gaze.

2. **Smooth transitions** — mood changes lerp over ~300ms. No instant jumps.

3. **Anticipation** — before a big expression change, a brief opposite motion (e.g., slight squint before eyes go wide).

4. **Personality over accuracy** — the goal is charm, not realism. Exaggerate expressions.

5. **Audio-reactive mouth** — during speech, mouth openness maps to audio RMS amplitude. 4-6 distinct mouth shapes is enough (closed, slightly open, medium, wide, O-shape).

## Rendering Approach

The production renderer is the **PIL display service** (`display/`). PIL renders frames in Python and pushes them to the SPI LCD on the Pi, or to a tkinter preview window on desktop. The **React + Framer Motion** app (`app/`) is a browser-based dev UI for rapid expression/style iteration, not used in production on the Pi.

**Pygame fallback** (archived in `_legacy/face/`) was used for early prototyping. It used a sprite-based approach with pre-rendered PNG sequences.

## Animation System

The PIL renderer includes several animation subsystems (`display/animation.py`) that run at the frame level:

### BreathingState
Organic scale oscillation applied to body scale before passing to character renderers. All characters benefit automatically without implementing their own breathing logic. The breathing modulates `body.scale` in the expression config.

### GazeDrift (Saccadic Eye Movement)
Realistic eye movement using saccadic jumps (fast target changes) interspersed with slow drifts. Enhanced with pink noise microsaccadic jitter during fixation -- subtle involuntary eye tremor that prevents the "dead stare" look. The jitter follows a 1/f power spectrum via a leaky integrator, producing correlated noise that is neither too jittery (white noise) nor too mechanical (sinusoidal).

### BlinkState (Asymmetric Blinks + Clustering)
Delta-time based animation (frame-rate independent, 150ms wall-clock duration regardless of FPS). Uses asymmetric timing inspired by Disney/Pixar research: eyelids close in 28% of the blink duration (~42ms, fast snap) and open in 72% (~108ms, gentle ease). This creates the natural "alive" quality seen in high-quality animation.

Blink clustering mimics real human patterns: 35% probability of starting a cluster after any blink, with 1-2 extra blinks per cluster at 150-350ms intervals. Between clusters, a longer 3-8s pause (scaled by the mood's blink rate).

### Character Idle Quirks
Each character implements unique idle animations:
- **Cube:** Edge shimmer — a traveling glow effect along the cube's accent lines
- **BMO:** Pixel game on the screen area, CRT glitch effects, cursor blink, button glow + speaker vibration

### Speaking Reactions
Characters respond to speech amplitude with visual feedback:
- **Cube:** Scale pulse, edge glow intensity, eye glow
- **BMO:** Screen brightness modulation, speaker vibration

### Mood-Specific Tweaks
Characters apply extra animation based on the current mood:
- **Excited:** Extra bounce amplitude
- **Thinking:** Tilt oscillation (cube), spinner on screen (BMO)
- **Error:** Screen shake (cube), static effect (BMO)
- **Happy:** Hearts on screen (BMO)
- **Sleepy:** Dimmed screen (BMO)

### Expression Modifiers

Per-mood animation behaviors are now data-driven via `display/modifiers.py` instead of hardcoded in character draw methods. Modifiers are configured in `shared/expressions.yaml` under a `modifiers:` key and applied at render time.

Available modifiers:
- **bounce_boost** — Multiply bounce amplitude (used by excited: `factor: 1.4`)
- **tilt_oscillation** — Sinusoidal tilt variation (thinking: `speed: 0.8, amount: 2.5`)
- **eye_swap** — Periodic big/small eye swap with gaze-driven lateral shift (thinking: `cycle: 7.0, gaze_influence: 0.1`)
- **shake** — Random position jitter (error: `range: 2`)
- **squint_pulse** — Slow squint modulation (available for focused)
- **gaze_wander** — Lateral gaze drift (surprised_by_sound: `speed: 0.6`)

Characters call `apply_modifiers(expr, expr.modifiers, now)` which returns an overrides dict (`bounce_factor`, `extra_tilt`, `gaze_x_offset`, `swap_blend`, `shake_x/y`). Adding a new behavior: write the function in `modifiers.py`, register it, and reference it in YAML.

Expressions also support composition via `extends: <mood>` and `blend: {<mood>: <weight>}`, enabling compound expressions like `surprised_by_sound = surprised + 35% curious`.

## Mood Decorations

Per-mood decorative sub-animations rendered as overlays using RGBA compositing (`display/decorations.py`). These are drawn on top of the character and positioned relative to the character's actual face center (stored in `_last_face_cx`/`_last_face_cy` during `draw()`).

| Mood | Decoration | Description |
|------|-----------|-------------|
| happy | sparkles + blush | Floating sparkle particles + pink blush circles on cheeks |
| excited | sparkles | Dense floating sparkle particles |
| frustrated | sweat drops | Animated sweat drops near forehead |
| sleepy | ZZZs | Floating Z characters drifting upward |
| sad | tears | Tear drops below eyes |
| surprised | "!" | Flash-in exclamation mark |
| thinking | dots | Animated thinking dots (ellipsis) |

Key design decision: decorations use the character's face center rather than a fixed screen position, so they work correctly with any character (cube, BMO, future characters) regardless of where the face is drawn.

## Demo Mode

A showcase mode (`display/demo.py`) that auto-cycles through moods, characters, and face styles. Useful for trade shows, retail displays, or development review.

**Config settings** (under `character` section in `config/default.yaml`):
- `demo_mode: false` — enable/disable
- `demo_cycle_speed: 5` — seconds between mood changes
- `demo_include_characters: true` — cycle through characters
- `demo_include_styles: true` — cycle through face styles

When active, demo mode forces IDLE state and face view. The DemoController is integrated into the renderer loop and runs before mood resolution.

## Boot Animation

The display service plays a ~3-second "wake up" animation on startup, before entering the main render loop. The animation runs after the terminal-style boot splash and transitions seamlessly into the live face.

### Sequence

| Phase | Time | Description |
|-------|------|-------------|
| **Glow pulse** | 0-0.5s | Screen dark, a faint cyan glow pulse fades in at center -- the "soul" powering on |
| **Bars appear** | 0.5-1.0s | Two closed-eye bars (flat bars with filleted ends, matching the voxel.py closed-eye style) fade in close together at screen center |
| **Bars slide apart** | 1.0-1.5s | Bars slide outward to final eye positions (EYE_SPACING apart) using ease-out deceleration |
| **Eyes blink open** | 1.5-2.3s | Left eye blinks open first (~200ms), right eye follows ~150ms later. Uses asymmetric timing (fast close 28%, slow open 72%) matching the BlinkState animation research |
| **Look around** | 2.3-2.8s | Brief gaze drift left then right (curious look-around) with perspective eye sizing, then settle to center |
| **Settle** | 2.8-3.0s | Eyes reach full openness, gaze centered. Animation complete, hand off to main render loop |

### Configuration

- `character.boot_animation: true` (default) -- set to `false` to skip the animation and go straight to the main render loop
- The animation uses the configured `character.accent_color` for eye and glow colors
- Targets the configured `display.fps` (default 30) during animation
- Works on both Pi (SPI backend) and desktop (tkinter/pygame backend)

### Gateway Greeting

After the boot animation completes and the WebSocket connects to the backend, the server can optionally request a short greeting from the AI agent:

- The server sends a context prompt to the gateway: "You just woke up. Give a very brief greeting (under 10 words) appropriate for {time_of_day}. Be in character."
- The response is rendered as a fade-in/fade-out text overlay below the eyes on the display (0.5s fade in, 2s hold, 1s fade out)
- Color matches the accent color at 70% alpha
- If the gateway is unreachable, the greeting is silently skipped

**Config:**
- `character.greeting_enabled: true` -- enable/disable the gateway greeting
- `character.greeting_prompt: "..."` -- customize the prompt sent to the agent

## Concept Art Reference

See `assets/character/` for concept explorations:
- `concept-01-cube-mascot.png` — character design
- `concept-02-expressions.png` — expression sheet
- `concept-03-ui-mockup.png` — UI mockup (selected direction ✅)
