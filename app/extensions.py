"""Shared Flask extension singletons."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
cors = CORS()
