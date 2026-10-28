"""Inscription publique depuis la landing (section 4.10) : contact, organisation, affaire,
séquence, notification de l'équipe pour une association.

Une seule transaction ; l'exécution du premier pas et les notifications partent ensuite en
tâche de fond (la réponse ne les attend pas).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlmodel import Session, select

from .. import temps
from ..config import settings
from ..emails import gabarits
from ..fournisseurs.base import EmailProvider, ErreurFournisseur, MessageEmail
from ..journal import ajouter_activite
from ..modeles import Contact, Membre, Reglage
from . import affaires, moteur_sequences
from .contacts import libelle_detail, organisation_pour

log = logging.getLogger("merci.capture")


@dataclass
class Inscription:
    profil: str
    prenom: str
    email: str                    # déjà validé et normalisé
    structure: str | None
    source: str
    source_detail: str | None
    date: str | None
    consentement_texte: str


@dataclass
class Resultat:
    inscriptions: list[int] = field(default_factory=list)   # nouvelles inscriptions à exécuter
    notifications: list[MessageEmail] = field(default_factory=list)


def expediteur(session: Session) -> str:
    r = session.get(Reglage, 1)
    nom = (r.expediteur_nom if r else "") or settings.email_expediteur_nom
    adresse = (r.expediteur_email if r else "") or settings.email_expediteur
    return f"{nom} <{adresse}>"


def _inscrire_si_jamais(session: Session, contact: Contact, cle: str, res: Resultat) -> None:
    try:
        res.inscriptions.append(moteur_sequences.inscrire(session, contact, cle).id)
    except moteur_sequences.ErreurSequence:
        pass  # déjà parcourue, ou type incompatible : rien de plus à faire


def capturer(session: Session, d: Inscription) -> Resultat:
    """N'enregistre pas la transaction."""
    t = temps.maintenant()
    res = Resultat()
    contact = session.exec(select(Contact).where(Contact.email == d.email)).first()
    nouveau = contact is None
    if nouveau:
        contact = Contact(type=d.profil, prenom=d.prenom, email=d.email, source="landing",
                          source_detail=d.source_detail or d.source, cree_at=t, maj_at=t)
    else:
        contact.prenom = contact.prenom or d.prenom
        contact.source_detail = contact.source_detail or d.source_detail or d.source
        contact.desinscrit_at = None  # nouveau consentement explicite (décision D18)
    contact.consentement_at, contact.consentement_texte, contact.maj_at = t, d.consentement_texte, t
    org = None
    if d.profil != "donateur":
        org = organisation_pour(session, d.structure, d.profil, "landing", chercher_dans_source="landing")
        contact.organisation_id = contact.organisation_id or org.id
    session.add(contact)
    session.flush()

    ajouter_activite(
        session, "inscription" if nouveau else "reinscription",
        "Inscription via la landing" if nouveau else "Nouvelle inscription via la landing",
        texte=f"Source : {libelle_detail(d.source_detail or d.source)}.", contact_id=contact.id,
        organisation_id=org.id if org else None,
        donnees={"profil": d.profil, "source": d.source, "source_detail": d.source_detail, "date": d.date,
                 "structure": d.structure},
    )

    if d.profil == "entreprise":
        affaires.creer(session, "entreprises", "prospect", contact_id=contact.id, organisation_id=org.id)
        _inscrire_si_jamais(session, contact, "entreprise-entrante", res)
    elif d.profil == "donateur":
        pilote_ouvert = session.get(Reglage, 1).pilote_ouvert_at is not None
        affaire = affaires.creer(session, "donateurs", "pilote_ouvert" if pilote_ouvert else "inscrit",
                                 contact_id=contact.id)
        if pilote_ouvert:
            affaires.changer_etape(session, affaire, "pilote_ouvert", automatique=True)
            moteur_sequences.arreter_actives(session, contact.id, "objectif_atteint", sequence="donateur-bienvenue")
        _inscrire_si_jamais(session, contact, "donateur-pilote" if pilote_ouvert else "donateur-bienvenue", res)
    else:
        affaires.creer(session, "associations", "inscrite", contact_id=contact.id, organisation_id=org.id)
        _inscrire_si_jamais(session, contact, "association-bienvenue", res)
        if nouveau:
            res.notifications = _notifications(session, org.nom, d, contact.id)
    return res


def _notifications(session: Session, structure: str, d: Inscription, contact_id: int) -> list[MessageEmail]:
    """Message de service à chaque membre actif : ni pause ni créneau (décision D19)."""
    url = f"{settings.web_url.rstrip('/')}/contacts/{contact_id}"
    sujet, html, texte = gabarits.notification_association(structure, d.prenom, d.email, url)
    de = expediteur(session)
    membres = session.exec(select(Membre).where(Membre.actif.is_(True)).order_by(Membre.id))
    return [MessageEmail(a=m.email, sujet=sujet, html=html, texte=texte, expediteur=de) for m in membres]


def envoyer_notifications(fournisseur: EmailProvider, messages: list[MessageEmail]) -> None:
    for msg in messages:
        try:
            fournisseur.envoyer(msg)
        except ErreurFournisseur as e:
            log.warning("notification association non envoyée : %s", e)


def executer_inscriptions(ids: list[int], fournisseur: EmailProvider) -> None:
    """Envoi immédiat : part si le créneau est ouvert et rien n'est en pause, sinon au premier tick."""
    for inscription_id in ids:
        moteur_sequences.executer_pas(inscription_id, fournisseur)
