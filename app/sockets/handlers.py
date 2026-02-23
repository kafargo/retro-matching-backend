"""Socket.IO event handlers."""
from flask import request
from flask_socketio import join_room, leave_room
from ..extensions import socketio, db
from ..models.player import Player
from ..models.game import Game
from .emitters import register_socket, unregister_socket, emit_player_connection_changed


@socketio.on("join_game_room")
def handle_join_game_room(data: dict) -> None:
    """Handle a client joining (or rejoining) a game room.

    Associates the socket with the game room and marks the player as connected.

    Args:
        data: Dict containing game_code and session_token.
    """
    game_code = (data.get("game_code") or "").upper()
    session_token = data.get("session_token") or ""

    if not game_code or not session_token:
        return

    player = db.session.execute(
        db.select(Player).where(Player.session_token == session_token)
    ).scalar_one_or_none()

    if player is None:
        return

    game = db.session.execute(
        db.select(Game).where(Game.code == game_code)
    ).scalar_one_or_none()

    if game is None or player.game_id != game.id:
        return

    join_room(game_code)
    register_socket(session_token, request.sid)

    if not player.is_connected:
        player.is_connected = True
        db.session.commit()
        emit_player_connection_changed(game, player.id, True)


@socketio.on("leave_game_room")
def handle_leave_game_room(data: dict) -> None:
    """Handle a client intentionally leaving a game room.

    Args:
        data: Dict containing game_code and session_token.
    """
    game_code = (data.get("game_code") or "").upper()
    session_token = data.get("session_token") or ""

    if not game_code or not session_token:
        return

    player = db.session.execute(
        db.select(Player).where(Player.session_token == session_token)
    ).scalar_one_or_none()

    if player:
        leave_room(game_code)
        unregister_socket(request.sid)
        player.is_connected = False
        db.session.commit()

        game = db.session.get(Game, player.game_id)
        if game:
            emit_player_connection_changed(game, player.id, False)


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handle unexpected socket disconnection.

    Marks the associated player as disconnected without removing them from the game.
    """
    token = unregister_socket(request.sid)
    if token is None:
        return

    player = db.session.execute(
        db.select(Player).where(Player.session_token == token)
    ).scalar_one_or_none()

    if player:
        player.is_connected = False
        db.session.commit()

        game = db.session.get(Game, player.game_id)
        if game:
            emit_player_connection_changed(game, player.id, False)
