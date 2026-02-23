FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure SQLite data directory exists
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:////app/data/game.db
ENV FLASK_ENV=production

EXPOSE 5000

# Exactly 1 worker required — Flask-SocketIO room state is in-process memory
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", \
     "--bind", "0.0.0.0:5000", "--timeout", "120", "wsgi:app"]
