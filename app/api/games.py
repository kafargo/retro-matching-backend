"""All /api/games/* REST routes."""
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..api.auth import require_auth
from ..services import game_service, card_service, round_service, vote_service
from ..services.state_service import build_game_state_payload, build_hand_payload
from ..models.game import Game, GamePhase
from ..models.round import Round, RoundPhase
from ..errors import GameNotFoundError, PhaseMismatchError, ForbiddenError, ValidationError
from ..sockets.emitters import emit_game_state, emit_hand_to_all, emit_hand_to_player

games_bp = Blueprint("games", __name__)


def _get_game(code: str) -> Game:
    """Fetch a game by code or raise 404.

    Args:
        code: The game code (case-insensitive).

    Returns:
        The Game instance.

    Raises:
        GameNotFoundError: If the game does not exist.
    """
    game = db.session.execute(
        db.select(Game).where(Game.code == code.upper())
    ).scalar_one_or_none()
    if game is None:
        raise GameNotFoundError()
    return game


def _get_round(game: Game, round_id: int) -> Round:
    """Fetch a round by id, ensuring it belongs to the game.

    Args:
        game: The Game instance.
        round_id: The round primary key.

    Returns:
        The Round instance.

    Raises:
        PhaseMismatchError: If the round does not belong to this game.
    """
    round_obj = db.session.get(Round, round_id)
    if round_obj is None or round_obj.game_id != game.id:
        raise PhaseMismatchError("Round not found for this game.")
    return round_obj


# ---------------------------------------------------------------------------
# Create game
# ---------------------------------------------------------------------------

@games_bp.route("/games", methods=["POST"])
def create_game():
    """POST /api/games — create a new game session."""
    data = request.get_json(force=True) or {}
    display_name = (data.get("display_name") or "").strip()
    role = data.get("role", "player")

    if not display_name:
        raise ValidationError("display_name is required.")
    if len(display_name) > 50:
        raise ValidationError("display_name must be 50 characters or fewer.")
    if role not in ("player", "spectator"):
        raise ValidationError("role must be 'player' or 'spectator'.")

    result = game_service.create_game(display_name=display_name, role=role)
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Join game
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/join", methods=["POST"])
def join_game(code: str):
    """POST /api/games/<code>/join — join an existing lobby game as a player."""
    data = request.get_json(force=True) or {}
    display_name = (data.get("display_name") or "").strip()

    if not display_name:
        raise ValidationError("display_name is required.")
    if len(display_name) > 50:
        raise ValidationError("display_name must be 50 characters or fewer.")

    result = game_service.join_game(code=code, display_name=display_name)

    # Broadcast updated game state so lobby shows new player
    game = _get_game(code)
    emit_game_state(game)

    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Get game state
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>", methods=["GET"])
@require_auth
def get_game(code: str):
    """GET /api/games/<code> — full game state for the authenticated player."""
    game = _get_game(code)
    state = game_service.get_game_state_for_player(game, g.player)
    return jsonify(state), 200


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/reconnect", methods=["POST"])
@require_auth
def reconnect(code: str):
    """POST /api/games/<code>/reconnect — rehydrate client state after page refresh."""
    game = _get_game(code)
    state = game_service.get_game_state_for_player(game, g.player)
    return jsonify(state), 200


# ---------------------------------------------------------------------------
# Start game (lobby → card_creation)
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/start", methods=["POST"])
@require_auth
def start_game(code: str):
    """POST /api/games/<code>/start — creator transitions lobby to card creation."""
    game = _get_game(code)
    game_service.start_game(game, g.player)
    emit_game_state(game)
    return jsonify({"phase": game.phase.value}), 200


# ---------------------------------------------------------------------------
# Submit cards
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/cards", methods=["POST"])
@require_auth
def submit_cards(code: str):
    """POST /api/games/<code>/cards — player submits their 6 cards."""
    game = _get_game(code)
    data = request.get_json(force=True) or {}
    cards_data = data.get("cards", [])

    if not isinstance(cards_data, list):
        raise ValidationError("cards must be a list.")

    card_service.save_player_cards(game, g.player, cards_data)
    emit_game_state(game)
    return jsonify({"submitted": True}), 201


# ---------------------------------------------------------------------------
# Mark ready
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/ready", methods=["POST"])
@require_auth
def mark_ready(code: str):
    """POST /api/games/<code>/ready — player marks themselves ready."""
    game = _get_game(code)

    if game.phase != GamePhase.CARD_CREATION:
        raise PhaseMismatchError("Can only mark ready during card creation phase.")
    if g.player.is_spectator:
        raise ForbiddenError("Spectators do not mark ready.")

    # Ensure player has submitted cards first
    from ..models.card import Card
    card_count = db.session.execute(
        db.select(db.func.count()).select_from(Card).where(
            Card.game_id == game.id,
            Card.creator_id == g.player.id,
        )
    ).scalar() or 0

    if card_count < 6:
        raise PhaseMismatchError("You must submit all 6 cards before marking ready.")

    g.player.is_ready = True
    db.session.commit()
    emit_game_state(game)
    return jsonify({"ready": True}), 200


