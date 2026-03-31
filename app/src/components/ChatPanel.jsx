import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "./ChatPanel.css";

/* ── Inline SVG icons ──────────────────────────────────────── */

function MicIcon({ active }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="1" width="6" height="12" rx="3" fill={active ? "currentColor" : "none"} />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function SpeakerIcon({ enabled }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill={enabled ? "currentColor" : "none"} />
      {enabled ? (
        <>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
        </>
      ) : (
        <line x1="23" y1="9" x2="17" y2="15" />
      )}
    </svg>
  );
}

/**
 * ChatPanel — conversation history + text input + voice controls.
 *
 * On the 240x280 LCD: compact overlay sliding up from bottom.
 * On remote browser: taller panel with full history and text input.
 */
export default function ChatPanel({
  messages = [],
  visible = false,
  onSendText,
  onClose,
  currentAgent = "vxl",
  stateName = "IDLE",
  wsConnected = false,
  voice = null,
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const busy = stateName === "THINKING" || stateName === "SPEAKING" || stateName === "LISTENING";

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (visible && inputRef.current) {
      inputRef.current.focus();
    }
  }, [visible]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    onSendText?.(text);
    setInput("");
  };

  // Handle mic button press
  const handleMicToggle = () => {
    if (!voice) return;
    if (voice.listening) {
      voice.stopListening();
    } else {
      voice.startListening();
    }
  };

  // When STT produces a final transcript, send it as text input
  const lastSentRef = useRef("");
  useEffect(() => {
    if (!voice || voice.listening || !voice.sttTranscript) return;
    const text = voice.sttTranscript.trim();
    if (!text || text === lastSentRef.current) return;
    lastSentRef.current = text;
    onSendText?.(text);
  }, [voice?.listening, voice?.sttTranscript, onSendText]);

  // Deduplicate consecutive transcripts (backend sends status updates)
  const deduped = [];
  for (const msg of messages) {
    const last = deduped[deduped.length - 1];
    if (
      last &&
      last.role === msg.role &&
      Math.abs((last.timestamp || 0) - (msg.timestamp || 0)) < 2
    ) {
      // Update text of the last message (later transcript replaces earlier)
      deduped[deduped.length - 1] = msg;
    } else {
      deduped.push(msg);
    }
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="chat-panel"
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
        >
          {/* Header */}
          <div className="chat-header">
            <span className="chat-title">chat</span>
            <button className="chat-close" onClick={onClose}>
              ×
            </button>
          </div>

          {/* Messages */}
          <div className="chat-messages" ref={scrollRef}>
            {deduped.length === 0 && (
              <div className="chat-empty">
                No messages yet. Type below or press the button to talk.
              </div>
            )}
            {deduped.map((msg, i) => (
              <div
                key={`${msg.timestamp}-${i}`}
                className={`chat-msg chat-msg--${msg.role}`}
              >
                <span className="chat-msg-label">
                  {msg.role === "user"
                    ? "you"
                    : msg.role === "system"
                      ? "sys"
                      : msg.agent || currentAgent}
                </span>
                <span className="chat-msg-text">{msg.text}</span>
              </div>
            ))}
            {busy && (
              <div className="chat-msg chat-msg--system">
                <span className="chat-msg-label">···</span>
                <span className="chat-msg-text chat-thinking">
                  {stateName === "LISTENING"
                    ? "listening…"
                    : stateName === "THINKING"
                      ? "thinking…"
                      : "speaking…"}
                </span>
              </div>
            )}
          </div>

          {/* No-backend indicator */}
          {!wsConnected && (
            <div className="chat-no-backend">
              No backend — voice-only mode
            </div>
          )}

          {/* Voice STT error */}
          {voice?.sttError && (
            <div className="chat-stt-error">{voice.sttError}</div>
          )}

          {/* Voice STT interim transcript */}
          {voice?.listening && voice.sttTranscript && (
            <div className="chat-stt-interim">
              {voice.sttTranscript}
            </div>
          )}

          {/* Text input + voice controls */}
          <form className="chat-input-row" onSubmit={handleSubmit}>
            {voice?.sttSupported && (
              <button
                className={`chat-mic ${voice.listening ? "chat-mic--active" : ""}`}
                type="button"
                onClick={handleMicToggle}
                disabled={busy && !voice.listening}
                title={voice.listening ? "Stop listening" : "Speak"}
              >
                <MicIcon active={voice.listening} />
              </button>
            )}
            <input
              ref={inputRef}
              className="chat-input"
              type="text"
              placeholder={voice?.listening ? "listening…" : busy ? "wait…" : "type a message…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy || voice?.listening}
              maxLength={500}
            />
            <button
              className="chat-send"
              type="submit"
              disabled={busy || !input.trim()}
            >
              ▸
            </button>
            {voice?.ttsSupported && (
              <button
                className={`chat-tts-toggle ${voice.ttsEnabled ? "chat-tts-toggle--on" : ""}`}
                type="button"
                onClick={voice.toggleTts}
                title={voice.ttsEnabled ? "Disable voice output" : "Enable voice output"}
              >
                <SpeakerIcon enabled={voice.ttsEnabled} />
              </button>
            )}
          </form>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
