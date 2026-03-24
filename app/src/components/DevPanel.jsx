import { useState, useRef, useEffect, useCallback } from "react";
import { MOOD_LIST } from "../expressions";
import { STYLE_LIST, STYLES } from "../styles";
import "./DevPanel.css";

const STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"];
const AGENTS = ["Daemon", "Soren", "Ash", "Mira", "Jace", "Pip"];

const SHORTCUT_HELP = [
  ["` (backtick)", "Toggle dev panel"],
  ["1-9, 0", "Select mood (by index)"],
  ["S", "Cycle style"],
  ["Space", "Cycle state"],
  ["[ / ]", "Prev / next mood"],
  ["+ / -", "Amplitude +/- 0.1"],
];

/**
 * DevPanel — comprehensive controls for testing and tuning the Voxel character face.
 * All state is managed by the parent (App.jsx); this component receives values
 * and setter callbacks as props.
 */
export default function DevPanel({
  // Current values
  mood,
  style,
  stateName,
  speaking,
  amplitude,
  battery,
  agent,
  transitionSpeed,
  splitView,
  wsConnected,
  expressionOverride,
  logs,
  // Setters
  onSetMood,
  onSetStyle,
  onSetState,
  onSetAmplitude,
  onSetBattery,
  onSetAgent,
  onSetTransitionSpeed,
  onSetSplitView,
  onSetExpressionOverride,
}) {
  const [tunerOpen, setTunerOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const logEndRef = useRef(null);

  // Auto-scroll log viewer
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const updateOverride = useCallback(
    (section, key, value) => {
      onSetExpressionOverride((prev) => ({
        ...prev,
        [section]: {
          ...(prev[section] || {}),
          [key]: value,
        },
      }));
    },
    [onSetExpressionOverride],
  );

  const resetOverride = useCallback(() => {
    onSetExpressionOverride({ eyes: {}, mouth: {}, body: {} });
  }, [onSetExpressionOverride]);

  return (
    <div className="dev-panel">
      {/* ── Style ──────────────────────────────────────────── */}
      <h3>
        Style
        {!wsConnected && <span className="offline-badge">offline</span>}
      </h3>
      <div className="mood-grid">
        {STYLE_LIST.map((s) => (
          <button
            key={s}
            className={`mood-btn ${style === s ? "active" : ""}`}
            onClick={() => onSetStyle(s)}
            title={STYLES[s]?.description}
          >
            {STYLES[s]?.name || s}
          </button>
        ))}
      </div>

      {/* ── Mood ──────────────────────────────────────────── */}
      <h3>Mood</h3>
      <div className="mood-grid">
        {MOOD_LIST.map((m) => (
          <button
            key={m}
            className={`mood-btn ${mood === m ? "active" : ""}`}
            onClick={() => onSetMood(m)}
          >
            {m}
          </button>
        ))}
      </div>

      {/* ── State Flow ────────────────────────────────────── */}
      <h3>State</h3>
      <div className="state-row">
        {STATES.map((s) => (
          <button
            key={s}
            className={`state-btn ${stateName === s ? "active" : ""}`}
            onClick={() => onSetState(s)}
          >
            {s}
          </button>
        ))}
      </div>

      {/* ── Agent Selector ────────────────────────────────── */}
      <h3>Agent</h3>
      <div className="agent-row">
        {AGENTS.map((a) => (
          <button
            key={a}
            className={`mood-btn agent-btn ${agent === a ? "active" : ""}`}
            onClick={() => onSetAgent(a)}
          >
            {a}
          </button>
        ))}
      </div>

      {/* ── Amplitude Slider ──────────────────────────────── */}
      <h3>Amplitude</h3>
      <div className="slider-row">
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={amplitude}
          onChange={(e) => onSetAmplitude(parseFloat(e.target.value))}
          className="dev-slider"
        />
        <span className="slider-value">{amplitude.toFixed(2)}</span>
      </div>

      {/* ── Battery Slider ────────────────────────────────── */}
      <h3>Battery</h3>
      <div className="slider-row">
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          value={battery}
          onChange={(e) => onSetBattery(parseInt(e.target.value, 10))}
          className="dev-slider"
        />
        <span className={`slider-value ${battery < 20 ? "warn" : ""} ${battery < 5 ? "crit" : ""}`}>
          {battery}%
        </span>
      </div>

      {/* ── Transition Speed ──────────────────────────────── */}
      <h3>Transition Speed</h3>
      <div className="slider-row">
        <input
          type="range"
          min="0.1"
          max="3.0"
          step="0.1"
          value={transitionSpeed}
          onChange={(e) => onSetTransitionSpeed(parseFloat(e.target.value))}
          className="dev-slider"
        />
        <span className="slider-value">{transitionSpeed.toFixed(1)}x</span>
      </div>

      {/* ── Split View Toggle ─────────────────────────────── */}
      <h3>View</h3>
      <button
        className={`mood-btn full-width ${splitView ? "active" : ""}`}
        onClick={() => onSetSplitView(!splitView)}
      >
        {splitView ? "Single View" : "Split View (3 styles)"}
      </button>

      {/* ── Expression Tuner ──────────────────────────────── */}
      <h3
        className="collapsible"
        onClick={() => setTunerOpen(!tunerOpen)}
      >
        Expression Tuner {tunerOpen ? "[-]" : "[+]"}
      </h3>
      {tunerOpen && (
        <div className="tuner-section">
          <div className="tuner-group">
            <span className="tuner-label">Eye</span>
            <TunerSlider
              label="openness"
              min={0} max={1} step={0.01}
              value={expressionOverride.eyes?.openness}
              fallback={null}
              onChange={(v) => updateOverride("eyes", "openness", v)}
            />
            <TunerSlider
              label="gazeX"
              min={-1} max={1} step={0.01}
              value={expressionOverride.eyes?.gazeX}
              fallback={null}
              onChange={(v) => updateOverride("eyes", "gazeX", v)}
            />
            <TunerSlider
              label="gazeY"
              min={-1} max={1} step={0.01}
              value={expressionOverride.eyes?.gazeY}
              fallback={null}
              onChange={(v) => updateOverride("eyes", "gazeY", v)}
            />
            <TunerSlider
              label="squint"
              min={0} max={1} step={0.01}
              value={expressionOverride.eyes?.squint}
              fallback={null}
              onChange={(v) => updateOverride("eyes", "squint", v)}
            />
          </div>
          <div className="tuner-group">
            <span className="tuner-label">Mouth</span>
            <TunerSlider
              label="smile"
              min={-1} max={1} step={0.01}
              value={expressionOverride.mouth?.smile}
              fallback={null}
              onChange={(v) => updateOverride("mouth", "smile", v)}
            />
            <TunerSlider
              label="openness"
              min={0} max={1} step={0.01}
              value={expressionOverride.mouth?.openness}
              fallback={null}
              onChange={(v) => updateOverride("mouth", "openness", v)}
            />
          </div>
          <div className="tuner-group">
            <span className="tuner-label">Body</span>
            <TunerSlider
              label="bounceSpeed"
              min={0} max={2} step={0.01}
              value={expressionOverride.body?.bounceSpeed}
              fallback={null}
              onChange={(v) => updateOverride("body", "bounceSpeed", v)}
            />
            <TunerSlider
              label="bounceAmount"
              min={0} max={8} step={0.1}
              value={expressionOverride.body?.bounceAmount}
              fallback={null}
              onChange={(v) => updateOverride("body", "bounceAmount", v)}
            />
            <TunerSlider
              label="tilt"
              min={-15} max={15} step={0.5}
              value={expressionOverride.body?.tilt}
              fallback={null}
              onChange={(v) => updateOverride("body", "tilt", v)}
            />
            <TunerSlider
              label="scale"
              min={0.9} max={1.1} step={0.005}
              value={expressionOverride.body?.scale}
              fallback={null}
              onChange={(v) => updateOverride("body", "scale", v)}
            />
          </div>
          <button className="mood-btn full-width reset-btn" onClick={resetOverride}>
            Reset Overrides
          </button>
        </div>
      )}

      {/* ── Keyboard Shortcuts ────────────────────────────── */}
      <h3
        className="collapsible"
        onClick={() => setShortcutsOpen(!shortcutsOpen)}
      >
        Keyboard Shortcuts {shortcutsOpen ? "[-]" : "[+]"}
      </h3>
      {shortcutsOpen && (
        <div className="shortcuts-list">
          {SHORTCUT_HELP.map(([key, desc]) => (
            <div key={key} className="shortcut-row">
              <kbd>{key}</kbd>
              <span>{desc}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Log Viewer ────────────────────────────────────── */}
      <h3>Log</h3>
      <div className="log-viewer">
        {logs.map((entry, i) => (
          <div key={i} className="log-entry">
            <span className="log-time">{entry.time}</span>
            <span className="log-msg">{entry.msg}</span>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

/* ── Tuner Slider sub-component ─────────────────────────────── */

function TunerSlider({ label, min, max, step, value, onChange }) {
  // value can be undefined/null when no override is set
  const hasValue = value !== undefined && value !== null;
  const displayVal = hasValue ? value : (min + max) / 2;

  return (
    <div className="tuner-slider-row">
      <label className="tuner-slider-label">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={displayVal}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className={`dev-slider tuner-slider ${!hasValue ? "inactive" : ""}`}
      />
      <span className={`tuner-value ${!hasValue ? "inactive" : ""}`}>
        {hasValue ? displayVal.toFixed(2) : "--"}
      </span>
    </div>
  );
}
