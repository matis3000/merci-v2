"""Synchro sens unique CRM MERCI vers HubSpot (lot L8).

Marquage : toute création ou modification d'un contact, d'une organisation ou d'une affaire, quel
que soit le service qui l'écrit (capture, saisie, import, pipeline, prospection, séquences,
webhooks), marque l'objet « à synchroniser » dans la même transaction, par un écouteur
`after_flush` de session. Un retour arrière annule donc aussi le marquage.

Envoi : juste après la réponse (tâche de fond) et à chaque tick pour reprendre les échecs, sous
le verrou nommé `hubspot`. Ordre : organisations, contacts, affaires, avec leurs associations.
Échec : essais espacés (1 min, 5 min, 30 min, 2 h), plafond `ESSAIS_MAX` ; une nouvelle
modification ou « Tout synchroniser » relance les essais.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from contextvars import ContextVar
from decimal import Decimal
from typing import Callable
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session as SessionOrm
from sqlmodel import Session, select

from .. import db, temps, verrou
from ..fournisseurs.base import CrmExterneProvider, ErreurFournisseur, LimiteDebit, ObjetIntrouvable, ProprieteCrm
from ..modeles import Affaire, Contact, Organisation, Reglage, SynchroHubspot
from ..pipelines import PIPELINES, cles_etapes, etape

log = logging.getLogger("merci.hubspot")
_table = SynchroHubspot.__table__

ESSAIS_MAX = 5
DELAIS = (dt.timedelta(minutes=1), dt.timedelta(minutes=5), dt.timedelta(minutes=30), dt.timedelta(hours=2))
LOT = 200
DUREE_VERROU = dt.timedelta(minutes=10)
ORDRE = ("organisation", "contact", "affaire")
MODELES = {"contact": Contact, "organisation": Organisation, "affaire": Affaire}
_TYPES = {Contact: "contact", Organisation: "organisation", Affaire: "affaire"}

GROUPE = ("merci", "MERCI")
PROPRIETES = [
    ProprieteCrm("contacts", "merci_type", "Type MERCI", "enumeration", "select",
                 (("donateur", "Donateur"), ("association", "Association"), ("entreprise", "Entreprise"))),
    ProprieteCrm("contacts", "merci_source", "Source MERCI", "string", "text"),
    ProprieteCrm("contacts", "merci_consentement", "Consentement MERCI", "date", "date"),
    ProprieteCrm("contacts", "merci_desinscrit", "Désinscription MERCI", "date", "date"),
    ProprieteCrm("companies", "merci_type", "Type MERCI", "enumeration", "select",
                 (("entreprise", "Entreprise"), ("association", "Association"))),
    ProprieteCrm("deals", "merci_pipeline", "Pipeline MERCI", "string", "text"),
    ProprieteCrm("deals", "merci_etape", "Étape MERCI", "string", "text"),
]


class DonneesInsuffisantes(ErreurFournisseur):
    """L'objet ne peut pas être envoyé tel quel : pas de nouvel essai avant une modification."""


# --------------------------------------------------------------------------- marquage

def marquer(conn, objet_type: str, objet_id: int, t: dt.datetime | None = None) -> None:
    """À synchroniser, essais remis à zéro, version + 1. Portable SQLite et Postgres."""
    t = t or temps.maintenant()
    res = conn.execute(
        sa.update(_table).where(_table.c.objet_type == objet_type, _table.c.objet_id == objet_id)
        .values(etat="a_synchroniser", essais=0, derniere_erreur=None, prochain_essai_at=None,
                version=_table.c.version + 1, maj_at=t))
    if res.rowcount == 0:
        conn.execute(sa.insert(_table).values(objet_type=objet_type, objet_id=objet_id, etat="a_synchroniser",
                                              essais=0, version=1, cree_at=t, maj_at=t))


# Marquages faits pendant la requête en cours (posé par `suivre_requete`) : l'envoi de fond ne part
# que si la requête a réellement écrit un objet suivi, quelle que soit sa méthode HTTP.
_marques_requete: ContextVar[list | None] = ContextVar("marques_hubspot", default=None)


def suivre_requete() -> list:
    marques: list = []
    _marques_requete.set(marques)
    return marques


