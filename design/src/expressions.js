/**
 * Expression definitions — mirrors face/expressions.py
 * Each mood defines eyes, mouth, and body configs.
 */

export const EXPRESSIONS = {
  neutral: {
    eyes: { width: 1.0, height: 1.0, openness: 0.9, pupilSize: 0.4, gazeX: 0, gazeY: 0, blinkRate: 3.0, squint: 0 },
    mouth: { openness: 0, smile: 0.3, width: 1.0 },
    body: { bounceSpeed: 0.3, bounceAmount: 2, tilt: 0, scale: 1.0 },
  },
  happy: {
    eyes: { width: 1.05, height: 0.75, openness: 0.7, pupilSize: 0.4, gazeX: 0, gazeY: 0, blinkRate: 2.0, squint: 0 },
    // Happy squint — both eyes narrow, big U smile (closed mouth, high smile value)
    mouth: { openness: 0, smile: 1.0, width: 1.3 },
    body: { bounceSpeed: 0.7, bounceAmount: 4, tilt: 0, scale: 1.0 },
  },
  curious: {
    eyes: { width: 1.1, height: 1.1, openness: 1.0, pupilSize: 0.5, gazeX: 0, gazeY: 0, blinkRate: 1.5, squint: 0 },
    mouth: { openness: 0.15, smile: 0.1, width: 1.0 },
    body: { bounceSpeed: 0.4, bounceAmount: 2, tilt: 8, scale: 1.02 },
  },
  thinking: {
    eyes: { width: 1.0, height: 1.0, openness: 0.75, pupilSize: 0.35, gazeX: 0.4, gazeY: -0.2, blinkRate: 1.0, squint: 0 },
    // Gentle raised eyebrow — left open, right slightly narrower
    leftEye: { openness: 0.9, height: 1.05 },
    rightEye: { openness: 0.45, height: 0.65 },
    mouth: { openness: 0, smile: 0.0, width: 0.85 },
    body: { bounceSpeed: 0.2, bounceAmount: 1, tilt: -4, scale: 1.0 },
  },
  confused: {
    eyes: { width: 1.0, height: 1.0, openness: 0.9, pupilSize: 0.35, gazeX: 0, gazeY: 0, blinkRate: 4.0, squint: 0 },
    // Subtle asymmetry — one eye slightly bigger
    leftEye: { openness: 1.0, height: 1.08 },
    rightEye: { openness: 0.7, height: 0.85 },
    mouth: { openness: 0, smile: -0.15, width: 0.9 },
    body: { bounceSpeed: 0.3, bounceAmount: 2, tilt: 8, scale: 1.0 },
  },
  excited: {
    eyes: { width: 1.15, height: 1.15, openness: 1.0, pupilSize: 0.5, gazeX: 0, gazeY: 0, blinkRate: 2.0, squint: 0 },
    mouth: { openness: 0.4, smile: 1.0, width: 1.0 },
    body: { bounceSpeed: 1.2, bounceAmount: 6, tilt: 0, scale: 1.0 },
  },
  sleepy: {
    eyes: { width: 1.0, height: 0.7, openness: 0.25, pupilSize: 0.4, gazeX: 0, gazeY: 0.2, blinkRate: 0.5, squint: 0 },
    mouth: { openness: 0, smile: 0.0, width: 1.0 },
    body: { bounceSpeed: 0.15, bounceAmount: 1, tilt: 3, scale: 1.0 },
  },
  error: {
    eyes: { width: 1.0, height: 1.0, openness: 1.0, pupilSize: 0, gazeX: 0, gazeY: 0, blinkRate: 0, squint: 0 },
    mouth: { openness: 0, smile: -0.5, width: 1.0 },
    body: { bounceSpeed: 0, bounceAmount: 0, tilt: 0, scale: 1.0 },
  },
  listening: {
    eyes: { width: 1.05, height: 1.05, openness: 1.0, pupilSize: 0.45, gazeX: 0, gazeY: 0, blinkRate: 1.0, squint: 0 },
    mouth: { openness: 0.1, smile: 0.15, width: 1.0 },
    body: { bounceSpeed: 0.4, bounceAmount: 2, tilt: 2, scale: 1.03 },
  },
  sad: {
    eyes: { width: 0.95, height: 0.9, openness: 0.7, pupilSize: 0.4, gazeX: 0, gazeY: 0.3, blinkRate: 1.0, squint: 0 },
    leftEye: { tilt: -6 },
    rightEye: { tilt: 6 },
    mouth: { openness: 0, smile: -0.5, width: 0.9 },
    body: { bounceSpeed: 0.1, bounceAmount: 0.5, tilt: 3, scale: 0.98 },
  },
  surprised: {
    eyes: { width: 1.2, height: 1.25, openness: 1.0, pupilSize: 0.35, gazeX: 0, gazeY: 0, blinkRate: 0.5, squint: 0 },
    mouth: { openness: 0.5, smile: 0.0, width: 0.7 },
    body: { bounceSpeed: 0.5, bounceAmount: 3, tilt: 0, scale: 1.04 },
  },
  focused: {
    eyes: { width: 1.0, height: 0.7, openness: 0.65, pupilSize: 0.4, gazeX: 0, gazeY: 0, blinkRate: 0.8, squint: 0.15 },
    mouth: { openness: 0, smile: 0.0, width: 0.8 },
    body: { bounceSpeed: 0.15, bounceAmount: 0.5, tilt: 0, scale: 1.0 },
  },
  frustrated: {
    eyes: { width: 1.0, height: 0.8, openness: 0.75, pupilSize: 0.4, gazeX: 0, gazeY: 0, blinkRate: 1.5, squint: 0.2 },
    // Angry V-shaped — inner edges tilted down
    leftEye: { tilt: -12 },
    rightEye: { tilt: 12 },
    mouth: { openness: 0, smile: -0.5, width: 0.85 },
    body: { bounceSpeed: 0.3, bounceAmount: 1, tilt: 0, scale: 1.0 },
  },
  working: {
    eyes: { width: 1.0, height: 0.8, openness: 0.7, pupilSize: 0.4, gazeX: 0, gazeY: 0.1, blinkRate: 0.8, squint: 0.1 },
    mouth: { openness: 0, smile: 0.1, width: 0.85 },
    body: { bounceSpeed: 0.25, bounceAmount: 1, tilt: 0, scale: 1.0 },
  },
  lowBattery: {
    eyes: { width: 0.9, height: 0.8, openness: 0.5, pupilSize: 0.35, gazeX: 0, gazeY: 0.3, blinkRate: 0.8, squint: 0.1 },
    mouth: { openness: 0, smile: -0.2, width: 0.8 },
    body: { bounceSpeed: 0.1, bounceAmount: 0.5, tilt: 8, scale: 0.97 },
    eyeColorOverride: "#d4a020",  // amber/yellow dim
  },
  criticalBattery: {
    eyes: { width: 0.85, height: 0.7, openness: 0.3, pupilSize: 0.3, gazeX: 0, gazeY: 0.4, blinkRate: 0.3, squint: 0.15 },
    mouth: { openness: 0, smile: -0.4, width: 0.7 },
    body: { bounceSpeed: 0.05, bounceAmount: 0.3, tilt: 14, scale: 0.95 },
    eyeColorOverride: "#a07818",  // dim amber
  },
};

export const MOOD_LIST = Object.keys(EXPRESSIONS);
