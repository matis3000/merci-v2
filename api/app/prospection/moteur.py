"""Passage de prospection (section 7.1) et vue de l'écran Prospection (section 4.8).

Registre des entreprises, offres RSE (optionnel), décideurs LinkedIn (40 organisations au plus par
passage), note /10, affaires, inscription à `entreprise-prospection` par note décroissante.
Le plafond de 20 invitations par jour s'applique à l'envoi (moteur de séquences), pas ici.
Le passage est reprenable : les organisations sans `recherche_linkedin_at` sont reprises au suivant.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import db, temps, verrou
from ..fournisseurs.base import CompteLinkedInDeconnecte, ErreurFournisseur, LinkedInProvider, NonConfigure
from ..journal import ajouter_activite
from ..modeles import Affaire, Contact, InscriptionSequence, Organisation, PassageProspection, Reglage, Verrou
from ..services import affaires, moteur_sequences
from ..services.contacts import TRANCHES_LIBELLES, nom_affiche
from . import note, offres, registre

log = logging.getLogger("merci.prospection")

# Remplaçables par les tests (transports httpx simulés, aucune attente de cadence).
TRANSPORT_REGISTRE = None
TRANSPORT_OFFRES = None
ATTENDRE = time.sleep

RECHERCHES_LINKEDIN_PAR_PASSAGE = 40   # décision D21
DECIDEURS_PAR_ENTREPRISE = 2
PAGES_REGISTRE = 10
JOURS_OFFRES = 31
MOTS_OFFRES = ("RSE", "QVT")
DUREE_VERROU = dt.timedelta(minutes=60)
ENTREPRISES_AFFICHEES = 100
SEQUENCE = "entreprise-prospection"
DEPARTEMENTS = {"67": "Bas-Rhin", "68": "Haut-Rhin"}
ERREURS_LISIBLES = (registre.ErreurRegistre, offres.ErreurOffres, ErreurFournisseur, NonConfigure)


class ErreurProspection(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


# --------------------------------------------------------------------------- démarrage

def demarrer(session: Session, declencheur: str) -> tuple[PassageProspection, str | None]:
    """Crée le passage et prend le verrou. Jeton None : passage `cron` du jour déjà fait.
    Lève `ErreurProspection(409)` si un passage est en cours."""
    t = temps.maintenant()
    cle = f"cron:{temps.jour_paris(t).isoformat()}" if declencheur == "cron" else f"manuel:{t.isoformat()}"
    passage = PassageProspection(cle=cle, declencheur=declencheur, statut="en_cours", debut_at=t)
    try:
        session.add(passage)
        session.commit()
    except IntegrityError:
        session.rollback()
        existant = session.exec(select(PassageProspection).where(PassageProspection.cle == cle)).one()
        if declencheur == "cron":
            return existant, None
        raise ErreurProspection(409, "Un passage de prospection est déjà en cours") from None
    session.refresh(passage)
    jeton = verrou.prendre(session, "prospection", DUREE_VERROU)
    if jeton is None:
        passage.statut, passage.erreur, passage.fin_at = "erreur", "Un passage est déjà en cours", t
        session.add(passage)
        session.commit()
        raise ErreurProspection(409, "Un passage de prospection est déjà en cours")
    return passage, jeton


def executer(passage_id: int, jeton: str, linkedin: LinkedInProvider) -> None:
    """Tâche de fond : le passage complet, puis statistiques et relâche du verrou."""
    with Session(db.engine) as s:
        try:
            passage = s.get(PassageProspection, passage_id)
            _passage(s, passage, linkedin)
            passage.statut = "fini"
        except Exception as e:  # le passage est marqué en erreur, sans secret dans le message
            s.rollback()
            log.exception("passage de prospection %s en erreur", passage_id)
            passage = s.get(PassageProspection, passage_id)
            passage.statut = "erreur"
            passage.erreur = (str(e) if isinstance(e, ERREURS_LISIBLES) else "Erreur interne du passage")[:500]
        finally:
            passage = s.get(PassageProspection, passage_id)
            passage.fin_at = temps.maintenant()
            s.add(passage)
            s.commit()
            verrou.relacher(s, "prospection", jeton)


# --------------------------------------------------------------------------- étapes

def _liste(texte: str | None) -> list[str]:
    return json.loads(texte or "[]")


def _passage(s: Session, passage: PassageProspection, linkedin: LinkedInProvider) -> None:
    r = s.get(Reglage, 1)
    departements, postes = _liste(r.prospection_departements), _liste(r.prospection_postes)
    touchees: set[int] = set()
    _registre(s, passage, r, departements, touchees)
    _offres(s, departements, touchees)
    trouves, cherchees = _decideurs(s, passage, linkedin, postes, touchees)
    for org_id in sorted(touchees):
        org = s.get(Organisation, org_id)
        _noter(s, org, postes)
        if org.source == "prospection":
            _affaires(s, org, postes)
    passage.en_sequence = _sequences(s, r.prospection_seuil)
    _activites(s, trouves, cherchees)
    s.add(passage)
    s.commit()


def _registre(s: Session, passage: PassageProspection, r: Reglage, departements: list[str],
              touchees: set[int]) -> None:
    trouvees = registre.chercher_entreprises(
        departements, registre.tranches_depuis(r.prospection_effectif_min), PAGES_REGISTRE,
        transport=TRANSPORT_REGISTRE, sleep=ATTENDRE)
    uniques = {e.siren: e for e in trouvees if not e.naf.startswith("84.")}  # administration publique exclue
    passage.entreprises_vues = len(uniques)
    t = temps.maintenant()
    for e in uniques.values():
        org = s.exec(select(Organisation).where(Organisation.siren == e.siren)).first()
        if org is None:
            org = Organisation(
                type="entreprise", nom=e.nom[:200] or e.siren, siren=e.siren, ville=e.ville[:120] or None,
                code_postal=e.code_postal[:5] or None, departement=e.departement[:3] or None,
                tranche_effectif=e.tranche[:2] or None, naf_code=e.naf[:6] or None, source="prospection",
                cree_at=t, maj_at=t)
            s.add(org)
            s.flush()
            passage.nouvelles += 1
            touchees.add(org.id)
    s.add(passage)
    s.commit()


def _offres(s: Session, departements: list[str], touchees: set[int]) -> None:
    """Offres d'emploi RSE ou QVT publiées depuis 31 jours, rapprochées par nom normalisé."""
    if not offres.configure():
        return
    par_nom: dict[str, list[Organisation]] = {}
    for org in s.exec(select(Organisation).where(Organisation.type == "entreprise")):
        par_nom.setdefault(note.normaliser(org.nom), []).append(org)
    for mot in MOTS_OFFRES:
        try:
            trouvees = offres.chercher_offres([mot], departements, JOURS_OFFRES, transport=TRANSPORT_OFFRES)
        except offres.ErreurOffres as e:
            log.warning("offres %s ignorées : %s", mot, e)
            continue
        for o in trouvees:
            try:
                quand = dt.datetime.strptime(o.date, "%Y-%m-%d")
            except ValueError:
                continue
            for org in par_nom.get(note.normaliser(o.entreprise), []):
                if org.signal_rse_at is None or quand > org.signal_rse_at:
                    org.signal_rse_at, org.signal_rse_libelle = quand, f"Offre d'emploi {mot}"
                    org.maj_at = temps.maintenant()
                    s.add(org)
                    touchees.add(org.id)
    s.commit()


