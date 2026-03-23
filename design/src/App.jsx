import { useState } from "react";
import VoxelCube from "./components/VoxelCube";
import { MOOD_LIST } from "./expressions";
import { STYLE_LIST, STYLES, DEFAULT_STYLE } from "./styles";
import "./App.css";

function App() {
  const [mood, setMood] = useState("neutral");
  const [speaking, setSpeaking] = useState(false);
  const [styleName, setStyleName] = useState(DEFAULT_STYLE);

  return (
    <div className="workspace">
      {/* Device frame — exact 240x280 */}
      <div>
        <div className="device-frame" id="voxel-viewport">
          <VoxelCube mood={mood} speaking={speaking} styleName={styleName} />

          {/* Status bar */}
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: 24,
              background: "#14141c",
              borderTop: "1px solid #28283a",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0 8px",
              fontFamily: "ui-monospace, monospace",
              fontSize: 10,
              color: "#a0a0b4",
            }}
          >
            <span>Voxel v0.1</span>
            <span style={{ color: "#50c8a0", textTransform: "uppercase" }}>
              {mood}
            </span>
          </div>
        </div>
        <div className="label">240 × 280 — actual device size</div>
      </div>

      {/* Controls */}
      <div className="controls">
        <h3>Style</h3>
        <div className="mood-grid">
          {STYLE_LIST.map((s) => (
            <button
              key={s}
              className={`mood-btn ${styleName === s ? "active" : ""}`}
              onClick={() => setStyleName(s)}
              title={STYLES[s].description}
            >
              {STYLES[s].name}
            </button>
          ))}
        </div>

        <h3>Mood</h3>
        <div className="mood-grid">
          {MOOD_LIST.map((m) => (
            <button
              key={m}
              className={`mood-btn ${mood === m ? "active" : ""}`}
              onClick={() => setMood(m)}
            >
              {m}
            </button>
          ))}
        </div>

        <h3>Speech</h3>
        <button
          className={`mood-btn ${speaking ? "active" : ""}`}
          onClick={() => setSpeaking(!speaking)}
          style={{ width: "100%" }}
        >
          {speaking ? "⏹ Stop" : "▶ Simulate Speaking"}
        </button>
      </div>
    </div>
  );
}

export default App;
