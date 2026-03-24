import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { EXPRESSIONS } from "../expressions";
import { STYLES, DEFAULT_STYLE } from "../styles";
import "./VoxelCube.css";

/**
 * Deep-merge expression override onto a base expression.
 * Only override keys that are explicitly set (not undefined/null).
 */
function mergeExpression(base, override) {
  if (!override) return base;
  const result = { ...base };
  for (const section of ["eyes", "mouth", "body"]) {
    if (override[section] && typeof override[section] === "object") {
      const merged = { ...base[section] };
      for (const [key, val] of Object.entries(override[section])) {
        if (val !== undefined && val !== null) {
          merged[key] = val;
        }
      }
      result[section] = merged;
    }
  }
  return result;
}

/* ── Speaking animation hooks ─────────────────────────────────── */

/** #1 — Random blinks during speech. Returns 0 (open) or 1 (blinking). */
function useTalkBlink(speaking) {
  const [blink, setBlink] = useState(0);
  useEffect(() => {
    if (!speaking) { setBlink(0); return; }
    let mounted = true;
    let timer;
    const schedule = () => {
      timer = setTimeout(() => {
        if (!mounted) return;
        setBlink(1);
        timer = setTimeout(() => {
          if (!mounted) return;
          setBlink(0);
          schedule();
        }, 120);
      }, 800 + Math.random() * 2200);
    };
    schedule();
    return () => { mounted = false; clearTimeout(timer); };
  }, [speaking]);
  return blink;
}

/** #3 — Slow gaze drift during speech. Returns { x, y } offset. */
function useGazeDrift(speaking) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  useEffect(() => {
    if (!speaking) { setOffset({ x: 0, y: 0 }); return; }
    let mounted = true;
    let timer;
    const drift = () => {
      if (!mounted) return;
      setOffset({
        x: (Math.random() - 0.5) * 0.4,
        y: (Math.random() - 0.5) * 0.25,
      });
      timer = setTimeout(drift, 1200 + Math.random() * 1800);
    };
    timer = setTimeout(drift, 500);
    return () => { mounted = false; clearTimeout(timer); };
  }, [speaking]);
  return offset;
}

