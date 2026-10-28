"""Moteur de séquences (section 5) : inscription, tick, exécution d'un pas, arrêts, pilote,
désinscription, événements e-mail.

Au plus une fois : chaque pas est réservé en base (`envoi` unique par inscription et pas) et
la réservation est validée avant tout appel au fournisseur. Les pas LinkedIn respectent le
plafond d'invitations du jour (heure de Paris) et attendent si le compte est à reconnecter.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import db, securite, temps, verrou
from ..config import settings
from ..emails import gabarits
from ..fournisseurs.base import (
    CompteLinkedInDeconnecte, EmailProvider, ErreurFournisseur, EvenementEmail, EvenementLinkedIn, LinkedInProvider,
    MessageEmail, NonConfigure,
)
from ..journal import ajouter_activite
from ..modeles import Affaire, Contact, Envoi, InscriptionSequence, Organisation, Reglage, TextePas, WebhookRecu
from ..pipelines import etape_perdue
from ..sequences import (
    NOTE_INVITATION_MAX, SEQUENCES, Pas, Sequence, VariableManquante, canal_joignable, delai_libelle, remplacer,
)

log = logging.getLogger("merci.sequences")

LOT_TICK = 50
DUREE_VERROU_TICK = dt.timedelta(minutes=10)
DELAI_INCERTAIN = dt.timedelta(minutes=30)
ESSAIS_MAX = 3
VERIFICATIONS_PAR_TICK = 20  # lot L5b : profils vérifiés au plus par tick (quotas du fournisseur)

RAISONS = {
    "reponse": "réponse reçue",
    "etape_changee": "étape changée à la main",
    "perdu": "passé en perdu",
    "desinscription": "désinscription",
    "rebond": "rebond",
    "plainte": "plainte",
    "objectif_atteint": "objectif atteint",
    "sans_acceptation": "invitation non acceptée",
    "trois_essais": "trois essais en erreur",
    "envoi_incertain": "envoi incertain",
    "manuel": "arrêt manuel",
}
RAISONS_ECHEC = ("rebond", "trois_essais", "envoi_incertain")


class ErreurSequence(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


@dataclass
class Contexte:
    """Ce qu'il faut lire une fois par requête pour calculer les états affichés."""
    reglage: Reglage
    maintenant: dt.datetime
    fin_du_jour: dt.datetime
    invitations_aujourdhui: int

    @property
    def coupees(self) -> list[str]:
        return json.loads(self.reglage.sequences_coupees or "[]")


def invitations_du_jour(session: Session, t: dt.datetime) -> int:
    """Invitations LinkedIn réservées ou envoyées le jour de Paris contenant `t` (plafond journalier)."""
    debut, fin = temps.bornes_du_jour_paris(t)
    quand = sa.func.coalesce(Envoi.envoye_at, Envoi.cree_at)
    return int(session.exec(
        select(sa.func.count()).select_from(Envoi).where(
            Envoi.canal == "linkedin_invitation", Envoi.statut.in_(("en_cours", "envoye")),
            quand >= debut, quand < fin)
    ).one())


def contexte(session: Session) -> Contexte:
    t = temps.maintenant()
    _, fin = temps.bornes_du_jour_paris(t)
    return Contexte(reglage=session.get(Reglage, 1), maintenant=t, fin_du_jour=fin,
                    invitations_aujourdhui=invitations_du_jour(session, t))


def inscription_affichee(inscriptions: list[InscriptionSequence]) -> InscriptionSequence | None:
    """La séquence montrée sur une carte, une ligne ou une fiche : l'active, sinon la plus récente."""
    if not inscriptions:
        return None
    actives = [i for i in inscriptions if i.statut == "active"]
    return max(actives or inscriptions, key=lambda i: i.id)


def etat(insc: InscriptionSequence, contact: Contact, ctx: Contexte) -> dict:
    """Forme `EtatSequence` du contrat (section 4.2)."""
    seq = SEQUENCES[insc.sequence]
    total = len(seq.pas)
    r = ctx.reglage
    attente = None
    if insc.statut == "active":
        if contact.pause or r.relances_en_pause:
            code = "pause"
        elif insc.prochain_envoi_at is not None and insc.prochain_envoi_at < ctx.fin_du_jour:
            code = "due"
        else:
            code = "active"
        pas = seq.pas[min(insc.pas_courant, total) - 1]
        if code != "pause":
            if insc.prochain_envoi_at is None:
                attente = "acceptation"
            elif pas.canal != "email" and r.linkedin_etat == "a_reconnecter":
                attente = "linkedin_deconnecte"
            elif insc.prochain_envoi_at <= ctx.maintenant:
                if not temps.dans_creneau(ctx.maintenant, r):
                    attente = "creneau"
                elif pas.canal == "linkedin_invitation" and ctx.invitations_aujourdhui >= r.prospection_plafond_jour:
                    attente = "plafond"
        numero = min(insc.pas_courant, total)
    else:
        code = {"echec": "echec", "arretee": "arret", "terminee": "fini"}[insc.statut]
        numero = min(insc.pas_courant, total) if code == "echec" else max(min(insc.pas_courant - 1, total), 0)
    return {
        "inscription_id": insc.id,
        "sequence": insc.sequence,
        "nom": seq.nom,
        "pas": numero,
        "total": total,
        "etat": code,
        "prochain_envoi_at": temps.iso(insc.prochain_envoi_at),
        "attente": attente,
        "raison": RAISONS.get(insc.raison_arret) if insc.raison_arret else None,
    }