@event.listens_for(SessionOrm, "after_flush")
def _marquer_apres_flush(session: SessionOrm, _contexte) -> None:
    # En `after_flush`, `new` et `dirty` montrent encore l'état d'avant l'écriture, identifiants connus.
    objets = {(_TYPES[type(o)], o.id) for o in session.new if type(o) in _TYPES}
    objets |= {(_TYPES[type(o)], o.id) for o in session.dirty
               if type(o) in _TYPES and session.is_modified(o, include_collections=False)}
    if objets:
        conn, t = session.connection(), temps.maintenant()
        for objet_type, objet_id in sorted(objets):
            marquer(conn, objet_type, objet_id, t)
        if (marques := _marques_requete.get()) is not None:
            marques.extend(objets)


def tout_marquer(session: Session) -> int:
    """« Tout synchroniser » : chaque contact, organisation et affaire repasse à synchroniser."""
    conn, t, n = session.connection(), temps.maintenant(), 0
    for objet_type in ORDRE:
        for ident in session.exec(select(MODELES[objet_type].id)).all():
            marquer(conn, objet_type, ident, t)
            n += 1
    return n


# --------------------------------------------------------------------------- correspondance des étapes

def lire_correspondance(r: Reglage) -> dict[str, dict[str, str]]:
    brut = json.loads(r.hubspot_etapes or "{}")
    return {p: {e: str(i) for e, i in (brut.get(p) or {}).items() if e in cles_etapes(p) and i}
            for p in PIPELINES}


def valider_correspondance(valeur: dict) -> dict[str, dict[str, str]]:
    """Lève ValueError (message en français) si un pipeline ou une étape est inconnu."""
    propre: dict[str, dict[str, str]] = {p: {} for p in PIPELINES}
    for pipeline, etapes in valeur.items():
        if pipeline not in PIPELINES:
            raise ValueError(f"Pipeline inconnu : {pipeline}")
        for cle, ident in (etapes or {}).items():
            if cle not in cles_etapes(pipeline):
                raise ValueError(f"Étape inconnue pour le pipeline {pipeline} : {cle}")
            ident = (ident or "").strip()
            if len(ident) > 100:
                raise ValueError("Identifiant d'étape HubSpot trop long")
            if ident:
                propre[pipeline][cle] = ident
    return propre


# --------------------------------------------------------------------------- correspondance des champs

def _date(t: dt.datetime | None) -> str:
    return t.date().isoformat() if t else ""   # chaîne vide : la valeur est effacée côté HubSpot


def domaine(site_web: str | None) -> str | None:
    if not site_web:
        return None
    hote = (urlparse(site_web if "://" in site_web else "http://" + site_web).hostname or "").lower()
    return hote.removeprefix("www.") or None


def proprietes_contact(c: Contact) -> dict[str, str]:
    props = {cle: v for cle, v in (("firstname", c.prenom), ("lastname", c.nom), ("phone", c.telephone),
                                   ("jobtitle", c.poste), ("city", c.ville)) if v}
    props["merci_type"] = c.type
    props["merci_source"] = c.source + (f" ({c.source_detail})" if c.source_detail else "")
    props["merci_consentement"] = _date(c.consentement_at)
    props["merci_desinscrit"] = _date(c.desinscrit_at)
    return props


def proprietes_organisation(o: Organisation) -> dict[str, str]:
    props = {"name": o.nom}
    if o.ville:
        props["city"] = o.ville
    if d := domaine(o.site_web):
        props["domain"] = d
    props["merci_type"] = o.type
    return props


def _nom_contact(session: Session, c: Contact) -> str:
    from .contacts import nom_affiche
    return nom_affiche(c, session.get(Organisation, c.organisation_id) if c.organisation_id else None)


def _liens_affaire(session: Session, a: Affaire) -> tuple[Contact | None, Organisation | None]:
    contact = session.get(Contact, a.contact_id) if a.contact_id else None
    org_id = a.organisation_id or (contact.organisation_id if contact else None)
    return contact, session.get(Organisation, org_id) if org_id else None


