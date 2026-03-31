# Design System

The Voxel design system uses a **shared YAML data layer** with a **PIL renderer** as the production display engine.

1. **Shared data** (`shared/`) — YAML files defining expressions, styles, and mood metadata. Single source of truth for both Python and React.
2. **PIL renderer** (`display/`) — Production renderer for Pi hardware. Renders frames with PIL, pushes to SPI LCD via the WhisPlay driver. Also runs in a tkinter preview window on desktop for development.
3. **React renderer** (`app/`) — Browser-based dev UI with Framer Motion animations. Useful for rapid expression/style iteration with HMR. Not used in production on the Pi. The old pygame renderer is archived in `_legacy/face/`.

## Running the App

```bash
# Full stack (backend + frontend)
run_dev_windows.bat   # Windows
./run.sh              # macOS / Linux

# Frontend only (standalone, no backend needed)
cd app && npm install && npm run dev
```

Opens at http://localhost:5173. The UI shows:

- A **device frame** (240x280, actual pixel size) with the animated cube
- A **status bar** at the bottom with version, state, and connectivity
- A **dev panel** (toggle with backtick key) for style/mood/speaking controls

When the Python backend is running (`uv run server.py`), the app connects via WebSocket and uses server-driven state. Without the backend, it falls back to local state with the dev panel auto-shown.

Tech stack: React 19, Framer Motion 12, Tailwind CSS 4, Vite 8.

## Expression System

Defined in `shared/expressions.yaml`. Each mood is an object with three required config blocks.

> **Note:** YAML source uses `snake_case` keys (`pupil_size`, `bounce_speed`). The JS YAML loader auto-converts to `camelCase` for React. Properties below are shown in camelCase (as used in components).

### EyeConfig (`eyes`)

| Property    | Range         | Description                    |
|-------------|---------------|--------------------------------|
| `width`     | 0.0 -- 1.5   | Horizontal scale factor        |
| `height`    | 0.0 -- 1.5   | Vertical scale factor          |
| `openness`  | 0.0 -- 1.0   | 0 = closed, 1 = fully open    |
| `pupilSize` | 0.0 -- 1.0   | Relative to eye size           |
| `gazeX`     | -1.0 -- 1.0  | Left/right gaze direction      |
| `gazeY`     | -1.0 -- 1.0  | Up (-1) / down (+1) gaze       |
| `blinkRate` | 0.0 -- 5.0   | Blinks per ~10 seconds         |
| `squint`    | 0.0 -- 1.0   | Eyelid droop amount            |

### MouthConfig (`mouth`)

| Property   | Range         | Description                        |
|------------|---------------|------------------------------------|
| `openness` | 0.0 -- 1.0   | 0 = closed, 1 = wide open         |
| `smile`    | -1.0 -- 1.0  | Negative = frown, positive = smile |
| `width`    | 0.0 -- 2.0   | Horizontal scale factor            |

### BodyConfig (`body`)

| Property       | Range          | Description                       |
|----------------|----------------|-----------------------------------|
| `bounceSpeed`  | 0.0 -- 2.0    | Idle bounce animation speed       |
| `bounceAmount` | 0 -- 10       | Pixels of vertical bounce         |
| `tilt`         | -20 -- 20     | Degrees of rotation               |
| `scale`        | 0.9 -- 1.1    | Body scale (1.03 = "leaning in")  |

### Per-eye overrides

Any mood can include `leftEye` and/or `rightEye` objects that override specific base `eyes` properties for that eye only. This creates asymmetric expressions.

```yaml
thinking:
  eyes: { openness: 0.75, gazeX: 0.4, gazeY: -0.2, ... }
  leftEye: { openness: 0.9, height: 1.05 }   # raised eyebrow
  rightEye: { openness: 0.45, height: 0.65 }  # squinting
```

Used by: `thinking` (raised eyebrow), `confused` (asymmetric sizing), `sad` (tilted brows), `frustrated` (angry V-brows).

### Eye color overrides

A mood can set `eyeColorOverride` to change eye fill color. The override replaces the style's default `fillColor` and derives a matching glow.

