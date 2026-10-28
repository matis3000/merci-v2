"""Synchro HubSpot (lot L8) : état, « Tout synchroniser », étapes du pipeline HubSpot (admin),
et dépendance qui programme l'envoi juste après chaque requête d'écriture."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from ..auth import admin_requis
from ..db import get_session
from ..fournisseurs import get_crm_externe_provider
from ..fournisseurs.base import CrmExterneProvider, ErreurFournisseur
from ..services import synchro_hubspot as synchro

router = APIRouter(prefix="/hubspot", tags=["hubspot"], dependencies=[Depends(admin_requis)])


async def planifier_envoi(taches: BackgroundTasks, crm: CrmExterneProvider = Depends(get_crm_externe_provider)) -> None:
    """Dépendance des routeurs qui écrivent : l'envoi part en tâche de fond après la réponse, si la
    requête a écrit un contact, une organisation ou une affaire. `async` : la variable de contexte
    posée ici est visible de la route (exécutée ensuite dans un fil avec une copie du contexte)."""
    taches.add_task(synchro.envoyer_si_marques, synchro.suivre_requete(), crm)


@router.get("/etat")
def etat(session: Session = Depends(get_session), crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    return synchro.etat_api(session, crm)


@router.post("/tout-synchroniser", status_code=202)
def tout_synchroniser(taches: BackgroundTasks, session: Session = Depends(get_session),
                      crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    marques = synchro.tout_marquer(session)
    session.commit()
    taches.add_task(synchro.envoyer_en_tache_de_fond, crm)
    return {"marques": marques}


@router.get("/etapes")
def etapes(crm: CrmExterneProvider = Depends(get_crm_externe_provider)):
    """Étapes du pipeline de deals par défaut, pour régler la correspondance dans Réglages."""
    if not crm.connecte:
        raise HTTPException(409, "HubSpot non connecté : renseignez HUBSPOT_TOKEN")
    try:
        return {"etapes": crm.etapes_pipeline()}
    except ErreurFournisseur as e:
        raise HTTPException(502, str(e)) from None
