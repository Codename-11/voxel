/**
 * AudioWaveform — Animated SVG waveform driven by amplitude.
 * Adapted from Conjure's AudioWaveform.tsx for Voxel.
 *
 * Accepts tuning overrides for real-time parameter adjustment.
 */
import { useEffect, useRef } from "react";

const TAU = Math.PI * 2;

const WAVE_CONFIG = [
  { frequency: 0.8, multiplier: 2.0, phaseOffset: 0, opacity: 1 },
  { frequency: 1.0, multiplier: 1.7, phaseOffset: 0.85, opacity: 0.78 },
  { frequency: 1.25, multiplier: 1.3, phaseOffset: 1.7, opacity: 0.56 },
];

function createWavePath(width, baseline, amplitude, frequency, phase) {
  const segments = Math.max(72, Math.floor(width / 2));
  let path = `M 0 ${baseline + amplitude * Math.sin(phase)}`;
  for (let i = 1; i <= segments; i++) {
    const t = i / segments;
    const x = width * t;
    const theta = frequency * t * TAU + phase;
    const y = baseline + amplitude * Math.sin(theta);
    path += ` L ${x} ${y}`;
  }
  return path;
}

export default function AudioWaveform({
  amplitude = 0,
  active = false,
  width = 120,
  height = 28,
  strokeColor = "var(--vx-cyan)",
  strokeWidth = 1.4,
  tuning = {},
}) {
  const waveRefs = useRef([]);
  const animFrameRef = useRef(null);
  const stateRef = useRef({ phase: 0, currentLevel: 0, targetLevel: 0 });
  const tuningRef = useRef(tuning);

  waveRefs.current.length = WAVE_CONFIG.length;
  tuningRef.current = tuning;

  // Feed amplitude directly as target
  useEffect(() => {
    if (!active) return;
    stateRef.current.targetLevel = amplitude;
  }, [amplitude, active]);

  // Animation loop
  useEffect(() => {
    if (!active) {
      const s = stateRef.current;
      s.targetLevel = 0;
      s.currentLevel = 0;
      s.phase = 0;
      const baseline = height / 2;
      const flat = `M 0 ${baseline} L ${width} ${baseline}`;
      waveRefs.current.forEach((path) => path?.setAttribute("d", flat));
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      return;
    }

    const step = () => {
      const s = stateRef.current;
      const t = tuningRef.current;

      const levelSmoothing = t.waveSmoothing ?? 0.25;
      const targetDecay = t.waveDecay ?? 0.992;
      const basePhaseStep = t.waveSpeed ?? 0.065;
      const phaseGain = t.waveGain ?? 0.2;
      const minAmp = t.minAmp ?? 0.03;
      const maxAmp = t.maxAmp ?? 1.3;

      s.currentLevel += (s.targetLevel - s.currentLevel) * levelSmoothing;
      if (s.currentLevel < 0.0002) s.currentLevel = 0;
      s.targetLevel *= targetDecay;
      if (s.targetLevel < 0.0005) s.targetLevel = 0;

      const level = s.currentLevel;
      const advance = basePhaseStep + phaseGain * level;
      s.phase = (s.phase + advance) % TAU;

      const baseline = height / 2;

      waveRefs.current.forEach((path, i) => {
        if (!path) return;
        const cfg = WAVE_CONFIG[i];
        const ampFactor = Math.min(
          maxAmp,
          Math.max(minAmp, level * cfg.multiplier),
        );
        const amp = Math.max(1, height * 0.75 * ampFactor);
        const ph = s.phase + cfg.phaseOffset;
        path.setAttribute(
          "d",
          createWavePath(width, baseline, amp, cfg.frequency, ph),
        );
        path.setAttribute("opacity", cfg.opacity.toString());
      });

      animFrameRef.current = requestAnimationFrame(step);
    };

    animFrameRef.current = requestAnimationFrame(step);
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [active, width, height]);

  useEffect(
    () => () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    },
    [],
  );

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {WAVE_CONFIG.map((cfg, i) => (
        <path
          key={cfg.frequency}
          ref={(node) => {
            waveRefs.current[i] = node;
          }}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={cfg.opacity}
        />
      ))}
    </svg>
  );
}