# ---------------------------------------------------------------------------
# Begin game (card_creation → playing)
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/begin", methods=["POST"])
@require_auth
def begin_game(code: str):
    """POST /api/games/<code>/begin — creator begins the playing phase."""
    game = _get_game(code)

    if game.creator_id != g.player.id:
        raise ForbiddenError("Only the game creator can begin the game.")
    if game.phase != GamePhase.CARD_CREATION:
        raise PhaseMismatchError("Game is not in card creation phase.")

    # Verify all non-spectator players are ready
    from ..models.player import Player, PlayerRole
    not_ready = db.session.execute(
        db.select(db.func.count()).select_from(Player).where(
            Player.game_id == game.id,
            Player.role == PlayerRole.PLAYER,
            Player.is_ready.is_(False),
        )
    ).scalar() or 0

    if not_ready > 0:
        raise PhaseMismatchError("All players must be ready before the game can begin.")

    # Redistribute cards, transition phase, create first round
    card_service.redistribute_cards(game)
    game.phase = GamePhase.PLAYING
    db.session.commit()

    first_round = round_service.create_first_round(game)

    # Emit private hands to each player, then broadcast state
    emit_hand_to_all(game)
    emit_game_state(game)

    return jsonify({"phase": game.phase.value}), 200


# ---------------------------------------------------------------------------
# Submit card in a round
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/rounds/<int:round_id>/submit", methods=["POST"])
@require_auth
def submit_card(code: str, round_id: int):
    """POST /api/games/<code>/rounds/<id>/submit — player submits a card for the round."""
    game = _get_game(code)
    round_obj = _get_round(game, round_id)

    data = request.get_json(force=True) or {}
    card_id = data.get("card_id")
    if card_id is None:
        raise ValidationError("card_id is required.")

    round_service.submit_card(game, round_obj, g.player, int(card_id))

    # Send the updated hand (minus the played card) back to the submitting player
    emit_hand_to_player(g.player)

    # Check if all players have now submitted
    if round_service.check_all_submitted(game, round_obj):
        round_service.reveal_round(round_obj)

    emit_game_state(game)
    return jsonify({"submitted": True}), 200


# ---------------------------------------------------------------------------
# Judge picks winner
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/rounds/<int:round_id>/pick-winner", methods=["POST"])
@require_auth
def pick_winner(code: str, round_id: int):
    """POST /api/games/<code>/rounds/<id>/pick-winner — judge selects winning card."""
    game = _get_game(code)
    round_obj = _get_round(game, round_id)

    data = request.get_json(force=True) or {}
    submission_id = data.get("submission_id")
    if submission_id is None:
        raise ValidationError("submission_id is required.")

    winner = round_service.pick_winner(game, round_obj, g.player, int(submission_id))

    # Check for final round trigger
    if round_service.should_trigger_final_round(game):
        final_round = round_service.create_final_round(game)
        emit_game_state(game)
        return jsonify({"winner_player_id": winner.id, "final_round_triggered": True}), 200

    # Create next normal round
    round_service.create_next_round(game)
    emit_game_state(game)
    return jsonify({"winner_player_id": winner.id, "final_round_triggered": False}), 200


# ---------------------------------------------------------------------------
# Vote in final round
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/rounds/<int:round_id>/vote", methods=["POST"])
@require_auth
def vote(code: str, round_id: int):
    """POST /api/games/<code>/rounds/<id>/vote — cast a vote in the final round."""
    game = _get_game(code)
    round_obj = _get_round(game, round_id)

    data = request.get_json(force=True) or {}
    card_id = data.get("card_id")
    if card_id is None:
        raise ValidationError("card_id is required.")

    vote_service.record_vote(game, round_obj, g.player, int(card_id))

    # Check if all connected participants have voted
    if vote_service.all_voted(game, round_obj):
        final_scores = vote_service.tally_and_finish(game, round_obj)
        emit_game_state(game)
        return jsonify({"voted": True, "game_finished": True, "final_scores": final_scores}), 200

    emit_game_state(game)
    return jsonify({"voted": True, "game_finished": False}), 200


# ---------------------------------------------------------------------------
# Finish game (delete all data)
# ---------------------------------------------------------------------------

@games_bp.route("/games/<code>/finish", methods=["POST"])
@require_auth
def finish_game(code: str):
    """POST /api/games/<code>/finish — creator deletes the game and all its data."""
    game = _get_game(code)
    game_service.finish_game(game, g.player)
    return jsonify({"deleted": True}), 200