def definition_api(session: Session, cle: str, coupees: list[str]) -> dict:
    """Forme `SequenceDef` : textes modifiés dans l'app (`texte_pas`), sinon textes par défaut."""
    seq = SEQUENCES[cle]
    textes = {t.pas: t for t in session.exec(select(TextePas).where(TextePas.sequence == cle))}
    pas = []
    for p in seq.pas:
        t = textes.get(p.numero)
        pas.append({
            "numero": p.numero, "canal": p.canal, "delai_libelle": delai_libelle(p), "titre": p.titre,
            "sujet": (t.sujet if t else p.sujet) if p.canal == "email" else None,
            "corps": t.corps if t else p.corps,
            "personnalise": t is not None,
        })
    return {"cle": seq.cle, "nom": seq.nom, "public": seq.public, "declencheur": seq.declencheur,
            "coupee": cle in coupees, "pas": pas}


def sequences_possibles(contact: Contact, deja: set[str]) -> list[str]:
    """Séquences où l'équipe peut inscrire ce contact à la main."""
    if contact.desinscrit_at is not None:
        return []
    return [cle for cle, seq in SEQUENCES.items()
            if cle not in deja and contact.type in seq.types
            and canal_joignable(seq.pas[0].canal, contact.email, contact.linkedin_provider_id)]


def inscrire(session: Session, contact: Contact, cle: str, par: int | None = None) -> InscriptionSequence:
    """Inscription à une séquence (section 5.2). N'enregistre pas la transaction."""
    seq = SEQUENCES.get(cle)
    if seq is None:
        raise ErreurSequence(422, "Séquence inconnue")
    if contact.desinscrit_at is not None:
        raise ErreurSequence(409, "Ce contact s'est désinscrit")
    if contact.type not in seq.types:
        raise ErreurSequence(422, "Séquence incompatible avec ce type de contact")
    deja = session.exec(select(InscriptionSequence.id).where(
        InscriptionSequence.contact_id == contact.id, InscriptionSequence.sequence == cle)).first()
    if deja is not None:
        raise ErreurSequence(409, "Ce contact a déjà parcouru cette séquence ou la parcourt")
    premier = seq.pas[0]
    if not canal_joignable(premier.canal, contact.email, contact.linkedin_provider_id):
        raise ErreurSequence(422, "Aucun canal joignable pour le premier pas")

    t = temps.maintenant()
    insc = InscriptionSequence(
        contact_id=contact.id, sequence=cle, pas_courant=1, ancre_at=t,
        prochain_envoi_at=t + dt.timedelta(days=premier.delai_jours),
        statut="active", inscrit_par_id=par, cree_at=t, maj_at=t,
    )
    try:
        with session.begin_nested():
            session.add(insc)
            session.flush()
    except IntegrityError:
        raise ErreurSequence(409, "Ce contact a déjà parcouru cette séquence ou la parcourt") from None
    ajouter_activite(session, "sequence_inscrite", f"Inscription à la séquence « {seq.nom} »",
                     contact_id=contact.id, membre_id=par, donnees={"sequence": cle})
    return insc


def arreter(session: Session, insc: InscriptionSequence, raison: str, membre_id: int | None = None) -> None:
    """Arrêt d'une inscription active (section 5.4). N'enregistre pas la transaction."""
    insc.statut = "echec" if raison in RAISONS_ECHEC else "arretee"
    insc.raison_arret = raison
    insc.prochain_envoi_at = None
    insc.maj_at = temps.maintenant()
    session.add(insc)
    seq = SEQUENCES[insc.sequence]
    if insc.statut == "echec":
        type_, titre = "sequence_echec", "Séquence en échec"
    else:
        type_ = "sequence_arretee"
        titre = "Séquence arrêtée" if membre_id else "Séquence arrêtée automatiquement"
    ajouter_activite(session, type_, titre, texte=f"{seq.nom} : {RAISONS[raison]}.",
                     contact_id=insc.contact_id, membre_id=membre_id,
                     donnees={"sequence": insc.sequence, "raison": raison})