```yaml
lowBattery:
  eyeColorOverride: "#d4a020"  # amber/yellow
```

Used by: `lowBattery` (amber), `criticalBattery` (dim amber).

## Style System

Defined in `shared/styles.yaml`. Three face styles, each defining how eyes and mouth render.

### Kawaii (default)

- **Eye type:** `roundrect` -- white rounded rectangles, no iris/pupil detail
- **Mouth type:** `offset` -- small centered SVG curve, minimal
- Soft, modern companion aesthetic

### Retro

- **Eye type:** `iris` -- white sclera + dark iris + glossy highlight dot
- **Mouth type:** `teeth` -- wide grin with individual tooth elements when smiling/speaking
- Expressive, Fallout/Cuphead-inspired

### Minimal

- **Eye type:** `dot` -- tiny cyan circles
- **Mouth type:** `arc` -- simple SVG arc/line
- Lo-fi pixel art feel, uses `var(--vx-cyan)` instead of white

### Style config shape

Each style defines (in `shared/styles.yaml`):

```
eye:   { type, baseWidth, baseHeight, fillColor, glowColor, borderRadius, closedRadius, ... }
mouth: { type, baseWidth, strokeWidth, color, ... }
xEye:  { color, thickness, size }   // X_X error state rendering
```

## Mood Icons

Floating icons appear beside the cube to reinforce certain moods. Defined in `shared/moods.yaml` (icon metadata) and rendered by `MoodEffects` in `app/src/components/VoxelCube.jsx`.

| Mood             | Icon     | Description                                |
|------------------|----------|--------------------------------------------|
| sleepy           | z z Z    | Floating upward, staggered fade            |
| happy            | heart    | Pulsing pink heart                         |
| thinking         | brain+cog | Brain bobbing, cog spinning               |
| curious          | ?        | Bouncing question mark                     |
| confused         | ???      | Pulsing triple question marks              |
| excited          | !!       | Shaking double exclamation                 |
| listening        | )))      | Pulsing sound waves                        |
| sad              | tear     | Slow-drifting tear symbol                  |
| surprised        | !        | Flash-in exclamation                       |
| focused          | dots     | Pulsing ellipsis                           |
| working          | cog      | Spinning gear                              |
| frustrated       | #        | Shaking anger symbol                       |
| error            | ?!       | Pulsing interrobang                        |
| lowBattery       | battery  | SVG battery icon, slow pulse               |
| criticalBattery  | battery  | SVG battery icon, fast pulse, lower fill   |

`neutral` has no floating icon.

## All 16 Moods

| Mood              | Visual Description                                        | Icon        | When Used                              |
|-------------------|-----------------------------------------------------------|-------------|----------------------------------------|
| **neutral**       | Calm open eyes, gentle smile, slow breathing bounce       | --          | Default idle state                     |
| **happy**         | Squint-smile eyes, wide U-mouth, bouncy body              | heart       | Positive response, greeting            |
| **curious**       | Wide eyes, head tilt, leaning forward                     | ?           | Processing interesting input           |
| **thinking**      | Asymmetric brow raise, gaze up-left, slight tilt          | brain + cog | Waiting for AI response                |
| **confused**      | Asymmetric eye sizes, rapid blinks, head tilt             | ???         | Unclear input, parse failure           |
| **excited**       | Wide-open everything, big smile, fast bounce              | !!          | Great news, achievements               |
| **sleepy**        | Half-closed droopy eyes, no smile, slow sway              | z z Z       | Idle timeout approaching               |
| **error**         | X_X eyes, flat red mouth, no movement                     | ?!          | Connection failure, API error          |
| **listening**     | Wide focused eyes, slight lean forward, open mouth        | )))         | Recording audio input                  |
| **sad**           | Droopy tilted brows, downward gaze, frown, shrunk body    | tear        | Negative sentiment, apology            |
| **surprised**     | Very wide tall eyes, small pupil, O-mouth, slight scale up| !           | Unexpected input                       |
| **focused**       | Narrowed squinting eyes, neutral mouth, still body        | dots        | Deep processing, long task             |
| **frustrated**    | Angry V-brows, squint, frown, tense                       | #           | Repeated errors, user frustration      |
| **working**       | Slightly narrowed eyes, downward gaze, calm               | cog         | Background task in progress            |
| **lowBattery**    | Droopy amber eyes, slight frown, leaning, shrunk          | battery     | Battery below warning threshold        |
| **criticalBattery** | Very droopy dim-amber eyes, strong lean, deep frown     | battery     | Battery critically low                 |

