"""Game lifecycle service — creation, joining, starting, and finishing games."""
from typing import Any
from ..extensions import db
from ..models.game import Game, GamePhase
from ..models.player import Player, PlayerRole
from ..utils.code_generator import generate_game_code
from ..utils.token_generator import generate_session_token
from ..errors import (
    GameNotFoundError,
    DisplayNameTakenError,
    PhaseMismatchError,
    ForbiddenError,
)


def create_game(display_name: str, role: str) -> dict[str, Any]:
    """Create a new game and its creator player.

    Args:
        display_name: The creator's chosen display name.
        role: "player" or "spectator".

    Returns:
        Dict with game_code, session_token, player_id, and player data.
    """
    # Generate a unique game code
    for _ in range(10):
        code = generate_game_code()
        existing = db.session.execute(
            db.select(Game).where(Game.code == code)
        ).scalar_one_or_none()
        if existing is None:
            break
    else:
        code = generate_game_code()  # Accept small collision risk after 10 attempts

    game = Game(code=code, phase=GamePhase.LOBBY)
    db.session.add(game)
    db.session.flush()  # Get game.id without committing

    player_role = PlayerRole.SPECTATOR if role == "spectator" else PlayerRole.PLAYER
    token = generate_session_token()
    player = Player(
        game_id=game.id,
        display_name=display_name,
        role=player_role,
        session_token=token,
        join_order=0,
        is_ready=False,
        score=0,
        is_connected=True,
    )
    db.session.add(player)
    db.session.flush()

    game.creator_id = player.id
    db.session.commit()

    return {
        "game_code": game.code,
        "session_token": token,
        "player_id": player.id,
        "player": _player_dict(player),
    }


def join_game(code: str, display_name: str) -> dict[str, Any]:
    """Join an existing lobby game as a player.

    Args:
        code: The game code to join.
        display_name: Desired display name.

    Returns:
        Dict with session_token, player_id, and player data.

    Raises:
        GameNotFoundError: If no game with that code exists.
        PhaseMismatchError: If the game is not in the lobby phase.
        DisplayNameTakenError: If the name is already taken in this game.
    """
    game = _get_game_or_404(code)

    if game.phase != GamePhase.LOBBY:
        raise PhaseMismatchError("This game has already started and is not accepting new players.")

    # Check name uniqueness within this game
    existing_name = db.session.execute(
        db.select(Player).where(
            Player.game_id == game.id,
            Player.display_name == display_name,
        )
    ).scalar_one_or_none()
    if existing_name is not None:
        raise DisplayNameTakenError()

    next_order = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(Player.game_id == game.id)
    ).scalar() or 0

    token = generate_session_token()
    player = Player(
        game_id=game.id,
        display_name=display_name,
        role=PlayerRole.PLAYER,
        session_token=token,
        join_order=next_order,
        is_ready=False,
        score=0,
        is_connected=True,
    )
    db.session.add(player)
    db.session.commit()

    return {
        "session_token": token,
        "player_id": player.id,
        "player": _player_dict(player),
    }


def start_game(game: Game, requesting_player: Player) -> None:
    """Transition a game from lobby to card_creation phase.

    Args:
        game: The Game instance.
        requesting_player: Must be the game creator.

    Raises:
        ForbiddenError: If the requester is not the creator.
        PhaseMismatchError: If the game is not in the lobby phase.
    """
    _assert_creator(game, requesting_player)
    if game.phase != GamePhase.LOBBY:
        raise PhaseMismatchError("Game is not in the lobby phase.")

    # Need at least 2 players (non-spectator) to start
    player_count = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(
            Player.game_id == game.id,
            Player.role == PlayerRole.PLAYER,
        )
    ).scalar() or 0

    if player_count < 2:
        raise PhaseMismatchError("At least 2 players are required to start.")

    game.phase = GamePhase.CARD_CREATION
    db.session.commit()


def finish_game(game: Game, requesting_player: Player) -> None:
    """Delete all game data once the game is finished.

    Args:
        game: The Game instance.
        requesting_player: Must be the game creator.

    Raises:
        ForbiddenError: If the requester is not the creator.
    """
    _assert_creator(game, requesting_player)

    from ..models.vote import Vote
    from ..models.submission import Submission
    from ..models.card import Card
    from ..models.round import Round

    game_id = game.id
    round_ids = [
        r.id for r in db.session.execute(
            db.select(Round).where(Round.game_id == game_id)
        ).scalars().all()
    ]

    if round_ids:
        db.session.execute(db.delete(Vote).where(Vote.round_id.in_(round_ids)))
        db.session.execute(db.delete(Submission).where(Submission.round_id.in_(round_ids)))

    db.session.execute(db.delete(Round).where(Round.game_id == game_id))
    db.session.execute(db.delete(Card).where(Card.game_id == game_id))

    # Decouple foreign keys before deleting
    game.creator_id = None
    game.current_round_id = None
    db.session.flush()

    db.session.execute(db.delete(Player).where(Player.game_id == game_id))
    db.session.delete(game)
    db.session.commit()


def get_game_state_for_player(game: Game, requesting_player: Player) -> dict[str, Any]:
    """Return full game state enriched with the requesting player's private hand.

    Args:
        game: The Game instance.
        requesting_player: The player requesting the state.

    Returns:
        Dict combining the public game state and the player's private cards.
    """
    from .state_service import build_game_state_payload, build_hand_payload
    state = build_game_state_payload(game)
    hand = build_hand_payload(requesting_player)
    state["my_cards"] = hand["cards"]
    return state


def _get_game_or_404(code: str) -> Game:
    """Fetch game by code or raise GameNotFoundError.

    Args:
        code: The game code to look up.

    Returns:
        The matching Game instance.

    Raises:
        GameNotFoundError: If not found.
    """
    game = db.session.execute(
        db.select(Game).where(Game.code == code.upper())
    ).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError()
    return game


def _assert_creator(game: Game, player: Player) -> None:
    """Raise ForbiddenError if player is not the game creator.

    Args:
        game: The Game instance.
        player: The player to check.

    Raises:
        ForbiddenError: If the player is not the creator.
    """
    if game.creator_id != player.id:
        raise ForbiddenError("Only the game creator can perform this action.")


def _player_dict(player: Player) -> dict[str, Any]:
    """Serialise a Player instance to a dict.

    Args:
        player: The Player instance.

    Returns:
        Dict with player fields.
    """
    return {
        "id": player.id,
        "display_name": player.display_name,
        "role": player.role.value,
        "join_order": player.join_order,
        "score": player.score,
        "is_connected": player.is_connected,
        "is_ready": player.is_ready,
    }
