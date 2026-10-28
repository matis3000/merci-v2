"""Cron : tick des séquences et passage de prospection (section 4.11). Authentification par `X-Cron-Secret`."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session

from .. import securite
from ..config import settings
from ..db import get_session
from ..fournisseurs import get_crm_externe_provider, get_email_provider, get_linkedin_provider
from ..fournisseurs.base import CrmExterneProvider, EmailProvider, LinkedInProvider
from ..prospection import moteur as prospection
from ..services import moteur_sequences, synchro_hubspot

router = APIRouter(prefix="/cron", tags=["cron"])


def _secret_cron(x_cron_secret: str | None = Header(default=None)) -> None:
    if not securite.secrets_egaux(x_cron_secret, settings.cron_secret):
        raise HTTPException(401, "Secret du cron invalide")


@router.post("/tick", dependencies=[Depends(_secret_cron)])
def tick(email: EmailProvider = Depends(get_email_provider),
         linkedin: LinkedInProvider = Depends(get_linkedin_provider),
         crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    rep = moteur_sequences.tick(email, linkedin)
    # Synchro HubSpot (lot L8) : envois en attente et reprises dues, quel que soit l'état des relances.
    synchro_hubspot.envoyer_en_tache_de_fond(crm)
    return rep


@router.post("/prospection", dependencies=[Depends(_secret_cron)], status_code=202)
def lancer_prospection(taches: BackgroundTasks, session: Session = Depends(get_session),
                       linkedin: LinkedInProvider = Depends(get_linkedin_provider),
                       crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    """202 puis passage en tâche de fond ; 200 `deja_fait` si le passage du jour (Paris) existe."""
    try:
        passage, jeton = prospection.demarrer(session, "cron")
    except prospection.ErreurProspection as e:
        raise HTTPException(e.statut, e.message) from None
    if jeton is None:
        return JSONResponse({"statut": "deja_fait", "passage_id": passage.id}, status_code=200)
    taches.add_task(prospection.executer, passage.id, jeton, linkedin)
    taches.add_task(synchro_hubspot.envoyer_en_tache_de_fond, crm)   # après le passage
    return {"passage_id": passage.id}
