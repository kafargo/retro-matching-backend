"""State serialization service — single source of truth for WebSocket payloads.

This module is the only place that constructs game state dicts for broadcast.
Card attribution and hand contents are intentionally excluded from room-wide payloads
to preserve anonymity.
"""
from typing import Any
from ..extensions import db
from ..models.game import Game
from ..models.round import RoundPhase


def build_game_state_payload(game: Game) -> dict[str, Any]:
    """Build the full game state dict for a room-wide broadcast.

    This payload is safe to send to every client in the room because:
    - Card text is never included (hand contents go via targeted your_cards_updated)
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

        current_round_data = {
            "id": r.id,
            "round_number": r.round_number,
            "judge_id": r.judge_id,
            "adjective": r.adjective,
            "phase": r.phase.value,
            "is_final_round": r.is_final_round,
            "submission_status": submission_status,
            "revealed_submissions": revealed,
            "winner_id": r.winner_id,
            "winning_card_id": r.winning_card_id,
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
    """Build submission status list for the sidebar — who has submitted vs pending.

    Only non-judge, non-spectator players appear in this list.

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
        if not round_obj.is_final_round and p.id == round_obj.judge_id:
            continue
        result.append({
            "player_id": p.id,
            "display_name": p.display_name,
            "has_submitted": p.id in submitted_player_ids,
        })
    return result


def _build_revealed_submissions(round_obj) -> list[dict[str, Any]]:
    """Build anonymised revealed submissions for broadcast after all cards are in.

    Attribution (which player submitted which card) is intentionally excluded.

    Args:
        round_obj: The Round instance in revealed or complete phase.

    Returns:
        List of dicts with submission_id, card_type, and card_text only.
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
