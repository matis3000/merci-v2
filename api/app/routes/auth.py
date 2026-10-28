"""Routes /auth : lien magique, vérification, session, déconnexion (section 4.3).

Seuls les membres existants et actifs reçoivent un lien ; la réponse est identique pour
toute adresse (pas d'énumération). Le jeton voyage dans le corps JSON, jamais dans l'URL d'un
POST, et seul son hash est stocké.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from .. import auth, securite, temps
from ..config import settings
from ..db import get_session
from ..emails import gabarits
from ..fournisseurs import get_email_provider
from ..fournisseurs.base import EmailProvider, ErreurFournisseur, MessageEmail
from ..modeles import JetonConnexion, Membre, Reglage, normaliser_email

log = logging.getLogger("merci.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

limite_lien = securite.LimiteDebit(5, dt.timedelta(minutes=1))
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MembreRep(BaseModel):
    id: int
    email: str
    prenom: str
    role: str
    actif: bool


class DemandeLien(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _email_valide(cls, v: str) -> str:
        v = normaliser_email(v) or ""
        if not _EMAIL.match(v):
            raise ValueError("Adresse e-mail invalide")
        return v


class Verification(BaseModel):
    jeton: str = Field(min_length=1, max_length=200)


def _expediteur(session: Session) -> str:
    r = session.get(Reglage, 1)
    nom = (r.expediteur_nom if r else "") or settings.email_expediteur_nom
    adresse = (r.expediteur_email if r else "") or settings.email_expediteur
    return f"{nom} <{adresse}>"


@router.post("/lien")
def demander_lien(
    corps: DemandeLien,
    request: Request,
    session: Session = Depends(get_session),
    email_provider: EmailProvider = Depends(get_email_provider),
):
    if not limite_lien.autoriser(securite.ip_client(request)):
        raise HTTPException(429, "Trop de demandes, réessayez dans une minute")
    rep: dict = {"ok": True}
    membre = session.exec(select(Membre).where(Membre.email == corps.email)).first()
    if membre is None or not membre.actif:
        return rep

    jeton = auth.new_magic_token()
    t = temps.maintenant()
    session.add(JetonConnexion(jeton_hash=auth.hash_magic_token(jeton), email=membre.email,
                               expire_at=t + auth.DUREE_LIEN, cree_at=t))
    session.commit()
    url = f"{settings.web_url.rstrip('/')}/connexion/verifier?jeton={jeton}"
    sujet, html, texte = gabarits.lien_magique(url)
    # Message de service : ignore pause et créneau (décision D19).
    try:
        email_provider.envoyer(MessageEmail(a=membre.email, sujet=sujet, html=html, texte=texte,
                                            expediteur=_expediteur(session)))
    except ErreurFournisseur as e:
        log.warning("lien de connexion non envoyé : %s", e)
    if settings.mode == "development" and auth.is_local_request(request):
        rep["dev_lien"] = url
    return rep


@router.post("/verifier")
def verifier(corps: Verification, response: Response, session: Session = Depends(get_session)):
    t = temps.maintenant()
    jeton_hash = auth.hash_magic_token(corps.jeton)
    table = JetonConnexion.__table__
    # Usage unique : le jeton est consommé par une seule mise à jour conditionnelle.
    res = session.execute(
        sa.update(table)
        .where(table.c.jeton_hash == jeton_hash, table.c.utilise_at.is_(None), table.c.expire_at > t)
        .values(utilise_at=t)
    )
    session.commit()
    if res.rowcount != 1:
        raise HTTPException(401, "Lien invalide ou expiré, demandez-en un nouveau")
    ligne = session.exec(select(JetonConnexion).where(JetonConnexion.jeton_hash == jeton_hash)).one()
    membre = session.exec(select(Membre).where(Membre.email == ligne.email)).first()
    if membre is None:
        raise HTTPException(401, "Lien invalide ou expiré, demandez-en un nouveau")
    if not membre.actif:
        raise HTTPException(403, "Compte désactivé")
    membre.derniere_connexion_at = t
    session.add(membre)
    session.commit()
    auth.poser_cookie(response, auth.create_jwt(membre.id, membre.email))
    return {"membre": MembreRep.model_validate(membre, from_attributes=True)}


@router.get("/moi", response_model=MembreRep)
def moi(membre: Membre = Depends(auth.membre_connecte)):
    return membre


@router.post("/deconnexion", status_code=204)
def deconnexion():
    response = Response(status_code=204)
    auth.effacer_cookie(response)
    return response
