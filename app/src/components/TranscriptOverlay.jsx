import { motion, AnimatePresence } from "framer-motion";
import "./TranscriptOverlay.css";

/**
 * TranscriptOverlay — shows speech transcript just above the status bar.
 *
 * Props:
 *   userText    - what the user said (STT result)
 *   voxelText   - what Voxel is saying (TTS text)
 *   visible     - whether to show the overlay
 */
export default function TranscriptOverlay({
  userText = "",
  voxelText = "",
  visible = false,
}) {
  const hasContent = visible && (userText || voxelText);

  return (
    <AnimatePresence>
      {hasContent && (
        <motion.div
          className="transcript-overlay"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.3 }}
        >
          {userText && (
            <div className="transcript-line transcript-user">
              <span className="transcript-label">you</span>
              <span className="transcript-text">{userText}</span>
            </div>
          )}
          {voxelText && (
            <div className="transcript-line transcript-voxel">
              <span className="transcript-label">vxl</span>
              <span className="transcript-text">{voxelText}</span>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
