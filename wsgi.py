"""WSGI entry point for gunicorn."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    from app.extensions import socketio
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
