"""Adjective list and random picker for round prompts."""
import random
from typing import List

ADJECTIVES: List[str] = [
    "Funny",
    "Sad",
    "Miserable",
    "Tolerable",
    "Exciting",
    "Inspiring",
    "Exhausting",
    "Surprising",
    "Awkward",
    "Brilliant",
    "Chaotic",
    "Delightful",
    "Embarrassing",
    "Frustrating",
    "Groundbreaking",
    "Hilarious",
    "Insightful",
    "Jarring",
    "Legendary",
    "Mysterious",
    "Nostalgic",
    "Overwhelming",
    "Perplexing",
    "Refreshing",
    "Reassuring",
    "Stressful",
    "Transformative",
    "Unexpected",
    "Vivid",
    "Wholesome",
    "Anxious",
    "Bold",
    "Calm",
    "Dramatic",
    "Energetic",
    "Fearless",
    "Gloomy",
    "Hopeful",
    "Intense",
    "Joyful",
    "Complicated",
    "Satisfying",
    "Memorable",
    "Powerful",
    "Quiet",
]


def pick_adjective() -> str:
    """Return a randomly selected adjective from the list.

    Returns:
        A random adjective string.
    """
    return random.choice(ADJECTIVES)
