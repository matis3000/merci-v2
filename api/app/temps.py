"""Point unique d'horloge.

Toutes les dates sont stockées en UTC naïf et produites par `maintenant()` (remplacée par
la fixture `horloge` dans les tests). Europe/Paris sert seulement au créneau d'envoi et à
l'affichage.
"""
from __future__ import annotations

import datetime as dt
from typing import Protocol
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


class Creneau(Protocol):
    creneau_jours: str   # "1,2,3,4,5" (ISO, lundi = 1)
    creneau_debut: int   # heure incluse
    creneau_fin: int     # heure exclue


def maintenant() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def vers_paris(t: dt.datetime) -> dt.datetime:
    """UTC naïf vers heure de Paris (consciente du fuseau, heure d'été comprise)."""
    return t.replace(tzinfo=dt.timezone.utc).astimezone(PARIS)


def iso(t: dt.datetime | None) -> str | None:
    """Sérialisation de l'API : ISO 8601 UTC suffixé `Z`, à la seconde."""
    return None if t is None else t.strftime("%Y-%m-%dT%H:%M:%SZ")


def jour_paris(t: dt.datetime) -> dt.date:
    return vers_paris(t).date()


def bornes_du_jour_paris(t: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """[début, fin) du jour de Paris contenant `t`, en UTC naïf (heure d'été comprise)."""
    jour = jour_paris(t)

    def utc(d: dt.date) -> dt.datetime:
        return dt.datetime.combine(d, dt.time(0), tzinfo=PARIS).astimezone(dt.timezone.utc).replace(tzinfo=None)

    return utc(jour), utc(jour + dt.timedelta(days=1))


def dans_creneau(t: dt.datetime, r: Creneau) -> bool:
    p = vers_paris(t)
    jours = {int(j) for j in r.creneau_jours.split(",") if j.strip()}
    return p.isoweekday() in jours and r.creneau_debut <= p.hour < r.creneau_fin
