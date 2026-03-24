import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import AgentSelect from "./AgentSelect";
import "./MenuOverlay.css";

const MENU_ITEMS = [
  { id: "agent", label: "Agent", icon: ">" },
  { id: "voice", label: "Voice", icon: "~" },
  { id: "brightness", label: "Brightness", icon: "*" },
  { id: "volume", label: "Volume", icon: ")" },
  { id: "battery", label: "Battery", icon: "%" },
  { id: "about", label: "About", icon: "i" },
  { id: "close", label: "Close", icon: "x" },
];

/**
 * MenuOverlay — the main settings menu that slides up from the bottom.
 *
 * Navigation:
 *   left button  = move up
 *   right button = move down / select
 *   press        = select (confirm)
 *   menu         = close menu
 *
 * Props:
 *   open        - boolean, whether menu is visible
 *   onClose     - callback to close the menu
 *   onNavigate  - { direction: "up" | "down" | "select" | "back" }
 *   agents      - array of agent objects from config
 *   currentAgent - current agent id
 *   onSelectAgent - callback(agentId)
 *   battery     - current battery level
 *   brightness  - current brightness (0-100)
 *   volume      - current volume (0-100)
 *   onSetBrightness - callback(value)
 *   onSetVolume     - callback(value)
 *   onSetMood       - callback(mood) - for mood changes when browsing
 */
