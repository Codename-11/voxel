import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useCallback, useRef } from "react";
import "./NotificationToast.css";

/**
 * NotificationToast — slides down from the top, auto-dismisses after 3s.
 *
 * Usage:
 *   const { notify, toastElement } = useNotificationToast();
 *   notify("Connected to Daemon");
 *   // Render {toastElement} inside the device frame
 */
export function useNotificationToast() {
  const [messages, setMessages] = useState([]);
  const counterRef = useRef(0);

  const notify = useCallback((text, duration = 3000) => {
    const id = ++counterRef.current;
    setMessages((prev) => [...prev, { id, text }]);
    setTimeout(() => {
      setMessages((prev) => prev.filter((m) => m.id !== id));
    }, duration);
  }, []);

  const toastElement = (
    <div className="toast-container">
      <AnimatePresence>
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            className="toast"
            initial={{ y: -30, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -20, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
          >
            {msg.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );

  return { notify, toastElement };
}

export default function NotificationToast({ message, visible, onDone }) {
  useEffect(() => {
    if (visible && onDone) {
      const t = setTimeout(onDone, 3000);
      return () => clearTimeout(t);
    }
  }, [visible, onDone]);

  return (
    <AnimatePresence>
      {visible && message && (
        <motion.div
          className="toast-container"
          initial={{ y: -30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -20, opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
          <div className="toast">{message}</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
