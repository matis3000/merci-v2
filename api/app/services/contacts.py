"""Contacts et organisations : lignes de liste, fiche, création, mise à jour, fil d'activité,
import et export CSV (section 4.6).

Les listes sont construites en mémoire à partir de quelques requêtes groupées (`Vue`) : la base
du pilote compte au plus quelques milliers de contacts.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

import sqlalchemy as sa
from sqlmodel import Session, select

from .. import temps
from ..journal import ajouter_activite
from ..modeles import (
    TYPES_CONTACT, Activite, Affaire, Contact, Envoi, InscriptionSequence, Membre, Organisation,
    normaliser_email,
)
from . import affaires, moteur_sequences, synchro_hubspot

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TRANCHES_LIBELLES = {
    "00": "Aucun salarié", "01": "1 ou 2 salariés", "02": "3 à 5 salariés", "03": "6 à 9 salariés",
    "11": "10 à 19 salariés", "12": "20 à 49 salariés", "21": "50 à 99 salariés", "22": "100 à 199 salariés",
    "31": "200 à 249 salariés", "32": "250 à 499 salariés", "41": "500 à 999 salariés",
    "42": "1 000 à 1 999 salariés", "51": "2 000 à 4 999 salariés", "52": "5 000 à 9 999 salariés",
    "53": "10 000 salariés et plus",
}
SOURCES_LIBELLES = {"landing": "Landing", "prospection": "Prospection", "import": "Import", "manuel": "Saisie manuelle"}


def libelle_detail(detail: str) -> str:
    """Détail de source affiché avec une majuscule (« instagram » devient « Instagram »)."""
    return detail[:1].upper() + detail[1:]

COLONNES_CSV = ["type", "prenom", "nom", "email", "telephone", "poste", "organisation", "ville", "linkedin_url",
                "source", "source_detail", "pipeline", "etape", "note", "sequence", "etat_sequence", "cree_at"]
COLONNES_IMPORT = COLONNES_CSV[:11]
LONGUEURS = {"prenom": 80, "nom": 80, "email": 254, "telephone": 30, "poste": 200, "organisation": 200,
             "ville": 120, "linkedin_url": 300, "source_detail": 80}
CHAMPS_COMPLETABLES = ("prenom", "nom", "telephone", "poste", "ville", "linkedin_url", "source_detail")
TAILLE_MAX_IMPORT = 2 * 1024 * 1024
LIGNES_MAX_IMPORT = 5000


class ErreurContact(Exception):
    def __init__(self, statut: int, message: str, contact_id: int | None = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.contact_id = contact_id


# --------------------------------------------------------------------------- outils

def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, espaces réduits : comparaison de noms et recherche."""
    if not texte:
        return ""
    sans_accents = "".join(ch for ch in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(ch))
    return " ".join(sans_accents.lower().split())


def email_valide(email: str | None) -> bool:
    return bool(email) and len(email) <= 254 and bool(_EMAIL.match(email))


def vide_en_none(valeur):
    if isinstance(valeur, str):
        valeur = valeur.strip()
        return valeur or None
    return valeur


def nom_affiche(contact: Contact, org: Organisation | None = None) -> str:
    complet = " ".join(x for x in (contact.prenom, contact.nom) if x)
    return complet or (org.nom if org else None) or contact.email or "Profil LinkedIn"


def sous_titre(contact: Contact, org: Organisation | None) -> str:
    if contact.type == "donateur":
        return f"Donateur, {contact.ville}" if contact.ville else "Donateur"
    if contact.type == "association":
        return org.nom if org else "Association"
    return ", ".join(x for x in (contact.poste, org.nom if org else None) if x) or "Entreprise"


def trouver_organisation(session: Session, nom: str, type: str, source: str | None = None) -> Organisation | None:
    cible = normaliser(nom)
    requete = select(Organisation).where(Organisation.type == type)
    if source:
        requete = requete.where(Organisation.source == source)
    return next((o for o in session.exec(requete) if normaliser(o.nom) == cible), None)


def organisation_pour(session: Session, nom: str, type: str, source: str,
                      chercher_dans_source: str | None = None) -> Organisation:
    """Organisation de ce nom (comparaison sans casse ni accents), créée si absente."""
    org = trouver_organisation(session, nom, type, chercher_dans_source)
    if org is None:
        t = temps.maintenant()
        org = Organisation(type=type, nom=" ".join(nom.split())[:200], source=source, cree_at=t, maj_at=t)
        session.add(org)
        session.flush()
    return org