def _decideurs(s: Session, passage: PassageProspection, linkedin: LinkedInProvider, postes: list[str],
               touchees: set[int]) -> tuple[list[int], list[int]]:
    """Renvoie (contacts trouvés, organisations cherchées) pendant ce passage."""
    trouves: list[int] = []
    cherchees: list[int] = []
    if s.get(Reglage, 1).linkedin_etat == "a_reconnecter":
        return trouves, cherchees
    orgs = s.exec(
        select(Organisation)
        .where(Organisation.source == "prospection", Organisation.type == "entreprise",
               Organisation.recherche_linkedin_at.is_(None))
        .order_by(sa.nulls_last(Organisation.tranche_effectif.desc()), Organisation.id)
        .limit(RECHERCHES_LINKEDIN_PAR_PASSAGE)).all()
    for org in orgs:
        try:
            personnes = linkedin.chercher(org.nom, postes, DECIDEURS_PAR_ENTREPRISE)
        except CompteLinkedInDeconnecte:
            _a_reconnecter(s)
            break
        except (ErreurFournisseur, NonConfigure) as e:
            log.warning("recherche LinkedIn ignorée pour l'organisation %s : %s", org.id, e)
            continue
        retenues = [p for p in personnes if note.libelle_poste(p.poste, postes)][:DECIDEURS_PAR_ENTREPRISE]
        for p in retenues:
            contact = _fusionner(s, p, org)
            trouves.append(contact.id)
            passage.decideurs += 1
            _signal_post(s, linkedin, p.provider_id, org)
        t = temps.maintenant()
        org.recherche_linkedin_at = org.maj_at = t
        s.add(org)
        s.add(passage)
        s.commit()
        touchees.add(org.id)
        cherchees.append(org.id)
    return trouves, cherchees


