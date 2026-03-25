import { useState, useEffect, useCallback, useRef } from "react";
import VoxelCube from "./components/VoxelCube";
import StatusBar from "./components/StatusBar";
import DevPanel from "./components/DevPanel";
import { MenuOverlay } from "./components/menu";
import { useNotificationToast } from "./components/NotificationToast";
import TranscriptOverlay from "./components/TranscriptOverlay";
import ChatPanel from "./components/ChatPanel";
import SpeakingPill from "./components/SpeakingPill";
import { MOOD_LIST } from "./expressions";
import { STYLE_LIST, STYLES, DEFAULT_STYLE } from "./styles";
import useVoxelSocket from "./hooks/useVoxelSocket";
import useAudioAmplitude from "./hooks/useAudioAmplitude";
import "./App.css";

// Agent definitions (from config/default.yaml)
const AGENTS = [
  { id: "daemon", name: "Daemon", emoji: "\u{1F5A4}", description: "Lead agent \u2014 coordinator" },
  { id: "soren", name: "Soren", emoji: "\u2B50", description: "Senior architect" },
  { id: "ash", name: "Ash", emoji: "\u{1F529}", description: "Builder/executor" },
  { id: "mira", name: "Mira", emoji: "\u{1F4C8}", description: "Business operator" },
  { id: "jace", name: "Jace", emoji: "\u{1F504}", description: "Flex agent" },
  { id: "pip", name: "Pip", emoji: "\u{1F4CB}", description: "Intern" },
];

const STATES = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"];