export default function MenuOverlay({
  open,
  onClose,
  agents = [],
  currentAgent = "daemon",
  onSelectAgent,
  battery = 100,
  brightness = 80,
  volume = 80,
  onSetBrightness,
  onSetVolume,
  onSetMood,
}) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [subScreen, setSubScreen] = useState(null); // "agent" | "brightness" | "volume" | null
  const [localBrightness, setLocalBrightness] = useState(brightness);
  const [localVolume, setLocalVolume] = useState(volume);

  // Reset state when menu opens
  useEffect(() => {
    if (open) {
      setSelectedIndex(0);
      setSubScreen(null);
      setLocalBrightness(brightness);
      setLocalVolume(volume);
    }
  }, [open, brightness, volume]);

  const handleSelect = useCallback(
    (itemId) => {
      switch (itemId) {
        case "agent":
          setSubScreen("agent");
          onSetMood?.("curious");
          break;
        case "brightness":
          setSubScreen("brightness");
          break;
        case "volume":
          setSubScreen("volume");
          break;
        case "close":
          onClose?.();
          break;
        case "about":
          setSubScreen("about");
          break;
        case "battery":
          setSubScreen("battery");
          break;
        case "voice":
          // Voice settings placeholder — could be expanded later
          setSubScreen("voice");
          break;
        default:
          break;
      }
    },
    [onClose, onSetMood],
  );

  const handleBack = useCallback(() => {
    if (subScreen) {
      setSubScreen(null);
      onSetMood?.("neutral");
    } else {
      onClose?.();
    }
  }, [subScreen, onClose, onSetMood]);

  // Keyboard / button navigation
  useEffect(() => {
    if (!open) return;

    const onKey = (e) => {
      // Ignore if input/textarea focused
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      switch (e.key) {
        case "ArrowUp":
        case "ArrowLeft":
          e.preventDefault();
          if (subScreen === "brightness") {
            setLocalBrightness((v) => {
              const nv = Math.max(0, v - 10);
              onSetBrightness?.(nv);
              return nv;
            });
          } else if (subScreen === "volume") {
            setLocalVolume((v) => {
              const nv = Math.max(0, v - 10);
              onSetVolume?.(nv);
              return nv;
            });
          } else if (!subScreen) {
            setSelectedIndex((i) => (i > 0 ? i - 1 : MENU_ITEMS.length - 1));
          }
          break;

        case "ArrowDown":
        case "ArrowRight":
          e.preventDefault();
          if (subScreen === "brightness") {
            setLocalBrightness((v) => {
              const nv = Math.min(100, v + 10);
              onSetBrightness?.(nv);
              return nv;
            });
          } else if (subScreen === "volume") {
            setLocalVolume((v) => {
              const nv = Math.min(100, v + 10);
              onSetVolume?.(nv);
              return nv;
            });
          } else if (!subScreen) {
            setSelectedIndex((i) => (i < MENU_ITEMS.length - 1 ? i + 1 : 0));
          }
          break;

        case "Enter":
          e.preventDefault();
          if (subScreen === "brightness" || subScreen === "volume" || subScreen === "about" || subScreen === "battery" || subScreen === "voice") {
            handleBack();
          } else if (!subScreen) {
            handleSelect(MENU_ITEMS[selectedIndex].id);
          }
          break;

        case "Escape":
          e.preventDefault();
          handleBack();
          break;

        default:
          break;
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, subScreen, selectedIndex, handleBack, handleSelect, onSetBrightness, onSetVolume]);

  // Expose navigation handler for WebSocket button events
  useEffect(() => {
    if (!open) return;

    const handler = (e) => {
      const { button } = e.detail || {};
      if (button === "left") {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp" }));
      } else if (button === "right") {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
      } else if (button === "press") {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
      } else if (button === "menu") {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      }
    };

    window.addEventListener("voxel-button", handler);
    return () => window.removeEventListener("voxel-button", handler);
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="menu-overlay"
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "spring", damping: 28, stiffness: 300 }}
        >
          {/* Dimmed backdrop */}
          <div className="menu-backdrop" />

          {/* Menu content */}
          <div className="menu-content">
            <AnimatePresence mode="wait">
              {subScreen === "agent" ? (
                <motion.div
                  key="agent"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <AgentSelect
                    agents={agents}
                    currentAgent={currentAgent}
                    onSelect={(id) => {
                      onSelectAgent?.(id);
                      handleBack();
                    }}
                    onBack={handleBack}
                  />
                </motion.div>
              ) : subScreen === "brightness" ? (
                <motion.div
                  key="brightness"
                  className="menu-sub"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="sub-header">Brightness</div>
                  <SliderDisplay value={localBrightness} label="%" />
                  <div className="sub-hint">left/right to adjust</div>
                </motion.div>
              ) : subScreen === "volume" ? (
                <motion.div
                  key="volume"
                  className="menu-sub"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="sub-header">Volume</div>
                  <SliderDisplay value={localVolume} label="%" />
                  <div className="sub-hint">left/right to adjust</div>
                </motion.div>
              ) : subScreen === "battery" ? (
                <motion.div
                  key="battery"
                  className="menu-sub"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="sub-header">Battery</div>
                  <div className="sub-value-large">{battery}%</div>
                  <div className="sub-hint">
                    {battery > 50 ? "charge good" : battery > 20 ? "getting low" : "charge soon"}
                  </div>
                </motion.div>
              ) : subScreen === "about" ? (
                <motion.div
                  key="about"
                  className="menu-sub"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="sub-header">About</div>
                  <div className="about-info">
                    <div className="about-line">Voxel Relay</div>
                    <div className="about-line dim">v0.1.0</div>
                    <div className="about-line dim">Pi Zero 2W</div>
                    <div className="about-line dim">Whisplay HAT</div>
                    <div className="about-line accent">axiom-labs.ai</div>
                  </div>
                </motion.div>
              ) : subScreen === "voice" ? (
                <motion.div
                  key="voice"
                  className="menu-sub"
                  initial={{ x: 40, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="sub-header">Voice</div>
                  <div className="about-info">
                    <div className="about-line dim">TTS: edge-tts</div>
                    <div className="about-line dim">STT: whisper</div>
                  </div>
                  <div className="sub-hint">per-agent voice</div>
                </motion.div>
              ) : (
                <motion.div
                  key="main"
                  initial={{ x: 0, opacity: 1 }}
                  exit={{ x: -40, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <div className="menu-title">Settings</div>
                  <div className="menu-list">
                    {MENU_ITEMS.map((item, i) => (
                      <motion.div
                        key={item.id}
                        className={`menu-item ${i === selectedIndex ? "menu-item--active" : ""}`}
                        animate={{
                          x: i === selectedIndex ? 4 : 0,
                          backgroundColor:
                            i === selectedIndex
                              ? "rgba(0, 212, 210, 0.08)"
                              : "rgba(0, 0, 0, 0)",
                        }}
                        transition={{ duration: 0.15 }}
                        onClick={() => {
                          setSelectedIndex(i);
                          handleSelect(item.id);
                        }}
                      >
                        <span className="menu-icon">{item.icon}</span>
                        <span className="menu-label">{item.label}</span>
                        {i === selectedIndex && (
                          <span className="menu-cursor" />
                        )}
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SliderDisplay({ value, label = "%" }) {
  const barWidth = Math.round((value / 100) * 100);
  return (
    <div className="slider-display">
      <div className="slider-track">
        <motion.div
          className="slider-fill"
          animate={{ width: `${barWidth}%` }}
          transition={{ duration: 0.15 }}
        />
      </div>
      <span className="slider-value">
        {value}{label}
      </span>
    </div>
  );
}
