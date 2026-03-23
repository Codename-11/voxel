import { motion, AnimatePresence } from "framer-motion";
import { EXPRESSIONS } from "../expressions";
import { STYLES, DEFAULT_STYLE } from "../styles";
import "./VoxelCube.css";

export default function VoxelCube({ mood = "neutral", speaking = false, styleName = DEFAULT_STYLE }) {
  const expr = EXPRESSIONS[mood] || EXPRESSIONS.neutral;
  const style = STYLES[styleName] || STYLES[DEFAULT_STYLE];

  return (
    <div className="voxel-scene">
      {/* Ambient glow behind the cube */}
      <motion.div
        className="ambient-glow"
        animate={{
          opacity: [0.3, 0.5, 0.3],
          scale: [1, 1.05, 1],
        }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* 3D cube container */}
      <motion.div
        className="cube-wrapper"
        animate={{
          y: [0, -expr.body.bounceAmount, 0],
          rotateZ: expr.body.tilt,
          scale: expr.body.scale,
        }}
        transition={{
          y: {
            duration: 1 / Math.max(expr.body.bounceSpeed, 0.1),
            repeat: Infinity,
            ease: "easeInOut",
          },
          rotateZ: { duration: 0.3, ease: "easeOut" },
          scale: { duration: 0.3, ease: "easeOut" },
        }}
      >
        <div className="cube" style={{ transform: `rotateX(-15deg) rotateY(-25deg)` }}>
          {/* Front face */}
          <div className="cube-face front">
            <div className="face-inner">
              <Eyes expr={expr} mood={mood} style={style} />
              <Mouth expr={expr} mood={mood} speaking={speaking} style={style} />
            </div>
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          {/* Top face */}
          <div className="cube-face top">
            <div className="face-shading top-shade" />
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          {/* Right face */}
          <div className="cube-face right">
            <div className="face-shading right-shade" />
            <div className="edge-glow edge-top" />
            <div className="edge-glow edge-bottom" />
            <div className="edge-glow edge-left" />
            <div className="edge-glow edge-right" />
          </div>

          <div className="cube-face left" />
          <div className="cube-face back" />
          <div className="cube-face bottom" />
        </div>
      </motion.div>

      <MoodEffects mood={mood} />
    </div>
  );
}

/* ── Eyes ─────────────────────────────────────────────────── */

function Eyes({ expr, mood, style }) {
  const { eyes } = expr;
  const s = style.xEye;
  const colorOverride = expr.eyeColorOverride || null;

  // Merge per-eye overrides onto base eyes config
  const leftEyes = expr.leftEye ? { ...eyes, ...expr.leftEye } : eyes;
  const rightEyes = expr.rightEye ? { ...eyes, ...expr.rightEye } : eyes;

  if (mood === "error") {
    return (
      <div className="eyes-row">
        <XEye size={s.size} color={s.color} thickness={s.thickness} />
        <XEye size={s.size} color={s.color} thickness={s.thickness} />
      </div>
    );
  }

  return (
    <div className="eyes-row">
      <Eye eyes={leftEyes} style={style} colorOverride={colorOverride} />
      <Eye eyes={rightEyes} style={style} colorOverride={colorOverride} />
    </div>
  );
}

