"""Generates unique 6-character alphanumeric game codes."""
import random
import string


_ALPHABET = string.ascii_uppercase + string.digits


def generate_game_code(length: int = 6) -> str:
    """Generate a random uppercase alphanumeric game code.

    Args:
        length: Number of characters in the code. Defaults to 6.

    Returns:
        A random uppercase alphanumeric string.
    """
    return "".join(random.choices(_ALPHABET, k=length))
