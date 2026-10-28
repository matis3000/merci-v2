"""Webhooks des fournisseurs (section 4.12). La signature est vérifiée par le fournisseur lui-même."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ..db import get_session
from ..fournisseurs import get_email_provider, get_linkedin_provider
from ..fournisseurs.base import EmailProvider, LinkedInProvider, SignatureInvalide
from ..services import moteur_sequences

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/resend")
async def resend(request: Request, session: Session = Depends(get_session),
                 email: EmailProvider = Depends(get_email_provider)):
    corps = await request.body()
    try:
        evenements = email.analyser_webhook(request.headers, corps)
    except SignatureInvalide:
        raise HTTPException(401, "Signature invalide") from None
    for ev in evenements:
        moteur_sequences.traiter_evenement_email(session, ev, "resend")
    session.commit()
    return {"ok": True}


@router.post("/linkedin")
async def linkedin(request: Request, session: Session = Depends(get_session),
                   fournisseur: LinkedInProvider = Depends(get_linkedin_provider)):
    """Chemin neutre (décision D2) : le fournisseur configuré vérifie et normalise l'événement."""
    corps = await request.body()
    try:
        evenements = fournisseur.analyser_webhook(request.headers, corps)
    except SignatureInvalide:
        raise HTTPException(401, "Signature invalide") from None
    traites = sum(moteur_sequences.traiter_evenement_linkedin(session, ev, fournisseur.nom) for ev in evenements)
    session.commit()
    return {"ok": True, "traites": traites}
