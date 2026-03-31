import { useState, useEffect, useCallback, useRef } from "react";

/**
 * useVoice — browser-based STT (Web Speech API) and TTS (speechSynthesis).
 *
 * STT: Uses SpeechRecognition / webkitSpeechRecognition for voice input.
 * TTS: Uses window.speechSynthesis to read assistant messages aloud.
 *
 * Works standalone (no backend) — transcribed text is returned via onResult
 * so the caller can decide whether to send it over WebSocket or display locally.
 */

const SpeechRecognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export default function useVoice() {
  // ── STT state ──
  const [sttSupported] = useState(() => !!SpeechRecognition);
  const [listening, setListening] = useState(false);
  const [sttTranscript, setSttTranscript] = useState("");
  const [sttError, setSttError] = useState(null);
  const recognitionRef = useRef(null);

  // ── TTS state ──
  const [ttsSupported] = useState(
    () => typeof window !== "undefined" && "speechSynthesis" in window,
  );
  const [ttsEnabled, setTtsEnabled] = useState(() => {
    try {
      return localStorage.getItem("voxel-tts-enabled") === "true";
    } catch {
      return false;
    }
  });
  const [ttsSpeaking, setTtsSpeaking] = useState(false);
  const utteranceRef = useRef(null);

  // Persist TTS preference
  useEffect(() => {
    try {
      localStorage.setItem("voxel-tts-enabled", ttsEnabled ? "true" : "false");
    } catch {
      // localStorage unavailable
    }
  }, [ttsEnabled]);

  // ── STT: start listening ──
  const startListening = useCallback(() => {
    if (!SpeechRecognition) {
      setSttError("Speech recognition not supported in this browser");
      return;
    }

    // Stop any existing recognition
    if (recognitionRef.current) {
      try { recognitionRef.current.abort(); } catch { /* ignore */ }
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      setListening(true);
      setSttError(null);
      setSttTranscript("");
    };

    recognition.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }
      setSttTranscript(final || interim);
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        setSttError("Microphone permission denied");
      } else if (event.error === "no-speech") {
        setSttError(null); // silent timeout, not really an error
      } else if (event.error !== "aborted") {
        setSttError(`Speech recognition error: ${event.error}`);
      }
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch (e) {
      setSttError(`Failed to start: ${e.message}`);
      setListening(false);
    }
  }, []);

  // ── STT: stop listening ──
  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
    }
    setListening(false);
  }, []);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch { /* ignore */ }
      }
    };
  }, []);

  // ── TTS: speak text ──
  const speak = useCallback(
    (text) => {
      if (!ttsSupported || !ttsEnabled || !text) return;

      // Cancel any current speech
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      utterance.onstart = () => setTtsSpeaking(true);
      utterance.onend = () => setTtsSpeaking(false);
      utterance.onerror = () => setTtsSpeaking(false);

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [ttsSupported, ttsEnabled],
  );

  // ── TTS: cancel speech ──
  const cancelSpeech = useCallback(() => {
    if (ttsSupported) {
      window.speechSynthesis.cancel();
    }
    setTtsSpeaking(false);
  }, [ttsSupported]);

  // ── TTS: toggle on/off ──
  const toggleTts = useCallback(() => {
    setTtsEnabled((prev) => {
      if (prev) {
        // Turning off — cancel any current speech
        window.speechSynthesis.cancel();
        setTtsSpeaking(false);
      }
      return !prev;
    });
  }, []);

  // Cancel speech on unmount
  useEffect(() => {
    return () => {
      if (ttsSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [ttsSupported]);

  return {
    // STT
    sttSupported,
    listening,
    sttTranscript,
    sttError,
    startListening,
    stopListening,

    // TTS
    ttsSupported,
    ttsEnabled,
    ttsSpeaking,
    speak,
    cancelSpeech,
    toggleTts,
  };
}
