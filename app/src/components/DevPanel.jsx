import { useState, useRef, useEffect, useCallback } from "react";
import { MOOD_LIST } from "../expressions";
import { STYLE_LIST, STYLES } from "../styles";
import "./DevPanel.css";

const STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"];
const AGENTS = ["Daemon", "Soren", "Ash", "Mira", "Jace", "Pip"];
const TABS = ["controls", "tuner"];

export default function DevPanel({
  mood, style, stateName, speaking, amplitude, battery, agent,
  transitionSpeed, splitView, previewScale, wsConnected, expressionOverride, logs,
  onSetMood, onSetStyle, onSetState, onSetAmplitude, onSetBattery,
  onSetAgent, onSetTransitionSpeed, onSetSplitView, onSetPreviewScale, onSetExpressionOverride,
  micActive, micAmplitude, onToggleMic, micSensitivity, onSetMicSensitivity,
  audioTuning, onSetAudioTuning,
}) {
  const [activeTab, setActiveTab] = useState("controls");
  const [logOpen, setLogOpen] = useState(false);
  const logEndRef = useRef(null);

  useEffect(() => {
    if (logOpen) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, logOpen]);

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
    <div className={`dev-panel-wrapper ${logOpen ? "log-open" : ""}`}>
    <div className="dev-panel">
      {/* Tab bar */}
      <div className="dev-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            className={`dev-tab ${activeTab === t ? "active" : ""}`}
            onClick={() => setActiveTab(t)}
          >
            {t === "controls" ? "Controls" : "Tuner"}
          </button>
        ))}
        <button
          className={`dev-tab log-toggle ${logOpen ? "active" : ""}`}
          onClick={() => setLogOpen(!logOpen)}
          title="Toggle log sidebar"
        >
          Log {logs.length > 0 ? `(${logs.length})` : ""}
        </button>
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
            <div className="dev-slider-row">
              <span className="dev-slider-label">Mouth</span>
              {micActive ? (
                <div className="dev-mic-bar">
                  <div className="dev-mic-bar-fill" style={{ width: `${micAmplitude * 100}%` }} />
                </div>
              ) : (
                <input type="range" className="dev-slider" min={0} max={1} step={0.01}
                  value={amplitude} onChange={(e) => onSetAmplitude(parseFloat(e.target.value))} />
              )}
              <span className={`dev-slider-val ${micActive ? "mic-live" : ""}`}>
                {micActive ? micAmplitude.toFixed(2) : amplitude.toFixed(2)}
              </span>
              <button className={`dev-chip sm dev-mic-btn ${micActive ? "active" : ""}`}
                onClick={onToggleMic} title={micActive ? "Stop mic" : "Test with mic"}>
                MIC
              </button>
            </div>
            {micActive && (
              <>
                <SliderRow label="Sens" value={micSensitivity} min={0} max={1} step={0.05}
                  onChange={onSetMicSensitivity} fmt={(v) => `${Math.round(v * 100)}%`} />
                <AudioTuner tuning={audioTuning} onChange={onSetAudioTuning} />
              </>
            )}
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
              {[1, 1.5, 2, 2.5, 3].map((s) => (
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

    </div>

    {/* Log sidebar — expands to the right */}
    {logOpen && (
      <div className="dev-log-sidebar">
        <div className="dev-log-header">
          <span>Log</span>
          <button className="dev-log-close" onClick={() => setLogOpen(false)}>×</button>
        </div>
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

/* ── Audio tuner (live-adjustable waveform params) ───────────────── */
const AUDIO_PARAMS = [
  { key: "smoothing",     label: "Smooth",    min: 0.01, max: 0.5,  step: 0.01, fmt: (v) => v.toFixed(2) },
  { key: "decay",         label: "Decay",     min: 0.95, max: 0.999,step: 0.001,fmt: (v) => v.toFixed(3) },
  { key: "gamma",         label: "Gamma",     min: 0.3,  max: 1.5,  step: 0.05, fmt: (v) => v.toFixed(2) },
  { key: "waveSmoothing", label: "W.Smooth",  min: 0.05, max: 0.6,  step: 0.01, fmt: (v) => v.toFixed(2) },
  { key: "waveDecay",     label: "W.Decay",   min: 0.95, max: 0.999,step: 0.001,fmt: (v) => v.toFixed(3) },
  { key: "waveSpeed",     label: "W.Speed",   min: 0.01, max: 0.2,  step: 0.005,fmt: (v) => v.toFixed(3) },
  { key: "waveGain",      label: "W.Gain",    min: 0,    max: 0.6,  step: 0.02, fmt: (v) => v.toFixed(2) },
  { key: "minAmp",        label: "Min Amp",   min: 0,    max: 0.2,  step: 0.01, fmt: (v) => v.toFixed(2) },
  { key: "maxAmp",        label: "Max Amp",   min: 0.5,  max: 3.0,  step: 0.1,  fmt: (v) => v.toFixed(1) },
];

function AudioTuner({ tuning, onChange }) {
  const update = (key, value) => onChange((prev) => ({ ...prev, [key]: value }));
  return (
    <div className="dev-audio-tuner">
      <span className="dev-label" style={{ marginBottom: 2 }}>Audio Tuning</span>
      {AUDIO_PARAMS.map(({ key, label, min, max, step, fmt }) => (
        <div key={key} className="dev-slider-row">
          <span className="dev-slider-label">{label}</span>
          <input type="range" className="dev-slider" min={min} max={max} step={step}
            value={tuning[key]} onChange={(e) => update(key, parseFloat(e.target.value))} />
          <span className="dev-slider-val">{fmt(tuning[key])}</span>
        </div>
      ))}
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
