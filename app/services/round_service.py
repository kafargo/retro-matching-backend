"""Round service — creation, submission handling, winner picking, and phase transitions."""
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


def create_first_round(game: Game) -> Round:
    """Create the first round of a game after begin is clicked.

    Args:
        game: The Game instance transitioning to playing phase.

    Returns:
        The newly created Round instance.
    """
    return _create_round(game, round_number=1)


def create_next_round(game: Game) -> Round:
    """Create the next normal round after the previous one completes.

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
    players = _eligible_players(game)
    judge = players[(round_number - 1) % len(players)]

    new_round = Round(
        game_id=game.id,
        round_number=round_number,
        judge_id=judge.id,
        adjective=pick_adjective(),
        phase=RoundPhase.SUBMITTING,
        is_final_round=False,
    )
    db.session.add(new_round)
    db.session.flush()
    game.current_round_id = new_round.id
    db.session.commit()
    return new_round


def submit_card(game: Game, round_obj: Round, player: Player, card_id: int) -> Submission:
    """Record a player's card submission for the current round.

    Args:
        game: The Game instance.
        round_obj: The current Round.
        player: The submitting player.
        card_id: ID of the card to submit.

    Returns:
        The created Submission instance.

    Raises:
        PhaseMismatchError: If the round is not in the submitting phase.
        ForbiddenError: If the player is the judge or a spectator.
        AlreadySubmittedError: If the player already submitted this round.
        InvalidCardError: If the card is not held by the player or already played.
    """
    if round_obj.phase != RoundPhase.SUBMITTING:
        raise PhaseMismatchError("This round is not accepting submissions.")
    if player.is_spectator:
        raise ForbiddenError("Spectators cannot submit cards.")
    if not round_obj.is_final_round and player.id == round_obj.judge_id:
        raise ForbiddenError("The judge does not submit a card.")

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
    """Check whether all eligible players have submitted for this round.

    Eligible = non-spectator, non-judge players.

    Args:
        game: The Game instance.
        round_obj: The current Round.

    Returns:
        True if all eligible players have submitted.
    """
    players = _eligible_players(game)
    submitters = [p for p in players if p.id != round_obj.judge_id]
    submitted_count = db.session.execute(
        db.select(db.func.count()).select_from(Submission).where(
            Submission.round_id == round_obj.id
        )
    ).scalar() or 0
    return submitted_count >= len(submitters)


def reveal_round(round_obj: Round) -> None:
    """Transition a round from submitting to revealed phase.

    Args:
        round_obj: The Round to reveal.
    """
    round_obj.phase = RoundPhase.REVEALED
    db.session.commit()


def pick_winner(game: Game, round_obj: Round, judge: Player, submission_id: int) -> Player:
    """Judge picks the winning submission, awarding 1 point to the author.

    Args:
        game: The Game instance.
        round_obj: The current Round (must be in revealed phase).
        judge: The judging player.
        submission_id: ID of the winning Submission.

    Returns:
        The winning Player instance.

    Raises:
        ForbiddenError: If the caller is not the judge.
        PhaseMismatchError: If the round is not in revealed phase.
        InvalidCardError: If the submission does not belong to this round.
    """
    if round_obj.phase != RoundPhase.REVEALED:
        raise PhaseMismatchError("Cards have not been revealed yet.")
    if judge.id != round_obj.judge_id:
        raise ForbiddenError("Only the judge can pick the winner.")

    submission = db.session.get(Submission, submission_id)
    if submission is None or submission.round_id != round_obj.id:
        raise InvalidCardError("Invalid submission selection.")

    winner = db.session.get(Player, submission.player_id)
    winner.score += 1

    round_obj.winner_id = winner.id
    round_obj.winning_card_id = submission.card_id
    round_obj.phase = RoundPhase.COMPLETE
    db.session.commit()

    return winner


def should_trigger_final_round(game: Game) -> bool:
    """Check if all non-spectator players have exactly 1 card left.

    This condition triggers the final round.

    Args:
        game: The Game instance.

    Returns:
        True if the final round should begin.
    """
    players = _eligible_players(game)
    for player in players:
        held_count = db.session.execute(
            db.select(db.func.count()).select_from(Card).where(
                Card.holder_id == player.id,
                Card.is_played.is_(False),
            )
        ).scalar() or 0
        if held_count != 1:
            return False
    return len(players) > 0


def create_final_round(game: Game) -> Round:
    """Create the final round and auto-submit all remaining cards.

    All players' single remaining cards are submitted without attribution.
    The round transitions immediately to revealed phase.

    Args:
        game: The Game instance.

    Returns:
        The created final Round instance.
    """
    last_round_number = db.session.execute(
        db.select(db.func.max(Round.round_number)).where(Round.game_id == game.id)
    ).scalar() or 0

    final_round = Round(
        game_id=game.id,
        round_number=last_round_number + 1,
        judge_id=None,
        adjective=pick_adjective(),
        phase=RoundPhase.SUBMITTING,
        is_final_round=True,
    )
    db.session.add(final_round)
    db.session.flush()
    game.current_round_id = final_round.id
    game.phase = GamePhase.FINAL_ROUND
    db.session.flush()

    # Auto-submit each player's last card
    players = _eligible_players(game)
    for player in players:
        last_card = db.session.execute(
            db.select(Card).where(
                Card.holder_id == player.id,
                Card.is_played.is_(False),
            )
        ).scalar_one_or_none()
        if last_card is not None:
            last_card.is_played = True
            last_card.holder_id = None
            submission = Submission(
                round_id=final_round.id,
                player_id=player.id,
                card_id=last_card.id,
            )
            db.session.add(submission)

    final_round.phase = RoundPhase.REVEALED
    db.session.commit()

    return final_round


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
