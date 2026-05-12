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

    # Games start directly in CARD_CREATION — no separate lobby step. Late joiners
    # can still hop in while card_creation is open.
    game = Game(code=code, phase=GamePhase.CARD_CREATION)
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
    """Join an existing game as a new player, or rejoin a disconnected slot.

    Brand-new players may join while the game is in LOBBY (legacy) or
    CARD_CREATION. Once the game has reached PLAYING / FINISHED, only the
    rejoin-by-name path is available for a disconnected player to come back.

    Args:
        code: The game code to join.
        display_name: Desired display name.

    Returns:
        Dict with session_token, player_id, and player data.

    Raises:
        GameNotFoundError: If no game with that code exists.
        PhaseMismatchError: If the game has started and no reconnect match exists.
        DisplayNameTakenError: If the name is taken by a connected player.
    """
    game = _get_game_or_404(code)

    # Check if a player with this name already exists in the game (case-insensitive)
    existing_player = db.session.execute(
        db.select(Player).where(
            Player.game_id == game.id,
            db.func.lower(Player.display_name) == display_name.lower(),
        )
    ).scalar_one_or_none()

    # --- Reconnect path: same display name + disconnected → reattach to existing row.
    # Works in every phase (including card_creation) so a player who drops in the
    # initial stage can still come back with their original name.
    if existing_player is not None:
        if existing_player.is_connected:
            raise DisplayNameTakenError()
        new_token = generate_session_token()
        existing_player.session_token = new_token
        existing_player.is_connected = True
        db.session.commit()

        return {
            "session_token": new_token,
            "player_id": existing_player.id,
            "player": _player_dict(existing_player),
        }

    # --- New-join path: brand-new player. Only allowed while card_creation is open
    # (LOBBY kept here for legacy DB rows; new games skip lobby entirely).
    if game.phase not in (GamePhase.LOBBY, GamePhase.CARD_CREATION):
        raise PhaseMismatchError("This game has already started and is not accepting new players.")

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


def remove_player(
    game: Game, requesting_player: Player, target_player_id: int
) -> dict[str, Any]:
    """Host removes another player during the card_creation phase.

    Card creation is the only phase where a connected-but-idle player can wedge
    the game (they keep is_ready=False and block /begin). In every other phase
    disconnect handling is sufficient, so removal is intentionally not allowed.

    Args:
        game: The Game instance.
        requesting_player: Must be the game creator.
        target_player_id: The player to remove.

    Returns:
        Snapshot of the deleted player (id, display_name, session_token) so the
        caller can notify the kicked client's socket after the row is gone.

    Raises:
        ForbiddenError: If requester isn't the creator, or target is the creator.
        PhaseMismatchError: If the game is not in card_creation phase.
        ValidationError: If target_player_id doesn't belong to this game.
    """
    from ..errors import ValidationError

    _assert_creator(game, requesting_player)
    if game.phase != GamePhase.CARD_CREATION:
        raise PhaseMismatchError("Players can only be removed during card creation.")

    target = db.session.get(Player, target_player_id)
    if target is None or target.game_id != game.id:
        raise ValidationError("Player not found in this game.")
    if target.id == game.creator_id:
        raise ForbiddenError("The host cannot remove themselves.")

    snapshot = {
        "id": target.id,
        "display_name": target.display_name,
        "session_token": target.session_token,
    }

    from ..models.card import Card
    # Safe in card_creation because cards have not been redistributed yet —
    # holder_id still equals creator_id, so deleting by creator_id removes
    # exactly the cards this player would have contributed to the pool.
    db.session.execute(
        db.delete(Card).where(Card.game_id == game.id, Card.creator_id == target.id)
    )
    db.session.delete(target)
    db.session.commit()
    return snapshot


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
