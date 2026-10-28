"""Réglages et équipe (section 4.9).

L'expéditeur, l'adresse de réponse et le créneau sont réservés à l'administrateur ; la pause
générale et les liens sont modifiables par toute l'équipe.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session, select

from .. import auth, temps
from ..auth import admin_requis, membre_connecte
from ..config import settings
from ..db import get_session
from ..emails import gabarits
from ..fournisseurs import get_email_provider
from ..fournisseurs.base import EmailProvider, ErreurFournisseur, MessageEmail
from ..modeles import Activite, Envoi, JetonConnexion, Membre, Reglage, normaliser_email
from ..services.accueil import creneau as creneau_api, etat_linkedin
from ..services import synchro_hubspot
from ..services.affaires import membre_api
from ..services.capture import expediteur
from ..services.contacts import email_valide

log = logging.getLogger("merci.reglages")
router = APIRouter(tags=["reglages"])


class CreneauCorps(BaseModel):
    jours: list[int] = Field(min_length=1, max_length=7)
    debut: int = Field(ge=0, le=23)
    fin: int = Field(ge=1, le=24)

    @field_validator("jours")
    @classmethod
    def _jours(cls, v: list[int]) -> list[int]:
        if any(j < 1 or j > 7 for j in v):
            raise ValueError("Jours attendus de 1 (lundi) à 7 (dimanche)")
        return sorted(set(v))

    @model_validator(mode="after")
    def _ordre(self) -> "CreneauCorps":
        if self.fin <= self.debut:
            raise ValueError("L'heure de fin doit suivre l'heure de début")
        return self


class ExpediteurCorps(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)


class ReglagesCorps(BaseModel):
    relances_en_pause: bool | None = None
    creneau: CreneauCorps | None = None
    expediteur: ExpediteurCorps | None = None
    reponse_a: str | None = Field(default=None, max_length=254)
    lien_rdv: str | None = Field(default=None, max_length=300)
    lien_creation_compte: str | None = Field(default=None, max_length=300)
    hubspot_etapes: dict[str, dict[str, str | None]] | None = None   # {pipeline: {étape: id d'étape HubSpot}}


RESERVES_ADMIN = ("creneau", "expediteur", "reponse_a", "hubspot_etapes")


def _email(valeur: str | None) -> str | None:
    email = normaliser_email(valeur)
    if email is not None and not email_valide(email):
        raise HTTPException(422, "Adresse e-mail invalide")
    return email


def _lien(valeur: str | None) -> str | None:
    lien = (valeur or "").strip() or None
    if lien is None:
        return None
    prefixes = ("https://",) if settings.mode == "production" else ("https://", "http://")
    if not lien.startswith(prefixes) or " " in lien:
        raise HTTPException(422, "Adresse web invalide : https attendu")
    return lien


def reglages_api(session: Session) -> dict:
    r = session.get(Reglage, 1)
    derniere_inscription = session.exec(select(sa.func.max(Activite.cree_at)).where(
        Activite.type.in_(("inscription", "reinscription")))).one()
    envoi_email = select(Envoi).where(Envoi.canal == "email").order_by(Envoi.maj_at.desc(), Envoi.id.desc())
    dernier = session.exec(envoi_email).first()
    derniere_erreur = session.exec(envoi_email.where(Envoi.statut.in_(("erreur", "echec")))).first()
    if not settings.resend_api_key:
        etat_email = "non_configure"
    elif dernier is not None and dernier.statut in ("erreur", "echec"):
        etat_email = "erreur"
    else:
        etat_email = "ok"
    cle = settings.cle_app_merci
    equipe = session.exec(select(Membre).order_by(Membre.id))
    return {
        "relances_en_pause": r.relances_en_pause,
        "creneau": {**creneau_api(r), "fuseau": "Europe/Paris"},
        "expediteur": {"nom": r.expediteur_nom or settings.email_expediteur_nom,
                       "email": r.expediteur_email or settings.email_expediteur},
        "reponse_a": r.reponse_a, "lien_rdv": r.lien_rdv, "lien_creation_compte": r.lien_creation_compte,
        "pilote_ouvert_at": temps.iso(r.pilote_ouvert_at),
        "connexions": {
            "landing": {"derniere_inscription_at": temps.iso(derniere_inscription), "origines": settings.origines_cors},
            "email": {"fournisseur": "resend" if settings.resend_api_key else "console", "etat": etat_email,
                      "derniere_erreur_at": temps.iso(derniere_erreur.maj_at) if derniere_erreur else None},
            "linkedin": {"fournisseur": settings.linkedin_fournisseur, "etat": etat_linkedin(r)},
            "app_merci": {"cle_configuree": bool(cle), "cle_masquee": f"••••{cle[-4:]}" if cle else None},
        },
        "equipe": [membre_api(m) for m in equipe],
        "hubspot_etapes": synchro_hubspot.lire_correspondance(r),
    }


@router.get("/reglages", dependencies=[Depends(membre_connecte)])
def lire(session: Session = Depends(get_session)):
    return reglages_api(session)


@router.patch("/reglages")
def modifier(corps: ReglagesCorps, session: Session = Depends(get_session), membre: Membre = Depends(membre_connecte)):
    champs = corps.model_fields_set
    if membre.role != "admin" and any(c in champs for c in RESERVES_ADMIN):
        raise HTTPException(403, "Action réservée à l'administrateur")
    r = session.get(Reglage, 1)
    if "reponse_a" in champs:
        r.reponse_a = _email(corps.reponse_a)
    if corps.expediteur is not None:
        email = _email(corps.expediteur.email)
        if email is None:
            raise HTTPException(422, "Adresse e-mail invalide")
        r.expediteur_nom, r.expediteur_email = corps.expediteur.nom.strip(), email
    if "lien_rdv" in champs:
        r.lien_rdv = _lien(corps.lien_rdv)
    if "lien_creation_compte" in champs:
        r.lien_creation_compte = _lien(corps.lien_creation_compte)
    if corps.creneau is not None:
        r.creneau_jours = ",".join(str(j) for j in corps.creneau.jours)
        r.creneau_debut, r.creneau_fin = corps.creneau.debut, corps.creneau.fin
    if corps.relances_en_pause is not None:
        r.relances_en_pause = corps.relances_en_pause
    if corps.hubspot_etapes is not None:
        try:
            r.hubspot_etapes = json.dumps(synchro_hubspot.valider_correspondance(corps.hubspot_etapes))
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
    r.maj_at = temps.maintenant()
    session.add(r)
    session.commit()
    return reglages_api(session)


class NouveauMembre(BaseModel):
    email: str = Field(max_length=254)
    prenom: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "equipe"]


class MembreModifie(BaseModel):
    prenom: str | None = Field(default=None, min_length=1, max_length=80)
    role: Literal["admin", "equipe"] | None = None
    actif: bool | None = None


def _inviter(session: Session, membre: Membre, fournisseur: EmailProvider) -> None:
    """Lien magique envoyé au nouveau membre : message de service (décision D19)."""
    jeton = auth.new_magic_token()
    t = temps.maintenant()
    session.add(JetonConnexion(jeton_hash=auth.hash_magic_token(jeton), email=membre.email,
                               expire_at=t + auth.DUREE_LIEN, cree_at=t))
    session.commit()
    url = f"{settings.web_url.rstrip('/')}/connexion/verifier?jeton={jeton}"
    sujet, html, texte = gabarits.lien_magique(url)
    try:
        fournisseur.envoyer(MessageEmail(a=membre.email, sujet=sujet, html=html, texte=texte,
                                         expediteur=expediteur(session)))
    except ErreurFournisseur as e:
        log.warning("invitation non envoyée : %s", e)


@router.post("/equipe", status_code=201, dependencies=[Depends(admin_requis)])
def ajouter(corps: NouveauMembre, session: Session = Depends(get_session),
            fournisseur: EmailProvider = Depends(get_email_provider)):
    email = _email(corps.email)
    if email is None:
        raise HTTPException(422, "Adresse e-mail invalide")
    if session.exec(select(Membre).where(Membre.email == email)).first() is not None:
        raise HTTPException(409, "Ce membre existe déjà")
    m = Membre(email=email, prenom=corps.prenom.strip(), role=corps.role, actif=True, cree_at=temps.maintenant())
    session.add(m)
    session.commit()
    session.refresh(m)
    _inviter(session, m, fournisseur)
    return membre_api(m)


@router.patch("/equipe/{membre_id}", dependencies=[Depends(admin_requis)])
def modifier_membre(membre_id: int, corps: MembreModifie, session: Session = Depends(get_session)):
    m = session.get(Membre, membre_id)
    if m is None:
        raise HTTPException(404, "Membre introuvable")
    champs = corps.model_dump(exclude_unset=True, exclude_none=True)
    perd_admin = m.role == "admin" and m.actif and (champs.get("role") == "equipe" or champs.get("actif") is False)
    if perd_admin:
        autres = session.exec(select(sa.func.count()).select_from(Membre).where(
            Membre.role == "admin", Membre.actif.is_(True), Membre.id != m.id)).one()
        if not autres:
            raise HTTPException(409, "Il faut garder au moins un administrateur actif")
    for cle, valeur in champs.items():
        setattr(m, cle, valeur.strip() if isinstance(valeur, str) else valeur)
    session.add(m)
    session.commit()
    session.refresh(m)
    return membre_api(m)

