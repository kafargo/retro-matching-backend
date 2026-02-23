"""Card service — submission, validation, and redistribution."""
import random
from typing import Any, List
from ..extensions import db
from ..models.card import Card, CardType
from ..models.player import Player, PlayerRole
from ..models.game import Game, GamePhase
from ..errors import PhaseMismatchError, ValidationError, ForbiddenError


def save_player_cards(game: Game, player: Player, cards_data: List[dict]) -> None:
    """Save 6 cards for a player during the card_creation phase.

    Each player must submit exactly 2 start, 2 stop, and 2 continue cards.

    Args:
        game: The Game instance.
        player: The player submitting cards.
        cards_data: List of dicts with 'card_type' and 'text' keys.

    Raises:
        PhaseMismatchError: If the game is not in card_creation phase.
        ForbiddenError: If the player is a spectator.
        ValidationError: If card counts don't match requirements.
    """
    if game.phase != GamePhase.CARD_CREATION:
        raise PhaseMismatchError("Cards can only be submitted during the card creation phase.")
    if player.is_spectator:
        raise ForbiddenError("Spectators do not submit cards.")

    # Validate exactly 2 of each type
    type_counts: dict[str, int] = {"start": 0, "stop": 0, "continue": 0}
    for c in cards_data:
        ct = c.get("card_type", "")
        if ct not in type_counts:
            raise ValidationError(f"Invalid card_type '{ct}'. Must be start, stop, or continue.")
        type_counts[ct] += 1

    for ct, count in type_counts.items():
        if count != 2:
            raise ValidationError(f"Exactly 2 '{ct}' cards required; got {count}.")

    # Delete any previously submitted cards for this player in this game (re-submission)
    db.session.execute(
        db.delete(Card).where(Card.game_id == game.id, Card.creator_id == player.id)
    )

    for c in cards_data:
        card = Card(
            game_id=game.id,
            creator_id=player.id,
            holder_id=player.id,  # Initially held by the creator
            card_type=CardType(c["card_type"]),
            text=c["text"].strip(),
            is_played=False,
        )
        db.session.add(card)

    db.session.commit()


def redistribute_cards(game: Game) -> None:
    """Shuffle and redistribute all cards among players when the game begins.

    Each player receives exactly 2 cards of each type (start, stop, continue).
    Cards are shuffled independently per type to break authorship correlation.
    Players may receive cards they originally wrote — this is by design.

    Args:
        game: The Game instance (must be transitioning to playing phase).
    """
    players = sorted(
        [p for p in game.players if not p.is_spectator],
        key=lambda p: p.join_order,
    )
    player_ids = [p.id for p in players]
    n = len(player_ids)

    for card_type in CardType:
        cards = db.session.execute(
            db.select(Card).where(
                Card.game_id == game.id,
                Card.card_type == card_type,
            )
        ).scalars().all()

        card_list = list(cards)
        random.shuffle(card_list)

        for i, player_id in enumerate(player_ids):
            chunk = card_list[i * 2 : i * 2 + 2]
            for card in chunk:
                card.holder_id = player_id
                card.is_played = False

    db.session.commit()


def get_player_hand(player: Player) -> List[dict[str, Any]]:
    """Return the cards currently held by a player.

    Args:
        player: The Player instance.

    Returns:
        List of card dicts including text (private).
    """
    cards = db.session.execute(
        db.select(Card).where(
            Card.holder_id == player.id,
            Card.is_played.is_(False),
        )
    ).scalars().all()

    return [
        {
            "id": c.id,
            "card_type": c.card_type.value,
            "text": c.text,
        }
        for c in cards
    ]