function Eye({ eyes, style, colorOverride }) {
  const s = style.eye;
  const fillColor = colorOverride || s.fillColor;
  const glowColor = colorOverride ? `${colorOverride}55` : s.glowColor;

  const w = s.baseWidth * eyes.width;
  const h = s.baseHeight * eyes.height * Math.max(eyes.openness, 0.08);
  const radius = eyes.openness < 0.3 ? s.closedRadius : s.borderRadius;

  const tilt = eyes.tilt || 0;

  // Rounded rectangle — modern companion style (default)
  if (s.type === "roundrect") {
    return (
      <motion.div
        className="eye eye--roundrect"
        animate={{
          width: w,
          height: h,
          borderRadius: radius,
          background: fillColor,
          rotate: tilt,
        }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        style={{ boxShadow: `0 0 12px ${glowColor}` }}
      >
        {eyes.squint > 0 && (
          <motion.div
            className="eyelid"
            animate={{ height: `${eyes.squint * 45}%` }}
            transition={{ duration: 0.3 }}
          />
        )}
      </motion.div>
    );
  }

  if (s.type === "dot") {
    return (
      <motion.div
        className="eye eye--dot"
        animate={{ width: w, height: h, borderRadius: radius, background: fillColor }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        style={{ boxShadow: `0 0 8px ${glowColor}` }}
      />
    );
  }

  if (s.type === "iris") {
    return (
      <motion.div
        className="eye eye--iris"
        animate={{ width: w, height: h, borderRadius: radius }}
        transition={{ duration: 0.3, ease: "easeOut" }}
      >
        {/* Sclera — tints with color override */}
        <motion.div
          className="eye-fill"
          animate={{ background: colorOverride ? colorOverride : s.fillColor }}
          transition={{ duration: 0.5 }}
        />

        {/* Dark iris */}
        <motion.div
          className="eye-iris"
          animate={{
            width: Math.min(w, h) * s.irisSize,
            height: Math.min(w, h) * s.irisSize,
            x: eyes.gazeX * 5,
            y: eyes.gazeY * 4,
          }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          style={{ background: s.irisColor }}
        />

        {/* Highlight */}
        {s.highlightSize > 0 && (
          <motion.div
            className="eye-highlight"
            animate={{ opacity: eyes.openness > 0.3 ? 1 : 0 }}
            transition={{ duration: 0.2 }}
            style={{
              width: s.highlightSize,
              height: s.highlightSize,
              background: s.highlightColor,
            }}
          />
        )}

        {eyes.squint > 0 && (
          <motion.div
            className="eyelid"
            animate={{ height: `${eyes.squint * 45}%` }}
            transition={{ duration: 0.3 }}
          />
        )}
      </motion.div>
    );
  }

  // Default: flat kawaii
  return (
    <motion.div
      className="eye eye--flat"
      animate={{ width: w, height: h, borderRadius: radius }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <motion.div
        className="eye-fill"
        animate={{ background: fillColor }}
        transition={{ duration: 0.5 }}
        style={{
          boxShadow: `inset 0 -3px 6px rgba(0, 180, 170, 0.4), 0 0 8px ${glowColor}`,
        }}
      />

      {s.highlightSize > 0 && (
        <motion.div
          className="eye-highlight"
          animate={{ opacity: eyes.openness > 0.3 ? 1 : 0 }}
          transition={{ duration: 0.2 }}
          style={{
            width: s.highlightSize,
            height: s.highlightSize,
            background: s.highlightColor,
          }}
        />
      )}

      {eyes.squint > 0 && (
        <motion.div
          className="eyelid"
          animate={{ height: `${eyes.squint * 45}%` }}
          transition={{ duration: 0.3 }}
        />
      )}
    </motion.div>
  );
}

function XEye({ size = 22, color = "var(--vx-error)", thickness = 3 }) {
  return (
    <div className="x-eye" style={{ width: size + 6, height: size + 6 }}>
      <div
        className="x-line x-line-1"
        style={{ width: size, height: thickness, background: color, boxShadow: `0 0 8px ${color}` }}
      />
      <div
        className="x-line x-line-2"
        style={{ width: size, height: thickness, background: color, boxShadow: `0 0 8px ${color}` }}
      />
    </div>
  );
}

/* ── Mouth ────────────────────────────────────────────────── */

function Mouth({ expr, mood, speaking, style }) {
  const { mouth } = expr;
  const s = style.mouth;

  if (mood === "error") {
    return <div className="mouth-flat" />;
  }

  const openness = speaking ? 0.5 : mouth.openness;

  // Offset mouth — centered below eyes (modern companion)
  if (s.type === "offset") {
    const smile = mouth.smile;
    const w = s.baseWidth * mouth.width;

    // Open mouth — speaking or expressive (like happy openness: 0.3)
    if (openness > 0.15) {
      return (
        <motion.div
          className="mouth-offset"
          animate={{
            width: w * (0.6 + openness * 0.4),
            height: 14 * openness,
          }}
          transition={{ duration: speaking ? 0.08 : 0.3 }}
        >
          <div
            className="mouth-offset-open"
            style={{
              background: s.color,
              borderRadius: smile > 0.5 ? "2px 2px 50% 50%" : "50%",
            }}
          />
        </motion.div>
      );
    }

    // Closed mouth — SVG smile/frown curve
    const curveDepth = smile * 8;
    return (
      <motion.div
        className="mouth-offset"
        animate={{ width: w, height: 14 }}
        transition={{ duration: 0.3 }}
      >
        <svg viewBox="0 0 30 14" className="mouth-svg" overflow="visible">
          <motion.path
            animate={{
              d: smile >= 0
                ? `M 2 5 Q 15 ${5 + curveDepth} 28 5`
                : `M 2 9 Q 15 ${9 + curveDepth} 28 9`,
            }}
            stroke={s.color}
            strokeWidth={s.strokeWidth}
            strokeLinecap="round"
            fill="none"
            transition={{ duration: 0.3 }}
          />
        </svg>
      </motion.div>
    );
  }

  // Teeth-style mouth (retro)
  if (s.type === "teeth") {
    const smile = mouth.smile;

    if (openness > 0.15 || smile > 0.4) {
      const w = s.baseWidth * mouth.width;
      const h = Math.max(14 * Math.max(openness, smile * 0.5), 8);
      return (
        <motion.div
          className="mouth-teeth"
          animate={{ width: w, height: h }}
          transition={{ duration: speaking ? 0.08 : 0.3 }}
        >
          {/* Mouth opening */}
          <div className="mouth-teeth-bg" />
          {/* Teeth row */}
          <div className="mouth-teeth-row">
            {[...Array(Math.max(Math.round(w / 6), 3))].map((_, i) => (
              <div key={i} className="tooth" />
            ))}
          </div>
        </motion.div>
      );
    }

    // Closed retro mouth
    const curveY = smile * 6;
    return (
      <motion.div
        className="mouth-closed"
        animate={{ width: s.baseWidth * mouth.width }}
        transition={{ duration: 0.3 }}
      >
        <svg viewBox="0 0 36 12" className="mouth-svg">
          <motion.path
            animate={{
              d: smile >= 0
                ? `M 2 4 Q 18 ${4 + curveY} 34 4`
                : `M 2 8 Q 18 ${8 + curveY} 34 8`,
            }}
            stroke={s.color}
            strokeWidth={s.strokeWidth}
            strokeLinecap="round"
            fill="none"
            transition={{ duration: 0.3 }}
          />
        </svg>
      </motion.div>
    );
  }

  // Arc-style mouth (kawaii / minimal)
  if (openness > 0.15) {
    return (
      <motion.div
        className="mouth-open"
        animate={{
          width: s.baseWidth * mouth.width * (0.6 + openness * 0.4),
          height: 18 * openness,
          borderRadius: "50%",
        }}
        transition={{ duration: speaking ? 0.08 : 0.3 }}
      />
    );
  }

  const smile = mouth.smile;
  const curveY = smile * 6;

  return (
    <motion.div
      className="mouth-closed"
      animate={{ width: s.baseWidth * mouth.width }}
      transition={{ duration: 0.3 }}
    >
      <svg viewBox="0 0 28 12" className="mouth-svg">
        <motion.path
          animate={{
            d: smile >= 0
              ? `M 2 4 Q 14 ${4 + curveY} 26 4`
              : `M 2 8 Q 14 ${8 + curveY} 26 8`,
          }}
          stroke={s.color || "var(--vx-mouth)"}
          strokeWidth={s.strokeWidth}
          strokeLinecap="round"
          fill="none"
          transition={{ duration: 0.3 }}
        />
      </svg>
    </motion.div>
  );
}

/* ── Mood effects ─────────────────────────────────────────── */

function MoodEffects({ mood }) {
  return (
    <AnimatePresence>
      {mood === "sleepy" && (
        <motion.div
          key="zzz"
          className="mood-effect zzz"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.span
            animate={{ y: [-5, -20], opacity: [1, 0] }}
            transition={{ duration: 2, repeat: Infinity, delay: 0 }}
          >z</motion.span>
          <motion.span
            animate={{ y: [-5, -25], opacity: [1, 0] }}
            transition={{ duration: 2, repeat: Infinity, delay: 0.5 }}
          >z</motion.span>
          <motion.span
            animate={{ y: [-5, -30], opacity: [1, 0] }}
            transition={{ duration: 2, repeat: Infinity, delay: 1.0 }}
          >Z</motion.span>
        </motion.div>
      )}
      {mood === "happy" && (
        <motion.div
          key="heart"
          className="mood-effect heart-icon"
          initial={{ opacity: 0, scale: 0.3 }}
          animate={{ opacity: [0.6, 1, 0.6], scale: [1, 1.15, 1] }}
          exit={{ opacity: 0, scale: 0.3 }}
          transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
        >
          ♥
        </motion.div>
      )}
      {mood === "thinking" && (
        <motion.div
          key="thinking"
          className="mood-effect thinking-icons"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.8 }}
          exit={{ opacity: 0 }}
        >
          <motion.span
            className="thinking-brain"
            animate={{ y: [0, -2, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          >🧠</motion.span>
          <motion.span
            className="thinking-cog"
            animate={{ rotate: 360 }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
          >⚙</motion.span>
        </motion.div>
      )}
      {mood === "curious" && (
        <motion.div
          key="question"
          className="mood-effect question"
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: [0, -3, 0] }}
          exit={{ opacity: 0 }}
          transition={{ y: { duration: 1.5, repeat: Infinity } }}
        >
          ?
        </motion.div>
      )}
      {mood === "confused" && (
        <motion.div
          key="confused"
          className="mood-effect confused-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.4, 0.8, 0.4], y: [0, -2, 0] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          ???
        </motion.div>
      )}
      {mood === "excited" && (
        <motion.div
          key="excited"
          className="mood-effect excited-icon"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: [1, 1.2, 1], rotate: [0, 10, -10, 0] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1, repeat: Infinity }}
        >
          !!
        </motion.div>
      )}
      {mood === "listening" && (
        <motion.div
          key="listening"
          className="mood-effect listening-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.3, 0.8, 0.3] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          )))
        </motion.div>
      )}
      {mood === "sad" && (
        <motion.div
          key="sad"
          className="mood-effect sad-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.6, y: [0, 3, 0] }}
          exit={{ opacity: 0 }}
          transition={{ y: { duration: 3, repeat: Infinity } }}
        >
          ╥
        </motion.div>
      )}
      {mood === "surprised" && (
        <motion.div
          key="surprised"
          className="mood-effect surprised-icon"
          initial={{ opacity: 0, scale: 2 }}
          animate={{ opacity: [0.8, 1, 0.8], scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.2, repeat: Infinity }}
        >
          !
        </motion.div>
      )}
      {mood === "focused" && (
        <motion.div
          key="focused"
          className="mood-effect focused-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.7 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="loading-dots"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
          >
            •••
          </motion.div>
        </motion.div>
      )}
      {mood === "working" && (
        <motion.div
          key="working"
          className="mood-effect working-icon"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 0.8, scale: 1, rotate: 360 }}
          exit={{ opacity: 0, scale: 0.5 }}
          transition={{ rotate: { duration: 2, repeat: Infinity, ease: "linear" } }}
        >
          ⚙
        </motion.div>
      )}
      {mood === "frustrated" && (
        <motion.div
          key="frustrated"
          className="mood-effect frustrated-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.5, 0.9, 0.5], x: [-1, 1, -1] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6, repeat: Infinity }}
        >
          #
        </motion.div>
      )}
      {mood === "error" && (
        <motion.div
          key="error"
          className="mood-effect error-icon"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.6, 1, 0.6] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.8, repeat: Infinity }}
        >
          ?!
        </motion.div>
      )}
      {(mood === "lowBattery" || mood === "criticalBattery") && (
        <motion.div
          key="battery"
          className="mood-effect battery-icon"
          initial={{ opacity: 0 }}
          animate={{
            opacity: mood === "criticalBattery" ? [0.4, 0.9, 0.4] : [0.5, 0.8, 0.5],
            y: [0, -2, 0],
          }}
          exit={{ opacity: 0 }}
          transition={{ duration: mood === "criticalBattery" ? 1.0 : 2.0, repeat: Infinity }}
        >
          <svg width="16" height="10" viewBox="0 0 16 10">
            <rect x="0" y="0" width="14" height="10" rx="2" fill="none"
              stroke={mood === "criticalBattery" ? "#a07818" : "#d4a020"} strokeWidth="1.5" />
            <rect x="14" y="3" width="2" height="4" rx="0.5"
              fill={mood === "criticalBattery" ? "#a07818" : "#d4a020"} />
            <rect x="2" y="2.5" width={mood === "criticalBattery" ? 3 : 6} height="5" rx="1"
              fill={mood === "criticalBattery" ? "#a07818" : "#d4a020"} />
          </svg>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
