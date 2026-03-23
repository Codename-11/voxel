/**
 * Face style themes — each defines how eyes, mouth, and body render.
 * The VoxelCube component reads the active style to determine rendering.
 */

export const STYLES = {
  kawaii: {
    name: "Kawaii",
    description: "White rounded-rect eyes, small offset smile — modern companion style",
    eye: {
      type: "roundrect",     // rounded rectangle, solid white
      baseWidth: 30,
      baseHeight: 38,
      highlightSize: 0,
      highlightColor: "transparent",
      fillColor: "#f0f0f0",
      glowColor: "rgba(240, 240, 240, 0.15)",
      borderRadius: "28%",
      closedRadius: "35% / 50%",
    },
    mouth: {
      type: "offset",        // small centered smile
      baseWidth: 30,
      strokeWidth: 3,
      color: "#f0f0f0",
    },
    xEye: {
      color: "var(--vx-error)",
      thickness: 3,
      size: 22,
    },
  },

  retro: {
    name: "Retro",
    description: "Big expressive eyes with irises, toothy grin — Fallout/Cuphead style",
    eye: {
      type: "iris",          // white sclera + dark iris + highlight
      baseWidth: 36,
      baseHeight: 42,
      highlightSize: 7,
      highlightColor: "rgba(255, 255, 255, 0.9)",
      fillColor: "#f0f0f0",  // white sclera
      irisColor: "#0a0a12",  // dark iris
      irisSize: 0.55,        // relative to eye size
      glowColor: "rgba(255, 255, 255, 0.1)",
      borderRadius: "50%",
      closedRadius: "45% / 50%",
    },
    mouth: {
      type: "teeth",         // wide grin with teeth
      baseWidth: 36,
      strokeWidth: 2,
      color: "#f0f0f0",
      teethColor: "#ffffff",
      lipColor: "var(--vx-body-dark)",
    },
    xEye: {
      color: "var(--vx-error)",
      thickness: 4,
      size: 26,
    },
  },

  minimal: {
    name: "Minimal",
    description: "Tiny dot eyes, dash mouth — lo-fi pixel style",
    eye: {
      type: "dot",           // simple circle dots
      baseWidth: 10,
      baseHeight: 10,
      highlightSize: 0,
      highlightColor: "transparent",
      fillColor: "var(--vx-cyan)",
      glowColor: "rgba(0, 212, 210, 0.4)",
      borderRadius: "50%",
      closedRadius: "50%",
    },
    mouth: {
      type: "arc",
      baseWidth: 18,
      strokeWidth: 2,
      color: "var(--vx-cyan-dim)",
    },
    xEye: {
      color: "var(--vx-error)",
      thickness: 2,
      size: 12,
    },
  },
};

export const STYLE_LIST = Object.keys(STYLES);
export const DEFAULT_STYLE = "kawaii";
