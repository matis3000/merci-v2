"""Moteur de base de données et session par requête.

Le schéma est géré par Alembic (`alembic upgrade head` dans la commande de démarrage),
jamais à l'import de l'application.
"""
from __future__ import annotations

from sqlmodel import Session, create_engine

from .config import settings

_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _sqlite else {},
    # Postgres coupe les connexions inactives : vérification avant usage (hors SQLite).
    pool_pre_ping=not _sqlite,
)


def get_session():
    with Session(engine) as session:
        yield session