def _a_reconnecter(s: Session) -> None:
    r = s.get(Reglage, 1)
    t = temps.maintenant()
    r.linkedin_etat, r.linkedin_etat_at, r.maj_at = "a_reconnecter", t, t
    s.add(r)
    s.commit()


def _fusionner(s: Session, p, org: Organisation) -> Contact:
    """Contact fusionné par `linkedin_provider_id` : champs vides complétés, jamais écrasés."""
    t = temps.maintenant()
    champs = {"prenom": (p.prenom or "")[:80] or None, "nom": (p.nom or "")[:80] or None,
              "poste": (p.poste or "")[:200] or None, "linkedin_url": (p.url or "")[:300] or None,
              "organisation_id": org.id}
    c = s.exec(select(Contact).where(Contact.linkedin_provider_id == p.provider_id)).first()
    if c is None:
        c = Contact(type="entreprise", linkedin_provider_id=p.provider_id, source="prospection",
                    source_detail="Registre + LinkedIn", cree_at=t, maj_at=t, **champs)
    else:
        for k, v in champs.items():
            if getattr(c, k) is None and v is not None:
                setattr(c, k, v)
        c.maj_at = t
    s.add(c)
    s.flush()
    return c


def _signal_post(s: Session, linkedin: LinkedInProvider, provider_id: str, org: Organisation) -> None:
    """Post RSE de moins de 30 jours : signal retenu s'il est plus récent."""
    try:
        profil = linkedin.profil(provider_id)
    except (ErreurFournisseur, NonConfigure) as e:
        log.warning("profil LinkedIn non lu : %s", e)
        return
    t = temps.maintenant()
    for quand, texte in profil.posts_recents:
        if note.texte_rse(texte) and note.signal_valide(quand, t) and (
                org.signal_rse_at is None or quand > org.signal_rse_at):
            org.signal_rse_at, org.signal_rse_libelle = quand, "Post RSE"


def _decideurs_de(s: Session, org: Organisation, postes: list[str]) -> list[Contact]:
    contacts = s.exec(select(Contact).where(Contact.organisation_id == org.id).order_by(Contact.id)).all()
    return [c for c in contacts if note.libelle_poste(c.poste, postes)]


def _noter(s: Session, org: Organisation, postes: list[str]) -> None:
    decideurs = _decideurs_de(s, org, postes)
    n, raisons = note.calculer(org, decideurs[0].poste if decideurs else None, postes, temps.maintenant())
    org.note, org.raisons_note = n, json.dumps(raisons, ensure_ascii=False)
    org.maj_at = temps.maintenant()
    s.add(org)


