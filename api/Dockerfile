FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY alembic.ini .
COPY migrations/ migrations/
EXPOSE 8000
# Migration dans la commande de démarrage, jamais à l'import de l'application (un seul worker).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