def proprietes_affaire(session: Session, a: Affaire, correspondance: dict[str, dict[str, str]]) -> dict[str, str]:
    contact, org = _liens_affaire(session, a)
    nom = org.nom if org else _nom_contact(session, contact)
    pipeline = PIPELINES[a.pipeline]["nom"]
    props = {"dealname": f"{nom} · {pipeline}", "merci_pipeline": pipeline,
             "merci_etape": etape(a.pipeline, a.etape)["nom"]}
    if a.montant_mensuel is not None:
        props["amount"] = f"{Decimal(a.montant_mensuel):.2f}"
    if stage := correspondance.get(a.pipeline, {}).get(a.etape):
        props["dealstage"] = stage
    return props


def nom_objet(session: Session, objet_type: str, objet_id: int) -> str:
    obj = session.get(MODELES[objet_type], objet_id)
    if obj is None:
        return "Objet supprimé"
    if objet_type == "contact":
        return _nom_contact(session, obj)
    if objet_type == "organisation":
        return obj.nom
    return proprietes_affaire(session, obj, {})["dealname"]


# --------------------------------------------------------------------------- envoi

class _Passage:
    """Un passage d'envoi : session, fournisseur, identifiants connus, étapes lues une fois."""

    def __init__(self, s: Session, crm: CrmExterneProvider):
        self.s, self.crm = s, crm
        r = s.get(Reglage, 1)
        self.correspondance = lire_correspondance(r)
        self.proprietes_ok = r.hubspot_proprietes_at is not None
        self.ids: dict[tuple[str, int], str] = {}
        self._etapes: list[dict[str, str]] | None = None

    def preparer(self) -> None:
        """Propriétés MERCI créées une seule fois, au premier envoi."""
        if self.proprietes_ok:
            return
        self.crm.assurer_proprietes(GROUPE, PROPRIETES)
        self.proprietes_ok = True
        if self.crm.connecte:
            r = self.s.get(Reglage, 1)
            r.hubspot_proprietes_at = temps.maintenant()
            self.s.add(r)
            self.s.commit()

    def hubspot_id(self, objet_type: str, objet_id: int) -> str | None:
        if (objet_type, objet_id) in self.ids:
            return self.ids[(objet_type, objet_id)]
        return self.s.exec(select(SynchroHubspot.hubspot_id).where(
            SynchroHubspot.objet_type == objet_type, SynchroHubspot.objet_id == objet_id)).first()

    def premiere_etape(self) -> str | None:
        if not self.crm.connecte:
            return None
        if self._etapes is None:
            self._etapes = self.crm.etapes_pipeline()
        if not self._etapes:
            raise ErreurFournisseur("Pipeline de deals HubSpot par défaut sans étape")
        return self._etapes[0]["id"]

    def associer(self, objet: str, ident: str, vers: str, vers_type: str, vers_id: int) -> None:
        cible = self.hubspot_id(vers_type, vers_id)
        if cible is None and self.crm.connecte:
            libelle = "Organisation" if vers_type == "organisation" else "Contact lié"
            raise ErreurFournisseur(f"{libelle} pas encore envoyé(e) à HubSpot : nouvel essai plus tard")
        self.crm.associer(objet, ident, vers, cible)

    def creer_ou_modifier(self, objet: str, hid: str | None, props_maj: dict[str, str],
                          creer: Callable[[], str], memoriser: Callable[[str], None]) -> str:
        if hid:
            try:
                self.crm.modifier(objet, hid, props_maj)
                return hid
            except ObjetIntrouvable:
                log.warning("objet %s %s absent de HubSpot : recréé", objet, hid)
        hid = creer()
        memoriser(hid)
        return hid

    # ---------------------------------------------------------------- objets

    def organisation(self, o: Organisation, hid: str | None, memoriser) -> str:
        props = proprietes_organisation(o)
        return self.creer_ou_modifier("companies", hid, props, lambda: self.crm.creer("companies", props), memoriser)

    def contact(self, c: Contact, hid: str | None, memoriser) -> str:
        props = proprietes_contact(c)

        def creer() -> str:
            if c.email:
                return self.crm.upsert_contact(c.email, props)
            if not (c.prenom or c.nom):
                raise DonneesInsuffisantes("Contact sans e-mail ni nom : HubSpot exige l'un des deux")
            return self.crm.creer("contacts", props)

        hid = self.creer_ou_modifier("contacts", hid, {**props, "email": c.email} if c.email else props,
                                     creer, memoriser)
        if c.organisation_id:
            self.associer("contacts", hid, "companies", "organisation", c.organisation_id)
        return hid

    def affaire(self, a: Affaire, hid: str | None, memoriser) -> str:
        props = proprietes_affaire(self.s, a, self.correspondance)

        def creer() -> str:
            corps = {**props, "pipeline": "default"}
            if "dealstage" not in corps and (premiere := self.premiere_etape()):
                corps["dealstage"] = premiere
            return self.crm.creer("deals", corps)

        hid = self.creer_ou_modifier("deals", hid, props, creer, memoriser)
        contact, org = _liens_affaire(self.s, a)
        if contact is not None:
            self.associer("deals", hid, "contacts", "contact", contact.id)
        if org is not None:
            self.associer("deals", hid, "companies", "organisation", org.id)
        return hid