def type_organisation(type_contact: str) -> str:
    return "association" if type_contact == "association" else "entreprise"


# --------------------------------------------------------------------------- sérialisation

def organisation_api(o: Organisation) -> dict:
    return {
        "id": o.id, "type": o.type, "nom": o.nom, "siren": o.siren, "ville": o.ville,
        "code_postal": o.code_postal, "departement": o.departement, "tranche_effectif": o.tranche_effectif,
        "effectif_libelle": TRANCHES_LIBELLES.get(o.tranche_effectif or ""),
        "naf_code": o.naf_code, "naf_libelle": o.naf_libelle, "site_web": o.site_web,
        "note": o.note, "raisons": json.loads(o.raisons_note) if o.raisons_note else [],
    }


def contact_api(c: Contact) -> dict:
    return {
        "id": c.id, "type": c.type, "prenom": c.prenom, "nom": c.nom, "email": c.email,
        "telephone": c.telephone, "poste": c.poste, "ville": c.ville, "linkedin_url": c.linkedin_url,
        "source": c.source, "source_detail": c.source_detail,
        "consentement_at": temps.iso(c.consentement_at), "consentement_texte": c.consentement_texte,
        "desinscrit_at": temps.iso(c.desinscrit_at), "pause": c.pause, "cree_at": temps.iso(c.cree_at),
    }


def canal_activite(type: str) -> str:
    if type.startswith("email_"):
        return "email"
    if type.startswith("linkedin_"):
        return "linkedin"
    return "equipe" if type in ("note", "appel") else "systeme"


def activite_api(a: Activite, membres: dict[int, Membre]) -> dict:
    auteur = membres.get(a.membre_id) if a.membre_id else None
    return {
        "id": a.id, "type": a.type, "canal": canal_activite(a.type), "titre": a.titre, "texte": a.texte,
        "fort": a.type == "linkedin_reponse",
        "auteur": {"id": auteur.id, "prenom": auteur.prenom} if auteur else None,
        "cree_at": temps.iso(a.cree_at),
    }


def activites(session: Session, *, contact_id: int | None = None, organisation_id: int | None = None,
              avant: int | None = None, limite: int = 50) -> tuple[list[dict], int | None]:
    """Fil le plus récent d'abord ; `suivant` = identifiant à passer en `avant` pour la suite."""
    requete = select(Activite)
    requete = requete.where(Activite.contact_id == contact_id) if contact_id is not None else \
        requete.where(Activite.organisation_id == organisation_id)
    if avant is not None:
        requete = requete.where(Activite.id < avant)
    lignes = list(session.exec(requete.order_by(Activite.id.desc()).limit(limite + 1)))
    page = lignes[:limite]
    ids = {a.membre_id for a in page if a.membre_id}
    membres = {m.id: m for m in session.exec(select(Membre).where(Membre.id.in_(ids)))} if ids else {}
    suivant = page[-1].id if len(lignes) > limite else None
    return [activite_api(a, membres) for a in page], suivant


# --------------------------------------------------------------------------- vue groupée

@dataclass
class Element:
    """Une ligne de la liste Contacts, avant pagination."""
    ligne: dict
    contact: Contact | None
    organisation: Organisation | None
    affaire: Affaire | None
    cree_at: object
    recherche: str


