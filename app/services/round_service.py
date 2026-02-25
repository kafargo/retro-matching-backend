"""Round service — creation, submission handling, and phase transitions."""
from typing import Any
from ..extensions import db
from ..models.game import Game, GamePhase
from ..models.player import Player, PlayerRole
from ..models.round import Round, RoundPhase
from ..models.card import Card
from ..models.submission import Submission
from ..utils.adjectives import pick_adjective
from ..errors import (
    PhaseMismatchError,
    ForbiddenError,
    InvalidCardError,
    AlreadySubmittedError,
)

# The game always lasts exactly 6 rounds.
MAX_ROUNDS = 6


def create_first_round(game: Game) -> Round:
    """Create the first round of a game after begin is clicked.

    Args:
        game: The Game instance transitioning to playing phase.

    Returns:
        The newly created Round instance.
    """
    return _create_round(game, round_number=1)


def create_next_round(game: Game) -> Round:
    """Create the next round after the previous one completes.

    Args:
        game: The Game instance currently in playing phase.

    Returns:
        The newly created Round instance.
    """
    last_round_number = db.session.execute(
        db.select(db.func.max(Round.round_number)).where(Round.game_id == game.id)
    ).scalar() or 0
    return _create_round(game, round_number=last_round_number + 1)


def _create_round(game: Game, round_number: int) -> Round:
    """Internal helper to build and persist a new Round row.

    Args:
        game: The Game instance.
        round_number: The 1-indexed round number.

    Returns:
        The saved Round instance.
    """
    new_round = Round(
        game_id=game.id,
        round_number=round_number,
        adjective=pick_adjective(),
        phase=RoundPhase.SUBMITTING,
    )
    db.session.add(new_round)
    db.session.flush()
    game.current_round_id = new_round.id

    # On the final round every player has exactly 1 card left — auto-submit it
    # and skip straight to voting. Only auto-submit for connected players.
    if round_number >= MAX_ROUNDS:
        players = _eligible_players(game)
        for player in players:
            if not player.is_connected:
                continue
            card = db.session.execute(
                db.select(Card).where(
                    Card.holder_id == player.id,
                    Card.is_played.is_(False),
                    Card.game_id == game.id,
                )
            ).scalar_one_or_none()
            if card is not None:
                card.is_played = True
                card.holder_id = None
                db.session.add(Submission(
                    round_id=new_round.id,
                    player_id=player.id,
                    card_id=card.id,
                ))
        new_round.phase = RoundPhase.VOTING

    db.session.commit()
    return new_round


def submit_card(game: Game, round_obj: Round, player: Player, card_id: int) -> Submission:
    """Record a player's card submission for the current round.

    All non-spectator players submit one card per round.

    Args:
        game: The Game instance.
        round_obj: The current Round.
        player: The submitting player.
        card_id: ID of the card to submit.

    Returns:
        The created Submission instance.

    Raises:
        PhaseMismatchError: If the round is not in the submitting phase.
        ForbiddenError: If the player is a spectator.
        AlreadySubmittedError: If the player already submitted this round.
        InvalidCardError: If the card is not held by the player or already played.
    """
    if round_obj.phase != RoundPhase.SUBMITTING:
        raise PhaseMismatchError("This round is not accepting submissions.")
    if player.is_spectator:
        raise ForbiddenError("Spectators cannot submit cards.")

    # Check for duplicate submission
    existing = db.session.execute(
        db.select(Submission).where(
            Submission.round_id == round_obj.id,
            Submission.player_id == player.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadySubmittedError()

    # Validate card ownership and playability
    card = db.session.get(Card, card_id)
    if card is None or card.holder_id != player.id or card.is_played or card.game_id != game.id:
        raise InvalidCardError("Card is invalid, not in your hand, or already played.")

    # Mark card as played
    card.is_played = True
    card.holder_id = None

    submission = Submission(
        round_id=round_obj.id,
        player_id=player.id,
        card_id=card_id,
    )
    db.session.add(submission)
    db.session.commit()

    return submission


def check_all_submitted(game: Game, round_obj: Round) -> bool:
    """Check whether all connected non-spectator players have submitted for this round.

    Disconnected players are excluded so the game can proceed without them.

    Args:
        game: The Game instance.
        round_obj: The current Round.

    Returns:
        True if all connected non-spectator players have submitted.
    """
    from ..models.player import PlayerRole
    eligible_count = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(
            Player.game_id == game.id,
            Player.is_connected.is_(True),
            Player.role == PlayerRole.PLAYER,
        )
    ).scalar() or 0

    submitted_count = db.session.execute(
        db.select(db.func.count()).select_from(Submission).where(
            Submission.round_id == round_obj.id
        )
    ).scalar() or 0
    return submitted_count >= eligible_count


def begin_voting(round_obj: Round) -> None:
    """Transition a round from submitting to voting phase.

    Args:
        round_obj: The Round to transition.
    """
    round_obj.phase = RoundPhase.VOTING
    db.session.commit()


def advance_round(game: Game, round_obj: Round, requesting_player: Player) -> Round | None:
    """Host advances to the next round, or finishes the game after the last round.

    Args:
        game: The Game instance.
        round_obj: The current Round (must be in complete phase).
        requesting_player: Must be the game creator.

    Returns:
        The new Round if advancing, or None if the game is now finished.

    Raises:
        ForbiddenError: If the requester is not the creator.
        PhaseMismatchError: If the round is not in complete phase.
    """
    if game.creator_id != requesting_player.id:
        raise ForbiddenError("Only the game creator can advance the round.")
    if round_obj.phase != RoundPhase.COMPLETE:
        raise PhaseMismatchError("The round has not been completed yet.")

    if round_obj.round_number >= MAX_ROUNDS:
        game.phase = GamePhase.FINISHED
        db.session.commit()
        return None

    return create_next_round(game)


def _eligible_players(game: Game) -> list[Player]:
    """Return non-spectator players sorted by join_order.

    Args:
        game: The Game instance.

    Returns:
        Sorted list of eligible Player instances.
    """
    return sorted(
        [p for p in game.players if not p.is_spectator],
        key=lambda p: p.join_order,
    )
