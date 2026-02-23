"""Socket.IO emitter helpers — the only place that calls socketio.emit()."""
from typing import Any
from ..extensions import db, socketio
from ..models.game import Game
from ..models.player import Player


# In-memory mapping of session_token → socket_id for targeted hand delivery.
# Acceptable for single-instance Railway deployment. Refreshed on each join_game_room event.
_token_to_sid: dict[str, str] = {}


def register_socket(session_token: str, sid: str) -> None:
    """Associate a session token with a Socket.IO session ID.

    Args:
        session_token: The player's session token.
        sid: The Socket.IO session ID.
    """
    _token_to_sid[session_token] = sid


def unregister_socket(sid: str) -> str | None:
    """Remove a socket mapping by sid and return the associated token if found.

    Args:
        sid: The Socket.IO session ID to remove.

    Returns:
        The session token that was removed, or None.
    """
    for token, socket_id in list(_token_to_sid.items()):
        if socket_id == sid:
            del _token_to_sid[token]
            return token
    return None


def emit_game_state(game: Game) -> None:
    """Broadcast the full game state to all clients in the game's room.

    Args:
        game: The Game instance.
    """
    from ..services.state_service import build_game_state_payload
    payload = build_game_state_payload(game)
    socketio.emit("game_state_updated", payload, room=game.code)


def emit_hand_to_player(player: Player) -> None:
    """Send the player's private hand to their individual socket only.

    Args:
        player: The Player instance whose hand to emit.
    """
    from ..services.state_service import build_hand_payload
    sid = _token_to_sid.get(player.session_token)
    if sid:
        payload = build_hand_payload(player)
        socketio.emit("your_cards_updated", payload, to=sid)


def emit_hand_to_all(game: Game) -> None:
    """Send each player's private hand to their individual socket after redistribution.

    Args:
        game: The Game instance.
    """
    for player in game.players:
        if not player.is_spectator:
            emit_hand_to_player(player)


def emit_player_connection_changed(game: Game, player_id: int, is_connected: bool) -> None:
    """Broadcast a player connection status change to the game room.

    Args:
        game: The Game instance.
        player_id: The ID of the player whose status changed.
        is_connected: The new connection status.
    """
    socketio.emit(
        "player_connection_changed",
        {"type": "player_connection_changed", "player_id": player_id, "is_connected": is_connected},
        room=game.code,
    )