def arreter_actives(session: Session, contact_id: int, raison: str, membre_id: int | None = None,
                    sequence: str | None = None) -> int:
    requete = select(InscriptionSequence).where(
        InscriptionSequence.contact_id == contact_id, InscriptionSequence.statut == "active")
    if sequence:
        requete = requete.where(InscriptionSequence.sequence == sequence)
    actives = session.exec(requete).all()
    for insc in actives:
        arreter(session, insc, raison, membre_id)
    return len(actives)




# --------------------------------------------------------------------------- exécution d'un pas

@dataclass
class Compteurs:
    traites: int = 0
    envoyes: int = 0
    erreurs: int = 0
    echecs: int = 0
    sautes: int = 0
    en_attente: dict[str, int] = field(default_factory=lambda: {"plafond": 0, "linkedin_deconnecte": 0})

    def api(self, statut: str, debut: float) -> dict:
        return {"statut": statut, "traites": self.traites, "envoyes": self.envoyes, "erreurs": self.erreurs,
                "echecs": self.echecs, "sautes": self.sautes, "en_attente": dict(self.en_attente),
                "duree_ms": int((time.monotonic() - debut) * 1000)}


def _coupees(r: Reglage) -> list[str]:
    return json.loads(r.sequences_coupees or "[]")


def _peut_partir(insc: InscriptionSequence | None, contact: Contact | None, r: Reglage, t: dt.datetime) -> bool:
    """Revérification au moment de l'envoi (section 5.3, étape 1)."""
    return (insc is not None and insc.statut == "active" and contact is not None
            and not contact.pause and contact.desinscrit_at is None
            and not r.relances_en_pause and temps.dans_creneau(t, r)
            and insc.sequence not in _coupees(r)
            and insc.prochain_envoi_at is not None and insc.prochain_envoi_at <= t)


def _pipeline(seq: Sequence) -> str:
    return "donateurs" if "donateur" in seq.types else "entreprises"


def _condition_remplie(p: Pas, contact: Contact) -> bool:
    if p.si == "email_connu":
        return bool(contact.email)
    if p.si == "linkedin_connu":
        return bool(contact.linkedin_provider_id)
    return True


def _acceptee(session: Session, inscription_id: int) -> bool:
    return session.exec(select(Envoi.id).where(
        Envoi.inscription_id == inscription_id, Envoi.accepte_at.is_not(None))).first() is not None


def _avancer(session: Session, insc: InscriptionSequence, seq: Sequence) -> None:
    insc.pas_courant += 1
    insc.maj_at = temps.maintenant()
    if insc.pas_courant > len(seq.pas):
        insc.statut, insc.prochain_envoi_at = "terminee", None
        ajouter_activite(session, "sequence_terminee", "Séquence terminée", texte=f"{seq.nom}.",
                         contact_id=insc.contact_id, donnees={"sequence": insc.sequence})
    else:
        p = seq.pas[insc.pas_courant - 1]
        delai = dt.timedelta(days=p.delai_jours)
        if p.ancre == "inscription":
            insc.prochain_envoi_at = insc.cree_at + delai
        else:  # en attente de l'acceptation LinkedIn tant qu'elle n'est pas reçue
            insc.prochain_envoi_at = insc.ancre_at + delai if _acceptee(session, insc.id) else None
    session.add(insc)


def _reserver(session: Session, insc: InscriptionSequence, seq: Sequence, p: Pas,
              t: dt.datetime) -> Envoi | None:
    """Réservation du pas (section 5.3, étape 6). None : rien à envoyer par ce processus."""
    envoi = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id, Envoi.pas == p.numero)).first()
    if envoi is None:
        envoi = Envoi(inscription_id=insc.id, pas=p.numero, canal=p.canal, statut="en_cours", essais=1,
                      cree_at=t, maj_at=t)
        try:
            with session.begin_nested():
                session.add(envoi)
                session.flush()
        except IntegrityError:
            return None  # un autre processus l'a pris
        return envoi
    if envoi.statut == "erreur" and envoi.essais < ESSAIS_MAX:
        lu = envoi.essais
        res = session.execute(
            sa.update(Envoi)
            .where(Envoi.id == envoi.id, Envoi.statut == "erreur", Envoi.essais == lu)
            .values(statut="en_cours", essais=lu + 1, maj_at=t))
        if res.rowcount != 1:
            session.rollback()
            return None
        session.expire(envoi)
        return envoi
    if envoi.statut in ("envoye", "saute"):  # pas déjà fait : réparation du pointeur, jamais de second appel
        _avancer(session, insc, seq)
        session.commit()
    return None


