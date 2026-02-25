"""State serialization service — single source of truth for WebSocket payloads.

This module is the only place that constructs game state dicts for broadcast.
Card attribution and hand contents are intentionally excluded from room-wide payloads
to preserve anonymity.
"""
from typing import Any
from ..extensions import db
from ..models.game import Game
from ..models.round import RoundPhase
from ..services.round_service import MAX_ROUNDS


def build_game_state_payload(game: Game) -> dict[str, Any]:
    """Build the full game state dict for a room-wide broadcast.

    This payload is safe to send to every client in the room because:
    - Card text is never included in hand data (hand contents go via targeted your_cards_updated)
    - Submission player attribution is never included when round.phase == submitting
    - Revealed submissions include card text but NOT which player submitted them

    Args:
        game: The Game ORM instance (must be inside an active db session).

    Returns:
        A dict representing the full game state.
    """
    from ..models.card import Card

    players_data = []
    for p in sorted(game.players, key=lambda x: x.join_order):
        held_count = db.session.execute(
            db.select(db.func.count()).select_from(Card).where(
                Card.holder_id == p.id,
                Card.is_played.is_(False),
            )
        ).scalar() or 0

        players_data.append({
            "id": p.id,
            "display_name": p.display_name,
            "role": p.role.value,
            "join_order": p.join_order,
            "score": p.score,
            "is_connected": p.is_connected,
            "is_ready": p.is_ready,
            "card_count": held_count,
        })

    current_round_data = None
    if game.current_round is not None:
        r = game.current_round
        submission_status = _build_submission_status(game, r)
        revealed = _build_revealed_submissions(r) if r.phase != RoundPhase.SUBMITTING else None
        vote_status = _build_vote_status(game, r) if r.phase == RoundPhase.VOTING else None
        winning_card_ids, winner_player_ids = (
            _compute_winners(r) if r.phase == RoundPhase.COMPLETE else ([], [])
        )

        current_round_data = {
            "id": r.id,
            "round_number": r.round_number,
            "adjective": r.adjective,
            "phase": r.phase.value,
            "submission_status": submission_status,
            "revealed_submissions": revealed,
            "vote_status": vote_status,
            "winning_card_ids": winning_card_ids,
            "winner_player_ids": winner_player_ids,
            "total_rounds": MAX_ROUNDS,
        }

    return {
        "type": "game_state_updated",
        "game": {
            "code": game.code,
            "phase": game.phase.value,
            "creator_id": game.creator_id,
            "players": players_data,
            "current_round": current_round_data,
        },
    }


def _build_submission_status(game: Game, round_obj) -> list[dict[str, Any]]:
    """Build submission status list — who has submitted vs pending.

    All non-spectator players appear in this list.

    Args:
        game: The Game instance.
        round_obj: The current Round instance.

    Returns:
        List of dicts with player_id, display_name, and has_submitted.
    """
    from ..models.submission import Submission

    submitted_player_ids = {
        s.player_id
        for s in db.session.execute(
            db.select(Submission).where(Submission.round_id == round_obj.id)
        ).scalars().all()
    }

    result = []
    for p in sorted(game.players, key=lambda x: x.join_order):
        if p.is_spectator:
            continue
        result.append({
            "player_id": p.id,
            "display_name": p.display_name,
            "has_submitted": p.id in submitted_player_ids,
        })
    return result


def _build_vote_status(game: Game, round_obj) -> list[dict[str, Any]]:
    """Build vote status list — who has voted vs pending.

    Only non-spectator players are listed (spectators cannot vote).

    Args:
        game: The Game instance.
        round_obj: The current Round instance.

    Returns:
        List of dicts with player_id, display_name, and has_voted.
    """
    from ..models.vote import Vote

    voted_player_ids = {
        v.voter_id
        for v in db.session.execute(
            db.select(Vote).where(Vote.round_id == round_obj.id)
        ).scalars().all()
    }

    result = []
    for p in sorted(game.players, key=lambda x: x.join_order):
        if p.is_spectator:
            continue
        result.append({
            "player_id": p.id,
            "display_name": p.display_name,
            "has_voted": p.id in voted_player_ids,
        })
    return result


def _build_revealed_submissions(round_obj) -> list[dict[str, Any]]:
    """Build anonymised revealed submissions for broadcast.

    Attribution (which player submitted which card) is intentionally excluded.

    Args:
        round_obj: The Round instance in voting or complete phase.

    Returns:
        List of dicts with submission_id, card_id, card_type, and card_text only.
    """
    from ..models.submission import Submission

    submissions = db.session.execute(
        db.select(Submission).where(Submission.round_id == round_obj.id)
    ).scalars().all()

    return [
        {
            "submission_id": s.id,
            "card_id": s.card_id,
            "card_type": s.card.card_type.value,
            "card_text": s.card.text,
        }
        for s in submissions
    ]


def _compute_winners(round_obj) -> tuple[list[int], list[int]]:
    """Compute winning card IDs and winner player IDs from vote tally.

    Args:
        round_obj: The Round instance in complete phase.

    Returns:
        Tuple of (winning_card_ids, winner_player_ids).
    """
    from ..models.vote import Vote
    from ..models.submission import Submission

    votes = db.session.execute(
        db.select(Vote).where(Vote.round_id == round_obj.id)
    ).scalars().all()

    if not votes:
        return [], []

    vote_counts: dict[int, int] = {}
    for v in votes:
        vote_counts[v.card_id] = vote_counts.get(v.card_id, 0) + 1

    max_votes = max(vote_counts.values())
    winning_card_ids = [cid for cid, cnt in vote_counts.items() if cnt == max_votes]

    winning_submissions = db.session.execute(
        db.select(Submission).where(
            Submission.round_id == round_obj.id,
            Submission.card_id.in_(winning_card_ids),
        )
    ).scalars().all()

    winner_player_ids = [sub.player_id for sub in winning_submissions]

    return winning_card_ids, winner_player_ids


def build_hand_payload(player) -> dict[str, Any]:
    """Build the private hand payload for a single player's socket.

    This is intentionally NOT broadcast to the room — only sent to the individual socket.

    Args:
        player: The Player instance.

    Returns:
        Dict with type and cards list including card text.
    """
    from ..models.card import Card
    cards = db.session.execute(
        db.select(Card).where(
            Card.holder_id == player.id,
            Card.is_played.is_(False),
        )
    ).scalars().all()

    return {
        "type": "your_cards_updated",
        "cards": [
            {
                "id": c.id,
                "card_type": c.card_type.value,
                "text": c.text,
            }
            for c in cards
        ],
    }