def _affaires(s: Session, org: Organisation, postes: list[str]) -> None:
    """Une affaire « prospect » par décideur ; sans décideur, une affaire « organisation seule »."""
    decideurs = [c for c in _decideurs_de(s, org, postes) if c.source == "prospection"]
    if decideurs:
        for c in decideurs:
            affaires.creer(s, "entreprises", "prospect", contact_id=c.id, organisation_id=org.id)
    elif s.exec(select(Affaire.id).where(Affaire.organisation_id == org.id,
                                         Affaire.pipeline == "entreprises")).first() is None:
        affaires.creer(s, "entreprises", "prospect", organisation_id=org.id)
    s.commit()


def _sequences(s: Session, seuil: int) -> int:
    """Contacts LinkedIn de la prospection, non désinscrits, note >= seuil, jamais inscrits :
    inscription par note décroissante (l'ordre d'inscription sert la file du plafond)."""
    deja = select(InscriptionSequence.contact_id).where(InscriptionSequence.sequence == SEQUENCE)
    candidats = s.exec(
        select(Contact).join(Organisation, Organisation.id == Contact.organisation_id)
        .where(Contact.source == "prospection", Contact.linkedin_provider_id.is_not(None),
               Contact.desinscrit_at.is_(None), Organisation.note >= seuil, Contact.id.not_in(deja))
        .order_by(Organisation.note.desc(), Contact.id)).all()
    inscrits = 0
    for c in candidats:
        affaire = s.exec(select(Affaire).where(Affaire.contact_id == c.id, Affaire.pipeline == "entreprises")).first()
        if affaire is not None and affaire.etape != "prospect":
            continue  # l'équipe a déjà pris la main
        try:
            moteur_sequences.inscrire(s, c, SEQUENCE)
        except moteur_sequences.ErreurSequence:
            continue
        s.commit()
        inscrits += 1
    return inscrits


def _origine(org: Organisation) -> str:
    zone = DEPARTEMENTS.get(org.departement or "", f"département {org.departement}" if org.departement else "")
    effectif = TRANCHES_LIBELLES.get(org.tranche_effectif or "")
    details = ", ".join(x for x in (zone, effectif) if x)
    return f"Registre des entreprises ({details})" if details else "Registre des entreprises"


def _activites(s: Session, trouves: list[int], cherchees: list[int]) -> None:
    for contact_id in trouves:
        c = s.get(Contact, contact_id)
        org = s.get(Organisation, c.organisation_id)
        ajouter_activite(s, "prospection_trouve", "Trouvé par la prospection",
                         texte=f"{_origine(org)}, puis profil LinkedIn « {c.poste} ». Note {org.note}/10.",
                         contact_id=c.id, organisation_id=org.id)
    avec_contact = {s.get(Contact, i).organisation_id for i in trouves}
    for org_id in cherchees:
        if org_id in avec_contact:
            continue
        org = s.get(Organisation, org_id)
        ajouter_activite(s, "prospection_trouve", "Trouvée par la prospection",
                         texte=f"{_origine(org)}. Aucun décideur RH ou RSE trouvé. Note {org.note}/10.",
                         organisation_id=org.id)
    s.commit()


# --------------------------------------------------------------------------- vue GET /prospection

def passage_api(p: PassageProspection | None) -> dict | None:
    if p is None:
        return None
    return {"id": p.id, "declencheur": p.declencheur, "statut": p.statut, "debut_at": temps.iso(p.debut_at),
            "fin_at": temps.iso(p.fin_at), "entreprises_vues": p.entreprises_vues, "nouvelles": p.nouvelles,
            "decideurs": p.decideurs, "en_sequence": p.en_sequence, "erreur": p.erreur}


def cible_api(r: Reglage) -> dict:
    return {"departements": _liste(r.prospection_departements), "effectif_min": r.prospection_effectif_min,
            "postes": _liste(r.prospection_postes), "plafond_jour": r.prospection_plafond_jour,
            "seuil": r.prospection_seuil}


def en_cours(s: Session) -> bool:
    v = s.get(Verrou, "prospection")
    return v is not None and v.expire_at > temps.maintenant()