function timestamp() {
  return new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function App() {
  const { state, wsConnected, send, setMood, setStyle, setAgent, setSetting, sendTextInput } =
    useVoxelSocket();
  const [devMode, setDevMode] = useState(false);

  // Dev panel state
  const [amplitude, setAmplitude] = useState(0);
  const [audioTuning, setAudioTuning] = useState({
    // useAudioAmplitude (mic processing)
    smoothing: 0.14,    // per-frame ease toward target
    decay: 0.988,       // target decay between inputs
    gamma: 0.7,         // power curve
    // AudioWaveform (SVG rendering)
    waveSmoothing: 0.25, // waveform ease speed
    waveDecay: 0.992,    // waveform target decay
    waveSpeed: 0.065,    // base phase step (wave scroll speed)
    waveGain: 0.2,       // how much amplitude affects wave speed
    minAmp: 0.03,        // wave noise floor
    maxAmp: 1.3,         // wave ceiling
  });
  const mic = useAudioAmplitude(audioTuning);

  // Local overrides for when backend isn't connected (standalone dev)
  const [localMood, setLocalMood] = useState("neutral");
  const [localStyle, setLocalStyle] = useState(DEFAULT_STYLE);
  const [localSpeaking, setLocalSpeaking] = useState(false);
  const [localAgent, setLocalAgent] = useState("Daemon");
  const [localState, setLocalState] = useState("IDLE");

  const [localBattery, setLocalBattery] = useState(100);
  const [transitionSpeed, setTransitionSpeed] = useState(1.0);
  const [splitView, setSplitView] = useState(false);
  const [previewScale, setPreviewScale] = useState(2.0);
  const [expressionOverride, setExpressionOverride] = useState({
    eyes: {},
    mouth: {},
    body: {},
  });
  const [logs, setLogs] = useState([]);

  // Menu and chat state (UI-only, not sent to backend)
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [brightness, setBrightness] = useState(80);
  const [volume, setVolume] = useState(80);

  // Transcript state — driven by backend when connected
  const [transcript, setTranscript] = useState({
    user: "",
    voxel: "",
    visible: false,
  });
  const transcriptTimerRef = useRef(null);

  // Notification toast
  const { notify, toastElement } = useNotificationToast();

  // Use backend state when connected, local state when not
  const mood = wsConnected ? state.mood : localMood;
  const style = wsConnected ? state.style : localStyle;
  const speaking = wsConnected ? state.speaking : localSpeaking;
  const battery = wsConnected ? state.battery : localBattery;
  const agents = wsConnected && state.agents?.length ? state.agents : AGENTS;
  const effectiveBrightness = wsConnected ? state.brightness ?? brightness : brightness;
  const effectiveVolume = wsConnected ? state.volume ?? volume : volume;
  const stateName = menuOpen
    ? "MENU"
    : wsConnected
      ? state.state
      : localState;
  const currentAgent = wsConnected
    ? state.agent || "daemon"
    : localAgent;

  // Get agent info -- match by id or name
  const agentInfo =
    agents.find((a) => a.id === currentAgent || a.name === currentAgent) ||
    agents[0] ||
    AGENTS[0];

  // ── Logging utility ──────────────────────────────────────
  const addLog = useCallback((msg) => {
    setLogs((prev) => {
      const next = [...prev, { time: timestamp(), msg }];
      return next.length > 20 ? next.slice(-20) : next;
    });
  }, []);

  // ── Battery -> mood auto-switch ──────────────────────────
  const prevBatteryMoodRef = useRef(null);
  useEffect(() => {
    if (wsConnected) return; // let backend handle it
    if (battery < 5 && prevBatteryMoodRef.current !== "criticalBattery") {
      setLocalMood("criticalBattery");
      prevBatteryMoodRef.current = "criticalBattery";
      addLog("Battery critical (<5%) -> mood: criticalBattery");
    } else if (
      battery >= 5 &&
      battery < 20 &&
      prevBatteryMoodRef.current !== "lowBattery"
    ) {
      setLocalMood("lowBattery");
      prevBatteryMoodRef.current = "lowBattery";
      addLog("Battery low (<20%) -> mood: lowBattery");
    } else if (battery >= 20 && prevBatteryMoodRef.current) {
      prevBatteryMoodRef.current = null;
    }
  }, [battery, wsConnected, addLog]);

  // ── Handlers ─────────────────────────────────────────────

  const handleSetMood = useCallback(
    (m) => {
      if (wsConnected) setMood(m);
      else setLocalMood(m);
      prevBatteryMoodRef.current = null;
      addLog(`Mood: ${mood} -> ${m}`);
    },
    [wsConnected, setMood, mood, addLog],
  );

  const handleSetStyle = useCallback(
    (s) => {
      if (wsConnected) setStyle(s);
      else setLocalStyle(s);
      addLog(`Style: ${s}`);
    },
    [wsConnected, setStyle, addLog],
  );

  const handleSetState = useCallback(
    (s) => {
      if (wsConnected) {
        send({ type: "set_state", state: s });
      } else {
        setLocalState(s);
        setLocalSpeaking(s === "SPEAKING");
      }
      addLog(`State: ${s}`);
    },
    [wsConnected, send, addLog],
  );

  const handleSetAmplitude = useCallback((v) => {
    setAmplitude(v);
  }, []);

  const handleSetBattery = useCallback((v) => {
    setLocalBattery(v);
  }, []);

  const handleSetAgent = useCallback(
    (agentIdOrName) => {
      const agent = agents.find(
        (a) => a.id === agentIdOrName || a.name === agentIdOrName,
      );
      if (!agent) return;
      if (wsConnected) {
        setAgent?.(agent.id);
      } else {
        setLocalAgent(agent.name);
      }
      addLog(`Agent: ${agent.name}`);
      notify(`Connected to ${agent.name}`);
    },
    [agents, wsConnected, setAgent, addLog, notify],
  );

  const handleSelectAgent = useCallback(
    (agentId) => {
      const agent = agents.find((a) => a.id === agentId);
      if (!agent) return;
      handleSetAgent(agent.id);
    },
    [agents, handleSetAgent],
  );

  const handleSetBrightness = useCallback(
    (value) => {
      setBrightness(value);
      if (wsConnected) {
        setSetting("display", "brightness", value);
      }
    },
    [wsConnected, setSetting],
  );

  const handleSetVolume = useCallback(
    (value) => {
      setVolume(value);
      if (wsConnected) {
        setSetting("audio", "volume", value);
      }
    },
    [wsConnected, setSetting],
  );

  const handleMenuClose = useCallback(() => {
    setMenuOpen(false);
    if (wsConnected) setMood("neutral");
    else setLocalMood("neutral");
  }, [wsConnected, setMood]);

  // ── Keyboard shortcuts (single listener) ─────────────────
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")
        return;

      // Backtick: toggle dev panel
      if (e.key === "`") {
        setDevMode((d) => !d);
        return;
      }

      // M: toggle menu
      if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        setMenuOpen((prev) => !prev);
        return;
      }

      // C: toggle chat panel
      if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        setChatOpen((prev) => !prev);
        return;
      }

      // Remaining shortcuts only active when dev panel is visible
      if (!devMode) return;

      // 1-9, 0: select mood by index
      if (e.key >= "1" && e.key <= "9") {
        const idx = parseInt(e.key, 10) - 1;
        if (idx < MOOD_LIST.length) handleSetMood(MOOD_LIST[idx]);
        return;
      }
      if (e.key === "0") {
        if (9 < MOOD_LIST.length) handleSetMood(MOOD_LIST[9]);
        return;
      }

      // S: cycle style
      if (e.key === "s" || e.key === "S") {
        const idx = STYLE_LIST.indexOf(style);
        handleSetStyle(STYLE_LIST[(idx + 1) % STYLE_LIST.length]);
        return;
      }

      // Space: cycle state
      if (e.key === " ") {
        e.preventDefault();
        const cur = wsConnected ? state.state : localState;
        const idx = STATES.indexOf(cur);
        handleSetState(STATES[(idx + 1) % STATES.length]);
        return;
      }

      // [ / ]: prev/next mood
      if (e.key === "[") {
        const idx = MOOD_LIST.indexOf(mood);
        handleSetMood(
          MOOD_LIST[(idx - 1 + MOOD_LIST.length) % MOOD_LIST.length],
        );
        return;
      }
      if (e.key === "]") {
        const idx = MOOD_LIST.indexOf(mood);
        handleSetMood(MOOD_LIST[(idx + 1) % MOOD_LIST.length]);
        return;
      }

      // + / -: amplitude up/down by 0.1
      if (e.key === "+" || e.key === "=") {
        setAmplitude((a) => Math.min(1, +(a + 0.1).toFixed(2)));
        return;
      }
      if (e.key === "-" || e.key === "_") {
        setAmplitude((a) => Math.max(0, +(a - 0.1).toFixed(2)));
        return;
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    devMode,
    mood,
    style,
    localState,
    wsConnected,
    state.state,
    handleSetMood,
    handleSetStyle,
    handleSetState,
  ]);

  // Log WebSocket connection changes
  const prevConnectedRef = useRef(wsConnected);
  useEffect(() => {
    if (prevConnectedRef.current !== wsConnected) {
      addLog(
        wsConnected
          ? "WebSocket connected"
          : "WebSocket disconnected (standalone mode)",
      );
      prevConnectedRef.current = wsConnected;
    }
  }, [wsConnected, addLog]);

  // Handle WebSocket button events for menu
  useEffect(() => {
    if (wsConnected && state.buttonEvent?.button) {
      const btn = state.buttonEvent.button;
      addLog(`WS button: ${btn}`);
      if (btn === "menu") {
        setMenuOpen((prev) => !prev);
      } else if (menuOpen) {
        window.dispatchEvent(
          new CustomEvent("voxel-button", { detail: { button: btn } }),
        );
      }
    }
  }, [wsConnected, state.buttonEvent, menuOpen, addLog]);

  // Auto-show dev panel when no backend connected
  useEffect(() => {
    if (!wsConnected) setDevMode(true);
  }, [wsConnected]);

  // Wire backend transcript to overlay
  useEffect(() => {
    if (!wsConnected || !state.transcript) return;
    const t = state.transcript;
    if (t.status === "error") return; // errors don't go in transcript overlay

    setTranscript((prev) => ({
      user: t.role === "user" ? t.text : prev.user,
      voxel: t.role === "assistant" ? t.text : prev.voxel,
      visible: true,
    }));

    // Clear auto-hide timer and set a new one
    clearTimeout(transcriptTimerRef.current);
  }, [wsConnected, state.transcript]);

  // Auto-hide transcript after returning to IDLE
  useEffect(() => {
    if (stateName === "IDLE" && transcript.visible) {
      transcriptTimerRef.current = setTimeout(() => {
        setTranscript((prev) => ({ ...prev, visible: false }));
      }, 5000);
    }
    return () => clearTimeout(transcriptTimerRef.current);
  }, [stateName, transcript.visible]);

  // Check if expression override has any non-empty values
  const hasOverride = Object.values(expressionOverride).some(
    (section) =>
      section &&
      Object.values(section).some((v) => v !== undefined && v !== null),
  );

  // Mic overrides manual amplitude when active
  const effectiveAmplitude = mic.isActive ? mic.amplitude : amplitude;

  // Common VoxelCube props
  const cubeProps = {
    mood,
    speaking: speaking || effectiveAmplitude > 0,
    amplitude: effectiveAmplitude,
    expressionOverride: hasOverride ? expressionOverride : null,
    transitionSpeed,
  };

  return (
    <div className={devMode ? "workspace" : "workspace production"}>
      {/* Main viewport */}
      <div>
        {splitView && devMode ? (
          /* Split view: 3 cubes side by side, one per style */
          <>
            <div className="split-view-row" style={{ zoom: previewScale }}>
              {STYLE_LIST.map((s) => (
                <div key={s} className="split-view-col">
                  <div className="split-view-frame">
                    <div
                      className={
                        menuOpen
                          ? "face-layer face-layer--dimmed"
                          : "face-layer"
                      }
                    >
                      <VoxelCube {...cubeProps} styleName={s} />
                    </div>
                    <SpeakingPill speaking={speaking || effectiveAmplitude > 0} amplitude={effectiveAmplitude} tuning={audioTuning} />
                    <StatusBar
                      agentName={agentInfo.name}
                      agentEmoji={agentInfo.emoji}
                      stateName={stateName}
                      battery={battery}
                      connected={wsConnected}
                    />
                  </div>
                  <div className="split-view-label">
                    {STYLES[s]?.name || s}
                  </div>
                </div>
              ))}
            </div>
            <div className="label">
              Split View -- {wsConnected ? "connected" : "standalone"}
            </div>
          </>
        ) : (
          /* Normal single view */
          <>
            <div className="preview-scaler" style={devMode && previewScale !== 1 ? { zoom: previewScale } : undefined}>
            <div className="device-frame" id="voxel-viewport">
              <div
                className={
                  menuOpen ? "face-layer face-layer--dimmed" : "face-layer"
                }
              >
                <VoxelCube {...cubeProps} styleName={style} />
              </div>

              {toastElement}

              <TranscriptOverlay
                userText={transcript.user}
                voxelText={transcript.voxel}
                visible={transcript.visible && !menuOpen && !chatOpen}
              />

              <ChatPanel
                messages={state.chatHistory || []}
                visible={chatOpen && !menuOpen}
                onSendText={sendTextInput}
                onClose={() => setChatOpen(false)}
                currentAgent={agentInfo?.name || "vxl"}
                stateName={stateName}
              />

              <MenuOverlay
                open={menuOpen}
                onClose={handleMenuClose}
                agents={agents}
                currentAgent={currentAgent}
                onSelectAgent={handleSelectAgent}
                battery={battery}
                brightness={effectiveBrightness}
                volume={effectiveVolume}
                onSetBrightness={handleSetBrightness}
                onSetVolume={handleSetVolume}
                onSetMood={handleSetMood}
              />

              <SpeakingPill speaking={speaking || effectiveAmplitude > 0} amplitude={effectiveAmplitude} tuning={audioTuning} />

              <StatusBar
                agentName={agentInfo.name}
                agentEmoji={agentInfo.emoji}
                stateName={stateName}
                battery={battery}
                connected={wsConnected}
              />
            </div>
            </div>{/* close preview-scaler */}
            {devMode && (
              <div className="label">
                {previewScale === 1 ? "1:1 real size" : `${previewScale}x`} — {wsConnected ? "connected" : "standalone"}
              </div>
            )}
          </>
        )}
      </div>

      {/* Dev controls panel -- toggle with backtick key */}
      {devMode && (
        <DevPanel
          mood={mood}
          style={style}
          stateName={stateName}
          speaking={speaking}
          amplitude={amplitude}
          battery={battery}
          agent={agentInfo.name}
          transitionSpeed={transitionSpeed}
          splitView={splitView}
          wsConnected={wsConnected}
          expressionOverride={expressionOverride}
          logs={logs}
          onSetMood={handleSetMood}
          onSetStyle={handleSetStyle}
          onSetState={handleSetState}
          onSetAmplitude={handleSetAmplitude}
          onSetBattery={handleSetBattery}
          onSetAgent={handleSetAgent}
          onSetTransitionSpeed={setTransitionSpeed}
          onSetSplitView={setSplitView}
          previewScale={previewScale}
          onSetPreviewScale={setPreviewScale}
          onSetExpressionOverride={setExpressionOverride}
          micActive={mic.isActive}
          micAmplitude={mic.amplitude}
          onToggleMic={() => mic.isActive ? mic.stop() : mic.start()}
          micSensitivity={mic.sensitivity}
          onSetMicSensitivity={mic.setSensitivity}
          audioTuning={audioTuning}
          onSetAudioTuning={setAudioTuning}
        />
      )}
    </div>
  );
}

export default App;
