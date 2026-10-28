"""Événements de l'App MERCI : compte créé, dons (section 4.10).

Une adresse inconnue ne crée rien (décision D11). L'affaire Donateurs ne recule jamais.
"""
from __future__ import annotations

import datetime as dt

from sqlmodel import Session, select

from .. import temps
from ..journal import ajouter_activite
from ..modeles import Affaire, Contact
from . import affaires, moteur_sequences

TITRES = {
    "compte_cree": "Compte créé dans l'App MERCI",
    "don": "Don dans l'App MERCI",
    "don_suivi": "Nouveau don dans l'App MERCI",
}


def traiter(session: Session, email: str, type: str, at: dt.datetime | None) -> dict:
    """N'enregistre pas la transaction."""
    contact = session.exec(select(Contact).where(Contact.email == email)).first()
    if contact is None:
        return {"ok": True, "connu": False, "etape": None}
    affaire = session.exec(select(Affaire).where(
        Affaire.contact_id == contact.id, Affaire.pipeline == "donateurs")).first()
    ajouter_activite(session, "evenement_app", TITRES[type], contact_id=contact.id,
                     affaire_id=affaire.id if affaire else None,
                     donnees={"type": type, "at": temps.iso(at) if at else None})
    if affaire is not None:
        cible = {"compte_cree": "compte_cree", "don_suivi": "fidele",
                 "don": "fidele" if affaire.etape == "premier_don" else "premier_don"}[type]
        affaires.changer_etape(session, affaire, cible, automatique=True)
    if type == "compte_cree":
        moteur_sequences.arreter_actives(session, contact.id, "objectif_atteint", sequence="donateur-pilote")
    return {"ok": True, "connu": True, "etape": affaire.etape if affaire else None}
