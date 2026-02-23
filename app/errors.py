"""Custom exception classes and Flask error handlers."""
from flask import jsonify
from typing import Any


class AppError(Exception):
    """Base application error with a machine-readable code and HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        """Initialise the error.

        Args:
            code: Machine-readable error code.
            message: Human-readable description.
            status: HTTP status code.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class GameNotFoundError(AppError):
    """Raised when a game with the given code does not exist."""

    def __init__(self) -> None:
        super().__init__("GAME_NOT_FOUND", "Game not found.", 404)


class DisplayNameTakenError(AppError):
    """Raised when the chosen display name is already in use in a game."""

    def __init__(self) -> None:
        super().__init__("DISPLAY_NAME_TAKEN", "That display name is already taken.", 409)


class PhaseMismatchError(AppError):
    """Raised when an action is not valid for the current game phase."""

    def __init__(self, message: str = "Action not valid for the current game phase.") -> None:
        super().__init__("PHASE_MISMATCH", message, 403)


class UnauthorizedError(AppError):
    """Raised when the session token is missing or invalid."""

    def __init__(self) -> None:
        super().__init__("UNAUTHORIZED", "Missing or invalid session token.", 401)


class ForbiddenError(AppError):
    """Raised when a player tries an action they are not permitted to perform."""

    def __init__(self, message: str = "You are not permitted to perform this action.") -> None:
        super().__init__("FORBIDDEN", message, 403)


class InvalidCardError(AppError):
    """Raised when a submitted card does not belong to the player or is already played."""

    def __init__(self, message: str = "Invalid card selection.") -> None:
        super().__init__("INVALID_CARD", message, 400)


class AlreadySubmittedError(AppError):
    """Raised when a player tries to submit a second time in a round."""

    def __init__(self) -> None:
        super().__init__("ALREADY_SUBMITTED", "You have already submitted a card this round.", 409)


class ValidationError(AppError):
    """Raised when request data fails validation."""

    def __init__(self, message: str) -> None:
        super().__init__("VALIDATION_ERROR", message, 400)


def register_error_handlers(app: Any) -> None:
    """Register error handlers on the Flask app.

    Args:
        app: The Flask application instance.
    """

    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify({"error": err.code, "message": err.message}), err.status

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({"error": "NOT_FOUND", "message": "The requested resource was not found."}), 404

    @app.errorhandler(405)
    def handle_405(err):
        return jsonify({"error": "METHOD_NOT_ALLOWED", "message": "Method not allowed."}), 405

    @app.errorhandler(500)
    def handle_500(err):
        return jsonify({"error": "INTERNAL_ERROR", "message": "An internal server error occurred."}), 500
