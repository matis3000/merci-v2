"""Routes publiques : inscription de la landing, événements de l'App MERCI, désinscription
(section 4.10)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from .. import securite
from ..config import settings
from ..db import get_session
from ..emails import gabarits
from ..fournisseurs import get_crm_externe_provider, get_email_provider
from ..fournisseurs.base import CrmExterneProvider, EmailProvider
from ..modeles import Contact, normaliser_email
from ..services import capture, evenements_app, moteur_sequences, synchro_hubspot
from ..services.contacts import email_valide

router = APIRouter(prefix="/public", tags=["public"])

limite_inscription = securite.LimiteDebit(5, dt.timedelta(minutes=1))


def _limite(request: Request) -> None:
    """Compte toutes les requêtes, valides ou non : passe avant la validation du corps."""
    if not limite_inscription.autoriser(securite.ip_client(request)):
        raise HTTPException(429, "Trop d'envois, réessayez dans une minute")


def _cle_app(x_cle_app: str | None = Header(default=None)) -> None:
    if not securite.secrets_egaux(x_cle_app, settings.cle_app_merci):
        raise HTTPException(401, "Clé de l'App MERCI invalide")


class InscriptionCorps(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    profil: Literal["donateur", "association", "entreprise"]
    prenom: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    structure: str | None = Field(default=None, max_length=200)
    source: str = Field(min_length=1, max_length=60)
    source_detail: str | None = Field(default=None, max_length=60)
    date: str | None = Field(default=None, max_length=40)
    consentement: Any = None
    consentement_texte: str | None = Field(default=None, max_length=500)
    site_web: str | None = Field(default=None, max_length=300)  # champ piège


@router.post("/inscription", status_code=201, dependencies=[Depends(_limite)])
def inscription(
    corps: InscriptionCorps,
    taches: BackgroundTasks,
    session: Session = Depends(get_session),
    email_provider: EmailProvider = Depends(get_email_provider),
    crm: CrmExterneProvider = Depends(get_crm_externe_provider),
):
    if corps.site_web:
        return {"ok": True}  # robot : rien n'est écrit, rien n'est dit
    if corps.consentement is not True or not corps.consentement_texte:
        raise HTTPException(422, "Consentement obligatoire")
    email = normaliser_email(corps.email)
    if not email_valide(email):
        raise HTTPException(422, "Adresse e-mail invalide")
    if corps.profil != "donateur" and not corps.structure:
        raise HTTPException(422, "Nom de la structure obligatoire")

    res = capture.capturer(session, capture.Inscription(
        profil=corps.profil, prenom=corps.prenom, email=email,
        structure=corps.structure if corps.profil != "donateur" else None,
        source=corps.source, source_detail=corps.source_detail or None, date=corps.date,
        consentement_texte=corps.consentement_texte,
    ))
    session.commit()
    if res.inscriptions:
        taches.add_task(capture.executer_inscriptions, res.inscriptions, email_provider)
    if res.notifications:
        taches.add_task(capture.envoyer_notifications, email_provider, res.notifications)
    if res.inscriptions:  # le premier pas peut avancer l'étape : nouvel envoi HubSpot après lui
        taches.add_task(synchro_hubspot.envoyer_en_tache_de_fond, crm)
    return {"ok": True}


class EvenementCorps(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    type: Literal["compte_cree", "don", "don_suivi"]
    at: dt.datetime | None = None


@router.post("/evenement", dependencies=[Depends(_cle_app)])
def evenement(corps: EvenementCorps, session: Session = Depends(get_session)):
    rep = evenements_app.traiter(session, normaliser_email(corps.email), corps.type, corps.at)
    session.commit()
    return rep


def _desinscrire(jeton: str, session: Session) -> bool:
    contact_id = securite.lire_jeton_desinscription(jeton)
    contact = session.get(Contact, contact_id) if contact_id is not None else None
    if contact is None:
        return False
    moteur_sequences.desinscrire(session, contact)
    session.commit()
    return True


_LIEN_INVALIDE = gabarits.page("Lien invalide", "Lien invalide. Écrivez-nous et nous vous désinscrirons à la main.")


@router.get("/desinscription/{jeton}", response_class=HTMLResponse)
def desinscription_page(jeton: str, session: Session = Depends(get_session)):
    """Un clic suffit (décision D12) : pas de page de confirmation."""
    if not _desinscrire(jeton, session):
        return HTMLResponse(_LIEN_INVALIDE, status_code=400)
    return HTMLResponse(gabarits.page("Désinscription", "C'est noté, vous ne recevrez plus nos e-mails."))


@router.post("/desinscription/{jeton}", response_class=PlainTextResponse)
def desinscription_un_clic(jeton: str, session: Session = Depends(get_session)):
    """Désinscription en un clic des messageries (RFC 8058, `List-Unsubscribe=One-Click`)."""
    if not _desinscrire(jeton, session):
        return HTMLResponse(_LIEN_INVALIDE, status_code=400)
    return PlainTextResponse("ok")
