import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "./ChatPanel.css";

/**
 * ChatPanel — conversation history + text input.
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

          {/* Text input */}
          <form className="chat-input-row" onSubmit={handleSubmit}>
            <input
              ref={inputRef}
              className="chat-input"
              type="text"
              placeholder={busy ? "wait…" : "type a message…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              maxLength={500}
            />
            <button
              className="chat-send"
              type="submit"
              disabled={busy || !input.trim()}
            >
              ▸
            </button>
          </form>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
