"""Écran Prospection (section 4.8) : vue, cible, lancement manuel d'un passage."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlmodel import Session

from ..auth import membre_connecte
from ..db import get_session
from ..fournisseurs import get_crm_externe_provider, get_linkedin_provider
from ..fournisseurs.base import CrmExterneProvider, LinkedInProvider
from ..prospection import moteur
from ..services import synchro_hubspot

router = APIRouter(prefix="/prospection", tags=["prospection"], dependencies=[Depends(membre_connecte)])

CodeDepartement = Annotated[str, StringConstraints(pattern=r"^(\d{2,3}|2[AB])$")]
Poste = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class CibleCorps(BaseModel):
    departements: list[CodeDepartement] = Field(min_length=1, max_length=5)
    effectif_min: Literal[50, 100, 200, 250, 500]
    postes: list[Poste] = Field(min_length=1, max_length=10)
    plafond_jour: int = Field(ge=1, le=80)
    seuil: int = Field(ge=1, le=10)


@router.get("")
def vue(session: Session = Depends(get_session)):
    return moteur.vue(session)


@router.put("/cible")
def cible(corps: CibleCorps, session: Session = Depends(get_session)):
    return moteur.changer_cible(session, corps.model_dump())


@router.post("/lancer", status_code=202)
def lancer(taches: BackgroundTasks, session: Session = Depends(get_session),
           linkedin: LinkedInProvider = Depends(get_linkedin_provider),
           crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    try:
        passage, jeton = moteur.demarrer(session, "manuel")
    except moteur.ErreurProspection as e:
        raise HTTPException(e.statut, e.message) from None
    taches.add_task(moteur.executer, passage.id, jeton, linkedin)
    taches.add_task(synchro_hubspot.envoyer_en_tache_de_fond, crm)   # après le passage
    return {"passage_id": passage.id}