def _valeurs(session: Session, contact: Contact) -> dict[str, str | None]:
    r = session.get(Reglage, 1)
    org = session.get(Organisation, contact.organisation_id) if contact.organisation_id else None
    return {"prenom": contact.prenom, "entreprise": org.nom if org else None,
            "lien_rdv": r.lien_rdv, "lien_compte": r.lien_creation_compte}


def _texte_pas(session: Session, insc: InscriptionSequence, p: Pas) -> TextePas | None:
    return session.exec(select(TextePas).where(TextePas.sequence == insc.sequence, TextePas.pas == p.numero)).first()


def _texte_linkedin(session: Session, insc: InscriptionSequence, contact: Contact, p: Pas) -> str:
    """Rendu d'une note d'invitation ou d'un message LinkedIn (variables remplacées)."""
    texte = _texte_pas(session, insc, p)
    rendu = remplacer(texte.corps if texte else p.corps, _valeurs(session, contact))
    if p.canal == "linkedin_invitation" and len(rendu) > NOTE_INVITATION_MAX:
        raise VariableManquante(f"Note d'invitation de plus de {NOTE_INVITATION_MAX} caractères")
    return rendu


def _message(session: Session, insc: InscriptionSequence, contact: Contact, p: Pas, essais: int) -> MessageEmail:
    """Rendu (section 5.3, étape 7). Lève `VariableManquante` plutôt que d'envoyer un texte troué."""
    from .capture import expediteur
    r = session.get(Reglage, 1)
    texte = _texte_pas(session, insc, p)
    valeurs = _valeurs(session, contact)
    sujet = remplacer(texte.sujet if texte and texte.sujet else p.sujet or p.titre, valeurs)
    corps = remplacer(texte.corps if texte else p.corps, valeurs)
    if not contact.email:
        raise VariableManquante("Adresse e-mail absente")
    lien = f"{settings.api_url_publique.rstrip('/')}/public/desinscription/{securite.jeton_desinscription(contact.id)}"
    html, texte_brut = gabarits.email_sequence(corps, lien)
    return MessageEmail(
        a=contact.email, sujet=sujet, html=html, texte=texte_brut, expediteur=expediteur(session),
        repondre_a=r.reponse_a,
        entetes={"List-Unsubscribe": f"<{lien}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
        cle_idempotence=f"envoi-{insc.id}-{p.numero}-{essais}",
        etiquettes={"inscription_id": str(insc.id), "pas": str(p.numero)},
    )


def _activite_envoi(p: Pas, seq: Sequence, resume: str) -> tuple[str, str, str]:
    """(type, titre, texte) de l'activité d'un envoi réussi. `resume` : sujet ou texte LinkedIn."""
    if p.canal == "linkedin_invitation":
        return ("linkedin_invitation", "Invitation LinkedIn envoyée",
                f"Pas {p.numero} de {seq.nom}, avec une note de {len(resume)} caractères.")
    if p.canal == "linkedin_message":
        return "linkedin_message", "Message LinkedIn envoyé", f"Pas {p.numero} de {seq.nom}. « {resume} »"
    return "email_envoye", f"E-mail envoyé : {p.titre}", resume


def _succes(session: Session, envoi_id: int, insc_id: int, seq: Sequence, p: Pas, fournisseur: str,
            ident: str, resume: str, c: Compteurs) -> None:
    from . import affaires
    t = temps.maintenant()
    envoi = session.get(Envoi, envoi_id)
    envoi.statut, envoi.fournisseur, envoi.fournisseur_id = "envoye", fournisseur, ident[:120]
    envoi.envoye_at = envoi.maj_at = t
    session.add(envoi)
    insc = session.get(InscriptionSequence, insc_id)
    type_, titre, texte = _activite_envoi(p, seq, resume)
    ajouter_activite(session, type_, titre, texte=texte, contact_id=insc.contact_id, envoi_id=envoi_id,
                     donnees={"sequence": insc.sequence, "pas": p.numero})
    if p.numero == 1 and seq.succes_pas_1:
        pipeline, depuis, vers = seq.succes_pas_1
        affaire = session.exec(select(Affaire).where(
            Affaire.contact_id == insc.contact_id, Affaire.pipeline == pipeline)).first()
        if affaire is not None and affaire.etape == depuis:
            affaires.changer_etape(session, affaire, vers, automatique=True)
    if insc.statut == "active" and insc.pas_courant == p.numero:
        _avancer(session, insc, seq)
    session.commit()
    c.envoyes += 1


def _erreur(session: Session, envoi_id: int, insc_id: int, message: str, c: Compteurs) -> None:
    """Le pas reste dû (nouvel essai au tick suivant) ; au troisième essai, échec visible."""
    session.rollback()
    envoi = session.get(Envoi, envoi_id)
    envoi.statut, envoi.derniere_erreur, envoi.maj_at = "erreur", message[:500], temps.maintenant()
    c.erreurs += 1
    if envoi.essais >= ESSAIS_MAX:
        envoi.statut = "echec"
        insc = session.get(InscriptionSequence, insc_id)
        if insc.statut == "active":
            arreter(session, insc, "trois_essais")
        c.echecs += 1
    session.add(envoi)
    session.commit()
    log.warning("pas non envoyé (inscription %s) : %s", insc_id, message)


def _compte_deconnecte(session: Session, envoi_id: int, message: str, c: Compteurs) -> None:
    """L'essai ne compte pas ; le compte passe « à reconnecter » ; le pas reste dû."""
    session.rollback()
    t = temps.maintenant()
    envoi = session.get(Envoi, envoi_id)
    envoi.statut, envoi.derniere_erreur, envoi.maj_at = "erreur", message[:500], t
    envoi.essais = max(envoi.essais - 1, 0)
    session.add(envoi)
    r = session.get(Reglage, 1)
    r.linkedin_etat, r.linkedin_etat_at, r.maj_at = "a_reconnecter", t, t
    session.add(r)
    session.commit()
    c.en_attente["linkedin_deconnecte"] += 1
    log.warning("compte LinkedIn à reconnecter : %s", message)


def executer_pas(inscription_id: int, email: EmailProvider, c: Compteurs | None = None,
                 linkedin: LinkedInProvider | None = None) -> None:
    """Exécute le pas dû d'une inscription (envoi immédiat après capture, puis tick, section 5.3).
    Sans fournisseur LinkedIn (envoi immédiat après capture), un pas LinkedIn reste dû."""
    c = c if c is not None else Compteurs()
    with Session(db.engine) as s:
        insc = s.get(InscriptionSequence, inscription_id)
        contact = s.get(Contact, insc.contact_id) if insc else None
        t = temps.maintenant()
        if not _peut_partir(insc, contact, s.get(Reglage, 1), t):
            return
        seq = SEQUENCES[insc.sequence]
        affaire = s.exec(select(Affaire).where(
            Affaire.contact_id == contact.id, Affaire.pipeline == _pipeline(seq))).first()
        if affaire is not None and affaire.etape == etape_perdue(affaire.pipeline):
            arreter(s, insc, "perdu")
            s.commit()
            return
        p = seq.pas[insc.pas_courant - 1]
        if not _condition_remplie(p, contact):
            try:
                with s.begin_nested():
                    s.add(Envoi(inscription_id=insc.id, pas=p.numero, canal=p.canal, statut="saute", essais=0,
                                cree_at=t, maj_at=t))
                    s.flush()
            except IntegrityError:
                return
            _avancer(s, insc, seq)
            s.commit()
            c.sautes += 1
            return
        if p.canal != "email":
            if linkedin is None:
                return
            r = s.get(Reglage, 1)
            if r.linkedin_etat == "a_reconnecter":
                c.en_attente["linkedin_deconnecte"] += 1
                return
            if p.canal == "linkedin_invitation" and invitations_du_jour(s, t) >= r.prospection_plafond_jour:
                c.en_attente["plafond"] += 1
                return
        envoi = _reserver(s, insc, seq, p, t)
        if envoi is None:
            return
        s.commit()  # réservation validée avant tout appel réseau
        envoi_id, essais = envoi.id, envoi.essais
        try:
            if p.canal == "email":
                msg = _message(s, insc, contact, p, essais)
                ident, fournisseur, resume = email.envoyer(msg), email.nom, msg.sujet
            else:
                resume = _texte_linkedin(s, insc, contact, p)
                envoyer = linkedin.inviter if p.canal == "linkedin_invitation" else linkedin.ecrire
                ident, fournisseur = envoyer(contact.linkedin_provider_id, resume), linkedin.nom
        except CompteLinkedInDeconnecte as e:
            _compte_deconnecte(s, envoi_id, str(e), c)
            return
        except (ErreurFournisseur, NonConfigure, VariableManquante) as e:
            _erreur(s, envoi_id, inscription_id, str(e), c)
            return
        _succes(s, envoi_id, inscription_id, seq, p, fournisseur, ident, resume, c)


# --------------------------------------------------------------------------- tick et ménage

def menage(session: Session) -> None:
    """Toujours exécuté, même en pause ou hors créneau. N'enregistre pas la transaction."""
    t = temps.maintenant()
    anciens = session.exec(select(Envoi).where(
        Envoi.statut == "en_cours", Envoi.maj_at < t - DELAI_INCERTAIN)).all()
    for envoi in anciens:  # on ne renvoie jamais un message dont on ne sait pas s'il est parti
        envoi.statut, envoi.maj_at = "incertain", t
        session.add(envoi)
        insc = session.get(InscriptionSequence, envoi.inscription_id)
        if insc.statut == "active":
            arreter(session, insc, "envoi_incertain")
    for seq in SEQUENCES.values():
        if not seq.expire_sans_acceptation_jours:
            continue
        limite = t - dt.timedelta(days=seq.expire_sans_acceptation_jours)
        expirees = session.exec(
            select(InscriptionSequence)
            .join(Envoi, sa.and_(Envoi.inscription_id == InscriptionSequence.id, Envoi.pas == 1))
            .where(InscriptionSequence.sequence == seq.cle, InscriptionSequence.statut == "active",
                   InscriptionSequence.pas_courant == 2, InscriptionSequence.prochain_envoi_at.is_(None),
                   Envoi.envoye_at <= limite)).all()
        for insc in expirees:
            insc.statut, insc.raison_arret, insc.prochain_envoi_at, insc.maj_at = "terminee", "sans_acceptation", None, t
            session.add(insc)
            ajouter_activite(session, "sequence_terminee", "Séquence terminée",
                             texte=f"{seq.nom} : {RAISONS['sans_acceptation']}.", contact_id=insc.contact_id,
                             donnees={"sequence": seq.cle, "raison": "sans_acceptation"})


def verifier_acceptations(session: Session, linkedin: LinkedInProvider) -> int:
    """Lot L5b, pour un fournisseur sans webhook d'acceptation (ConnectSafely) : vérifie la relation
    des invitations en attente envoyées par ce fournisseur, les moins récemment vérifiées d'abord,
    au plus `VERIFICATIONS_PAR_TICK`. Au 1er degré : même traitement que le webhook d'acceptation.
    Une erreur d'appel interrompt les vérifications du tick, sans rien modifier. Renvoie le nombre
    d'acceptations traitées."""
    if session.get(Reglage, 1).linkedin_etat == "a_reconnecter":
        return 0
    lignes = session.exec(
        select(Envoi.id, Contact.linkedin_provider_id, Contact.linkedin_url)
        .join(InscriptionSequence, InscriptionSequence.id == Envoi.inscription_id)
        .join(Contact, Contact.id == InscriptionSequence.contact_id)
        .where(Envoi.canal == "linkedin_invitation", Envoi.statut == "envoye", Envoi.accepte_at.is_(None),
               Envoi.fournisseur == linkedin.nom, InscriptionSequence.statut == "active",
               InscriptionSequence.prochain_envoi_at.is_(None), Contact.linkedin_provider_id.is_not(None))
        .order_by(Envoi.maj_at, Envoi.id)
        .limit(VERIFICATIONS_PAR_TICK)).all()
    acceptees = 0
    for envoi_id, provider_id, url in lignes:
        try:
            relation = linkedin.verifier_acceptation(provider_id, url)
        except (ErreurFournisseur, NonConfigure) as e:
            log.warning("vérification des acceptations interrompue : %s", e)
            break
        if relation is None:
            continue  # fournisseur à webhook, ou profil sans identifiant public
        t = temps.maintenant()
        if relation:
            ev = EvenementLinkedIn(cle=f"verification:{envoi_id}", type="invitation_acceptee",
                                   provider_id=provider_id, texte=None, recu_at=t)
            acceptees += int(traiter_evenement_linkedin(session, ev, linkedin.nom))
        else:  # vérifiée, toujours en attente : passe en fin de file
            session.execute(sa.update(Envoi).where(Envoi.id == envoi_id, Envoi.accepte_at.is_(None))
                            .values(maj_at=t))
        session.commit()
    return acceptees


def tick(email: EmailProvider, linkedin: LinkedInProvider | None = None) -> dict:
    """Tick synchrone et borné (section 5.3)."""
    debut = time.monotonic()
    c = Compteurs()
    with Session(db.engine) as s:
        jeton = verrou.prendre(s, "tick", DUREE_VERROU_TICK)
        if jeton is None:
            return c.api("verrouille", debut)
        try:
            menage(s)
            s.commit()
            r = s.get(Reglage, 1)
            t = temps.maintenant()
            if r.relances_en_pause:
                statut = "pause"
            elif not temps.dans_creneau(t, r):
                statut = "hors_creneau"
            else:
                statut = "fait"
                if linkedin is not None:
                    verifier_acceptations(s, linkedin)
                ids = s.exec(
                    select(InscriptionSequence.id)
                    .join(Contact, Contact.id == InscriptionSequence.contact_id)
                    .where(InscriptionSequence.statut == "active",
                           InscriptionSequence.prochain_envoi_at.is_not(None),
                           InscriptionSequence.prochain_envoi_at <= t,
                           Contact.pause.is_(False), Contact.desinscrit_at.is_(None),
                           InscriptionSequence.sequence.not_in(_coupees(r)))
                    .order_by(InscriptionSequence.prochain_envoi_at, InscriptionSequence.id)
                    .limit(LOT_TICK)).all()
                for inscription_id in ids:
                    c.traites += 1
                    try:
                        executer_pas(inscription_id, email, c, linkedin)
                    except Exception:  # une inscription défaillante ne bloque pas les suivantes
                        log.exception("tick : inscription %s", inscription_id)
                        c.erreurs += 1
        finally:
            verrou.relacher(s, "tick", jeton)
    return c.api(statut, debut)


# --------------------------------------------------------------------------- pilote, désinscription

def ouvrir_pilote(session: Session) -> dict:
    """Section 5.6. N'enregistre pas la transaction."""
    from . import affaires
    r = session.get(Reglage, 1)
    if r.pilote_ouvert_at is not None:
        raise ErreurSequence(409, "Le pilote est déjà ouvert")
    t = temps.maintenant()
    r.pilote_ouvert_at = r.maj_at = t
    session.add(r)
    lignes = session.exec(
        select(Affaire, Contact).join(Contact, Contact.id == Affaire.contact_id)
        .where(Affaire.pipeline == "donateurs", Affaire.etape.in_(("inscrit", "bienvenue_envoyee")),
               Contact.desinscrit_at.is_(None))
        .order_by(Affaire.id)).all()
    inscrits = 0
    for affaire, contact in lignes:
        affaires.changer_etape(session, affaire, "pilote_ouvert", automatique=True)
        arreter_actives(session, contact.id, "objectif_atteint", sequence="donateur-bienvenue")
        try:
            inscrire(session, contact, "donateur-pilote")
            inscrits += 1
        except ErreurSequence:
            pass  # déjà parcourue, ou aucune adresse e-mail
    return {"ouvert_at": temps.iso(t), "inscrits": inscrits}


def desinscrire(session: Session, contact: Contact) -> None:
    """Idempotent. N'enregistre pas la transaction."""
    if contact.desinscrit_at is not None:
        return
    t = temps.maintenant()
    contact.desinscrit_at = contact.maj_at = t
    session.add(contact)
    arreter_actives(session, contact.id, "desinscription")
    ajouter_activite(session, "desinscription", "Désinscription des e-mails", contact_id=contact.id)


# --------------------------------------------------------------------------- événements e-mail

TITRES_EMAIL = {
    "delivre": ("email_delivre", "E-mail délivré"),
    "ouvert": ("email_ouvert", "E-mail ouvert"),
    "clique": ("email_clique", "Lien cliqué dans l'e-mail"),
    "rebond": ("email_rebond", "E-mail en rebond"),
    "plainte": ("email_plainte", "E-mail signalé comme indésirable"),
}


def traiter_evenement_email(session: Session, ev: EvenementEmail, fournisseur: str) -> None:
    """Section 4.12. Rejeu (même clé) et e-mail inconnu : sans effet. N'enregistre pas la transaction."""
    try:
        with session.begin_nested():
            session.add(WebhookRecu(fournisseur=fournisseur, cle=ev.cle[:120], recu_at=temps.maintenant()))
            session.flush()
    except IntegrityError:
        return
    envoi = session.exec(select(Envoi).where(Envoi.fournisseur_id == ev.fournisseur_id)).first()
    if envoi is None or ev.type not in TITRES_EMAIL:
        return
    insc = session.get(InscriptionSequence, envoi.inscription_id)
    contact = session.get(Contact, insc.contact_id)
    t = ev.recu_at
    journaliser = True
    if ev.type == "delivre":
        journaliser = envoi.delivre_at is None
        envoi.delivre_at = envoi.delivre_at or t
    elif ev.type == "ouvert":
        journaliser = envoi.ouvert_at is None
        envoi.ouvert_at = envoi.ouvert_at or t
    elif ev.type == "clique":
        envoi.clique_at = envoi.clique_at or t
    elif ev.type == "rebond":
        if insc.statut in ("active", "terminee"):
            arreter(session, insc, "rebond")
    elif ev.type == "plainte":
        arreter_actives(session, contact.id, "plainte")
        desinscrire(session, contact)
    envoi.maj_at = temps.maintenant()
    session.add(envoi)
    if journaliser:
        type_, titre = TITRES_EMAIL[ev.type]
        ajouter_activite(session, type_, titre, contact_id=contact.id, envoi_id=envoi.id,
                         donnees={"sequence": insc.sequence, "pas": envoi.pas})


# --------------------------------------------------------------------------- événements LinkedIn

def traiter_evenement_linkedin(session: Session, ev: EvenementLinkedIn, fournisseur: str) -> bool:
    """Section 4.12. Vrai si l'événement a eu un effet. Rejeu (même clé), type « autre » et profil
    inconnu : sans effet. N'enregistre pas la transaction."""
    from . import affaires
    if ev.type == "autre":
        return False
    try:
        with session.begin_nested():
            session.add(WebhookRecu(fournisseur=fournisseur, cle=ev.cle[:120], recu_at=temps.maintenant()))
            session.flush()
    except IntegrityError:
        return False
    t = temps.maintenant()
    if ev.type in ("compte_deconnecte", "compte_ok"):
        r = session.get(Reglage, 1)
        r.linkedin_etat = "a_reconnecter" if ev.type == "compte_deconnecte" else "ok"
        r.linkedin_etat_at = r.maj_at = t
        session.add(r)
        return True
    contact = session.exec(select(Contact).where(Contact.linkedin_provider_id == ev.provider_id)).first() \
        if ev.provider_id else None
    if contact is None:
        return False
    if ev.type == "invitation_acceptee":
        envoi = session.exec(
            select(Envoi).join(InscriptionSequence, InscriptionSequence.id == Envoi.inscription_id)
            .where(InscriptionSequence.contact_id == contact.id, Envoi.canal == "linkedin_invitation",
                   Envoi.statut == "envoye", Envoi.accepte_at.is_(None))
            .order_by(Envoi.id.desc())).first()
        if envoi is None:
            return False  # relation sans invitation de notre part
        envoi.accepte_at = envoi.maj_at = t
        session.add(envoi)
        insc = session.get(InscriptionSequence, envoi.inscription_id)
        seq = SEQUENCES[insc.sequence]
        if insc.statut == "active" and insc.pas_courant <= len(seq.pas) and insc.prochain_envoi_at is None:
            p = seq.pas[insc.pas_courant - 1]
            if p.ancre == "acceptation":  # les délais suivants partent de l'acceptation (décision D8)
                insc.ancre_at = t
                insc.prochain_envoi_at = t + dt.timedelta(days=p.delai_jours)
                insc.maj_at = t
                session.add(insc)
        ajouter_activite(session, "linkedin_acceptee", "Invitation acceptée", contact_id=contact.id,
                         envoi_id=envoi.id, donnees={"sequence": insc.sequence})
        return True
    # message_recu : une réponse arrête les séquences et fait avancer l'affaire (jamais de recul).
    arreter_actives(session, contact.id, "reponse")
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == contact.id,
                                                 Affaire.pipeline == "entreprises")).first()
    if affaire is not None:
        affaires.changer_etape(session, affaire, "a_repondu", automatique=True)
    ajouter_activite(session, "linkedin_reponse", "Réponse reçue sur LinkedIn", texte=ev.texte,
                     contact_id=contact.id, affaire_id=affaire.id if affaire else None)
    return True