class Vue:
    """Données lues une fois par requête pour construire lignes, cartes et accueil."""

    def __init__(self, session: Session):
        self.session = session
        self.ctx = moteur_sequences.contexte(session)
        self.contacts: dict[int, Contact] = {c.id: c for c in session.exec(select(Contact))}
        self.orgs: dict[int, Organisation] = {o.id: o for o in session.exec(select(Organisation))}
        self.affaires: list[Affaire] = list(session.exec(select(Affaire).order_by(Affaire.id)))
        self.inscriptions: dict[int, list[InscriptionSequence]] = defaultdict(list)
        for i in session.exec(select(InscriptionSequence).order_by(InscriptionSequence.id)):
            self.inscriptions[i.contact_id].append(i)
        self.affaires_contact: dict[int, list[Affaire]] = defaultdict(list)
        self.affaire_org_seule: dict[int, Affaire] = {}
        for a in self.affaires:
            if a.contact_id is not None:
                self.affaires_contact[a.contact_id].append(a)
            elif a.organisation_id is not None:
                self.affaire_org_seule.setdefault(a.organisation_id, a)
        self.contacts_par_org: dict[int, list[Contact]] = defaultdict(list)
        for c in self.contacts.values():
            if c.organisation_id is not None:
                self.contacts_par_org[c.organisation_id].append(c)

    def _dernieres(self, colonne) -> dict[int, Activite]:
        ids = select(sa.func.max(Activite.id)).where(colonne.is_not(None)).group_by(colonne)
        return {getattr(a, colonne.key): a for a in self.session.exec(select(Activite).where(Activite.id.in_(ids)))}

    def affaire_principale(self, contact: Contact) -> Affaire | None:
        liste = self.affaires_contact.get(contact.id, [])
        pipeline = affaires.PIPELINE_DU_TYPE.get(contact.type)
        return next((a for a in liste if a.pipeline == pipeline), liste[0] if liste else None)

    def etat_sequence(self, contact: Contact) -> dict | None:
        insc = moteur_sequences.inscription_affichee(self.inscriptions.get(contact.id, []))
        return moteur_sequences.etat(insc, contact, self.ctx) if insc else None

    def organisations_sans_decideur(self) -> list[Organisation]:
        return [self.orgs[oid] for oid in self.affaire_org_seule
                if oid in self.orgs and not self.contacts_par_org.get(oid)]

    def elements(self) -> list[Element]:
        dernieres_c = self._dernieres(Activite.contact_id)
        dernieres_o = self._dernieres(Activite.organisation_id)

        def derniere(a: Activite | None) -> dict | None:
            return {"titre": a.titre, "at": temps.iso(a.cree_at)} if a else None

        resultat: list[Element] = []
        for c in self.contacts.values():
            org = self.orgs.get(c.organisation_id) if c.organisation_id else None
            affaire = self.affaire_principale(c)
            nom = nom_affiche(c, org)
            ligne = {
                "genre": "contact", "id": c.id, "nom_affiche": nom, "sous_titre": sous_titre(c, org),
                "type": c.type, "email": c.email,
                "organisation": {"id": org.id, "nom": org.nom} if org else None,
                "ville": c.ville, "source": c.source, "source_detail": c.source_detail,
                "affaire": affaires.resume_api(affaire) if affaire else None,
                "note": org.note if org else None, "sequence": self.etat_sequence(c),
                "derniere_activite": derniere(dernieres_c.get(c.id)),
            }
            recherche = normaliser(" ".join(x for x in (nom, c.prenom, c.nom, c.email, org.nom if org else None) if x))
            resultat.append(Element(ligne, c, org, affaire, c.cree_at, recherche))
        for o in self.organisations_sans_decideur():
            affaire = self.affaire_org_seule[o.id]
            ligne = {
                "genre": "organisation", "id": o.id, "nom_affiche": o.nom, "sous_titre": "Aucun décideur trouvé",
                "type": o.type, "email": None, "organisation": {"id": o.id, "nom": o.nom}, "ville": o.ville,
                "source": o.source, "source_detail": "Registre seul" if o.source == "prospection" else None,
                "affaire": affaires.resume_api(affaire), "note": o.note, "sequence": None,
                "derniere_activite": derniere(dernieres_o.get(o.id)),
            }
            resultat.append(Element(ligne, None, o, affaire, o.cree_at, normaliser(o.nom)))
        resultat.sort(key=lambda e: (e.cree_at, e.ligne["genre"] == "organisation", e.ligne["id"]), reverse=True)
        return resultat


@dataclass
class Filtres:
    type: str | None = None
    source: str | None = None
    pipeline: str | None = None
    etape: str | None = None
    note_min: int | None = None
    sequence: str | None = None
    etat_sequence: str | None = None
    q: str | None = None


def filtrer(elements: list[Element], f: Filtres) -> list[Element]:
    q = normaliser(f.q)

    def garde(e: Element) -> bool:
        ligne, seq = e.ligne, e.ligne["sequence"]
        return all((
            f.type is None or ligne["type"] == f.type,
            f.source is None or ligne["source"] == f.source,
            f.pipeline is None or (e.affaire is not None and e.affaire.pipeline == f.pipeline),
            f.etape is None or (e.affaire is not None and e.affaire.etape == f.etape),
            f.note_min is None or (ligne["note"] is not None and ligne["note"] >= f.note_min),
            f.sequence is None or (seq is not None and seq["sequence"] == f.sequence),
            f.etat_sequence is None or (seq is not None and seq["etat"] == f.etat_sequence),
            not q or q in e.recherche,
        ))

    return [e for e in elements if garde(e)]


