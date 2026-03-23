"""Expression/mood definitions for the cube mascot."""

from dataclasses import dataclass, field
from enum import Enum, auto


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
class Expression:
    """Complete expression definition."""
    mood: Mood
    eyes: EyeConfig = field(default_factory=EyeConfig)
    mouth: MouthConfig = field(default_factory=MouthConfig)
    body: BodyConfig = field(default_factory=BodyConfig)


# Predefined expressions
EXPRESSIONS: dict[Mood, Expression] = {
    Mood.NEUTRAL: Expression(
        mood=Mood.NEUTRAL,
        eyes=EyeConfig(openness=0.9, blink_rate=3.0),
        mouth=MouthConfig(smile=0.2),
        body=BodyConfig(bounce_speed=0.3, bounce_amount=1.5),
    ),
    Mood.HAPPY: Expression(
        mood=Mood.HAPPY,
        eyes=EyeConfig(openness=0.85, height=0.9, squint=0.2, blink_rate=2.0),
        mouth=MouthConfig(smile=0.8, openness=0.2),
        body=BodyConfig(bounce_speed=0.7, bounce_amount=3.0),
    ),
    Mood.CURIOUS: Expression(
        mood=Mood.CURIOUS,
        eyes=EyeConfig(openness=1.0, width=1.1, height=1.1, pupil_size=0.5, blink_rate=1.5),
        mouth=MouthConfig(smile=0.1, openness=0.15),
        body=BodyConfig(tilt=8.0, scale=1.02),
    ),
    Mood.THINKING: Expression(
        mood=Mood.THINKING,
        eyes=EyeConfig(openness=0.7, gaze_x=0.6, gaze_y=-0.4, squint=0.3, blink_rate=1.0),
        mouth=MouthConfig(smile=0.0, openness=0.05),
        body=BodyConfig(tilt=-5.0, bounce_speed=0.2),
    ),
    Mood.CONFUSED: Expression(
        mood=Mood.CONFUSED,
        eyes=EyeConfig(openness=0.95, width=1.05, pupil_size=0.35, blink_rate=4.0),
        mouth=MouthConfig(smile=-0.3, openness=0.1),
        body=BodyConfig(tilt=12.0),
    ),
    Mood.EXCITED: Expression(
        mood=Mood.EXCITED,
        eyes=EyeConfig(openness=1.0, width=1.15, height=1.15, pupil_size=0.5, blink_rate=2.0),
        mouth=MouthConfig(smile=1.0, openness=0.4),
        body=BodyConfig(bounce_speed=1.2, bounce_amount=5.0),
    ),
    Mood.SLEEPY: Expression(
        mood=Mood.SLEEPY,
        eyes=EyeConfig(openness=0.25, height=0.7, blink_rate=0.5),
        mouth=MouthConfig(smile=0.0, openness=0.0),
        body=BodyConfig(bounce_speed=0.15, bounce_amount=1.0, tilt=3.0),
    ),
    Mood.ERROR: Expression(
        mood=Mood.ERROR,
        eyes=EyeConfig(openness=1.0, pupil_size=0.0),  # X_X rendered specially
        mouth=MouthConfig(smile=-0.5, openness=0.0),
        body=BodyConfig(bounce_speed=0.0, bounce_amount=0.0),
    ),
    Mood.LISTENING: Expression(
        mood=Mood.LISTENING,
        eyes=EyeConfig(openness=1.0, width=1.05, height=1.05, pupil_size=0.45, blink_rate=1.0),
        mouth=MouthConfig(smile=0.15, openness=0.1),
        body=BodyConfig(scale=1.03, tilt=2.0, bounce_speed=0.4),
    ),
}