def _a_envoyer(s: Session, objet_type: str, t: dt.datetime, limite: int, seulement_neufs: bool) -> list[int]:
    condition = SynchroHubspot.etat == "a_synchroniser"
    if not seulement_neufs:
        condition = sa.or_(condition, sa.and_(SynchroHubspot.etat == "erreur", SynchroHubspot.essais < ESSAIS_MAX,
                                              SynchroHubspot.prochain_essai_at <= t))
    return list(s.exec(select(SynchroHubspot.id).where(SynchroHubspot.objet_type == objet_type, condition)
                       .order_by(SynchroHubspot.id).limit(limite)).all())


def _succes(s: Session, ligne_id: int, version: int, hid: str) -> None:
    t = temps.maintenant()
    s.execute(sa.update(_table).where(_table.c.id == ligne_id, _table.c.version == version)
              .values(etat="ok", hubspot_id=hid, essais=0, derniere_erreur=None, prochain_essai_at=None,
                      synchro_at=t, maj_at=t))
    s.commit()


def _echec(s: Session, ligne_id: int, version: int, essais_avant: int, message: str, definitif: bool = False) -> None:
    t = temps.maintenant()
    essais = ESSAIS_MAX if definitif else min(essais_avant + 1, ESSAIS_MAX)
    prochain = t + DELAIS[essais - 1] if essais < ESSAIS_MAX else None
    # Version inchangée seulement : une modification arrivée pendant l'envoi garde son marquage.
    s.execute(sa.update(_table).where(_table.c.id == ligne_id, _table.c.version == version)
              .values(etat="erreur", essais=essais, derniere_erreur=message[:500], prochain_essai_at=prochain, maj_at=t))
    s.commit()


def _envoyer_ligne(p: _Passage, ligne_id: int) -> str:
    """Renvoie `envoye`, `erreur`, `limite` ou `ignore`. Factice : rien n'est écrit en base."""
    s = p.s
    ligne = s.get(SynchroHubspot, ligne_id)
    objet_type, objet_id, version, essais = ligne.objet_type, ligne.objet_id, ligne.version, ligne.essais
    obj = s.get(MODELES[objet_type], objet_id)
    if obj is None:                       # objet supprimé localement : plus rien à répliquer
        s.delete(ligne)
        s.commit()
        return "ignore"

    def memoriser(hid: str) -> None:      # identifiant gardé tout de suite : jamais de doublon au nouvel essai
        p.ids[(objet_type, objet_id)] = hid
        if p.crm.connecte:
            s.execute(sa.update(_table).where(_table.c.id == ligne_id).values(hubspot_id=hid))
            s.commit()

    resultat, message, definitif = "erreur", None, False
    try:
        p.preparer()
        hid = getattr(p, objet_type)(obj, ligne.hubspot_id, memoriser)
        resultat = "envoye"
    except DonneesInsuffisantes as e:
        message, definitif = str(e), True
    except LimiteDebit as e:
        resultat, message = "limite", str(e)
    except ErreurFournisseur as e:
        message = str(e)
    except Exception:
        log.exception("HubSpot : erreur interne sur %s %s", objet_type, objet_id)
        s.rollback()
        message = "Erreur interne pendant l'envoi à HubSpot"
    if not p.crm.connecte:
        return resultat
    if resultat == "envoye":
        _succes(s, ligne_id, version, hid)
    else:
        log.warning("HubSpot : %s %s non synchronisé(e) : %s", objet_type, objet_id, message)
        _echec(s, ligne_id, version, essais, message, definitif)
    return resultat


