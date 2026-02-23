"""Application factory."""
import os
from flask import Flask
from .config import config_map
from .extensions import db, migrate, socketio, cors
from .errors import register_error_handlers


def create_app(env: str | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        env: Configuration environment name. Defaults to FLASK_ENV env var.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    env = env or os.environ.get("FLASK_ENV", "default")
    app.config.from_object(config_map.get(env, config_map["default"]))

    # Initialise extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        logger=False,
        engineio_logger=False,
    )

    # Import models so Alembic can detect them
    with app.app_context():
        from .models import game, player, card, round, submission, vote  # noqa: F401

    # Register blueprints
    from .api import register_blueprints
    register_blueprints(app)

    # Register socket handlers
    from .sockets import register_handlers
    register_handlers()

    # Register error handlers
    register_error_handlers(app)

    return app