def liste(session: Session, f: Filtres, page: int, par_page: int) -> dict:
    tous = Vue(session).elements()
    retenus = filtrer(tous, f)
    debut = (page - 1) * par_page
    return {
        "total": len(retenus), "page": page, "par_page": par_page,
        "resume": {"landing": sum(e.ligne["source"] == "landing" for e in tous),
                   "prospection": sum(e.ligne["source"] == "prospection" for e in tous)},
        "lignes": [e.ligne for e in retenus[debut:debut + par_page]],
    }


def nb_lignes(session: Session) -> int:
    """Contacts + organisations sans décideur, comme la liste."""
    contacts = session.exec(select(sa.func.count()).select_from(Contact)).one()
    avec_contact = select(Contact.organisation_id).where(Contact.organisation_id.is_not(None))
    seules = session.exec(select(sa.func.count(sa.distinct(Affaire.organisation_id))).where(
        Affaire.contact_id.is_(None), Affaire.organisation_id.is_not(None),
        Affaire.organisation_id.not_in(avec_contact))).one()
    return int(contacts) + int(seules)


# --------------------------------------------------------------------------- fiche

def _fiche(genre: str, ident: int, contact: Contact | None, org: Organisation | None,
           affaire: Affaire | None, autres: list[Contact], sequence: dict | None, possibles: list[str],
           session: Session) -> dict:
    fil, suivant = activites(session, contact_id=ident) if genre == "contact" else \
        activites(session, organisation_id=ident)
    return {
        "genre": genre, "id": ident,
        "contact": contact_api(contact) if contact else None,
        "organisation": organisation_api(org) if org else None,
        "affaire": affaires.affaire_api(session, affaire) if affaire else None,
        "autres_contacts": [{"id": a.id, "nom_affiche": nom_affiche(a, org), "poste": a.poste} for a in autres],
        "sequence": sequence, "sequences_possibles": possibles,
        "activites": fil, "activites_suivant": suivant,
        "hubspot": synchro_hubspot.etat_objet(session, genre, ident),
    }


def fiche_contact(session: Session, contact: Contact) -> dict:
    ctx = moteur_sequences.contexte(session)
    org = session.get(Organisation, contact.organisation_id) if contact.organisation_id else None
    liste_affaires = list(session.exec(select(Affaire).where(Affaire.contact_id == contact.id).order_by(Affaire.id)))
    pipeline = affaires.PIPELINE_DU_TYPE.get(contact.type)
    affaire = next((a for a in liste_affaires if a.pipeline == pipeline), liste_affaires[0] if liste_affaires else None)
    autres = list(session.exec(select(Contact).where(
        Contact.organisation_id == contact.organisation_id, Contact.id != contact.id).order_by(Contact.id))) \
        if contact.organisation_id else []
    inscriptions = list(session.exec(select(InscriptionSequence).where(InscriptionSequence.contact_id == contact.id)))
    insc = moteur_sequences.inscription_affichee(inscriptions)
    sequence = None
    if insc:
        envois = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id).order_by(Envoi.pas))
        sequence = {
            "etat": moteur_sequences.etat(insc, contact, ctx),
            "definition": moteur_sequences.definition_api(session, insc.sequence, ctx.coupees),
            "envois": [{"pas": e.pas, "statut": e.statut, "envoye_at": temps.iso(e.envoye_at)} for e in envois],
        }
    possibles = moteur_sequences.sequences_possibles(contact, {i.sequence for i in inscriptions})
    return _fiche("contact", contact.id, contact, org, affaire, autres, sequence, possibles, session)


def fiche_organisation(session: Session, org: Organisation) -> dict:
    liste_affaires = list(session.exec(select(Affaire).where(Affaire.organisation_id == org.id).order_by(
        Affaire.contact_id.is_not(None), Affaire.id)))
    autres = list(session.exec(select(Contact).where(Contact.organisation_id == org.id).order_by(Contact.id)))
    return _fiche("organisation", org.id, None, org, liste_affaires[0] if liste_affaires else None,
                  autres, None, [], session)


# --------------------------------------------------------------------------- écriture

