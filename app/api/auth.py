"""Session token authentication decorator and helper."""
from functools import wraps
from typing import Callable, Any
from flask import request, g
from ..extensions import db
from ..models.player import Player
from ..errors import UnauthorizedError


def require_auth(f: Callable) -> Callable:
    """Decorator that validates the X-Session-Token header and populates g.player.

    Raises:
        UnauthorizedError: If the token is missing or does not match any player.
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        token = request.headers.get("X-Session-Token")
        if not token:
            raise UnauthorizedError()
        player = db.session.execute(
            db.select(Player).where(Player.session_token == token)
        ).scalar_one_or_none()
        if player is None:
            raise UnauthorizedError()
        g.player = player
        return f(*args, **kwargs)

    return decorated


def get_player_by_token(token: str) -> Player | None:
    """Retrieve a player by session token without raising.

    Args:
        token: The session token to look up.

    Returns:
        The matching Player or None.
    """
    return db.session.execute(
        db.select(Player).where(Player.session_token == token)
    ).scalar_one_or_none()
