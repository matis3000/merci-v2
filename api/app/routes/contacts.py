"""Contacts, organisations, fiche, fil, import et export CSV, pause et inscription manuelle
(sections 4.6 et 4.7)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import temps
from ..auth import membre_connecte
from ..db import get_session
from ..modeles import Contact, InscriptionSequence, Membre, Organisation
from ..pipelines import PIPELINES, cles_etapes
from ..services import contacts as svc
from ..services import moteur_sequences

router = APIRouter(tags=["contacts"], dependencies=[Depends(membre_connecte)])

TypeContact = Literal["donateur", "association", "entreprise"]
SequenceCle = Literal["donateur-bienvenue", "donateur-pilote", "entreprise-entrante", "association-bienvenue",
                      "entreprise-prospection"]


def filtres(
    type: TypeContact | None = None,
    source: Literal["landing", "prospection", "import", "manuel"] | None = None,
    pipeline: Literal["donateurs", "entreprises", "associations"] | None = None,
    etape: str | None = Query(default=None, max_length=40),
    note_min: int | None = Query(default=None, ge=0, le=10),
    sequence: SequenceCle | None = None,
    etat_sequence: Literal["due", "active", "pause", "echec", "arret", "fini"] | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> svc.Filtres:
    if etape is not None:
        connues = cles_etapes(pipeline) if pipeline else {e for p in PIPELINES for e in cles_etapes(p)}
        if etape not in connues:
            raise HTTPException(422, "Étape inconnue")
    return svc.Filtres(type=type, source=source, pipeline=pipeline, etape=etape, note_min=note_min,
                       sequence=sequence, etat_sequence=etat_sequence, q=q or None)


def _erreur(e: svc.ErreurContact):
    if e.statut == 409 and e.contact_id is not None:
        return JSONResponse({"detail": e.message, "contact_id": e.contact_id}, status_code=409)
    raise HTTPException(e.statut, e.message)


def _contact(session: Session, contact_id: int) -> Contact:
    c = session.get(Contact, contact_id)
    if c is None:
        raise HTTPException(404, "Contact introuvable")
    return c


def _organisation(session: Session, organisation_id: int) -> Organisation:
    o = session.get(Organisation, organisation_id)
    if o is None:
        raise HTTPException(404, "Organisation introuvable")
    return o


# --------------------------------------------------------------------------- liste, export, import

@router.get("/contacts")
def lister(f: svc.Filtres = Depends(filtres), page: int = Query(default=1, ge=1),
           par_page: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)):
    return svc.liste(session, f, page, par_page)


@router.get("/contacts/export.csv")
def exporter(f: svc.Filtres = Depends(filtres), session: Session = Depends(get_session)):
    jour = temps.jour_paris(temps.maintenant()).isoformat()
    return Response(svc.exporter(session, f), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="contacts-merci-{jour}.csv"'})


@router.post("/contacts/import")
async def importer(fichier: UploadFile = File(...), session: Session = Depends(get_session)):
    contenu = await fichier.read(svc.TAILLE_MAX_IMPORT + 1)
    try:
        bilan = svc.importer(session, contenu)
    except svc.ErreurContact as e:
        session.rollback()
        raise HTTPException(e.statut, e.message) from None
    session.commit()
    return bilan


# --------------------------------------------------------------------------- création, fiche

class ContactCorps(BaseModel):
    prenom: str | None = Field(default=None, max_length=80)
    nom: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telephone: str | None = Field(default=None, max_length=30)
    poste: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=300)
    ville: str | None = Field(default=None, max_length=120)
    organisation_nom: str | None = Field(default=None, max_length=200)
    source_detail: str | None = Field(default=None, max_length=80)


class NouveauContact(ContactCorps):
    type: TypeContact


class ContactModifie(ContactCorps):
    linkedin_provider_id: str | None = Field(default=None, max_length=120)


@router.post("/contacts", status_code=201)
def creer(corps: NouveauContact, session: Session = Depends(get_session), membre: Membre = Depends(membre_connecte)):
    try:
        c = svc.creer_contact(session, corps.model_dump(), membre)
    except svc.ErreurContact as e:
        session.rollback()
        return _erreur(e)
    session.commit()
    return svc.fiche_contact(session, c)


@router.get("/contacts/{contact_id}")
def fiche(contact_id: int, session: Session = Depends(get_session)):
    return svc.fiche_contact(session, _contact(session, contact_id))


@router.patch("/contacts/{contact_id}")
def modifier(contact_id: int, corps: ContactModifie, session: Session = Depends(get_session)):
    c = _contact(session, contact_id)
    try:
        svc.modifier_contact(session, c, corps.model_dump(exclude_unset=True))
    except svc.ErreurContact as e:
        session.rollback()
        return _erreur(e)
    session.commit()
    return svc.fiche_contact(session, c)


class OrganisationCorps(BaseModel):
    nom: str | None = Field(default=None, max_length=200)
    ville: str | None = Field(default=None, max_length=120)
    site_web: str | None = Field(default=None, max_length=300)


@router.get("/organisations/{organisation_id}")
def fiche_organisation(organisation_id: int, session: Session = Depends(get_session)):
    return svc.fiche_organisation(session, _organisation(session, organisation_id))


@router.patch("/organisations/{organisation_id}")
def modifier_organisation(organisation_id: int, corps: OrganisationCorps, session: Session = Depends(get_session)):
    o = _organisation(session, organisation_id)
    try:
        svc.modifier_organisation(session, o, corps.model_dump(exclude_unset=True))
    except svc.ErreurContact as e:
        session.rollback()
        raise HTTPException(e.statut, e.message) from None
    session.commit()
    return svc.fiche_organisation(session, o)


# --------------------------------------------------------------------------- fil d'activité

class NoteCorps(BaseModel):
    type: Literal["note", "appel"]
    texte: str = Field(min_length=1, max_length=5000)


@router.get("/contacts/{contact_id}/activites")
def activites_contact(contact_id: int, avant: int | None = None, limite: int = Query(default=50, ge=1, le=200),
                      session: Session = Depends(get_session)):
    _contact(session, contact_id)
    fil, suivant = svc.activites(session, contact_id=contact_id, avant=avant, limite=limite)
    return {"activites": fil, "suivant": suivant}


@router.get("/organisations/{organisation_id}/activites")
def activites_organisation(organisation_id: int, avant: int | None = None,
                           limite: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)):
    _organisation(session, organisation_id)
    fil, suivant = svc.activites(session, organisation_id=organisation_id, avant=avant, limite=limite)
    return {"activites": fil, "suivant": suivant}


@router.post("/contacts/{contact_id}/activites", status_code=201)
def noter_contact(contact_id: int, corps: NoteCorps, session: Session = Depends(get_session),
                  membre: Membre = Depends(membre_connecte)):
    rep = svc.noter(session, type=corps.type, texte=corps.texte, membre=membre, contact=_contact(session, contact_id))
    session.commit()
    return rep


@router.post("/organisations/{organisation_id}/activites", status_code=201)
def noter_organisation(organisation_id: int, corps: NoteCorps, session: Session = Depends(get_session),
                       membre: Membre = Depends(membre_connecte)):
    rep = svc.noter(session, type=corps.type, texte=corps.texte, membre=membre,
                    organisation=_organisation(session, organisation_id))
    session.commit()
    return rep


# --------------------------------------------------------------------------- pause et inscription manuelle

class PauseCorps(BaseModel):
    pause: bool


class SequenceCorps(BaseModel):
    sequence: SequenceCle


def _etat_affiche(session: Session, c: Contact) -> dict | None:
    inscriptions = list(session.exec(select(InscriptionSequence).where(InscriptionSequence.contact_id == c.id)))
    insc = moteur_sequences.inscription_affichee(inscriptions)
    return moteur_sequences.etat(insc, c, moteur_sequences.contexte(session)) if insc else None


@router.post("/contacts/{contact_id}/pause")
def pause(contact_id: int, corps: PauseCorps, session: Session = Depends(get_session)):
    c = _contact(session, contact_id)
    c.pause = corps.pause
    c.maj_at = temps.maintenant()
    session.add(c)
    session.commit()
    return {"pause": c.pause, "sequence": _etat_affiche(session, c)}


@router.post("/contacts/{contact_id}/sequence", status_code=201)
def inscrire(contact_id: int, corps: SequenceCorps, session: Session = Depends(get_session),
             membre: Membre = Depends(membre_connecte)):
    c = _contact(session, contact_id)
    try:
        insc = moteur_sequences.inscrire(session, c, corps.sequence, par=membre.id)
    except moteur_sequences.ErreurSequence as e:
        session.rollback()
        raise HTTPException(e.statut, e.message) from None
    session.commit()
    session.refresh(insc)
    return moteur_sequences.etat(insc, c, moteur_sequences.contexte(session))