def _email_libre(session: Session, email: str, sauf: int | None = None) -> None:
    existant = session.exec(select(Contact).where(Contact.email == email)).first()
    if existant is not None and existant.id != sauf:
        raise ErreurContact(409, "Cette adresse e-mail est déjà connue", existant.id)


def _rattacher(session: Session, contact: Contact, organisation_nom: str | None, source: str) -> None:
    if organisation_nom:
        contact.organisation_id = organisation_pour(session, organisation_nom, type_organisation(contact.type),
                                                    source).id
    else:
        contact.organisation_id = None


def creer_contact(session: Session, champs: dict, membre: Membre) -> Contact:
    champs = {k: vide_en_none(v) for k, v in champs.items()}
    email = normaliser_email(champs.get("email"))
    if email is not None:
        if not email_valide(email):
            raise ErreurContact(422, "Adresse e-mail invalide")
        _email_libre(session, email)
    if not email and not champs.get("prenom"):
        raise ErreurContact(422, "Un prénom ou une adresse e-mail est nécessaire")
    t = temps.maintenant()
    c = Contact(type=champs["type"], prenom=champs.get("prenom"), nom=champs.get("nom"), email=email,
                telephone=champs.get("telephone"), poste=champs.get("poste"),
                linkedin_url=champs.get("linkedin_url"), ville=champs.get("ville"), source="manuel",
                source_detail=champs.get("source_detail"), cree_at=t, maj_at=t)
    _rattacher(session, c, champs.get("organisation_nom"), "manuel")
    session.add(c)
    session.flush()
    _affaire_initiale(session, c)
    ajouter_activite(session, "creation_manuelle", "Contact ajouté à la main", contact_id=c.id,
                     organisation_id=c.organisation_id, membre_id=membre.id)
    return c


def _affaire_initiale(session: Session, c: Contact) -> Affaire:
    pipeline = affaires.PIPELINE_DU_TYPE[c.type]
    org_id = c.organisation_id if pipeline != "donateurs" else None
    return affaires.creer(session, pipeline, affaires.premiere_etape(pipeline), contact_id=c.id,
                          organisation_id=org_id)


def modifier_contact(session: Session, c: Contact, champs: dict) -> None:
    champs = {k: vide_en_none(v) for k, v in champs.items()}
    if "email" in champs:
        email = normaliser_email(champs["email"])
        if email is not None:
            if not email_valide(email):
                raise ErreurContact(422, "Adresse e-mail invalide")
            _email_libre(session, email, sauf=c.id)
        champs["email"] = email
    if champs.get("linkedin_provider_id"):
        existant = session.exec(select(Contact).where(
            Contact.linkedin_provider_id == champs["linkedin_provider_id"], Contact.id != c.id)).first()
        if existant is not None:
            raise ErreurContact(409, "Ce profil LinkedIn est déjà rattaché à un autre contact", existant.id)
    apres = {k: champs.get(k, getattr(c, k)) for k in ("email", "prenom", "linkedin_provider_id")}
    if not any(apres.values()):
        raise ErreurContact(422, "Un prénom, une adresse e-mail ou un profil LinkedIn est nécessaire")
    for cle, valeur in champs.items():
        if cle == "organisation_nom":
            _rattacher(session, c, valeur, "manuel")
        else:
            setattr(c, cle, valeur)
    c.maj_at = temps.maintenant()
    session.add(c)


def modifier_organisation(session: Session, o: Organisation, champs: dict) -> None:
    for cle, valeur in champs.items():
        valeur = vide_en_none(valeur)
        if cle == "nom" and not valeur:
            raise ErreurContact(422, "Le nom de l'organisation est obligatoire")
        setattr(o, cle, valeur)
    o.maj_at = temps.maintenant()
    session.add(o)


def noter(session: Session, *, type: str, texte: str, membre: Membre, contact: Contact | None = None,
          organisation: Organisation | None = None) -> dict:
    titre = "Note" if type == "note" else "Appel"
    a = ajouter_activite(session, type, titre, texte=texte, membre_id=membre.id,
                         contact_id=contact.id if contact else None,
                         organisation_id=organisation.id if organisation else
                         (contact.organisation_id if contact else None))
    return activite_api(a, {membre.id: membre})


# --------------------------------------------------------------------------- import et export CSV