## Adding Content

### Adding a new mood

1. **Define the expression** in `shared/expressions.yaml`:
   ```yaml
   myMood:
     eyes:
       width: 1.0
       height: 1.0
       openness: 0.9
       pupilSize: 0.4
       gazeX: 0
       gazeY: 0
       blinkRate: 3.0
       squint: 0
     mouth:
       openness: 0
       smile: 0.3
       width: 1.0
     body:
       bounceSpeed: 0.3
       bounceAmount: 2
       tilt: 0
       scale: 1.0
   ```
   Add `leftEye`/`rightEye` overrides if you need asymmetric eyes. Add `eyeColorOverride` if you need a different eye color.

2. **Add a mood icon** (optional) in `shared/moods.yaml` under `icons:`. Also add the rendering animation in `MoodEffects` in `app/src/components/VoxelCube.jsx` and style it in `VoxelCube.css`.

3. **Test in browser** — `npm run dev`, click through all styles to verify the mood looks correct in kawaii, retro, and minimal.

4. **Test in PIL renderer** — `uv run dev`, verify the mood renders correctly in the tkinter preview window.

### Adding a new face style

1. **Define the style** in `shared/styles.yaml`:
   ```yaml
   myStyle:
     name: "My Style"
     description: "Short description of the visual style"
     eye:
       type: roundrect
       baseWidth: 30
       baseHeight: 38
       fillColor: "#f0f0f0"
       # ... other eye properties
     mouth:
       type: offset
       baseWidth: 30
       strokeWidth: 3
       color: "#f0f0f0"
     xEye:
       color: "var(--vx-error)"
       thickness: 3
       size: 22
   ```

2. **If using a new eye/mouth type**, add rendering logic in the `Eye` or `Mouth` components in `app/src/components/VoxelCube.jsx`.

3. **Test** across all 16 moods in the browser to make sure every expression renders correctly with the new style.

Available eye types: `roundrect`, `iris`, `dot`. Available mouth types: `offset`, `teeth`, `arc`.

## Shared YAML → React Pipeline

React loads shared YAML at build/dev time via Vite raw imports:

```
shared/expressions.yaml  →  app/src/load-shared.js  →  app/src/expressions.js
shared/styles.yaml       →  app/src/load-shared.js  →  app/src/styles.js
```

Vite watches `shared/` and triggers HMR on changes, so edits to YAML files are reflected in the browser instantly.

## Mood Decorations

Per-mood decorative overlays are rendered by `display/decorations.py` using RGBA compositing. They are drawn after the character and positioned relative to the character's actual face center, not a fixed screen coordinate.

**Position reference:** Each character stores its face center in `_last_face_cx` and `_last_face_cy` (defined in the `Character` base class in `display/characters/base.py`) during its `draw()` call. The decoration system reads these values to place sparkles, tears, sweat drops, etc. in the correct position for any character.

**Available decorations:** sparkles (happy/excited), sweat drops (frustrated), ZZZs (sleepy), tears (sad), "!" (surprised), blush circles (happy), thinking dots. See [Character Design](character-design.md) for the full decoration table.

The renderer (`display/renderer.py`) calls decorations after the character draw pass, compositing the decoration overlay onto the frame.

## Shared YAML → Python Pipeline

Python loads shared YAML at startup via `shared/__init__.py`:

```
shared/expressions.yaml  →  shared/__init__.py  →  load_expressions()
shared/styles.yaml       →  shared/__init__.py  →  load_styles()
shared/moods.yaml        →  shared/__init__.py  →  load_moods()
```

The PIL display renderer reads expressions directly from `shared/expressions.yaml`. `server.py` reads `moods.yaml` for state-to-mood mapping and LED behavior.
