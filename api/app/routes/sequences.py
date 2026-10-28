"""Séquences et ouverture du pilote (section 4.7)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import temps
from ..auth import admin_requis, membre_connecte
from ..db import get_session
from ..modeles import Membre, Reglage, TextePas
from ..sequences import NOTE_INVITATION_MAX, SEQUENCES, Pas, longueur_max, variables_inconnues
from ..services import moteur_sequences

router = APIRouter(tags=["sequences"], dependencies=[Depends(membre_connecte)])


class TexteCorps(BaseModel):
    sujet: str | None = Field(default=None, max_length=200)
    corps: str = Field(max_length=5000)


class CoupureCorps(BaseModel):
    coupee: bool


def _pas(cle: str, numero: int) -> Pas:
    seq = SEQUENCES.get(cle)
    if seq is None or not 1 <= numero <= len(seq.pas):
        raise HTTPException(404, "Séquence ou pas introuvable")
    return seq.pas[numero - 1]


def _coupees(session: Session) -> list[str]:
    return json.loads(session.get(Reglage, 1).sequences_coupees or "[]")


@router.get("/sequences")
def lister(session: Session = Depends(get_session)):
    return moteur_sequences.sequences_api(session)


@router.put("/sequences/{cle}/pas/{numero}")
def modifier_texte(cle: str, numero: int, corps: TexteCorps, session: Session = Depends(get_session),
                   membre: Membre = Depends(membre_connecte)):
    p = _pas(cle, numero)
    existant = session.exec(select(TextePas).where(TextePas.sequence == cle, TextePas.pas == numero)).first()
    texte = corps.corps.strip()
    if not texte:  # corps vide : retour au texte par défaut
        if existant is not None:
            session.delete(existant)
            session.commit()
    else:
        sujet = (corps.sujet or "").strip() or None
        if p.canal == "email" and not sujet:
            raise HTTPException(422, "Sujet obligatoire pour un e-mail")
        inconnues = variables_inconnues(texte + " " + (sujet or ""))
        if inconnues:
            raise HTTPException(422, f"Variable inconnue : {{{inconnues[0]}}}")
        if p.canal == "linkedin_invitation" and longueur_max(texte) > NOTE_INVITATION_MAX:
            raise HTTPException(422, f"Invitation LinkedIn : {NOTE_INVITATION_MAX} caractères au plus, "
                                     "variables comprises")
        t = temps.maintenant()
        existant = existant or TextePas(sequence=cle, pas=numero, corps=texte, maj_at=t)
        existant.sujet = sujet if p.canal == "email" else None
        existant.corps, existant.maj_par_id, existant.maj_at = texte, membre.id, t
        session.add(existant)
        session.commit()
    definition = moteur_sequences.definition_api(session, cle, _coupees(session))
    return definition["pas"][numero - 1]


@router.patch("/sequences/{cle}")
def couper(cle: str, corps: CoupureCorps, session: Session = Depends(get_session)):
    if cle not in SEQUENCES:
        raise HTTPException(404, "Séquence introuvable")
    r = session.get(Reglage, 1)
    coupees = [c for c in _coupees(session) if c != cle] + ([cle] if corps.coupee else [])
    r.sequences_coupees, r.maj_at = json.dumps(coupees), temps.maintenant()
    session.add(r)
    session.commit()
    return moteur_sequences.definition_api(session, cle, coupees)


@router.post("/pilote/ouvrir", dependencies=[Depends(admin_requis)])
def ouvrir_pilote(session: Session = Depends(get_session)):
    try:
        rep = moteur_sequences.ouvrir_pilote(session)
    except moteur_sequences.ErreurSequence as e:
        session.rollback()
        raise HTTPException(e.statut, e.message) from None
    session.commit()
    return rep