def envoyer(crm: CrmExterneProvider, limite: int = LOT) -> dict:
    """Envoie ce qui est à synchroniser (et les reprises dues). Factice : journalise seulement."""
    bilan = {"statut": "fait" if crm.connecte else "non_connecte", "envoyes": 0, "erreurs": 0}
    with Session(db.engine) as s:
        jeton = verrou.prendre(s, "hubspot", DUREE_VERROU)
        if jeton is None:
            return {**bilan, "statut": "verrouille"}
        try:
            # Jusqu'à trois tours : les objets marqués pendant l'envoi partent aussi (factice : un tour).
            for tour in range(3 if crm.connecte else 1):
                p, traites = _Passage(s, crm), 0
                for objet_type in ORDRE:
                    for ligne_id in _a_envoyer(s, objet_type, temps.maintenant(), limite, seulement_neufs=tour > 0):
                        traites += 1
                        res = _envoyer_ligne(p, ligne_id)
                        bilan["envoyes"] += res == "envoye"
                        bilan["erreurs"] += res in ("erreur", "limite")
                        if res == "limite":
                            bilan["statut"] = "limite"
                            return bilan
                if not traites:
                    break
        finally:
            verrou.relacher(s, "hubspot", jeton)
    return bilan


def envoyer_en_tache_de_fond(crm: CrmExterneProvider) -> None:
    """Tâche de fond après une réponse : ne lève jamais (le tick reprendra)."""
    try:
        bilan = envoyer(crm)
        if bilan["envoyes"] or bilan["erreurs"]:
            log.info("synchro HubSpot : %s", bilan)
    except Exception:
        log.exception("synchro HubSpot en tâche de fond")


def envoyer_si_marques(marques: list, crm: CrmExterneProvider) -> None:
    """Tâche de fond d'une requête : envoi seulement si elle a écrit un objet suivi."""
    if marques:
        envoyer_en_tache_de_fond(crm)


# --------------------------------------------------------------------------- état

def etat_objet(session: Session, objet_type: str, objet_id: int) -> dict | None:
    ligne = session.exec(select(SynchroHubspot).where(
        SynchroHubspot.objet_type == objet_type, SynchroHubspot.objet_id == objet_id)).first()
    if ligne is None:
        return None
    return {"etat": ligne.etat, "message": ligne.derniere_erreur if ligne.etat == "erreur" else None,
            "synchro_at": temps.iso(ligne.synchro_at)}


def etat_api(session: Session, crm: CrmExterneProvider) -> dict:
    nombres = dict(session.exec(select(SynchroHubspot.etat, sa.func.count()).group_by(SynchroHubspot.etat)).all())
    derniere = session.exec(select(sa.func.max(SynchroHubspot.synchro_at))).one()
    erreurs = session.exec(select(SynchroHubspot).where(SynchroHubspot.etat == "erreur")
                           .order_by(SynchroHubspot.maj_at.desc(), SynchroHubspot.id.desc()).limit(10)).all()
    en_erreur = nombres.get("erreur", 0)
    return {
        "etat": "non_connecte" if not crm.connecte else ("erreurs" if en_erreur else "connecte"),
        "compteurs": {"synchronises": nombres.get("ok", 0), "en_attente": nombres.get("a_synchroniser", 0),
                      "en_erreur": en_erreur},
        "dernieres_erreurs": [{
            "objet_type": e.objet_type, "objet_id": e.objet_id, "nom": nom_objet(session, e.objet_type, e.objet_id),
            "message": e.derniere_erreur, "at": temps.iso(e.maj_at), "nouvel_essai_at": temps.iso(e.prochain_essai_at),
        } for e in erreurs],
        "derniere_synchro_at": temps.iso(derniere),
    }