def _suite(org: Organisation, decideurs: list[Contact], inscriptions: dict[int, list[InscriptionSequence]],
           en_file: set[int]) -> tuple[str, str]:
    if org.recherche_linkedin_at is None:
        return "a_rechercher", "Décideurs à chercher au prochain passage"
    if not decideurs:
        return "a_traiter", "À traiter à la main"
    for c in decideurs:
        for i in inscriptions.get(c.id, []):
            if i.sequence == SEQUENCE and i.statut == "active":
                if i.id in en_file:
                    return "file_plafond", "File d'attente (plafond du jour)"
                if i.pas_courant == 1:
                    return "en_sequence", "Invitation au prochain créneau"
                return "en_sequence", f"Séquence en cours, pas {i.pas_courant}/4"
    if any(inscriptions.get(c.id) for c in decideurs):
        return "deja_en_cours", "Déjà suivi par une séquence"
    return "a_traiter", "À traiter à la main"


def vue(s: Session) -> dict:
    r = s.get(Reglage, 1)
    ctx = moteur_sequences.contexte(s)
    dernier = s.exec(select(PassageProspection).order_by(PassageProspection.id.desc())).first()
    a_rechercher = s.exec(select(sa.func.count()).select_from(Organisation).where(
        Organisation.source == "prospection", Organisation.type == "entreprise",
        Organisation.recherche_linkedin_at.is_(None))).one()
    entreprises = []
    if dernier is not None:
        debut, fin = dernier.debut_at, dernier.fin_at or ctx.maintenant
        orgs = s.exec(
            select(Organisation)
            .where(Organisation.source == "prospection",
                   sa.or_(Organisation.cree_at.between(debut, fin), Organisation.recherche_linkedin_at.between(debut, fin)))
            .order_by(sa.nulls_last(Organisation.note.desc()), Organisation.id)
            .limit(ENTREPRISES_AFFICHEES)).all()
        # File du plafond : invitations dues servies dans l'ordre d'inscription, au-delà du reste du jour.
        file = s.exec(select(InscriptionSequence).where(
            InscriptionSequence.sequence == SEQUENCE, InscriptionSequence.statut == "active",
            InscriptionSequence.pas_courant == 1)
            .order_by(InscriptionSequence.prochain_envoi_at, InscriptionSequence.id)).all()
        reste = max(r.prospection_plafond_jour - ctx.invitations_aujourdhui, 0)
        en_file = {i.id for i in file[reste:]}
        postes = _liste(r.prospection_postes)
        for org in orgs:
            decideurs = _decideurs_de(s, org, postes)
            inscriptions: dict[int, list[InscriptionSequence]] = {}
            for i in s.exec(select(InscriptionSequence).where(
                    InscriptionSequence.contact_id.in_([c.id for c in decideurs]))):
                inscriptions.setdefault(i.contact_id, []).append(i)
            suite, libelle = _suite(org, decideurs, inscriptions, en_file)
            d = decideurs[0] if decideurs else None
            entreprises.append({
                "organisation_id": org.id, "nom": org.nom, "ville": org.ville,
                "effectif_libelle": TRANCHES_LIBELLES.get(org.tranche_effectif or ""),
                "naf_libelle": org.naf_libelle,
                "decideur": {"contact_id": d.id, "nom": nom_affiche(d, org), "poste": d.poste} if d else None,
                "note": org.note, "suite": suite, "suite_libelle": libelle,
            })
    return {"cible": cible_api(r), "dernier_passage": passage_api(dernier), "en_cours": en_cours(s),
            "invitations_aujourdhui": ctx.invitations_aujourdhui, "a_rechercher": int(a_rechercher),
            "entreprises": entreprises}


def changer_cible(s: Session, cible: dict) -> dict:
    r = s.get(Reglage, 1)
    r.prospection_departements = json.dumps(cible["departements"])
    r.prospection_effectif_min = cible["effectif_min"]
    r.prospection_postes = json.dumps(cible["postes"], ensure_ascii=False)
    r.prospection_plafond_jour = cible["plafond_jour"]
    r.prospection_seuil = cible["seuil"]
    r.maj_at = temps.maintenant()
    s.add(r)
    s.commit()
    return cible_api(r)
