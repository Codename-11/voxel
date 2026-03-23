# Design System

The Voxel design system has two layers:

1. **Design workspace** (`design/`) -- A React + Tailwind + Framer Motion app for rapid visual prototyping on desktop. Runs in-browser at 240x280 to match the physical display.
2. **Pygame renderer** (`face/`) -- The production renderer that runs on the Raspberry Pi, reading from the same expression data translated into Python dataclasses.

Both layers share the same expression/mood model: eyes, mouth, and body configs per mood. The design workspace is where you iterate on expressions and styles visually; the pygame renderer is what ships on hardware.

## Running the Design Workspace

```bash
cd design && npm install && npm run dev
```

Opens at http://localhost:5173. The UI shows:

- A **device frame** (240x280, actual pixel size) with the animated cube
- **Style buttons** to switch between face styles
- **Mood buttons** to cycle through all 16 moods
- A **speaking toggle** to simulate mouth animation

Tech stack: React 19, Framer Motion 12, Tailwind CSS 4, Vite 8.

## Expression System

Defined in `design/src/expressions.js`. Each mood is an object with three required config blocks:

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

```js
thinking: {
  eyes: { openness: 0.75, gazeX: 0.4, gazeY: -0.2, ... },
  leftEye: { openness: 0.9, height: 1.05 },   // raised eyebrow
  rightEye: { openness: 0.45, height: 0.65 },  // squinting
  ...
}
```

Used by: `thinking` (raised eyebrow), `confused` (asymmetric sizing), `sad` (tilted brows), `frustrated` (angry V-brows).

### Eye color overrides

A mood can set `eyeColorOverride` to change eye fill color. The override replaces the style's default `fillColor` and derives a matching glow.

```js
lowBattery: {
  ...
  eyeColorOverride: "#d4a020",  // amber/yellow
}
```

Used by: `lowBattery` (amber), `criticalBattery` (dim amber).

## Style System

Defined in `design/src/styles.js`. Three face styles, each defining how eyes and mouth render:

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

Each style defines:

```
eye:   { type, baseWidth, baseHeight, fillColor, glowColor, borderRadius, closedRadius, ... }
mouth: { type, baseWidth, strokeWidth, color, ... }
xEye:  { color, thickness, size }   // X_X error state rendering
```

## Mood Icons

Floating icons appear beside the cube to reinforce certain moods. Defined in the `MoodEffects` component in `VoxelCube.jsx`.

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

## Design to Pygame Pipeline

The JS expression data in `design/src/expressions.js` maps to Python dataclasses in `face/expressions.py`:

| JS (design workspace)         | Python (pygame renderer)           |
|-------------------------------|------------------------------------|
| `EXPRESSIONS.neutral`         | `EXPRESSIONS[Mood.NEUTRAL]`        |
| `eyes.pupilSize`              | `EyeConfig.pupil_size`             |
| `eyes.gazeX` / `gazeY`       | `EyeConfig.gaze_x` / `gaze_y`     |
| `eyes.blinkRate`              | `EyeConfig.blink_rate`             |
| `mouth.openness`              | `MouthConfig.openness`             |
| `body.bounceSpeed`            | `BodyConfig.bounce_speed`          |
| `body.bounceAmount`           | `BodyConfig.bounce_amount`         |
| `leftEye` / `rightEye`       | Not yet in Python (planned)        |
| `eyeColorOverride`           | Not yet in Python (planned)        |

The design workspace currently has 16 moods; the Python side has 9. When adding moods in the design workspace, port them to `face/expressions.py` once finalized.

**Workflow:** Iterate in the browser (hot reload, visual feedback) then translate final values to the Python dataclasses. The numbers are the same -- just camelCase to snake_case.

## Adding Content

### Adding a new mood

1. **Define the expression** in `design/src/expressions.js`:
   ```js
   myMood: {
     eyes: { width: 1.0, height: 1.0, openness: 0.9, pupilSize: 0.4, gazeX: 0, gazeY: 0, blinkRate: 3.0, squint: 0 },
     mouth: { openness: 0, smile: 0.3, width: 1.0 },
     body: { bounceSpeed: 0.3, bounceAmount: 2, tilt: 0, scale: 1.0 },
   },
   ```
   Add `leftEye`/`rightEye` overrides if you need asymmetric eyes. Add `eyeColorOverride` if you need a different eye color.

2. **Add a mood icon** (optional) in the `MoodEffects` component in `design/src/components/VoxelCube.jsx`. Style it in `VoxelCube.css`.

3. **Test in browser** -- `npm run dev`, click through all styles to verify the mood looks correct in kawaii, retro, and minimal.

4. **Port to Python** -- Add the mood to the `Mood` enum and `EXPRESSIONS` dict in `face/expressions.py`:
   ```python
   Mood.MY_MOOD: Expression(
       mood=Mood.MY_MOOD,
       eyes=EyeConfig(openness=0.9, blink_rate=3.0),
       mouth=MouthConfig(smile=0.3),
       body=BodyConfig(bounce_speed=0.3, bounce_amount=2.0),
   ),
   ```

### Adding a new face style

1. **Define the style** in `design/src/styles.js`:
   ```js
   myStyle: {
     name: "My Style",
     description: "Short description of the visual style",
     eye: { type: "roundrect", baseWidth: 30, baseHeight: 38, fillColor: "#f0f0f0", ... },
     mouth: { type: "offset", baseWidth: 30, strokeWidth: 3, color: "#f0f0f0" },
     xEye: { color: "var(--vx-error)", thickness: 3, size: 22 },
   },
   ```

2. **If using a new eye/mouth type**, add rendering logic in the `Eye` or `Mouth` components in `VoxelCube.jsx`.

3. **Test** across all 16 moods in the browser to make sure every expression renders correctly with the new style.

Available eye types: `roundrect`, `iris`, `dot`. Available mouth types: `offset`, `teeth`, `arc`.
