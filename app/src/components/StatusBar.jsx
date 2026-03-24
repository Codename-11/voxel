import { motion } from "framer-motion";
import "./StatusBar.css";

const STATE_COLORS = {
  IDLE: "#50c8a0",
  LISTENING: "#50a0ff",
  THINKING: "#dcb43c",
  SPEAKING: "#50dc78",
  ERROR: "#ff5050",
  SLEEPING: "#64648c",
  MENU: "#a0a0b4",
};

function BatteryIcon({ level }) {
  // Determine fill width (0-10 out of 10) and color
  const fillWidth = Math.max(0, Math.min(10, Math.round(level / 10)));
  let color = "#50c8a0"; // good
  if (level <= 10) color = "#ff3c3c";
  else if (level <= 25) color = "#d4a020";
  else if (level <= 50) color = "#a0c040";

  const isCritical = level <= 10;

  return (
    <motion.svg
      width="18"
      height="10"
      viewBox="0 0 18 10"
      className="battery-svg"
      animate={isCritical ? { opacity: [0.4, 1, 0.4] } : { opacity: 1 }}
      transition={isCritical ? { duration: 1, repeat: Infinity } : {}}
    >
      <rect
        x="0.5"
        y="0.5"
        width="14"
        height="9"
        rx="2"
        fill="none"
        stroke={color}
        strokeWidth="1"
      />
      <rect x="14.5" y="3" width="2" height="4" rx="0.5" fill={color} />
      <rect x="2" y="2" width={fillWidth} height="6" rx="1" fill={color} />
    </motion.svg>
  );
}

function ConnectivityDot({ connected }) {
  return (
    <span
      className={`sb-dot ${connected ? "sb-dot--connected" : "sb-dot--disconnected"}`}
      title={connected ? "Connected" : "Disconnected"}
    />
  );
}

export default function StatusBar({
  agentName = "Voxel",
  agentEmoji = "",
  stateName = "IDLE",
  battery = 100,
  connected = false,
}) {
  const stateColor = STATE_COLORS[stateName] || STATE_COLORS.IDLE;

  return (
    <div className="statusbar">
      <span className="sb-left">
        {agentEmoji && <span className="sb-emoji">{agentEmoji}</span>}
        {agentName}
      </span>
      <span className="sb-center" style={{ color: stateColor }}>
        {stateName}
      </span>
      <span className="sb-right">
        <BatteryIcon level={battery} />
        <span className="sb-battery-pct">{battery}%</span>
        <ConnectivityDot connected={connected} />
      </span>
    </div>
  );
}
