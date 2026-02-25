"""Vote service — per-round voting and tallying."""
from typing import Any
from ..extensions import db
from ..models.game import Game
from ..models.player import Player, PlayerRole
from ..models.round import Round, RoundPhase
from ..models.submission import Submission
from ..models.vote import Vote
from ..errors import PhaseMismatchError, ForbiddenError, AlreadySubmittedError, InvalidCardError


def record_vote(game: Game, round_obj: Round, voter: Player, card_id: int) -> None:
    """Record a vote during the voting phase of any round.

    Only non-spectator players may vote, exactly once per round.

    Args:
        game: The Game instance.
        round_obj: The current Round (must be in voting phase).
        voter: The player casting the vote.
        card_id: The card being voted for.

    Raises:
        PhaseMismatchError: If the round is not in voting phase.
        ForbiddenError: If the voter is a spectator.
        AlreadySubmittedError: If the voter has already voted.
        InvalidCardError: If the card wasn't submitted in this round.
    """
    if round_obj.phase != RoundPhase.VOTING:
        raise PhaseMismatchError("Voting is not available in this phase.")
    if voter.is_spectator:
        raise ForbiddenError("Spectators cannot vote.")

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
    """Check whether all connected non-spectator players have voted.

    Args:
        game: The Game instance.
        round_obj: The current Round.

    Returns:
        True if every connected non-spectator player has cast a vote.
    """
    eligible_count = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(
            Player.game_id == game.id,
            Player.is_connected.is_(True),
            Player.role == PlayerRole.PLAYER,
        )
    ).scalar() or 0

    voted_count = db.session.execute(
        db.select(db.func.count()).select_from(Vote).where(
            Vote.round_id == round_obj.id
        )
    ).scalar() or 0

    return voted_count >= eligible_count


def tally_round(round_obj: Round) -> tuple[list[int], list[int]]:
    """Tally votes, award points to winners, and mark the round complete.

    All tied winners receive a point (regardless of how many are tied).

    Args:
        round_obj: The current Round.

    Returns:
        Tuple of (winning_card_ids, winner_player_ids).
    """
    votes = db.session.execute(
        db.select(Vote).where(Vote.round_id == round_obj.id)
    ).scalars().all()

    winning_card_ids: list[int] = []
    winner_player_ids: list[int] = []

    if votes:
        # Tally votes per card
        vote_counts: dict[int, int] = {}
        for v in votes:
            vote_counts[v.card_id] = vote_counts.get(v.card_id, 0) + 1

        max_votes = max(vote_counts.values())
        winning_card_ids = [cid for cid, cnt in vote_counts.items() if cnt == max_votes]

        # Award a point to each player who submitted a winning card
        winning_submissions = db.session.execute(
            db.select(Submission).where(
                Submission.round_id == round_obj.id,
                Submission.card_id.in_(winning_card_ids),
            )
        ).scalars().all()

        for sub in winning_submissions:
            winner = db.session.get(Player, sub.player_id)
            if winner:
                winner.score += 1
                winner_player_ids.append(winner.id)

    round_obj.phase = RoundPhase.COMPLETE
    db.session.commit()

    return winning_card_ids, winner_player_ids
