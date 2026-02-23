"""Vote service — final round voting and tie-breaking."""
from typing import Any
from ..extensions import db
from ..models.game import Game, GamePhase
from ..models.player import Player
from ..models.round import Round, RoundPhase
from ..models.submission import Submission
from ..models.vote import Vote
from ..errors import PhaseMismatchError, AlreadySubmittedError, InvalidCardError


def record_vote(game: Game, round_obj: Round, voter: Player, card_id: int) -> None:
    """Record a vote in the final round.

    Any participant (player or spectator) may vote exactly once.

    Args:
        game: The Game instance.
        round_obj: The final Round (must be in revealed phase).
        voter: The participant casting the vote.
        card_id: The card being voted for.

    Raises:
        PhaseMismatchError: If the round is not the final round or not in revealed phase.
        AlreadySubmittedError: If the voter has already voted.
        InvalidCardError: If the card wasn't submitted in this round.
    """
    if not round_obj.is_final_round:
        raise PhaseMismatchError("Voting is only available in the final round.")
    if round_obj.phase != RoundPhase.REVEALED:
        raise PhaseMismatchError("Voting is not yet available.")

    existing = db.session.execute(
        db.select(Vote).where(
            Vote.round_id == round_obj.id,
            Vote.voter_id == voter.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadySubmittedError()

    # Verify the card was submitted in this round
    submission = db.session.execute(
        db.select(Submission).where(
            Submission.round_id == round_obj.id,
            Submission.card_id == card_id,
        )
    ).scalar_one_or_none()
    if submission is None:
        raise InvalidCardError("That card was not submitted in this round.")

    vote = Vote(
        round_id=round_obj.id,
        voter_id=voter.id,
        card_id=card_id,
    )
    db.session.add(vote)
    db.session.commit()


def all_voted(game: Game, round_obj: Round) -> bool:
    """Check whether all connected participants have voted.

    Connected spectators are included in the required voter count.

    Args:
        game: The Game instance.
        round_obj: The final Round.

    Returns:
        True if every connected participant has cast a vote.
    """
    connected_count = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(
            Player.game_id == game.id,
            Player.is_connected.is_(True),
        )
    ).scalar() or 0

    voted_count = db.session.execute(
        db.select(db.func.count()).select_from(Vote).where(
            Vote.round_id == round_obj.id
        )
    ).scalar() or 0

    return voted_count >= connected_count


def tally_and_finish(game: Game, round_obj: Round) -> list[dict[str, Any]]:
    """Apply tie-breaking, award points, and transition the game to finished.

    Tie-breaking rules:
    - 1 winner: +1 point to that player
    - Exactly 2-way tie: +1 point to both players
    - 3+ way tie: no points awarded

    Args:
        game: The Game instance.
        round_obj: The completed final Round.

    Returns:
        List of final score dicts sorted descending by score.
    """
    votes = db.session.execute(
        db.select(Vote).where(Vote.round_id == round_obj.id)
    ).scalars().all()

    # Tally votes per card
    vote_counts: dict[int, int] = {}
    for v in votes:
        vote_counts[v.card_id] = vote_counts.get(v.card_id, 0) + 1

    if vote_counts:
        max_votes = max(vote_counts.values())
        winning_card_ids = [cid for cid, cnt in vote_counts.items() if cnt == max_votes]

        if len(winning_card_ids) == 1 or len(winning_card_ids) == 2:
            # Find the player who submitted each winning card and award points
            winning_submissions = db.session.execute(
                db.select(Submission).where(
                    Submission.round_id == round_obj.id,
                    Submission.card_id.in_(winning_card_ids),
                )
            ).scalars().all()

            for sub in winning_submissions:
                winner_player = db.session.get(Player, sub.player_id)
                if winner_player:
                    winner_player.score += 1

    round_obj.phase = RoundPhase.COMPLETE
    game.phase = GamePhase.FINISHED
    db.session.commit()

    # Build final scores
    players = sorted(
        [p for p in game.players if not p.is_spectator],
        key=lambda p: p.score,
        reverse=True,
    )
    return [
        {"player_id": p.id, "display_name": p.display_name, "score": p.score}
        for p in players
    ]
