/**
 * SpeakingPill — Pill-shaped waveform overlay that slides up from the
 * status bar when the character is speaking. Adapted from Conjure's
 * PillOverlayRoot pattern.
 */
import { motion, AnimatePresence } from "framer-motion";
import AudioWaveform from "./AudioWaveform";
import "./SpeakingPill.css";

export default function SpeakingPill({ speaking = false, amplitude = 0, tuning = {} }) {
  return (
    <AnimatePresence>
      {speaking && (
        <motion.div
          className="speaking-pill"
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 30, opacity: 0 }}
          transition={{ type: "tween", duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        >
          <div className="speaking-pill-inner">
            <AudioWaveform
              amplitude={amplitude}
              active={speaking}
              width={110}
              height={22}
              strokeColor="var(--vx-cyan)"
              strokeWidth={1.4}
              tuning={tuning}
            />
          </div>
          {/* Gradient edge fade — fades waveform at pill edges */}
          <div className="speaking-pill-fade" />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
