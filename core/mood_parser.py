"""Parse mood from AI responses — tag extraction + keyword fallback."""

import logging
import re
from typing import Optional

log = logging.getLogger("voxel.core.mood_parser")

# Valid moods (must match shared/expressions.yaml mood names)
VALID_MOODS = {
    "neutral", "happy", "curious", "thinking", "confused",
    "excited", "sleepy", "listening", "sad", "surprised",
    "focused", "frustrated", "working", "error",
}

# Tag pattern: [mood] at start of response
_TAG_PATTERN = re.compile(r'^\s*\[(\w+)\]\s*')

# Keyword → mood mapping for fallback sentiment
_KEYWORDS: dict[str, list[str]] = {
    "happy": ["great", "awesome", "wonderful", "fantastic", "love", "glad", "happy", "yay", "excellent"],
    "excited": ["exciting", "amazing", "incredible", "wow", "!!", "absolutely"],
    "sad": ["sorry", "unfortunately", "sadly", "bad news", "regret"],
    "curious": ["interesting", "hmm", "wonder", "curious", "fascinating"],
    "confused": ["not sure", "unclear", "confusing", "don't know", "uncertain"],
    "thinking": ["let me think", "considering", "perhaps", "maybe"],
    "surprised": ["really", "no way", "unexpected", "surprise", "didn't expect"],
    "frustrated": ["error", "failed", "can't", "unable", "problem", "issue"],
}


def extract_mood(text: str) -> tuple[str, str]:
    """Extract mood from response text.

    Returns (mood, clean_text) where clean_text has the tag removed.
    Falls back to keyword sentiment if no tag found.
    """
    if not text:
        return "neutral", text

    # Try tag extraction first
    match = _TAG_PATTERN.match(text)
    if match:
        mood = match.group(1).lower()
        if mood in VALID_MOODS:
            clean = text[match.end():].strip()
            log.debug(f"Mood tag extracted: {mood}")
            return mood, clean
        else:
            log.debug(f"Ignoring unknown mood tag: {mood}")

    # Fallback: keyword sentiment
    mood = _keyword_sentiment(text)
    if mood != "neutral":
        log.debug(f"Mood from keywords: {mood}")
    return mood, text


def _keyword_sentiment(text: str) -> str:
    """Simple keyword-based mood detection."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for mood, keywords in _KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[mood] = score

    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]
    return "neutral"
