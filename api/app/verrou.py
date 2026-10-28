"""Verrou nommé en base (tick, prospection), portable SQLite et Postgres.

Prise : INSERT ; en cas de conflit, UPDATE seulement si le verrou en place a expiré.
Relâche : DELETE par nom et jeton du détenteur.
"""
from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from . import temps
from .modeles import Verrou

_table = Verrou.__table__


def prendre(session: Session, nom: str, duree: dt.timedelta) -> str | None:
    """Jeton du détenteur si le verrou est pris, None s'il est tenu par un autre."""
    jeton = uuid.uuid4().hex
    t = temps.maintenant()
    try:
        session.execute(sa.insert(_table).values(nom=nom, jeton=jeton, expire_at=t + duree))
        session.commit()
        return jeton
    except IntegrityError:
        session.rollback()
    res = session.execute(
        sa.update(_table)
        .where(_table.c.nom == nom, _table.c.expire_at < t)
        .values(jeton=jeton, expire_at=t + duree)
    )
    session.commit()
    return jeton if res.rowcount == 1 else None


def relacher(session: Session, nom: str, jeton: str) -> None:
    session.execute(sa.delete(_table).where(_table.c.nom == nom, _table.c.jeton == jeton))
    session.commit()
