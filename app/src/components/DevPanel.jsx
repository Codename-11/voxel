import { useState, useRef, useEffect, useCallback } from "react";
import { MOOD_LIST } from "../expressions";
import { STYLE_LIST, STYLES } from "../styles";
import "./DevPanel.css";

const STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"];
const AGENTS = ["Daemon", "Soren", "Ash", "Mira", "Jace", "Pip"];
const TABS = ["controls", "tuner", "log"];

export default function DevPanel({
  mood, style, stateName, speaking, amplitude, battery, agent,
  transitionSpeed, splitView, previewScale, wsConnected, expressionOverride, logs,
  onSetMood, onSetStyle, onSetState, onSetAmplitude, onSetBattery,
  onSetAgent, onSetTransitionSpeed, onSetSplitView, onSetPreviewScale, onSetExpressionOverride,
}) {
  const [activeTab, setActiveTab] = useState("controls");
  const logEndRef = useRef(null);

  useEffect(() => {
    if (activeTab === "log") logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, activeTab]);

  const updateOverride = useCallback(
    (section, key, value) => {
      onSetExpressionOverride((prev) => ({
        ...prev,
        [section]: { ...(prev[section] || {}), [key]: value },
      }));
    },
    [onSetExpressionOverride],
  );

  const resetOverride = useCallback(() => {
    onSetExpressionOverride({ eyes: {}, mouth: {}, body: {} });
  }, [onSetExpressionOverride]);

  return (
    <div className="dev-panel">
      {/* Tab bar */}
      <div className="dev-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            className={`dev-tab ${activeTab === t ? "active" : ""}`}
            onClick={() => setActiveTab(t)}
          >
            {t === "controls" ? "Controls" : t === "tuner" ? "Tuner" : "Log"}
          </button>
        ))}
        {!wsConnected && <span className="offline-dot" title="No backend" />}
      </div>

      {/* ── Controls tab ────────────────────────────────────── */}
      {activeTab === "controls" && (
        <div className="dev-tab-content">
          {/* Top row: Style + State side by side */}
          <div className="dev-row-2col">
            <div>
              <label className="dev-label">Style</label>
              <div className="dev-btn-row">
                {STYLE_LIST.map((s) => (
                  <button key={s} className={`dev-chip ${style === s ? "active" : ""}`} onClick={() => onSetStyle(s)}>
                    {STYLES[s]?.name || s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="dev-label">State</label>
              <div className="dev-btn-row">
                {STATES.map((s) => (
                  <button key={s} className={`dev-chip sm ${stateName === s ? "active" : ""}`} onClick={() => onSetState(s)}>
                    {s.slice(0, 4)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Mood grid */}
          <label className="dev-label">Mood</label>
          <div className="dev-mood-grid">
            {MOOD_LIST.map((m) => (
              <button key={m} className={`dev-chip ${mood === m ? "active" : ""}`} onClick={() => onSetMood(m)}>
                {m}
              </button>
            ))}
          </div>

          {/* Agent row */}
          <label className="dev-label">Agent</label>
          <div className="dev-btn-row">
            {AGENTS.map((a) => (
              <button key={a} className={`dev-chip ${agent === a ? "active" : ""}`} onClick={() => onSetAgent(a)}>
                {a}
              </button>
            ))}
          </div>

          {/* Sliders: amplitude, battery, speed in compact layout */}
          <div className="dev-sliders">
            <SliderRow label="Mouth" value={amplitude} min={0} max={1} step={0.01}
              onChange={onSetAmplitude} fmt={(v) => v.toFixed(2)} />
            <SliderRow label="Battery" value={battery} min={0} max={100} step={1}
              onChange={onSetBattery}
              fmt={(v) => `${v}%`}
              cls={battery < 5 ? "crit" : battery < 20 ? "warn" : ""} />
            <SliderRow label="Speed" value={transitionSpeed} min={0.1} max={3} step={0.1}
              onChange={onSetTransitionSpeed} fmt={(v) => `${v.toFixed(1)}x`} />
          </div>

          {/* View controls: zoom + split */}
          <label className="dev-label">View</label>
          <div className="dev-view-row">
            <div className="dev-zoom-btns">
              {[1, 1.5, 2, 2.5].map((s) => (
                <button key={s} className={`dev-chip sm ${previewScale === s ? "active" : ""}`}
                  onClick={() => onSetPreviewScale(s)}>
                  {s === 1 ? "1:1" : `${s}x`}
                </button>
              ))}
            </div>
            <button className={`dev-chip ${splitView ? "active" : ""}`} onClick={() => onSetSplitView(!splitView)}>
              {splitView ? "Single" : "Split"}
            </button>
          </div>

          {/* Keyboard hint */}
          <div className="dev-hint">
            <kbd>`</kbd> panel <kbd>1-9</kbd> mood <kbd>S</kbd> style <kbd>Space</kbd> state <kbd>+/-</kbd> amp <kbd>M</kbd> menu
          </div>
        </div>
      )}

      {/* ── Tuner tab ───────────────────────────────────────── */}
      {activeTab === "tuner" && (
        <div className="dev-tab-content">
          <div className="tuner-section">
            <TunerGroup label="Eye" items={[
              { key: "openness", min: 0, max: 1 },
              { key: "gazeX", min: -1, max: 1 },
              { key: "gazeY", min: -1, max: 1 },
              { key: "squint", min: 0, max: 1 },
            ]} section="eyes" override={expressionOverride} onChange={updateOverride} />

            <TunerGroup label="Mouth" items={[
              { key: "smile", min: -1, max: 1 },
              { key: "openness", min: 0, max: 1 },
            ]} section="mouth" override={expressionOverride} onChange={updateOverride} />

            <TunerGroup label="Body" items={[
              { key: "bounceSpeed", min: 0, max: 2 },
              { key: "bounceAmount", min: 0, max: 8, step: 0.1 },
              { key: "tilt", min: -15, max: 15, step: 0.5 },
              { key: "scale", min: 0.9, max: 1.1, step: 0.005 },
            ]} section="body" override={expressionOverride} onChange={updateOverride} />
          </div>
          <button className="dev-chip wide reset-btn" onClick={resetOverride}>Reset</button>
        </div>
      )}

      {/* ── Log tab ─────────────────────────────────────────── */}
      {activeTab === "log" && (
        <div className="dev-tab-content">
          <div className="log-viewer">
            {logs.length === 0 && <div className="log-empty">No events yet</div>}
            {logs.map((entry, i) => (
              <div key={i} className="log-entry">
                <span className="log-time">{entry.time}</span>
                <span className="log-msg">{entry.msg}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Slider row ──────────────────────────────────────────────── */
function SliderRow({ label, value, min, max, step = 0.01, onChange, fmt, cls = "" }) {
  return (
    <div className="dev-slider-row">
      <span className="dev-slider-label">{label}</span>
      <input type="range" className="dev-slider" min={min} max={max} step={step}
        value={value} onChange={(e) => onChange(parseFloat(e.target.value))} />
      <span className={`dev-slider-val ${cls}`}>{fmt(value)}</span>
    </div>
  );
}

/* ── Tuner group ─────────────────────────────────────────────── */
function TunerGroup({ label, items, section, override, onChange }) {
  return (
    <div className="tuner-group">
      <span className="tuner-label">{label}</span>
      {items.map(({ key, min, max, step = 0.01 }) => {
        const val = override[section]?.[key];
        const hasVal = val !== undefined && val !== null;
        return (
          <div key={key} className="tuner-row">
            <span className="tuner-key">{key}</span>
            <input type="range" className={`dev-slider ${!hasVal ? "inactive" : ""}`}
              min={min} max={max} step={step}
              value={hasVal ? val : (min + max) / 2}
              onChange={(e) => onChange(section, key, parseFloat(e.target.value))} />
            <span className={`tuner-val ${!hasVal ? "dim" : ""}`}>
              {hasVal ? val.toFixed(2) : "--"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
