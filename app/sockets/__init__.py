"""Register all Socket.IO handlers."""


def register_handlers() -> None:
    """Import handler modules so their @socketio.on decorators are registered."""
    from . import handlers  # noqa: F401
