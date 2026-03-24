/**
 * useAudioAmplitude — Browser mic capture with tunable smoothing.
 *
 * Accepts tuning object for real-time parameter adjustment from dev panel.
 *
 * Returns { amplitude, isActive, sensitivity, setSensitivity, start, stop }
 */
import { useState, useRef, useCallback, useEffect } from "react";

// Defaults (Conjure-matched)
const DEFAULTS = {
  smoothing: 0.14,
  decay: 0.988,
  gamma: 0.7,
};

export default function useAudioAmplitude(tuning = {}) {
  const [amplitude, setAmplitude] = useState(0);
  const [isActive, setIsActive] = useState(false);
  const [sensitivity, setSensitivity] = useState(0.5);
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const dataRef = useRef(null);
  const smoothRef = useRef({ target: 0, current: 0 });
  const sensitivityRef = useRef(0.5);
  const tuningRef = useRef(tuning);

  useEffect(() => { sensitivityRef.current = sensitivity; }, [sensitivity]);
  useEffect(() => { tuningRef.current = tuning; }, [tuning]);

  const analyse = useCallback(() => {
    const analyser = analyserRef.current;
    const data = dataRef.current;
    const s = smoothRef.current;
    if (!analyser || !data) return;

    const t = tuningRef.current;
    const smoothing = t.smoothing ?? DEFAULTS.smoothing;
    const decay = t.decay ?? DEFAULTS.decay;
    const gamma = t.gamma ?? DEFAULTS.gamma;

    analyser.getByteTimeDomainData(data);

    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);

    const inputScale = 1.5 + sensitivityRef.current * 6.5;
    const boosted = Math.min(1, Math.pow(Math.min(1, rms * inputScale), gamma));

    // Momentum: 0.35 old + 0.65 new (Conjure defaults)
    s.target = Math.min(1, s.target * 0.35 + boosted * 0.65);

    s.current += (s.target - s.current) * smoothing;
    if (s.current < 0.005) s.current = 0;

    s.target *= decay;
    if (s.target < 0.005) s.target = 0;

    setAmplitude(s.current);
    rafRef.current = requestAnimationFrame(analyse);
  }, []);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.4;
      source.connect(analyser);

      ctxRef.current = ctx;
      analyserRef.current = analyser;
      streamRef.current = stream;
      dataRef.current = new Uint8Array(analyser.fftSize);
      smoothRef.current = { target: 0, current: 0 };

      setIsActive(true);
      rafRef.current = requestAnimationFrame(analyse);
    } catch (err) {
      console.warn("Mic access denied:", err);
    }
  }, [analyse]);

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    ctxRef.current?.close();
    ctxRef.current = null;
    analyserRef.current = null;
    streamRef.current = null;
    dataRef.current = null;
    smoothRef.current = { target: 0, current: 0 };
    setIsActive(false);
    setAmplitude(0);
  }, []);

  useEffect(() => () => stop(), [stop]);

  return { amplitude, isActive, sensitivity, setSensitivity, start, stop };
}
