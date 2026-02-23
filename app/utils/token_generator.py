"""Generates cryptographically secure session tokens."""
import secrets


def generate_session_token() -> str:
    """Generate a 64-character hexadecimal session token.

    Returns:
        A cryptographically secure hex token string.
    """
    return secrets.token_hex(32)