def importer(session: Session, contenu: bytes) -> dict:
    """Import CSV : crée les nouveaux contacts, complète les champs vides des contacts connus
    (par e-mail). Aucun consentement, aucune séquence automatique."""
    if len(contenu) > TAILLE_MAX_IMPORT:
        raise ErreurContact(413, "Fichier trop volumineux : 2 Mo au plus")
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErreurContact(422, "Fichier illisible : encodage UTF-8 attendu") from None
    premiere = texte.split("\n", 1)[0]
    lecteur = csv.reader(io.StringIO(texte), delimiter=";" if premiere.count(";") >= premiere.count(",") else ",")
    lignes = [(lecteur.line_num, ligne) for ligne in lecteur]
    if not lignes:
        raise ErreurContact(422, "Fichier vide")
    if len(lignes) - 1 > LIGNES_MAX_IMPORT:
        raise ErreurContact(413, "Fichier trop long : 5 000 lignes au plus")
    entete = [normaliser(h).replace(" ", "_") for h in lignes[0][1]]
    if "email" not in entete and "prenom" not in entete:
        raise ErreurContact(422, "L'en-tête doit contenir une colonne email ou prenom")
    index = {col: entete.index(col) for col in COLONNES_IMPORT if col in entete}

    bilan = {"crees": 0, "mis_a_jour": 0, "ignores": 0, "erreurs": []}
    t = temps.maintenant()
    for numero, cellules in lignes[1:]:
        v = {col: (cellules[i].strip() if i < len(cellules) else "") for col, i in index.items()}
        if not any(v.values()):
            bilan["ignores"] += 1
            continue
        type_contact = (v.get("type") or "donateur").lower()
        email = normaliser_email(v.get("email"))
        trop_long = next((col for col, n in LONGUEURS.items() if len(v.get(col) or "") > n), None)
        raison = None
        if type_contact not in TYPES_CONTACT:
            raison = f"Type inconnu : {type_contact}"
        elif email and not email_valide(email):
            raison = "Adresse e-mail invalide"
        elif not email and not v.get("prenom"):
            raison = "Ni e-mail ni prénom"
        elif trop_long:
            raison = f"Valeur trop longue dans la colonne {trop_long}"
        if raison:
            bilan["erreurs"].append({"ligne": numero, "raison": raison})
            continue

        existant = session.exec(select(Contact).where(Contact.email == email)).first() if email else None
        if existant is not None:
            change = False
            for champ in CHAMPS_COMPLETABLES:
                if v.get(champ) and not getattr(existant, champ):
                    setattr(existant, champ, v[champ])
                    change = True
            if v.get("organisation") and existant.organisation_id is None:
                _rattacher(session, existant, v["organisation"], "import")
                change = True
            if change:
                existant.maj_at = t
                session.add(existant)
                session.flush()
                bilan["mis_a_jour"] += 1
            else:
                bilan["ignores"] += 1
            continue

        c = Contact(type=type_contact, email=email, source="import", cree_at=t, maj_at=t,
                    **{champ: v.get(champ) or None for champ in CHAMPS_COMPLETABLES})
        _rattacher(session, c, v.get("organisation"), "import")
        session.add(c)
        session.flush()
        _affaire_initiale(session, c)
        ajouter_activite(session, "import", "Importé depuis un fichier CSV", contact_id=c.id,
                         organisation_id=c.organisation_id)
        bilan["crees"] += 1
    return bilan


def _cellule(valeur) -> str:
    texte = "" if valeur is None else str(valeur)
    return "'" + texte if texte[:1] in ("=", "+", "-", "@") else texte  # injection de formule


def exporter(session: Session, f: Filtres) -> bytes:
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=";", lineterminator="\r\n")
    ecrivain.writerow(COLONNES_CSV)
    for e in filtrer(Vue(session).elements(), f):
        c, o, a, seq = e.contact, e.organisation, e.affaire, e.ligne["sequence"]
        ecrivain.writerow([_cellule(x) for x in (
            e.ligne["type"], c.prenom if c else None, c.nom if c else None, e.ligne["email"],
            c.telephone if c else None, c.poste if c else None, o.nom if o else None, e.ligne["ville"],
            c.linkedin_url if c else None, e.ligne["source"], e.ligne["source_detail"],
            a.pipeline if a else None, a.etape if a else None, e.ligne["note"],
            seq["sequence"] if seq else None, seq["etat"] if seq else None, temps.iso(e.cree_at),
        )])
    return ("﻿" + sortie.getvalue()).encode("utf-8")
