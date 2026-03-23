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
    connected: false,
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

  return { state, wsConnected, send, setMood, setStyle, cycleState, pressButton };
}
