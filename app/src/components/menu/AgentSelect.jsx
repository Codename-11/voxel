import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import "./AgentSelect.css";

/**
 * AgentSelect — grid/list of available agents.
 *
 * Navigation:
 *   left/up    = previous agent
 *   right/down = next agent
 *   enter      = select
 *   escape     = back
 *
 * Props:
 *   agents       - array of { id, name, emoji, description }
 *   currentAgent - currently selected agent id
 *   onSelect     - callback(agentId)
 *   onBack       - callback to go back to main menu
 */
export default function AgentSelect({
  agents = [],
  currentAgent = "daemon",
  onSelect,
  onBack,
}) {
  const currentIndex = agents.findIndex((a) => a.id === currentAgent);
  const [hoveredIndex, setHoveredIndex] = useState(
    currentIndex >= 0 ? currentIndex : 0,
  );

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      switch (e.key) {
        case "ArrowUp":
        case "ArrowLeft":
          e.preventDefault();
          e.stopPropagation();
          setHoveredIndex((i) => (i > 0 ? i - 1 : agents.length - 1));
          break;

        case "ArrowDown":
        case "ArrowRight":
          e.preventDefault();
          e.stopPropagation();
          setHoveredIndex((i) => (i < agents.length - 1 ? i + 1 : 0));
          break;

        case "Enter":
          e.preventDefault();
          e.stopPropagation();
          if (agents[hoveredIndex]) {
            onSelect?.(agents[hoveredIndex].id);
          }
          break;

        case "Escape":
          e.preventDefault();
          e.stopPropagation();
          onBack?.();
          break;

        default:
          break;
      }
    };

    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [agents, hoveredIndex, onSelect, onBack]);

  if (!agents.length) {
    return (
      <div className="agent-select">
        <div className="agent-header">Select Agent</div>
        <div className="agent-empty">No agents configured</div>
      </div>
    );
  }

  return (
    <div className="agent-select">
      <div className="agent-header">Select Agent</div>
      <div className="agent-grid">
        {agents.map((agent, i) => {
          const isActive = agent.id === currentAgent;
          const isHovered = i === hoveredIndex;

          return (
            <motion.div
              key={agent.id}
              className={[
                "agent-card",
                isActive ? "agent-card--active" : "",
                isHovered ? "agent-card--hovered" : "",
              ].join(" ")}
              animate={{
                scale: isHovered ? 1.02 : 1,
                borderColor: isActive
                  ? "var(--vx-cyan)"
                  : isHovered
                    ? "var(--vx-cyan-dim)"
                    : "rgba(40, 40, 58, 0.6)",
              }}
              transition={{ duration: 0.15 }}
              onClick={() => onSelect?.(agent.id)}
              onMouseEnter={() => setHoveredIndex(i)}
            >
              <div className="agent-emoji">{agent.emoji}</div>
              <div className="agent-info">
                <div className="agent-name">{agent.name}</div>
                <div className="agent-desc">{agent.description}</div>
              </div>
              {isActive && <div className="agent-check" />}
            </motion.div>
          );
        })}
      </div>
      <div className="agent-hint">esc = back</div>
    </div>
  );
}
