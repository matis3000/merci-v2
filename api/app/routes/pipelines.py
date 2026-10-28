"""Pipelines et affaires (section 4.5)."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..auth import membre_connecte
from ..db import get_session
from ..modeles import Affaire, Membre
from ..pipelines import PIPELINES, definition, etape, etape_perdue
from ..services import affaires as svc_affaires
from ..services import contacts as svc_contacts

router = APIRouter(tags=["pipelines"], dependencies=[Depends(membre_connecte)])


@router.get("/pipelines")
def lister():
    return [definition(cle) for cle in PIPELINES]


def _carte(vue: svc_contacts.Vue, a: Affaire) -> tuple[dict, str]:
    contact = vue.contacts.get(a.contact_id) if a.contact_id else None
    org = vue.orgs.get(a.organisation_id) if a.organisation_id else None
    if org is None and contact is not None and contact.organisation_id:
        org = vue.orgs.get(contact.organisation_id)
    if contact is None:
        titre, sous_titre = org.nom, "Aucun décideur trouvé"
    elif a.pipeline == "entreprises":
        complet = " ".join(x for x in (contact.prenom, contact.nom) if x)
        titre = org.nom if org else svc_contacts.nom_affiche(contact)
        sous_titre = ", ".join(x for x in (complet, contact.poste) if x) if org else (contact.poste or "Entreprise")
    elif a.pipeline == "associations":
        titre = svc_contacts.nom_affiche(contact, org)
        sous_titre = org.nom if org else "Association"
    else:
        titre = svc_contacts.nom_affiche(contact, org)
        origine = svc_contacts.libelle_detail(contact.source_detail or svc_contacts.SOURCES_LIBELLES[contact.source])
        sous_titre = f"Via {origine}"
    carte = {
        "affaire_id": a.id,
        "cible": {"genre": "contact", "id": contact.id} if contact else {"genre": "organisation", "id": org.id},
        "titre": titre, "sous_titre": sous_titre,
        "note": org.note if org else None,
        "sequence": vue.etat_sequence(contact) if contact else None,
    }
    recherche = svc_contacts.normaliser(" ".join(x for x in (
        titre, sous_titre, contact.email if contact else None, org.nom if org else None) if x))
    return carte, recherche


@router.get("/pipelines/{cle}")
def voir(cle: str, q: str | None = Query(default=None, max_length=200), session: Session = Depends(get_session)):
    if cle not in PIPELINES:
        raise HTTPException(404, "Pipeline inconnu")
    vue = svc_contacts.Vue(session)
    perdue = etape_perdue(cle)
    filtre = svc_contacts.normaliser(q)
    compte = Counter(a.pipeline for a in vue.affaires if a.etape != etape_perdue(a.pipeline))
    colonnes = {c: [] for c, _ in PIPELINES[cle]["etapes"]}
    perdus = 0
    for a in sorted((a for a in vue.affaires if a.pipeline == cle), key=lambda a: (a.etape_depuis, a.id), reverse=True):
        carte, recherche = _carte(vue, a)
        if filtre and filtre not in recherche:
            continue
        if a.etape == perdue:
            perdus += 1
        elif a.etape in colonnes:
            colonnes[a.etape].append(carte)
    return {
        "pipeline": definition(cle),
        "colonnes": [{"etape": etape(cle, c), "cartes": cartes} for c, cartes in colonnes.items()],
        "perdus": perdus,
        "compte_par_pipeline": {p: compte[p] for p in PIPELINES},
    }


class AffaireCorps(BaseModel):
    etape: str | None = Field(default=None, max_length=40)
    perdue_raison: str | None = Field(default=None, max_length=300)
    responsable_id: int | None = None
    montant_mensuel: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


@router.patch("/affaires/{affaire_id}")
def modifier(affaire_id: int, corps: AffaireCorps, session: Session = Depends(get_session),
             membre: Membre = Depends(membre_connecte)):
    affaire = session.get(Affaire, affaire_id)
    if affaire is None:
        raise HTTPException(404, "Affaire introuvable")
    champs = corps.model_dump(exclude_unset=True)
    if "etape" in champs and champs["etape"] is None:
        raise HTTPException(422, "Étape inconnue pour ce pipeline")
    try:
        svc_affaires.modifier(session, affaire, champs, membre)
    except svc_affaires.ErreurAffaire as e:
        raise HTTPException(e.statut, e.message) from None
    session.commit()
    session.refresh(affaire)
    return svc_affaires.affaire_api(session, affaire)
