import { useState, useEffect } from "react";
import VoxelCube from "./components/VoxelCube";
import { MOOD_LIST } from "./expressions";
import { STYLE_LIST, STYLES, DEFAULT_STYLE } from "./styles";
import useVoxelSocket from "./hooks/useVoxelSocket";
import "./App.css";

function App() {
  const { state, wsConnected, setMood, setStyle, cycleState, pressButton } =
    useVoxelSocket();
  const [devMode, setDevMode] = useState(false);

  // Local overrides for when backend isn't connected (standalone dev)
  const [localMood, setLocalMood] = useState("neutral");
  const [localStyle, setLocalStyle] = useState(DEFAULT_STYLE);
  const [localSpeaking, setLocalSpeaking] = useState(false);

  // Use backend state when connected, local state when not
  const mood = wsConnected ? state.mood : localMood;
  const style = wsConnected ? state.style : localStyle;
  const speaking = wsConnected ? state.speaking : localSpeaking;
  const battery = wsConnected ? state.battery : 100;
  const stateName = wsConnected ? state.state : "IDLE";

  // Toggle dev panel with ` (backtick) key
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "`") setDevMode((d) => !d);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Auto-show dev panel when no backend connected
  useEffect(() => {
    if (!wsConnected) setDevMode(true);
  }, [wsConnected]);

  const handleSetMood = (m) => {
    if (wsConnected) setMood(m);
    else setLocalMood(m);
  };

  const handleSetStyle = (s) => {
    if (wsConnected) setStyle(s);
    else setLocalStyle(s);
  };

  return (
    <div className={devMode ? "workspace" : "workspace production"}>
      {/* Main viewport */}
      <div>
        <div className="device-frame" id="voxel-viewport">
          <VoxelCube mood={mood} speaking={speaking} styleName={style} />

          {/* Status bar */}
          <div className="status-bar">
            <span>
              {wsConnected && (
                <span className="ws-dot connected" title="Backend connected" />
              )}
              Voxel v0.1
            </span>
            <span style={{ color: "#50c8a0", textTransform: "uppercase" }}>
              {stateName}
            </span>
          </div>
        </div>
        {devMode && (
          <div className="label">
            240 × 280 — {wsConnected ? "connected" : "standalone"}
          </div>
        )}
      </div>

      {/* Dev controls panel — toggle with backtick key */}
      {devMode && (
        <div className="controls">
          <h3>
            Style
            {!wsConnected && (
              <span className="offline-badge">offline</span>
            )}
          </h3>
          <div className="mood-grid">
            {STYLE_LIST.map((s) => (
              <button
                key={s}
                className={`mood-btn ${style === s ? "active" : ""}`}
                onClick={() => handleSetStyle(s)}
                title={STYLES[s]?.description}
              >
                {STYLES[s]?.name || s}
              </button>
            ))}
          </div>

          <h3>Mood</h3>
          <div className="mood-grid">
            {MOOD_LIST.map((m) => (
              <button
                key={m}
                className={`mood-btn ${mood === m ? "active" : ""}`}
                onClick={() => handleSetMood(m)}
              >
                {m}
              </button>
            ))}
          </div>

          <h3>Actions</h3>
          <button
            className={`mood-btn ${speaking ? "active" : ""}`}
            onClick={() =>
              wsConnected
                ? cycleState()
                : setLocalSpeaking(!localSpeaking)
            }
            style={{ width: "100%" }}
          >
            {wsConnected ? "▶ Cycle State" : speaking ? "⏹ Stop" : "▶ Simulate Speaking"}
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