# --------------------------------------------------------------------------- écran Séquences

def sequences_api(session: Session) -> list[dict]:
    """`GET /sequences` : définitions, inscriptions actives et statistiques (section 4.7)."""
    coupees = _coupees(session.get(Reglage, 1))

    def compter(requete) -> int:
        return int(session.exec(requete).one())

    rep = []
    for cle, seq in SEQUENCES.items():
        envois = (select(sa.func.count()).select_from(Envoi)
                  .join(InscriptionSequence, InscriptionSequence.id == Envoi.inscription_id)
                  .where(InscriptionSequence.sequence == cle))
        inscriptions = select(sa.func.count()).select_from(InscriptionSequence).where(
            InscriptionSequence.sequence == cle)
        canaux = {p.canal for p in seq.pas}
        rep.append({
            **definition_api(session, cle, coupees),
            "actifs": compter(inscriptions.where(InscriptionSequence.statut == "active")),
            "stats": {
                "envoyes": compter(envois.where(Envoi.statut == "envoye")),
                "ouverts": compter(envois.where(Envoi.canal == "email", Envoi.ouvert_at.is_not(None)))
                if "email" in canaux else None,
                "acceptees": compter(envois.where(Envoi.canal == "linkedin_invitation",
                                                  Envoi.accepte_at.is_not(None)))
                if "linkedin_invitation" in canaux else None,
                "reponses": compter(inscriptions.where(InscriptionSequence.statut == "arretee",
                                                       InscriptionSequence.raison_arret == "reponse")),
            },
        })
    return rep
