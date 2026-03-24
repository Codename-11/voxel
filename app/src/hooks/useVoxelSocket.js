import { useState, useEffect, useCallback, useRef } from "react";

const WS_URL = `ws://${window.location.hostname || "localhost"}:8080`;
const RECONNECT_DELAY = 2000;

/**
 * WebSocket hook — connects to the Voxel backend server.
 * Receives state updates (mood, style, speaking, battery, etc.)
 * and provides send() for commands.
 */
export default function useVoxelSocket() {
  const [state, setState] = useState({
    mood: "neutral",
    style: "kawaii",
    speaking: false,
    amplitude: 0.0,
    battery: 100,
    state: "IDLE",
    agent: "daemon",
    brightness: 80,
    volume: 80,
    agents: [],
    connected: false,
    transcript: null,
    chatHistory: [],
  });
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setWsConnected(true);
        console.log("[voxel] WebSocket connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "state") {
            setState((prev) => ({ ...prev, ...data }));
          } else if (data.type === "button") {
            setState((prev) => ({
              ...prev,
              buttonEvent: { id: Date.now(), button: data.button },
            }));
          } else if (data.type === "transcript") {
            setState((prev) => ({
              ...prev,
              transcript: data,
              // Append to local chat history for immediate display
              chatHistory: [
                ...prev.chatHistory,
                { role: data.role, text: data.text, timestamp: data.timestamp },
              ].slice(-50),
            }));
          } else if (data.type === "chat_history") {
            setState((prev) => ({
              ...prev,
              chatHistory: data.messages || [],
            }));
          }
        } catch (e) {
          console.warn("[voxel] Invalid message:", event.data);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        wsRef.current = null;
        // Auto-reconnect
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch (e) {
      reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // Convenience methods
  const setMood = useCallback((mood) => send({ type: "set_mood", mood }), [send]);
  const setStyle = useCallback((style) => send({ type: "set_style", style }), [send]);
  const cycleState = useCallback(() => send({ type: "cycle_state" }), [send]);
  const pressButton = useCallback((button) => send({ type: "button", button }), [send]);
  const setAgent = useCallback((agent) => send({ type: "set_agent", agent }), [send]);
  const setSetting = useCallback((section, key, value) => (
    send({ type: "set_setting", section, key, value })
  ), [send]);
  const sendTextInput = useCallback((text) => send({ type: "text_input", text }), [send]);

  return {
    state,
    wsConnected,
    send,
    setMood,
    setStyle,
    cycleState,
    pressButton,
    setAgent,
    setSetting,
    sendTextInput,
  };
}