export default function VoxelCube({
  mood = "neutral",
  speaking = false,
  styleName = DEFAULT_STYLE,
  amplitude = 0,
  expressionOverride = null,
  transitionSpeed = 1.0,
}) {
  const baseExpr = EXPRESSIONS[mood] || EXPRESSIONS.neutral;
  const expr = expressionOverride ? mergeExpression(baseExpr, expressionOverride) : baseExpr;
  const style = STYLES[styleName] || STYLES[DEFAULT_STYLE];

  // #2 — Speaking-reactive bounce: amplitude adds energy to body bounce
  const speakBounce = speaking ? amplitude * 2.5 + 0.5 : 0;
  const totalBounce = expr.body.bounceAmount + speakBounce;
  const bounceSpeed = speaking
    ? Math.max(0.3, 0.6 - amplitude * 0.25) / transitionSpeed
    : (1 / Math.max(expr.body.bounceSpeed, 0.1)) / transitionSpeed;

  return (
    <div className="voxel-scene">
      {/* Ambient glow — intensifies when speaking */}
      <motion.div
        className="ambient-glow"
        animate={{
          opacity: speaking
            ? [0.3 + amplitude * 0.25, 0.55 + amplitude * 0.2, 0.3 + amplitude * 0.25]
            : [0.3, 0.5, 0.3],
          scale: speaking
            ? [1 + amplitude * 0.08, 1.08 + amplitude * 0.08, 1 + amplitude * 0.08]
            : [1, 1.05, 1],
        }}
        transition={{ duration: speaking ? 1.5 : 3, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* 3D cube container — #2 bounce syncs to amplitude */}
      <motion.div
        className="cube-wrapper"
        animate={{
          y: [0, -totalBounce, 0],
          rotateZ: expr.body.tilt,
          scale: expr.body.scale + (speaking ? amplitude * 0.015 : 0),
        }}
        transition={{
          y: { duration: bounceSpeed, repeat: Infinity, ease: "easeInOut" },
          rotateZ: { duration: 0.3 / transitionSpeed, ease: "easeOut" },
          scale: { duration: 0.12 / transitionSpeed, ease: "easeOut" },
        }}
      >
        <div className="cube" style={{ transform: `rotateX(-15deg) rotateY(-25deg)` }}>
          {/* Front face */}
          <div className="cube-face front">
            <div className="face-inner">
              <Eyes expr={expr} mood={mood} style={style} transitionSpeed={transitionSpeed}
                speaking={speaking} amplitude={amplitude} />
              <Mouth expr={expr} mood={mood} speaking={speaking} amplitude={amplitude}
                style={style} transitionSpeed={transitionSpeed} />
            </div>
            <EdgeGlows speaking={speaking} amplitude={amplitude} />
          </div>

          {/* Top face */}
          <div className="cube-face top">
            <div className="face-shading top-shade" />
            <EdgeGlows speaking={speaking} amplitude={amplitude} />
          </div>

          {/* Right face */}
          <div className="cube-face right">
            <div className="face-shading right-shade" />
            <EdgeGlows speaking={speaking} amplitude={amplitude} />
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

/* ── #4 Edge Glow Pulse ──────────────────────────────────────── */

function EdgeGlows({ speaking, amplitude }) {
  return (
    <>
      <div className="edge-glow edge-top" />
      <div className="edge-glow edge-bottom" />
      <div className="edge-glow edge-left" />
      <div className="edge-glow edge-right" />
      {speaking && (
        <motion.div
          className="speaking-edge-overlay"
          animate={{ opacity: 0.3 + amplitude * 0.7 }}
          transition={{ duration: 0.08 }}
        />
      )}
    </>
  );
}

/* ── Eyes ─────────────────────────────────────────────────── */

function Eyes({ expr, mood, style, transitionSpeed = 1.0, speaking = false, amplitude = 0 }) {
  const { eyes } = expr;
  const s = style.xEye;
  const colorOverride = expr.eyeColorOverride || null;

  // #1 — Talk blinks + #3 — Gaze drift
  const talkBlink = useTalkBlink(speaking);
  const gazeDrift = useGazeDrift(speaking);

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
      <Eye eyes={leftEyes} style={style} colorOverride={colorOverride}
        transitionSpeed={transitionSpeed} speaking={speaking} amplitude={amplitude}
        talkBlink={talkBlink} gazeDrift={gazeDrift} />
      <Eye eyes={rightEyes} style={style} colorOverride={colorOverride}
        transitionSpeed={transitionSpeed} speaking={speaking} amplitude={amplitude}
        talkBlink={talkBlink} gazeDrift={gazeDrift} />
    </div>
  );
}

function Eye({ eyes, style, colorOverride, transitionSpeed = 1.0,
  speaking = false, amplitude = 0, talkBlink = 0, gazeDrift = { x: 0, y: 0 } }) {
  const s = style.eye;
  const fillColor = colorOverride || s.fillColor;
  const glowColor = colorOverride ? `${colorOverride}55` : s.glowColor;

  const w = s.baseWidth * eyes.width;
  // #1 — Talk blink: rapidly shrink height to simulate blink
  const blinkMult = talkBlink ? 0.1 : 1;
  const h = s.baseHeight * eyes.height * Math.max(eyes.openness, 0.08) * blinkMult;
  const radius = (eyes.openness < 0.3 || talkBlink) ? s.closedRadius : s.borderRadius;
  const tilt = eyes.tilt || 0;

  // #3 — Gaze drift: add offset to base gaze
  const gazeX = (eyes.gazeX || 0) + gazeDrift.x;
  const gazeY = (eyes.gazeY || 0) + gazeDrift.y;

  // #7 — Highlight shimmer: shift highlight position with gaze drift
  const hlRight = speaking ? 6 + gazeDrift.x * 3 : 6;
  const hlTop = speaking ? 4 + gazeDrift.y * 2 : 4;
  const hlVisible = eyes.openness > 0.3 && !talkBlink;

  const dur = talkBlink ? 0.08 : 0.3;

  // Roundrect (kawaii) — gaze shifts whole eye position
  if (s.type === "roundrect") {
    return (
      <motion.div
        className="eye eye--roundrect"
        animate={{
          width: w, height: h, borderRadius: radius,
          background: fillColor, rotate: tilt,
          x: gazeX * 3, y: gazeY * 2,
        }}
        transition={{ duration: dur, ease: "easeOut" }}
        style={{ boxShadow: `0 0 12px ${glowColor}` }}
      >
        {eyes.squint > 0 && (
          <motion.div className="eyelid"
            animate={{ height: `${eyes.squint * 45}%` }}
            transition={{ duration: 0.3 }} />
        )}
      </motion.div>
    );
  }

  // Dot (minimal) — gaze shifts whole eye position
  if (s.type === "dot") {
    return (
      <motion.div
        className="eye eye--dot"
        animate={{
          width: w, height: h, borderRadius: radius, background: fillColor,
          x: gazeX * 2, y: gazeY * 1.5,
        }}
        transition={{ duration: dur, ease: "easeOut" }}
        style={{ boxShadow: `0 0 8px ${glowColor}` }}
      />
    );
  }

  // Iris (retro) — gaze moves iris, highlight shimmers
  if (s.type === "iris") {
    return (
      <motion.div
        className="eye eye--iris"
        animate={{ width: w, height: h, borderRadius: radius }}
        transition={{ duration: dur, ease: "easeOut" }}
      >
        <motion.div className="eye-fill"
          animate={{ background: colorOverride ? colorOverride : s.fillColor }}
          transition={{ duration: 0.5 }} />
        <motion.div className="eye-iris"
          animate={{
            width: Math.min(w, h) * s.irisSize,
            height: Math.min(w, h) * s.irisSize,
            x: gazeX * 5, y: gazeY * 4,
          }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          style={{ background: s.irisColor }} />
        {s.highlightSize > 0 && (
          <motion.div className="eye-highlight"
            animate={{ opacity: hlVisible ? 1 : 0, top: hlTop, right: hlRight }}
            transition={{ duration: speaking ? 0.4 : 0.2 }}
            style={{
              width: s.highlightSize, height: s.highlightSize,
              background: s.highlightColor,
            }} />
        )}
        {eyes.squint > 0 && (
          <motion.div className="eyelid"
            animate={{ height: `${eyes.squint * 45}%` }}
            transition={{ duration: 0.3 }} />
        )}
      </motion.div>
    );
  }

  // Default: flat
  return (
    <motion.div
      className="eye eye--flat"
      animate={{ width: w, height: h, borderRadius: radius }}
      transition={{ duration: dur, ease: "easeOut" }}
    >
      <motion.div className="eye-fill"
        animate={{ background: fillColor }}
        transition={{ duration: 0.5 }}
        style={{
          boxShadow: `inset 0 -3px 6px rgba(0, 180, 170, 0.4), 0 0 8px ${glowColor}`,
        }} />
      {s.highlightSize > 0 && (
        <motion.div className="eye-highlight"
          animate={{ opacity: hlVisible ? 1 : 0, top: hlTop, right: hlRight }}
          transition={{ duration: speaking ? 0.4 : 0.2 }}
          style={{
            width: s.highlightSize, height: s.highlightSize,
            background: s.highlightColor,
          }} />
      )}
      {eyes.squint > 0 && (
        <motion.div className="eyelid"
          animate={{ height: `${eyes.squint * 45}%` }}
          transition={{ duration: 0.3 }} />
      )}
    </motion.div>
  );
}

function XEye({ size = 22, color = "var(--vx-error)", thickness = 3 }) {
  return (
    <div className="x-eye" style={{ width: size + 6, height: size + 6 }}>
      <div className="x-line x-line-1"
        style={{ width: size, height: thickness, background: color, boxShadow: `0 0 8px ${color}` }} />
      <div className="x-line x-line-2"
        style={{ width: size, height: thickness, background: color, boxShadow: `0 0 8px ${color}` }} />
    </div>
  );
}

/* ── Mouth ────────────────────────────────────────────────── */

function Mouth({ expr, mood, speaking, amplitude = 0, style, transitionSpeed = 1.0 }) {
  const { mouth } = expr;
  const s = style.mouth;

  if (mood === "error") {
    return <div className="mouth-flat" />;
  }

  const openness = amplitude > 0 ? amplitude : speaking ? 0.5 : mouth.openness;
  const isAnimating = speaking || amplitude > 0;
  const fast = (isAnimating ? 0.08 : 0.3) / transitionSpeed;
  const slow = 0.3 / transitionSpeed;

  // #5 — Mouth shape variety: non-linear amplitude mapping for more expressive speech
  const speakWidth = speaking
    ? 0.4 + Math.pow(amplitude, 0.7) * 0.7   // wider range: tiny at whisper, full at shout
    : 0.6 + openness * 0.4;
  const speakHeight = speaking
    ? Math.max(3, 18 * Math.pow(amplitude, 0.7)) // power curve: quiet speech still visible
    : 14 * openness;
  const speakRadius = speaking
    ? (amplitude > 0.6 ? "4px 4px 50% 50%" : amplitude > 0.3 ? "40%" : "50%")
    : (mouth.smile > 0.5 ? "2px 2px 50% 50%" : "50%");

  // Offset mouth (kawaii)
  if (s.type === "offset") {
    const smile = mouth.smile;
    const w = s.baseWidth * mouth.width;

    if (openness > 0.15) {
      return (
        <motion.div className="mouth-offset"
          animate={{ width: w * speakWidth, height: speakHeight }}
          transition={{ duration: fast }}
        >
          <div className="mouth-offset-open"
            style={{ background: s.color, borderRadius: speakRadius }} />
        </motion.div>
      );
    }

    const curveDepth = smile * 8;
    return (
      <motion.div className="mouth-offset"
        animate={{ width: w, height: 14 }}
        transition={{ duration: slow }}
      >
        <svg viewBox="0 0 30 14" className="mouth-svg" overflow="visible">
          <motion.path
            animate={{
              d: smile >= 0
                ? `M 2 5 Q 15 ${5 + curveDepth} 28 5`
                : `M 2 9 Q 15 ${9 + curveDepth} 28 9`,
            }}
            stroke={s.color} strokeWidth={s.strokeWidth} strokeLinecap="round" fill="none"
            transition={{ duration: slow }} />
        </svg>
      </motion.div>
    );
  }

  // Teeth mouth (retro)
  if (s.type === "teeth") {
    const smile = mouth.smile;

    if (openness > 0.15 || smile > 0.4) {
      const w = s.baseWidth * mouth.width;
      const teethW = speaking ? w * speakWidth : w;
      const h = speaking
        ? Math.max(8, speakHeight)
        : Math.max(14 * Math.max(openness, smile * 0.5), 8);
      return (
        <motion.div className="mouth-teeth"
          animate={{ width: teethW, height: h }}
          transition={{ duration: fast }}
        >
          <div className="mouth-teeth-bg" />
          <div className="mouth-teeth-row">
            {[...Array(Math.max(Math.round(teethW / 6), 3))].map((_, i) => (
              <div key={i} className="tooth" />
            ))}
          </div>
        </motion.div>
      );
    }

    const curveY = smile * 6;
    return (
      <motion.div className="mouth-closed"
        animate={{ width: s.baseWidth * mouth.width }}
        transition={{ duration: slow }}
      >
        <svg viewBox="0 0 36 12" className="mouth-svg">
          <motion.path
            animate={{
              d: smile >= 0
                ? `M 2 4 Q 18 ${4 + curveY} 34 4`
                : `M 2 8 Q 18 ${8 + curveY} 34 8`,
            }}
            stroke={s.color} strokeWidth={s.strokeWidth} strokeLinecap="round" fill="none"
            transition={{ duration: slow }} />
        </svg>
      </motion.div>
    );
  }

  // Arc mouth (minimal / default)
  if (openness > 0.15) {
    return (
      <motion.div className="mouth-open"
        animate={{
          width: s.baseWidth * mouth.width * speakWidth,
          height: speakHeight,
          borderRadius: speakRadius,
        }}
        transition={{ duration: fast }} />
    );
  }

  const smile = mouth.smile;
  const curveY = smile * 6;
  return (
    <motion.div className="mouth-closed"
      animate={{ width: s.baseWidth * mouth.width }}
      transition={{ duration: slow }}
    >
      <svg viewBox="0 0 28 12" className="mouth-svg">
        <motion.path
          animate={{
            d: smile >= 0
              ? `M 2 4 Q 14 ${4 + curveY} 26 4`
              : `M 2 8 Q 14 ${8 + curveY} 26 8`,
          }}
          stroke={s.color || "var(--vx-mouth)"} strokeWidth={s.strokeWidth} strokeLinecap="round"
          fill="none" transition={{ duration: slow }} />
      </svg>
    </motion.div>
  );
}

/* ── Mood effects ─────────────────────────────────────────── */

const MOOD_ICON_CONFIG = {
  happy:     { text: "♥", cls: "heart-icon" },
  sleepy:    { text: null, cls: "zzz", custom: true },
  thinking:  { text: null, cls: "thinking-icons", custom: true },
  curious:   { text: "?", cls: "question" },
  confused:  { text: "???", cls: "confused-icon" },
  excited:   { text: "!!", cls: "excited-icon" },
  listening: { text: ")))", cls: "listening-icon" },
  sad:       { text: "╥", cls: "sad-icon" },
  surprised: { text: "!", cls: "surprised-icon" },
  focused:   { text: "•••", cls: "focused-icon" },
  working:   { text: "⚙", cls: "working-icon" },
  frustrated:{ text: "#", cls: "frustrated-icon" },
  error:     { text: "?!", cls: "error-icon" },
  lowBattery:      { text: null, cls: "battery-icon", custom: true },
  criticalBattery: { text: null, cls: "battery-icon", custom: true },
};

function MoodEffects({ mood }) {
  const config = MOOD_ICON_CONFIG[mood];

  return (
    <AnimatePresence mode="wait">
      {config && (
        <motion.div
          key={mood}
          className={`mood-effect ${config.cls}`}
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 0.8, scale: 1 }}
          exit={{ opacity: 0, scale: 0.7 }}
          transition={{ duration: 0.2 }}
        >
          {config.text && <span>{config.text}</span>}

          {mood === "sleepy" && (
            <>
              <motion.span animate={{ y: [-5, -20], opacity: [1, 0] }}
                transition={{ duration: 2, repeat: Infinity }}>z</motion.span>
              <motion.span animate={{ y: [-5, -25], opacity: [1, 0] }}
                transition={{ duration: 2, repeat: Infinity, delay: 0.5 }}>z</motion.span>
              <motion.span animate={{ y: [-5, -30], opacity: [1, 0] }}
                transition={{ duration: 2, repeat: Infinity, delay: 1 }}>Z</motion.span>
            </>
          )}

          {mood === "thinking" && (
            <>
              <motion.span className="thinking-brain"
                animate={{ y: [0, -2, 0] }}
                transition={{ duration: 2, repeat: Infinity }}>🧠</motion.span>
              <motion.span className="thinking-cog"
                animate={{ rotate: 360 }}
                transition={{ duration: 3, repeat: Infinity, ease: "linear" }}>⚙</motion.span>
            </>
          )}

          {(mood === "lowBattery" || mood === "criticalBattery") && (
            <svg width="16" height="10" viewBox="0 0 16 10">
              <rect x="0" y="0" width="14" height="10" rx="2" fill="none"
                stroke={mood === "criticalBattery" ? "#a07818" : "#d4a020"} strokeWidth="1.5" />
              <rect x="14" y="3" width="2" height="4" rx="0.5"
                fill={mood === "criticalBattery" ? "#a07818" : "#d4a020"} />
              <rect x="2" y="2.5" width={mood === "criticalBattery" ? 3 : 6} height="5" rx="1"
                fill={mood === "criticalBattery" ? "#a07818" : "#d4a020"} />
            </svg>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
