"""Affaires : création, changement d'étape manuel ou automatique, arrêts associés (sections 4.5, 5.4)."""
from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session, select

from .. import temps
from ..journal import ajouter_activite
from ..modeles import Affaire, Membre
from ..pipelines import PIPELINES, avance, cles_etapes, etape, etape_perdue
from . import moteur_sequences

PIPELINE_DU_TYPE = {"donateur": "donateurs", "entreprise": "entreprises", "association": "associations"}


class ErreurAffaire(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


def premiere_etape(pipeline: str) -> str:
    return PIPELINES[pipeline]["etapes"][0][0]


def membre_api(m: Membre | None) -> dict | None:
    if m is None:
        return None
    return {"id": m.id, "email": m.email, "prenom": m.prenom, "role": m.role, "actif": m.actif}


def creer(session: Session, pipeline: str, etape_cle: str, *, contact_id: int | None = None,
          organisation_id: int | None = None) -> Affaire:
    """Affaire du contact (ou de l'organisation seule) dans ce pipeline ; créée si absente.

    Un contact rattaché à une organisation qui n'avait qu'une affaire « organisation seule »
    reprend cette affaire : pas de seconde carte pour la même entreprise.
    """
    if contact_id is not None:
        existante = session.exec(select(Affaire).where(
            Affaire.contact_id == contact_id, Affaire.pipeline == pipeline)).first()
        if existante:
            return existante
    if organisation_id is not None:
        seule = session.exec(select(Affaire).where(
            Affaire.organisation_id == organisation_id, Affaire.contact_id.is_(None),
            Affaire.pipeline == pipeline)).first()
        if seule:
            if contact_id is not None:
                seule.contact_id = contact_id
                seule.maj_at = temps.maintenant()
                session.add(seule)
                session.flush()
            return seule
    t = temps.maintenant()
    a = Affaire(pipeline=pipeline, etape=etape_cle, etape_depuis=t, contact_id=contact_id,
                organisation_id=organisation_id, cree_at=t, maj_at=t)
    session.add(a)
    session.flush()
    return a


def changer_etape(session: Session, affaire: Affaire, cible: str, *, membre_id: int | None = None,
                  automatique: bool = False) -> bool:
    """Change l'étape. Automatique : jamais de recul ni de sortie de perdu (invariant 8).
    Manuel : toute séquence active du contact est arrêtée (section 5.4). Renvoie vrai si changé."""
    if cible not in cles_etapes(affaire.pipeline):
        raise ErreurAffaire(422, "Étape inconnue pour ce pipeline")
    if cible == affaire.etape or (automatique and not avance(affaire.pipeline, affaire.etape, cible)):
        return False
    avant = affaire.etape
    t = temps.maintenant()
    perdue = etape_perdue(affaire.pipeline)
    affaire.etape, affaire.etape_depuis, affaire.maj_at = cible, t, t
    if avant == perdue:
        affaire.perdue_raison = None
    session.add(affaire)
    ajouter_activite(
        session, "etape_changee",
        f"Étape passée de {etape(affaire.pipeline, avant)['nom']} à {etape(affaire.pipeline, cible)['nom']}",
        contact_id=affaire.contact_id, organisation_id=affaire.organisation_id, affaire_id=affaire.id,
        membre_id=membre_id, donnees={"avant": avant, "apres": cible},
    )
    if not automatique and affaire.contact_id is not None:
        moteur_sequences.arreter_actives(session, affaire.contact_id,
                                         "perdu" if cible == perdue else "etape_changee", membre_id)
    return True


def modifier(session: Session, affaire: Affaire, champs: dict, membre: Membre) -> None:
    """PATCH /affaires/{id} : tout est validé avant d'écrire."""
    cible = champs.get("etape", affaire.etape)
    if cible not in cles_etapes(affaire.pipeline):
        raise ErreurAffaire(422, "Étape inconnue pour ce pipeline")
    perdue = etape_perdue(affaire.pipeline)
    if champs.get("perdue_raison") and cible != perdue:
        raise ErreurAffaire(422, "Une raison de perte suppose le passage en perdu")
    if champs.get("responsable_id") is not None and session.get(Membre, champs["responsable_id"]) is None:
        raise ErreurAffaire(422, "Membre inconnu")

    if "etape" in champs:
        changer_etape(session, affaire, cible, membre_id=membre.id)
    if "perdue_raison" in champs:
        affaire.perdue_raison = champs["perdue_raison"] or None
    if "responsable_id" in champs:
        affaire.responsable_id = champs["responsable_id"]
    if "montant_mensuel" in champs:  # saisi par l'équipe uniquement (invariant 9)
        affaire.montant_mensuel = champs["montant_mensuel"]
    affaire.maj_at = temps.maintenant()
    session.add(affaire)


def resume_api(affaire: Affaire) -> dict:
    return {"id": affaire.id, "pipeline": affaire.pipeline, "etape": etape(affaire.pipeline, affaire.etape)}


def affaire_api(session: Session, affaire: Affaire) -> dict:
    p = PIPELINES[affaire.pipeline]
    montant = affaire.montant_mensuel
    return {
        **resume_api(affaire),
        "etape_depuis": temps.iso(affaire.etape_depuis),
        "etapes_possibles": [{"cle": c, "nom": n} for c, n in p["etapes"] + [p["perdue"]]],
        "responsable": membre_api(session.get(Membre, affaire.responsable_id)) if affaire.responsable_id else None,
        "montant_mensuel": f"{Decimal(montant):.2f}" if montant is not None else None,
        "perdue_raison": affaire.perdue_raison,
    }
