"""API blueprint registration."""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all API blueprints on the app.

    Args:
        app: The Flask application instance.
    """
    from .games import games_bp
    app.register_blueprint(games_bp, url_prefix="/api")
