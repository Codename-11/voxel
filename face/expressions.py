"""Expression/mood definitions for the cube mascot."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Mood(Enum):
    NEUTRAL = auto()
    HAPPY = auto()
    CURIOUS = auto()
    THINKING = auto()
    CONFUSED = auto()
    EXCITED = auto()
    SLEEPY = auto()
    ERROR = auto()
    LISTENING = auto()
    SAD = auto()
    SURPRISED = auto()
    FOCUSED = auto()
    FRUSTRATED = auto()
    WORKING = auto()
    LOW_BATTERY = auto()
    CRITICAL_BATTERY = auto()


@dataclass
class EyeConfig:
    """Defines how the eyes look for a given expression."""
    width: float = 1.0          # Scale factor (1.0 = normal)
    height: float = 1.0         # Scale factor
    openness: float = 1.0       # 0.0 = closed, 1.0 = fully open
    pupil_size: float = 0.4     # Relative to eye size
    gaze_x: float = 0.0        # -1.0 (left) to 1.0 (right)
    gaze_y: float = 0.0        # -1.0 (up) to 1.0 (down)
    blink_rate: float = 3.0     # Blinks per ~10 seconds
    squint: float = 0.0         # 0.0 = none, 1.0 = full squint


@dataclass
class MouthConfig:
    """Defines how the mouth looks for a given expression."""
    openness: float = 0.0       # 0.0 = closed, 1.0 = fully open
    smile: float = 0.3          # -1.0 = frown, 0.0 = neutral, 1.0 = smile
    width: float = 1.0          # Scale factor


@dataclass
class BodyConfig:
    """Defines body language for a given expression."""
    bounce_speed: float = 0.5   # Idle bounce animation speed
    bounce_amount: float = 2.0  # Pixels of vertical bounce
    tilt: float = 0.0           # Degrees of head tilt (-15 to 15)
    scale: float = 1.0          # Body scale (for "leaning in" effect)


@dataclass
class PerEyeOverride:
    """Optional per-eye overrides (left or right) layered on top of EyeConfig."""
    openness: Optional[float] = None
    height: Optional[float] = None
    width: Optional[float] = None
    squint: Optional[float] = None
    tilt: Optional[float] = None


@dataclass
class Expression:
    """Complete expression definition."""
    mood: Mood
    eyes: EyeConfig = field(default_factory=EyeConfig)
    mouth: MouthConfig = field(default_factory=MouthConfig)
    body: BodyConfig = field(default_factory=BodyConfig)
    left_eye: Optional[PerEyeOverride] = None
    right_eye: Optional[PerEyeOverride] = None
    eye_color_override: Optional[str] = None


# Predefined expressions — values match design/src/expressions.js exactly
EXPRESSIONS: dict[Mood, Expression] = {
    Mood.NEUTRAL: Expression(
        mood=Mood.NEUTRAL,
        eyes=EyeConfig(width=1.0, height=1.0, openness=0.9, pupil_size=0.4,
                        gaze_x=0, gaze_y=0, blink_rate=3.0, squint=0),
        mouth=MouthConfig(openness=0, smile=0.3, width=1.0),
        body=BodyConfig(bounce_speed=0.3, bounce_amount=2, tilt=0, scale=1.0),
    ),
    Mood.HAPPY: Expression(
        mood=Mood.HAPPY,
        # Happy squint — both eyes narrow, big U smile (closed mouth, high smile)
        eyes=EyeConfig(width=1.05, height=0.75, openness=0.7, pupil_size=0.4,
                        gaze_x=0, gaze_y=0, blink_rate=2.0, squint=0),
        mouth=MouthConfig(openness=0, smile=1.0, width=1.3),
        body=BodyConfig(bounce_speed=0.7, bounce_amount=4, tilt=0, scale=1.0),
    ),
    Mood.CURIOUS: Expression(
        mood=Mood.CURIOUS,
        eyes=EyeConfig(width=1.1, height=1.1, openness=1.0, pupil_size=0.5,
                        gaze_x=0, gaze_y=0, blink_rate=1.5, squint=0),
        mouth=MouthConfig(openness=0.15, smile=0.1, width=1.0),
        body=BodyConfig(bounce_speed=0.4, bounce_amount=2, tilt=8, scale=1.02),
    ),
    Mood.THINKING: Expression(
        mood=Mood.THINKING,
        eyes=EyeConfig(width=1.0, height=1.0, openness=0.75, pupil_size=0.35,
                        gaze_x=0.4, gaze_y=-0.2, blink_rate=1.0, squint=0),
        # Gentle raised eyebrow — left open, right slightly narrower
        left_eye=PerEyeOverride(openness=0.9, height=1.05),
        right_eye=PerEyeOverride(openness=0.45, height=0.65),
        mouth=MouthConfig(openness=0, smile=0.0, width=0.85),
        body=BodyConfig(bounce_speed=0.2, bounce_amount=1, tilt=-4, scale=1.0),
    ),
    Mood.CONFUSED: Expression(
        mood=Mood.CONFUSED,
        eyes=EyeConfig(width=1.0, height=1.0, openness=0.9, pupil_size=0.35,
                        gaze_x=0, gaze_y=0, blink_rate=4.0, squint=0),
        # Subtle asymmetry — one eye slightly bigger
        left_eye=PerEyeOverride(openness=1.0, height=1.08),
        right_eye=PerEyeOverride(openness=0.7, height=0.85),
        mouth=MouthConfig(openness=0, smile=-0.15, width=0.9),
        body=BodyConfig(bounce_speed=0.3, bounce_amount=2, tilt=8, scale=1.0),
    ),
    Mood.EXCITED: Expression(
        mood=Mood.EXCITED,
        eyes=EyeConfig(width=1.15, height=1.15, openness=1.0, pupil_size=0.5,
                        gaze_x=0, gaze_y=0, blink_rate=2.0, squint=0),
        mouth=MouthConfig(openness=0.4, smile=1.0, width=1.0),
        body=BodyConfig(bounce_speed=1.2, bounce_amount=6, tilt=0, scale=1.0),
    ),
    Mood.SLEEPY: Expression(
        mood=Mood.SLEEPY,
        eyes=EyeConfig(width=1.0, height=0.7, openness=0.25, pupil_size=0.4,
                        gaze_x=0, gaze_y=0.2, blink_rate=0.5, squint=0),
        mouth=MouthConfig(openness=0, smile=0.0, width=1.0),
        body=BodyConfig(bounce_speed=0.15, bounce_amount=1, tilt=3, scale=1.0),
    ),
    Mood.ERROR: Expression(
        mood=Mood.ERROR,
        eyes=EyeConfig(width=1.0, height=1.0, openness=1.0, pupil_size=0,
                        gaze_x=0, gaze_y=0, blink_rate=0, squint=0),
        mouth=MouthConfig(openness=0, smile=-0.5, width=1.0),
        body=BodyConfig(bounce_speed=0, bounce_amount=0, tilt=0, scale=1.0),
    ),
    Mood.LISTENING: Expression(
        mood=Mood.LISTENING,
        eyes=EyeConfig(width=1.05, height=1.05, openness=1.0, pupil_size=0.45,
                        gaze_x=0, gaze_y=0, blink_rate=1.0, squint=0),
        mouth=MouthConfig(openness=0.1, smile=0.15, width=1.0),
        body=BodyConfig(bounce_speed=0.4, bounce_amount=2, tilt=2, scale=1.03),
    ),
    Mood.SAD: Expression(
        mood=Mood.SAD,
        eyes=EyeConfig(width=0.95, height=0.9, openness=0.7, pupil_size=0.4,
                        gaze_x=0, gaze_y=0.3, blink_rate=1.0, squint=0),
        left_eye=PerEyeOverride(tilt=-6),
        right_eye=PerEyeOverride(tilt=6),
        mouth=MouthConfig(openness=0, smile=-0.5, width=0.9),
        body=BodyConfig(bounce_speed=0.1, bounce_amount=0.5, tilt=3, scale=0.98),
    ),
    Mood.SURPRISED: Expression(
        mood=Mood.SURPRISED,
        eyes=EyeConfig(width=1.2, height=1.25, openness=1.0, pupil_size=0.35,
                        gaze_x=0, gaze_y=0, blink_rate=0.5, squint=0),
        mouth=MouthConfig(openness=0.5, smile=0.0, width=0.7),
        body=BodyConfig(bounce_speed=0.5, bounce_amount=3, tilt=0, scale=1.04),
    ),
    Mood.FOCUSED: Expression(
        mood=Mood.FOCUSED,
        eyes=EyeConfig(width=1.0, height=0.7, openness=0.65, pupil_size=0.4,
                        gaze_x=0, gaze_y=0, blink_rate=0.8, squint=0.15),
        mouth=MouthConfig(openness=0, smile=0.0, width=0.8),
        body=BodyConfig(bounce_speed=0.15, bounce_amount=0.5, tilt=0, scale=1.0),
    ),
    Mood.FRUSTRATED: Expression(
        mood=Mood.FRUSTRATED,
        eyes=EyeConfig(width=1.0, height=0.8, openness=0.75, pupil_size=0.4,
                        gaze_x=0, gaze_y=0, blink_rate=1.5, squint=0.2),
        # Angry V-shaped — inner edges tilted down
        left_eye=PerEyeOverride(tilt=-12),
        right_eye=PerEyeOverride(tilt=12),
        mouth=MouthConfig(openness=0, smile=-0.5, width=0.85),
        body=BodyConfig(bounce_speed=0.3, bounce_amount=1, tilt=0, scale=1.0),
    ),
    Mood.WORKING: Expression(
        mood=Mood.WORKING,
        eyes=EyeConfig(width=1.0, height=0.8, openness=0.7, pupil_size=0.4,
                        gaze_x=0, gaze_y=0.1, blink_rate=0.8, squint=0.1),
        mouth=MouthConfig(openness=0, smile=0.1, width=0.85),
        body=BodyConfig(bounce_speed=0.25, bounce_amount=1, tilt=0, scale=1.0),
    ),
    Mood.LOW_BATTERY: Expression(
        mood=Mood.LOW_BATTERY,
        eyes=EyeConfig(width=0.9, height=0.8, openness=0.5, pupil_size=0.35,
                        gaze_x=0, gaze_y=0.3, blink_rate=0.8, squint=0.1),
        mouth=MouthConfig(openness=0, smile=-0.2, width=0.8),
        body=BodyConfig(bounce_speed=0.1, bounce_amount=0.5, tilt=8, scale=0.97),
        eye_color_override="#d4a020",  # amber/yellow dim
    ),
    Mood.CRITICAL_BATTERY: Expression(
        mood=Mood.CRITICAL_BATTERY,
        eyes=EyeConfig(width=0.85, height=0.7, openness=0.3, pupil_size=0.3,
                        gaze_x=0, gaze_y=0.4, blink_rate=0.3, squint=0.15),
        mouth=MouthConfig(openness=0, smile=-0.4, width=0.7),
        body=BodyConfig(bounce_speed=0.05, bounce_amount=0.3, tilt=14, scale=0.95),
        eye_color_override="#a07818",  # dim amber
    ),
}
