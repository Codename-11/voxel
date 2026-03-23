# Character Design — Voxel

> For the interactive design workspace, face styles, and the design-to-pygame pipeline, see [Design System](design-system.md).

## Identity

**Voxel** is the name of both the project and the character. The character is the soul of the device — it's what makes this a companion, not just a voice assistant.

## Visual Design

### Shape
- **Rounded cube** — isometric 2.5D flat style
- Not a perfect cube — slightly rounded edges, soft corners
- Semi-transparent glass-like quality to the body

### Color
- **Body:** Dark charcoal (#1a1a2e to #2d2d44)
- **Accents:** Glowing cyan/teal (#00d4ff) edge lines
- **Eyes:** White/cyan with glossy highlights
- **Background:** Deep dark (#0a0a0f)

### Face
- **Eyes:** Large expressive ovals, ~40% of face width
- Glossy highlight circles in upper-right of each eye
- Pupils that track gaze direction
- Eyelids for blinks and squints
- **Mouth:** Simple arc/line below eyes
- Scales from closed line to open oval
- Width changes with smile/frown amount

### Scale
The character should fill most of the 240×280 screen, with ~20px padding on sides and ~40px reserved for status bar at bottom. Effective character area: ~200×220px.

## Expression System

Each expression is defined by three config objects. Per-eye overrides (`leftEye`/`rightEye`) and `eyeColorOverride` are also supported for asymmetric or tinted expressions. See [Design System](design-system.md) for full details on config properties, styles, and the design-to-pygame pipeline.

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

## Sprite Sheet Approach

Each mood state gets a sprite sheet:
- **Idle loop:** 24 frames at 30fps = 0.8 second loop
- **Transition frames:** 8 frames between moods
- **Mouth overlay:** 6 mouth shapes rendered separately, composited at runtime based on audio amplitude

Sprites are pre-rendered in an external tool (Blender, Figma, or After Effects) and exported as PNG sequences to `face/sprites/`.

## Concept Art Reference

See `assets/character/` for concept explorations:
- `concept-01-cube-mascot.png` — character design
- `concept-02-expressions.png` — expression sheet
- `concept-03-ui-mockup.png` — UI mockup (selected direction ✅)
