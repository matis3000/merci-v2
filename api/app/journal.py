"""Point unique d'écriture du fil d'activité (invariant 10).

N'enregistre pas la transaction : l'appelant valide avec le reste de ses écritures.
"""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session

from . import temps
from .modeles import TYPES_ACTIVITE, Activite


def ajouter_activite(
    session: Session,
    type: str,
    titre: str,
    *,
    texte: str | None = None,
    contact_id: int | None = None,
    organisation_id: int | None = None,
    affaire_id: int | None = None,
    envoi_id: int | None = None,
    membre_id: int | None = None,
    donnees: dict[str, Any] | None = None,
) -> Activite:
    if type not in TYPES_ACTIVITE:
        raise ValueError(f"type d'activité inconnu : {type}")
    activite = Activite(
        type=type,
        titre=titre[:200],
        texte=texte,
        contact_id=contact_id,
        organisation_id=organisation_id,
        affaire_id=affaire_id,
        envoi_id=envoi_id,
        membre_id=membre_id,
        donnees=json.dumps(donnees, ensure_ascii=False) if donnees is not None else None,
        cree_at=temps.maintenant(),
    )
    session.add(activite)
    session.flush()
    return activite
